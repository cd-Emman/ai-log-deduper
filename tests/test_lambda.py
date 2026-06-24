from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError
import pytest
import json

# Setup boto3 mock structures before importing the handler
mock_ssm = MagicMock()
mock_db = MagicMock()
mock_table = MagicMock()
mock_db.Table.return_value = mock_table

def mock_get_parameter(Name, WithDecryption=True):
    if "webhook" in Name:
        return {"Parameter": {"Value": "https://discord.com/api/webhooks/mock"}}
    return {"Parameter": {"Value": "mock-secret-key"}}

mock_ssm.get_parameter.side_effect = mock_get_parameter

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../lambda")))

# Pre-populate environment variables for Lambda module initialization
os.environ["DYNAMODB_TABLE_NAME"] = "mock-table"
os.environ["GEMINI_API_KEY_PATH"] = "/mock/gemini_api_key"
os.environ["DISCORD_WEBHOOK_URL_PATH"] = "/mock/discord_webhook_url"

# Import with boto3 mocks active, avoiding reserved keyword 'lambda' import syntax
with patch("boto3.client", return_value=mock_ssm), \
     patch("boto3.resource", return_value=mock_db):
    import lambda_function

@pytest.fixture
def sqs_event():
    # Helper to generate a valid SQS test event
    return {
        "Records": [
            {
                "body": json.dumps({"service": "payment-api", "log": "database timeout error"}),
                "receiptHandle": "mock-handle"
            }
        ]
    }

@patch("urllib.request.urlopen")
def test_lambda_handler_success(mock_urlopen, sqs_event):
    # Mock Gemini response structure
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({
        "candidates": [{"content": {"parts": [{"text": "🚨 New Unique Error in payment-api"}]}}]
    }).encode("utf-8")
    
    # First call is Gemini, second is Webhook
    mock_urlopen.return_value.__enter__.side_effect = [mock_response, MagicMock(status=200)]
    mock_table.put_item.return_value = {}

    response = lambda_function.lambda_handler(sqs_event, None)
    assert response["statusCode"] == 200
    assert mock_table.put_item.called

def test_lambda_handler_duplicate(sqs_event):
    # Mock DynamoDB to throw duplicate conditional failure exception
    error_response = {"Error": {"Code": "ConditionalCheckFailedException", "Message": "The conditional request failed"}}
    mock_table.put_item.side_effect = ClientError(error_response, "put_item")

    response = lambda_function.lambda_handler(sqs_event, None)
    assert response["statusCode"] == 200 # Should drop quietly

def test_lambda_handler_invalid_json():
    # Test that bad JSON throws exception (which enables SQS DLQ redrive)
    bad_event = {"Records": [{"body": "invalid-json"}]}
    with pytest.raises(Exception):
        lambda_function.lambda_handler(bad_event, None)
