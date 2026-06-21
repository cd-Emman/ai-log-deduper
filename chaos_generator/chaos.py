import os
import time
import random
import sys
import requests

# Gateway configuration from env, fallback to localhost
GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://localhost:8000/logs")
INTERVAL = float(os.environ.get("GENERATOR_INTERVAL_SECONDS", "10.0"))

SERVICES = ["payment-processor", "user-auth", "inventory-db", "frontend-gateway"]

ERROR_TEMPLATES = [
    """Traceback (most recent call last):
  File "/app/services/payment.py", line 42, in process_transaction
    db.save(transaction)
  File "/app/lib/db.py", line 112, in save
    raise ConnectionTimeoutError("Failed to connect to database at 10.0.4.12:5432 after 5000ms")
ConnectionTimeoutError: Failed to connect to database at 10.0.4.12:5432 after 5000ms""",

    """Traceback (most recent call last):
  File "/app/services/auth.py", line 87, in verify_token
    user_id = payload["sub"]
KeyError: 'sub'""",

    """Traceback (most recent call last):
  File "/app/services/cart.py", line 19, in apply_discount
    discount_ratio = amount / discount_code.value
ZeroDivisionError: division by zero""",

    """NullPointerException: Attempt to invoke virtual method 'boolean java.lang.String.equals(java.lang.Object)' on a null object reference
	at com.android.internal.os.RuntimeInit$MethodAndArgsCaller.run(RuntimeInit.java:492)
	at com.android.internal.os.ZygoteInit.main(ZygoteInit.java:930)"""
]

def generate_chaos():
    print(f"Starting chaos log generator, target: {GATEWAY_URL} (Interval: {INTERVAL}s)...")
    while True:
        try:
            service = random.choice(SERVICES)
            raw_log = random.choice(ERROR_TEMPLATES)
            
            payload = {
                "service": service,
                "log": raw_log
            }
            
            print(f"[{service}] Sending error log to gateway...")
            response = requests.post(GATEWAY_URL, json=payload, timeout=5)
            print(f"[{service}] Gateway response status: {response.status_code}")
            
        except requests.exceptions.RequestException as e:
            print(f"Error sending log to gateway: {e}", file=sys.stderr)
            
        time.sleep(INTERVAL)

if __name__ == "__main__":
    try:
        generate_chaos()
    except KeyboardInterrupt:
        print("\nStopping chaos log generator.")
        sys.exit(0)
