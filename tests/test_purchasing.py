from decimal import Decimal as D

import pytest

from src import db, purchasing
from src.policy import Rules


@pytest.fixture
def payouts(tmp_path, monkeypatch):
    """Fresh database per test, and a fake PayPal that records every call."""
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("SUPPLIER_TEST_EMAIL", "supplier@example.com")
    calls = []

    def fake_payout(**kwargs):
        calls.append(kwargs)
        return {"batch_header": {"payout_batch_id": f"FAKE{len(calls)}"}}

    monkeypatch.setattr(purchasing, "send_payout", fake_payout)
    return calls


def test_small_approved_purchase_pays_automatically(payouts):
    r = purchasing.propose_purchase("PaperDirect", "printer paper", 2)
    assert r["status"] == "PAYOUT_SUBMITTED"
    assert r["amount"] == "77.00"
    assert len(payouts) == 1
    assert payouts[0]["amount"] == "77.00"
    assert payouts[0]["recipient_email"] == "supplier@example.com"


def test_large_purchase_waits_for_approval_and_pays_once(payouts):
    r = purchasing.propose_purchase("PaperDirect", "printer paper", 3)  # $115.50
    assert r["status"] == "PENDING_APPROVAL"
    assert payouts == []

    pid = r["purchase_id"]
    assert purchasing.approve_purchase(pid)["status"] == "PAYOUT_SUBMITTED"
    assert purchasing.approve_purchase(pid)["status"] == "ERROR"  # double-click is blocked
    assert len(payouts) == 1


def test_unapproved_vendor_needs_approval(payouts):
    r = purchasing.propose_purchase("BulkSupplies Co", "printer paper", 1)
    assert r["status"] == "PENDING_APPROVAL"
    assert payouts == []


def test_over_hard_cap_is_denied(payouts):
    r = purchasing.propose_purchase("PaperDirect", "printer paper", 12)  # $462
    assert r["status"] == "DENIED"
    assert payouts == []


def test_budget_accumulates_across_purchases(payouts, monkeypatch):
    monkeypatch.setattr(purchasing, "RULES", Rules(monthly_budget=D("100.00")))
    assert purchasing.propose_purchase("PaperDirect", "printer paper", 2)["status"] == "PAYOUT_SUBMITTED"  # $77
    assert purchasing.propose_purchase("PaperDirect", "printer paper", 1)["status"] == "DENIED"  # $77 + $38.50 > $100
    assert len(payouts) == 1


def test_owner_approval_still_respects_the_budget(payouts, monkeypatch):
    monkeypatch.setattr(purchasing, "RULES", Rules(monthly_budget=D("150.00")))
    pending = purchasing.propose_purchase("PaperDirect", "printer paper", 3)  # $115.50, needs approval
    assert pending["status"] == "PENDING_APPROVAL"
    assert purchasing.propose_purchase("PaperDirect", "printer paper", 2)["status"] == "PAYOUT_SUBMITTED"  # $77

    result = purchasing.approve_purchase(pending["purchase_id"])  # $77 + $115.50 > $150
    assert result["status"] == "DENIED"
    assert len(payouts) == 1


def test_payout_failure_is_recorded_and_not_counted(payouts, monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("PayPal down")

    monkeypatch.setattr(purchasing, "send_payout", boom)
    r = purchasing.propose_purchase("PaperDirect", "printer paper", 1)
    assert r["status"] == "FAILED"
    assert db.spent_this_month() == D("0")


def test_unknown_item_creates_no_purchase(payouts):
    r = purchasing.propose_purchase("PaperDirect", "yacht", 1)
    assert r["status"] == "ERROR"
    assert db.list_audit() == []


def test_bad_quantities_are_rejected(payouts):
    for q in (0, -1, 1.5, "abc", 10_000):
        assert purchasing.propose_purchase("PaperDirect", "printer paper", q)["status"] == "ERROR"
    assert payouts == []


def test_audit_log_tells_the_whole_story(payouts):
    r = purchasing.propose_purchase("PaperDirect", "printer paper", 1)
    events = [e["event"] for e in db.list_audit(r["purchase_id"])]
    assert events == ["PROPOSED", "POLICY_DECISION", "PAYOUT_SUBMITTED"]