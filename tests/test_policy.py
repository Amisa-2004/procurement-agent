from decimal import Decimal as D

from src.policy import PurchaseRequest, Rules, Verdict, evaluate

RULES = Rules()


def check(vendor, amount, spent="120.00", rules=RULES):
    req = PurchaseRequest(vendor=vendor, item="printer paper", amount=D(amount))
    return evaluate(req, rules, D(spent))


def test_small_approved_purchase_is_allowed():
    assert check("PaperDirect", "38.50").verdict == Verdict.ALLOW


def test_vendor_matching_ignores_case_and_spaces():
    assert check("  paperdirect ", "38.50").verdict == Verdict.ALLOW


def test_above_auto_limit_needs_approval():
    assert check("PaperDirect", "150.00").verdict == Verdict.NEEDS_APPROVAL


def test_unknown_vendor_needs_approval():
    assert check("ShadySupplies", "38.50").verdict == Verdict.NEEDS_APPROVAL


def test_above_hard_cap_is_denied():
    assert check("PaperDirect", "400.00").verdict == Verdict.DENY


def test_exceeding_monthly_budget_is_denied():
    assert check("PaperDirect", "90.00", spent="450.00").verdict == Verdict.DENY


def test_blocked_vendor_is_denied():
    rules = Rules(blocked_vendors=frozenset({"badvendor"}))
    assert check("BadVendor", "10.00", rules=rules).verdict == Verdict.DENY


def test_zero_and_negative_amounts_are_denied():
    assert check("PaperDirect", "0").verdict == Verdict.DENY
    assert check("PaperDirect", "-5").verdict == Verdict.DENY


def test_boundaries_are_inclusive():
    # exactly at the auto limit, and spending exactly the full budget
    assert check("PaperDirect", "100.00", spent="400.00").verdict == Verdict.ALLOW


def test_multiple_reasons_are_reported():
    decision = check("ShadySupplies", "150.00")
    assert decision.verdict == Verdict.NEEDS_APPROVAL
    assert len(decision.reasons) == 2