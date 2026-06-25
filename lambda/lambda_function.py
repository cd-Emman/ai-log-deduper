import os
import json
import time
import hashlib
import urllib.request
import urllib.error
import logging
import boto3
from botocore.exceptions import ClientError


logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize SSM client to load secrets securely
ssm = boto3.client("ssm")

def fetch_ssm_parameter(env_var_name):
    param_path = os.environ.get(env_var_name)
    if not param_path:
        logger.warning(f"{env_var_name} environment variable is not configured.")
        return None
    try:
        response = ssm.get_parameter(Name=param_path, WithDecryption=True)
        return response["Parameter"]["Value"]
    except ClientError as e:
        logger.error(f"Failed to fetch parameter {param_path} from SSM: {e}")
        return None

# Load configuration and fetch keys from SSM
DYNAMODB_TABLE_NAME = os.environ.get("DYNAMODB_TABLE_NAME")
GEMINI_API_KEY = fetch_ssm_parameter("GEMINI_API_KEY_PATH")
DISCORD_WEBHOOK_URL = fetch_ssm_parameter("DISCORD_WEBHOOK_URL_PATH")


dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(DYNAMODB_TABLE_NAME) if DYNAMODB_TABLE_NAME else None

def get_gemini_analysis(service: str, raw_log: str) -> str:
    if not GEMINI_API_KEY or GEMINI_API_KEY.startswith("your_") or GEMINI_API_KEY == "mock-gemini-key":
        logger.warning("GEMINI_API_KEY not configured. Skipping.")
        return None

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    
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
    
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST"
    )
    time.sleep(4)
    max_retries = 3
    backoff = 2
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                return res_data["candidates"][0]["content"]["parts"][0]["text"]
        except urllib.error.HTTPError as e:
            # retry on transient gateway/capacity codes
            if e.code in [429, 503] and attempt < max_retries - 1:
                logger.warning(f"Gemini API returned {e.code}. Retrying in {backoff}s...")
                time.sleep(backoff)
                backoff *= 2
            else:
                logger.error(f"Gemini API HTTP error: {e}")
                return f"Error analyzing log via Gemini: {str(e)}"
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
    
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
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
                # set fingerprint expiration to 24 hours from now
                ttl_timestamp = int(time.time()) + 86400
                # conditional expression drops the write if hash already exists in DB
                table.put_item(
                    Item={
                        "error_hash": log_hash,
                        "service": service,
                        "raw_log": raw_log,
                        "timestamp": int(time.time()),
                        "ttl_timestamp": ttl_timestamp
                    },
                    ConditionExpression="attribute_not_exists(error_hash)"
                )
                
                logger.info(f"New unique log found ({log_hash}). Analyzing...")
                analysis = get_gemini_analysis(service, raw_log)
                
                # Fallback to raw log alert if Gemini API is disabled, rate-limited, or fails
                if not analysis or "Error analyzing log via Gemini" in analysis:
                    analysis = (
                        f"🚨 **New Unique Error in {service}** (AI Summary Unavailable)\n"
                        f"**Raw Log:**\n```\n{raw_log}\n```"
                    )
                
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
            raise e

    return {"statusCode": 200, "body": "Batch processed successfully"}
