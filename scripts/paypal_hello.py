import os
import requests
from dotenv import load_dotenv

load_dotenv()

BASE = os.environ["PAYPAL_BASE_URL"]
CLIENT_ID = os.environ["PAYPAL_CLIENT_ID"]
SECRET = os.environ["PAYPAL_CLIENT_SECRET"]


def get_access_token() -> str:
    """Exchange client credentials for a short-lived access token."""
    resp = requests.post(
        f"{BASE}/v1/oauth2/token",
        auth=(CLIENT_ID, SECRET),
        data={"grant_type": "client_credentials"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def create_test_order(token: str) -> dict:
    """Create a $10 test order, just to prove the API works."""
    resp = requests.post(
        f"{BASE}/v2/checkout/orders",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "intent": "CAPTURE",
            "purchase_units": [
                {"amount": {"currency_code": "USD", "value": "10.00"}}
            ],
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


if __name__ == "__main__":
    token = get_access_token()
    print("Got access token:", token[:12] + "...")

    order = create_test_order(token)
    print("Order ID:", order["id"])
    print("Status:", order["status"])
    for link in order["links"]:
        print(f'  {link["rel"]}: {link["href"]}')