import os
import sys
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.paypal_client import send_payout, get_payout_status

supplier = os.environ["SUPPLIER_TEST_EMAIL"]

result = send_payout(
    recipient_email=supplier,
    amount="25.00",
    note="Test: office supplies order #1",
)

batch_id = result["batch_header"]["payout_batch_id"]
print("Batch ID:", batch_id)
print("Initial status:", result["batch_header"]["batch_status"])

time.sleep(5)  # give the sandbox a moment to process

status = get_payout_status(batch_id)
print("Batch status:", status["batch_header"]["batch_status"])
for item in status["items"]:
    print("Item status:", item["transaction_status"])