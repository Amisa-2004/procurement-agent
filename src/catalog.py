import os
from decimal import Decimal

# Mock supplier catalog. (Optional upgrade later: pull real products from Channel3.)
CATALOG = [
    {"vendor": "PaperDirect",     "item": "printer paper (case)", "unit_price": Decimal("38.50")},
    {"vendor": "BulkSupplies Co", "item": "printer paper (case)", "unit_price": Decimal("40.25")},
    {"vendor": "OfficeMax Pro",   "item": "printer paper (case)", "unit_price": Decimal("42.00")},
    {"vendor": "OfficeMax Pro",   "item": "toner cartridge",      "unit_price": Decimal("89.99")},
    {"vendor": "PaperDirect",     "item": "toner cartridge",      "unit_price": Decimal("94.50")},
    {"vendor": "BulkSupplies Co", "item": "toner cartridge",      "unit_price": Decimal("85.00")},
]


def search_catalog(item: str) -> list[dict]:
    q = (item or "").strip().casefold()
    if not q:
        return []
    return [e for e in CATALOG if q in e["item"].casefold()]


def find_quote(vendor: str, item: str) -> dict | None:
    """Exactly one matching catalog entry, or None."""
    v = (vendor or "").strip().casefold()
    matches = [e for e in search_catalog(item) if e["vendor"].casefold() == v]
    return matches[0] if len(matches) == 1 else None


def get_vendor_email(vendor: str) -> str:
    # Sandbox: every vendor maps to one test account. In production this would be a
    # verified vendor directory that the AI can never modify.
    return os.environ["SUPPLIER_TEST_EMAIL"]