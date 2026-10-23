import json
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.paypal_client import get_payout_status

status = get_payout_status(sys.argv[1])
print(json.dumps(status, indent=2))