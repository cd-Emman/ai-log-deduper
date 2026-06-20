import os
import json
import hashlib
import urllib.request
import urllib.error
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

import boto3
from botocore.exceptions import ClientError

# load config variables from lambda environment settings
DYNAMODB_TABLE_NAME = os.environ.get("DYNAMODB_TABLE_NAME")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(DYNAMODB_TABLE_NAME) if DYNAMODB_TABLE_NAME else None

def get_gemini_analysis(service: str, raw_log: str) -> str:
    if not GEMINI_API_KEY or GEMINI_API_KEY.startswith("your_"):
        logger.warning("GEMINI_API_KEY not configured. Skipping.")
        return "Gemini API key not configured. Logging error analysis skipped."

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    prompt = (
        f"You are an expert SRE. Analyze this error log from the service '{service}':\n\n"
        f"{raw_log}\n\n"
        f"Provide a concise summary in the following markdown template:\n"
        f"🚨 **New Unique Error in {service}**\n"
        f"**Summary:** [Explain what went wrong in 2 sentences max]\n"
        f"**Offending Line:** [File and line number if visible, otherwise 'Unknown']\n"
        f"**Recommended Fix:** [Provide a 1-2 sentence solution]"
    )
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }
    
    headers = {"Content-Type": "application/json"}
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            return res_data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        logger.error(f"Gemini API request failed: {e}")
        return f"Error analyzing log via Gemini: {str(e)}"

def send_webhook_alert(content: str):
    if not DISCORD_WEBHOOK_URL or DISCORD_WEBHOOK_URL.startswith("your_"):
        logger.warning("DISCORD_WEBHOOK_URL not set. Skipping.")
        return

    # payload format works for both discord and slack channels
    payload = {
        "content": content,
        "text": content
    }
    
    headers = {"Content-Type": "application/json"}
    req = urllib.request.Request(
        DISCORD_WEBHOOK_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            logger.info(f"Webhook sent. Status: {response.status}")
    except Exception as e:
        logger.error(f"Webhook alert failed: {e}")

def lambda_handler(event, context):
    logger.info(f"Processing batch of {len(event.get('Records', []))} records.")
    
    if not table:
        logger.error("DynamoDB Table Name is missing from env.")
        return {"statusCode": 500, "body": "Table not configured"}

    for record in event.get("Records", []):
        try:
            body = json.loads(record["body"])
            service = body.get("service", "unknown-service")
            raw_log = body.get("log", "")

            if not raw_log:
                continue

            # md5 hash acts as a unique fingerprint for this specific error string
            log_hash = hashlib.md5(raw_log.encode("utf-8")).hexdigest()

            try:
                # conditional expression drops the write if hash already exists in DB
                table.put_item(
                    Item={
                        "error_hash": log_hash,
                        "service": service,
                        "raw_log": raw_log,
                        "timestamp": int(context.epoch_now_ms / 1000) if context else 0
                    },
                    ConditionExpression="attribute_not_exists(error_hash)"
                )
                
                logger.info(f"New unique log found ({log_hash}). Analyzing...")
                analysis = get_gemini_analysis(service, raw_log)
                send_webhook_alert(analysis)

            except ClientError as e:
                # catch duplicate items quietly instead of crashing the whole container
                if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                    logger.info(f"Duplicate log dropped: {log_hash}")
                else:
                    logger.error(f"DynamoDB put failed: {e}")
                    raise e

        except Exception as e:
            logger.error(f"Failed to process record: {e}")
            continue

    return {"statusCode": 200, "body": "Batch processed successfully"}
