from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum


class Verdict(str, Enum):
    ALLOW = "ALLOW"                    # agent may pay automatically
    NEEDS_APPROVAL = "NEEDS_APPROVAL"  # pause and ask the owner
    DENY = "DENY"                      # blocked, with reasons


@dataclass(frozen=True)
class Rules:
    monthly_budget: Decimal = Decimal("500.00")
    auto_approve_limit: Decimal = Decimal("100.00")      # above this -> ask owner
    hard_cap_per_purchase: Decimal = Decimal("300.00")   # above this -> never
    approved_vendors: frozenset = frozenset({"paperdirect", "officemax pro"})
    blocked_vendors: frozenset = frozenset()


@dataclass(frozen=True)
class PurchaseRequest:
    vendor: str
    item: str
    amount: Decimal


@dataclass(frozen=True)
class Decision:
    verdict: Verdict
    reasons: list = field(default_factory=list)


def _norm(name: str) -> str:
    return name.strip().casefold()


def evaluate(req: PurchaseRequest, rules: Rules, spent_this_month: Decimal) -> Decision:
    """Deterministic checks. Hard denials come first, then approval triggers."""
    deny, approval = [], []

    if req.amount <= 0:
        deny.append("Amount must be greater than zero.")
    if _norm(req.vendor) in {_norm(v) for v in rules.blocked_vendors}:
        deny.append(f"Vendor '{req.vendor}' is blocked.")
    if req.amount > rules.hard_cap_per_purchase:
        deny.append(
            f"${req.amount} exceeds the hard cap of ${rules.hard_cap_per_purchase} per purchase."
        )
    if spent_this_month + req.amount > rules.monthly_budget:
        remaining = rules.monthly_budget - spent_this_month
        deny.append(
            f"${req.amount} would exceed the monthly budget (${remaining} remaining)."
        )
    if deny:
        return Decision(Verdict.DENY, deny)

    if _norm(req.vendor) not in {_norm(v) for v in rules.approved_vendors}:
        approval.append(f"'{req.vendor}' is not an approved vendor.")
    if req.amount > rules.auto_approve_limit:
        approval.append(
            f"${req.amount} is above the ${rules.auto_approve_limit} auto-approve limit."
        )
    if approval:
        return Decision(Verdict.NEEDS_APPROVAL, approval)

    return Decision(Verdict.ALLOW, ["Within all rules."])