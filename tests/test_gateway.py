from unittest.mock import patch
from fastapi.testclient import TestClient

# Mock boto3 client during import to prevent real AWS calls
with patch("boto3.client"):
    from gateway.main import app

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

@patch("gateway.main.sqs_client")
def test_receive_log_success(mock_sqs):
    # Mock SQS response payload
    mock_sqs.send_message.return_value = {"MessageId": "test-msg-id"}
    
    payload = {
        "service": "test-service",
        "log": "test log message"
    }
    response = client.post("/logs", json=payload)
    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert response.json()["message_id"] == "test-msg-id"

def test_receive_log_invalid_payload():
    # Test validation failure by omitting the log field
    payload = {
        "service": "test-service"
    }
    response = client.post("/logs", json=payload)
    assert response.status_code == 422
