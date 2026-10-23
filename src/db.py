import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal

SCHEMA = """
CREATE TABLE IF NOT EXISTS purchases (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  vendor TEXT NOT NULL,
  item TEXT NOT NULL,
  quantity INTEGER NOT NULL,
  unit_price TEXT NOT NULL,
  amount TEXT NOT NULL,
  status TEXT NOT NULL,
  reasons TEXT NOT NULL DEFAULT '[]',
  payout_batch_id TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  purchase_id INTEGER,
  event TEXT NOT NULL,
  detail TEXT NOT NULL DEFAULT ''
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def conn():
    c = sqlite3.connect(os.environ.get("DB_PATH", "procurement.db"))
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def create_purchase(vendor, item, quantity, unit_price, amount) -> int:
    now = _now()
    with conn() as c:
        cur = c.execute(
            "INSERT INTO purchases (vendor, item, quantity, unit_price, amount, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, 'PROPOSED', ?, ?)",
            (vendor, item, quantity, str(unit_price), str(amount), now, now),
        )
        return cur.lastrowid


def get_purchase(pid: int) -> dict | None:
    with conn() as c:
        row = c.execute("SELECT * FROM purchases WHERE id = ?", (pid,)).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["reasons"] = json.loads(d["reasons"])
    return d


def set_status(pid: int, status: str, reasons: list | None = None, batch_id: str | None = None) -> None:
    with conn() as c:
        c.execute(
            "UPDATE purchases SET status = ?, reasons = COALESCE(?, reasons), "
            "payout_batch_id = COALESCE(?, payout_batch_id), updated_at = ? WHERE id = ?",
            (status, json.dumps(reasons) if reasons is not None else None, batch_id, _now(), pid),
        )


def transition(pid: int, from_status: str, to_status: str) -> bool:
    """Atomically move a purchase between statuses. Only one caller can win."""
    with conn() as c:
        cur = c.execute(
            "UPDATE purchases SET status = ?, updated_at = ? WHERE id = ? AND status = ?",
            (to_status, _now(), pid, from_status),
        )
        return cur.rowcount == 1


def spent_this_month() -> Decimal:
    month = _now()[:7]  # e.g. "2026-10"
    with conn() as c:
        rows = c.execute(
            "SELECT amount FROM purchases WHERE status = 'PAYOUT_SUBMITTED' AND substr(updated_at, 1, 7) = ?",
            (month,),
        ).fetchall()
    return sum((Decimal(r["amount"]) for r in rows), Decimal("0"))


def list_pending() -> list[dict]:
    with conn() as c:
        rows = c.execute("SELECT * FROM purchases WHERE status = 'PENDING_APPROVAL' ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def log(pid: int | None, event: str, detail: str = "") -> None:
    with conn() as c:
        c.execute(
            "INSERT INTO audit_log (ts, purchase_id, event, detail) VALUES (?, ?, ?, ?)",
            (_now(), pid, event, detail),
        )


def list_audit(pid: int | None = None, limit: int = 100) -> list[dict]:
    with conn() as c:
        if pid is None:
            rows = c.execute("SELECT * FROM audit_log ORDER BY id LIMIT ?", (limit,)).fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM audit_log WHERE purchase_id = ? ORDER BY id LIMIT ?", (pid, limit)
            ).fetchall()
    return [dict(r) for r in rows]