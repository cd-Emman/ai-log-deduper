import os
import sys
import time
import boto3

# Set default local env variables before importing lambda_function
os.environ.setdefault("AWS_ACCESS_KEY_ID", "mock")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "mock")
os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault("AWS_ENDPOINT_URL", "http://localhost:4566")
os.environ.setdefault("DYNAMODB_TABLE_NAME", "ai-log-deduper-fingerprints")
os.environ.setdefault("GEMINI_API_KEY_PATH", "/ai-log-deduper/gemini_api_key")
os.environ.setdefault("DISCORD_WEBHOOK_URL_PATH", "/ai-log-deduper/discord_webhook_url")

# Add lambda path to search import
sys.path.insert(0, "./lambda")
import lambda_function

# Connect to SQS in LocalStack
sqs = boto3.client(
    "sqs",
    region_name=os.environ["AWS_REGION"],
    endpoint_url=os.environ["AWS_ENDPOINT_URL"]
)
queue_url = "http://sqs.us-east-1.localhost.localstack.cloud:4566/000000000000/ai-log-deduper-queue"

print("Starting local SQS listener for Lambda processor...")
while True:
    try:
        response = sqs.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=5
        )
        
        messages = response.get("Messages", [])
        if not messages:
            continue
            
        # Format event payload to match AWS SQS trigger format (lowercase keys)
        event = {
            "Records": [
                {
                    "body": messages[0]["Body"],
                    "receiptHandle": messages[0]["ReceiptHandle"]
                }
            ]
        }
        print(f"Processing SQS message {messages[0]['MessageId']}...")
        
        # Invoke lambda handler logic
        lambda_function.lambda_handler(event, None)
        
        # Delete message from local queue after processing
        sqs.delete_message(
            QueueUrl=queue_url,
            ReceiptHandle=messages[0]["ReceiptHandle"]
        )
        print("Successfully processed and deleted message.")
        
    except KeyboardInterrupt:
        print("\nStopping listener.")
        break
    except Exception as e:
        print(f"Error: {e}")
        time.sleep(2)
