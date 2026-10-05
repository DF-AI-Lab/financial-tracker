"""Home page layout (user, 3 Oct 2026): cards and rows in the user's own order (drag and drop) and rows renamed.

Kept for good in the kv table under "layout": {"order": {container: [ids]}, "names": {row id: name}}.
Page only: the bills, items, rules and the terminal are never changed. Rows not in a saved order go at the bottom.
"""
import json
from typing import Callable, List

from fintrack.store import get_value, set_value

KEY = "layout"
# The cards that can be moved, in their normal order (the ids the page uses).
CARDS = ["spend", "card", "bills", "lastmonth", "where", "cats", "subs", "periods"]
# The lists of rows that can be moved.
SORTS = ["cards", "bills", "lastmonth", "cats", "subs-active", "subs-stopped"]


def get_layout(conn) -> dict:
    try:
        saved = json.loads(get_value(conn, KEY) or "{}")
    except ValueError:
        saved = {}
    return {"order": saved.get("order", {}), "names": saved.get("names", {})}


def _save(conn, lay: dict) -> None:
    set_value(conn, KEY, json.dumps(lay))


def save_order(conn, sort: str, ids: List[str]) -> None:
    lay = get_layout(conn)
    lay["order"][sort] = [str(i) for i in ids]
    _save(conn, lay)


def set_name(conn, row_id: str, name: str) -> None:
    """Rename a row on the page; an empty name puts the normal one back."""
    lay = get_layout(conn)
    name = (name or "").strip()
    if name:
        lay["names"][row_id] = name
    else:
        lay["names"].pop(row_id, None)
    _save(conn, lay)


def reset_order(conn) -> None:
    """Put cards and rows back in the normal order (names are kept)."""
    lay = get_layout(conn)
    lay["order"] = {}
    _save(conn, lay)


def apply_order(rows: list, ids: List[str], key: Callable) -> list:
    """rows in the saved order; rows not in it keep their normal order, after the saved ones."""
    pos = {i: n for n, i in enumerate(ids)}
    return sorted(rows, key=lambda r: pos.get(key(r), len(pos)))   # sorted is stable: new rows keep their order
