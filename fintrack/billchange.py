"""Change a bill for this pay cycle only (user, 3 Oct 2026), e.g. next month's phone bill will be 151.

Kept in the kv table under "bill_changes" with the start of the cycle it is for, so it is forgotten by itself
when a new payday starts a new cycle. The bills (items, rules) are never changed.
"""
import json
from datetime import date
from typing import Dict

from fintrack.store import get_value, set_value

KEY = "bill_changes"


def _load(conn) -> dict:
    try:
        return json.loads(get_value(conn, KEY) or "{}")
    except ValueError:
        return {}


def get_changes(conn, start: date) -> Dict[str, float]:
    """{bill key: amount} for the cycle starting on start; {} when they were for another cycle."""
    saved = _load(conn)
    if saved.get("start") != start.isoformat():
        return {}
    return {k: float(v) for k, v in saved.get("bills", {}).items()}


def set_change(conn, start: date, key: str, amount: float) -> None:
    bills = get_changes(conn, start)
    bills[key] = amount
    set_value(conn, KEY, json.dumps({"start": start.isoformat(), "bills": bills}))


def clear_change(conn, start: date, key: str) -> None:
    bills = get_changes(conn, start)
    bills.pop(key, None)
    set_value(conn, KEY, json.dumps({"start": start.isoformat(), "bills": bills}))


# Left from last month (user, 3 Oct 2026): typed on the home page, added to the spare cash, forgotten at the next payday.
LEFT_KEY = "left_over_typed"


def get_left(conn, start: date) -> float:
    try:
        saved = json.loads(get_value(conn, LEFT_KEY) or "{}")
    except ValueError:
        return 0.0
    return float(saved["amount"]) if saved.get("start") == start.isoformat() else 0.0


def set_left(conn, start: date, amount: float) -> None:
    set_value(conn, LEFT_KEY, json.dumps({"start": start.isoformat(), "amount": amount}))


def clear_left(conn, start: date) -> None:
    set_value(conn, LEFT_KEY, "{}")
