import os
import json
import logging
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
import boto3

# Set up basic console logging for the gateway app
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gateway")

app = FastAPI()

SQS_QUEUE_URL = os.environ.get("SQS_QUEUE_URL")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

# Connect to AWS SQS if a queue URL is provided, otherwise fall back to local mock mode
sqs_client = None
if SQS_QUEUE_URL:
    try:
        sqs_client = boto3.client("sqs", region_name=AWS_REGION)
        logger.info(f"Connected to SQS queue: {SQS_QUEUE_URL}")
    except Exception as e:
        logger.warning(f"SQS init failed: {e}. Falling back to mock mode.")
else:
    logger.info("SQS_QUEUE_URL not set. Running in mock mode.")

# Schema for incoming log data from the chaos generator
class LogPayload(BaseModel):
    service: str
    log: str

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "sqs_connected": sqs_client is not None
    }

@app.post("/logs", status_code=status.HTTP_202_ACCEPTED)
def receive_log(payload: LogPayload):
    # Package the service and log data into a JSON string for the queue
    message_body = json.dumps({
        "service": payload.service,
        "log": payload.log
    })
    
    if sqs_client:
        try:
            response = sqs_client.send_message(
                QueueUrl=SQS_QUEUE_URL,
                MessageBody=message_body
            )
            return {
                "status": "queued",
                "message_id": response.get("MessageId")
            }
        except Exception as e:
            logger.error(f"Failed to route log to SQS: {e}")
            raise HTTPException(
                status_code=500,
                detail="Internal queue processing error"
            )
    
    # Fallback debug mode for local testing before AWS infra is deployed
    logger.info(f"[MOCK QUEUE] Received log from service '{payload.service}':\n{payload.log}")
    return {
        "status": "mock_queued",
        "message": "Log received (Mock SQS dry-run)"
    }
