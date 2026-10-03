"""Wage payer names: the built-in one plus any added with `run.py wage NAME` (for a job change)."""
from typing import List

from fintrack.store import get_value, set_value

KEY = "wage_payers"


def all_payers(conn, default: str) -> List[str]:
    """The default payer first, then the saved ones (one per line in the kv table)."""
    saved = [n for n in (get_value(conn, KEY) or "").split("\n") if n]
    return [default] + [n for n in saved if n.upper() != default.upper()]


def add_payer(conn, name: str) -> str:
    """Save a payer name (upper case, trimmed, no duplicates). Returns the saved name."""
    name = " ".join(name.split()).upper()
    saved = [n for n in (get_value(conn, KEY) or "").split("\n") if n]
    if name and name not in saved:
        set_value(conn, KEY, "\n".join(saved + [name]))
    return name
