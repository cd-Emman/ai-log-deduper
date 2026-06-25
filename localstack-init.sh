#!/bin/bash
echo "Initializing local AWS resources in LocalStack..."

# Disable AWS CLI from attempting to download HTTP parameter values
awslocal configure set cli_follow_urlparam false

# Create the DLQ first and get its URL dynamically
DLQ_URL=$(awslocal sqs create-queue --queue-name ai-log-deduper-dlq --query "QueueUrl" --output text)

# Get the DLQ ARN so we can attach it to the main queue redrive policy
DLQ_ARN=$(awslocal sqs get-queue-attributes --queue-url "$DLQ_URL" --attribute-names QueueArn --query "Attributes.QueueArn" --output text)

# Create the main queue linking it to the DLQ
awslocal sqs create-queue \
  --queue-name ai-log-deduper-queue \
  --attributes '{
    "VisibilityTimeout": "30",
    "RedrivePolicy": "{\"deadLetterTargetArn\":\"'"$DLQ_ARN"'\",\"maxReceiveCount\":3}"
  }'

# Create the DynamoDB table with the matching error_hash key
awslocal dynamodb create-table \
  --table-name ai-log-deduper-fingerprints \
  --attribute-definitions AttributeName=error_hash,AttributeType=S \
  --key-schema AttributeName=error_hash,KeyType=HASH \
  --provisioned-throughput ReadCapacityUnits=1,WriteCapacityUnits=1

# Create the SSM parameter paths used by Lambda to load credentials
awslocal ssm put-parameter \
  --name "/ai-log-deduper/gemini_api_key" \
  --type "SecureString" \
  --value "mock-gemini-key" \
  --overwrite

awslocal ssm put-parameter \
  --name "/ai-log-deduper/discord_webhook_url" \
  --type "SecureString" \
  --value "http://localhost:8000/mock-webhook" \
  --overwrite

echo "Initialization complete."
