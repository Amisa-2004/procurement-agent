import os
import time
import uuid
import requests
from dotenv import load_dotenv

load_dotenv()

BASE = os.environ["PAYPAL_BASE_URL"]
CLIENT_ID = os.environ["PAYPAL_CLIENT_ID"]
SECRET = os.environ["PAYPAL_CLIENT_SECRET"]

_token_cache = {"token": None, "expires_at": 0.0}


def get_access_token() -> str:
    """Return a cached token, refreshing it when it's about to expire."""
    if _token_cache["token"] and time.time() < _token_cache["expires_at"] - 60:
        return _token_cache["token"]

    resp = requests.post(
        f"{BASE}/v1/oauth2/token",
        auth=(CLIENT_ID, SECRET),
        data={"grant_type": "client_credentials"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    _token_cache["token"] = data["access_token"]
    _token_cache["expires_at"] = time.time() + data["expires_in"]
    return _token_cache["token"]


def send_payout(
    recipient_email: str,
    amount: str,
    currency: str = "USD",
    note: str = "Supplier payment",
    reference_id: str | None = None,
) -> dict:
    """Send money from the business account to a recipient's PayPal email."""
    reference_id = reference_id or uuid.uuid4().hex[:16]

    resp = requests.post(
        f"{BASE}/v1/payments/payouts",
        headers={
            "Authorization": f"Bearer {get_access_token()}",
            # Idempotency: retrying with the same ID never pays twice
            "PayPal-Request-Id": reference_id,
        },
        json={
            "sender_batch_header": {
                "sender_batch_id": reference_id,
                "email_subject": "You have a payment",
            },
            "items": [
                {
                    "recipient_type": "EMAIL",
                    "receiver": recipient_email,
                    "amount": {"value": amount, "currency": currency},
                    "note": note,
                    "sender_item_id": reference_id,
                }
            ],
        },
        timeout=30,
    )
    if not resp.ok:
        raise RuntimeError(f"Payout failed ({resp.status_code}): {resp.text}")
    return resp.json()


def get_payout_status(batch_id: str) -> dict:
    """Look up a payout batch and its item-level status."""
    resp = requests.get(
        f"{BASE}/v1/payments/payouts/{batch_id}",
        headers={"Authorization": f"Bearer {get_access_token()}"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()