from decimal import Decimal

from src import db
from src.catalog import find_quote, get_vendor_email
from src.paypal_client import send_payout
from src.policy import PurchaseRequest, Rules, Verdict, evaluate

RULES = Rules()
MAX_QUANTITY = 1000

_MESSAGES = {
    "PAYOUT_SUBMITTED": "Payment submitted to PayPal.",
    "PENDING_APPROVAL": "NOT paid. Waiting for the business owner to approve. You cannot approve it.",
    "DENIED": "NOT paid. Blocked by company spending rules.",
    "FAILED": "NOT paid. The payment failed.",
    "REJECTED": "NOT paid. The owner rejected this purchase.",
}


def _error(message: str) -> dict:
    return {"status": "ERROR", "message": message}


def _result(pid: int) -> dict:
    p = db.get_purchase(pid)
    return {
        "purchase_id": pid,
        "status": p["status"],
        "vendor": p["vendor"],
        "item": p["item"],
        "quantity": p["quantity"],
        "amount": p["amount"],
        "reasons": p["reasons"],
        "payout_batch_id": p["payout_batch_id"],
        "message": _MESSAGES.get(p["status"], ""),
    }


def _parse_quantity(q) -> int | None:
    try:
        f = float(q)
        n = int(f)
    except (TypeError, ValueError, OverflowError):
        return None
    if f != n or not 1 <= n <= MAX_QUANTITY:
        return None
    return n


def get_budget_summary() -> dict:
    spent = db.spent_this_month()
    return {
        "monthly_budget": str(RULES.monthly_budget),
        "spent_this_month": str(spent),
        "remaining": str(RULES.monthly_budget - spent),
        "auto_approve_limit": str(RULES.auto_approve_limit),
        "hard_cap_per_purchase": str(RULES.hard_cap_per_purchase),
    }


def propose_purchase(vendor: str, item: str, quantity=1) -> dict:
    """The ONLY purchasing action the agent gets. It cannot set price or payee."""
    qty = _parse_quantity(quantity)
    if qty is None:
        return _error(f"Quantity must be a whole number from 1 to {MAX_QUANTITY}.")

    quote = find_quote(vendor, item)
    if quote is None:
        return _error("No catalog quote for that vendor and item. Use search_suppliers first.")

    amount = quote["unit_price"] * qty
    pid = db.create_purchase(quote["vendor"], quote["item"], qty, quote["unit_price"], amount)
    db.log(pid, "PROPOSED", f"{qty} x {quote['item']} from {quote['vendor']} = ${amount}")

    decision = evaluate(
        PurchaseRequest(quote["vendor"], quote["item"], amount), RULES, db.spent_this_month()
    )
    db.log(pid, "POLICY_DECISION", f"{decision.verdict.value}: {'; '.join(decision.reasons)}")

    if decision.verdict == Verdict.DENY:
        db.set_status(pid, "DENIED", decision.reasons)
    elif decision.verdict == Verdict.NEEDS_APPROVAL:
        db.set_status(pid, "PENDING_APPROVAL", decision.reasons)
    else:
        db.set_status(pid, "PROCESSING", decision.reasons)
        return _execute_payment(pid)
    return _result(pid)


def _execute_payment(pid: int) -> dict:
    p = db.get_purchase(pid)
    try:
        response = send_payout(
            recipient_email=get_vendor_email(p["vendor"]),
            amount=f"{Decimal(p['amount']):.2f}",
            note=f"PO #{pid}: {p['quantity']} x {p['item']}",
            reference_id=f"po-{pid}",  # idempotency: retries can never pay twice
        )
        batch_id = response["batch_header"]["payout_batch_id"]
    except Exception as e:
        db.set_status(pid, "FAILED", reasons=[f"Payout failed: {e}"])
        db.log(pid, "PAYOUT_FAILED", str(e))
        return _result(pid)

    db.set_status(pid, "PAYOUT_SUBMITTED", batch_id=batch_id)
    db.log(pid, "PAYOUT_SUBMITTED", f"batch {batch_id}")
    return _result(pid)


# --- Owner-only actions: deliberately NOT exposed to the agent ---

def approve_purchase(purchase_id: int) -> dict:
    if db.get_purchase(purchase_id) is None:
        return _error("Purchase not found.")
    if not db.transition(purchase_id, "PENDING_APPROVAL", "PROCESSING"):
        return _error(f"Purchase {purchase_id} is not awaiting approval.")
    db.log(purchase_id, "OWNER_APPROVED")

    # Owner approval overrides soft rules, never hard ones. Re-check hard rules
    # because the budget may have changed since the request was made.
    p = db.get_purchase(purchase_id)
    decision = evaluate(
        PurchaseRequest(p["vendor"], p["item"], Decimal(p["amount"])), RULES, db.spent_this_month()
    )
    if decision.verdict == Verdict.DENY:
        db.set_status(purchase_id, "DENIED", decision.reasons)
        db.log(purchase_id, "POLICY_DECISION", f"DENY on re-check: {'; '.join(decision.reasons)}")
        return _result(purchase_id)
    return _execute_payment(purchase_id)


def reject_purchase(purchase_id: int) -> dict:
    if db.get_purchase(purchase_id) is None:
        return _error("Purchase not found.")
    if not db.transition(purchase_id, "PENDING_APPROVAL", "REJECTED"):
        return _error(f"Purchase {purchase_id} is not awaiting approval.")
    db.log(purchase_id, "OWNER_REJECTED")
    return _result(purchase_id)