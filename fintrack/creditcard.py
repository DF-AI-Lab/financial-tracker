"""Credit card (user, 5 Oct 2026): one card (Zopa, 500 limit), spends typed in by hand and taken off again.

Kept in the kv table under "credit_card": {"limit": 500.0, "next": 3, "items": [{"id", "date" (ISO), "amount", "name"}]}.
A negative amount = money paid off the card. Used = sum of the amounts, free = limit - used.
Nothing here touches the bills, the typed spends or the spare cash.
"""
import json
from datetime import date

from fintrack.store import get_value, set_value

KEY = "credit_card"
LIMIT = 500.0


def _load(conn) -> dict:
    try:
        saved = json.loads(get_value(conn, KEY) or "{}")
    except ValueError:
        saved = {}
    return {"limit": float(saved.get("limit", LIMIT)), "next": int(saved.get("next", 1)),
            "items": list(saved.get("items", []))}


def _save(conn, card: dict) -> None:
    set_value(conn, KEY, json.dumps(card))


def get_card(conn) -> dict:
    """{"limit", "items": [{"id", "date" (a date), "amount", "name"}], "used", "free"}."""
    card = _load(conn)
    items = [{"id": i["id"], "date": date.fromisoformat(i["date"]), "amount": float(i["amount"]), "name": i["name"]}
             for i in card["items"]]
    used = round(sum(i["amount"] for i in items), 2)
    return {"limit": card["limit"], "items": items, "used": used, "free": round(card["limit"] - used, 2)}


def add_card(conn, d: date, amount: float, name: str) -> None:
    """A spend on the card (amount > 0) or money paid off it (amount < 0)."""
    card = _load(conn)
    card["items"].append({"id": card["next"], "date": d.isoformat(), "amount": round(float(amount), 2),
                          "name": name.strip()[:60]})
    card["next"] += 1
    _save(conn, card)


def remove_card(conn, item_id: int) -> bool:
    card = _load(conn)
    keep = [i for i in card["items"] if i["id"] != item_id]
    if len(keep) == len(card["items"]):
        return False
    card["items"] = keep
    _save(conn, card)
    return True


def set_limit(conn, limit: float) -> None:
    card = _load(conn)
    card["limit"] = float(limit)
    _save(conn, card)


def set_balance(conn, d: date, amount: float) -> None:
    """The user typed what the card owes now (user, 5 Oct 2026): the list becomes one 'Balance' line (0 = empty)."""
    card = _load(conn)
    card["items"] = []
    _save(conn, card)
    if round(float(amount), 2) != 0:
        add_card(conn, d, amount, "Balance")
