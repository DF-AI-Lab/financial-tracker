"""Credit card (user, 5 Oct 2026): one card (Zopa, 500 limit), spends typed in by hand and taken off again.

Kept in the kv table under "credit_card":
    {"limit": 500.0, "next": 3, "carry": 0.0, "items": [{"id", "date" (ISO), "amount", "name", "kind"}]}
kind: "spend" (amount > 0), "paid" (amount < 0, money paid off) or "correction" (either sign: the Used box).
Paying off clears the OLDEST owed lines first (positive lines are owed, negative lines pay). A fully paid line is
crossed out; only the 5 newest crossed-out lines and the 5 newest used-up payments are kept, the rest are folded
into "carry" (an unseen line before all others) so used = carry + sum of the amounts stays right.
Nothing here touches the bills, the typed spends or the spare cash.
"""
import json
from datetime import date

from fintrack.store import get_value, set_value

KEY = "credit_card"
LIMIT = 500.0
KEEP = 5


def _load(conn) -> dict:
    try:
        saved = json.loads(get_value(conn, KEY) or "{}")
    except ValueError:
        saved = {}
    items = []
    for i in saved.get("items", []):
        kind = i.get("kind") or ("spend" if i["amount"] > 0 else "paid")       # lines saved before kinds existed
        items.append({"id": i["id"], "date": i["date"], "amount": float(i["amount"]), "name": i["name"], "kind": kind})
    return {"limit": float(saved.get("limit", LIMIT)), "next": int(saved.get("next", 1)),
            "carry": float(saved.get("carry", 0.0)), "items": items}


def allocate(items: list, carry: float = 0.0) -> list:
    """Each line with "status" (owed / part / paid for positive lines, credit for negative ones), "left" (still owed)
    and "used_up" (a payment that went fully into older lines). Payments clear the oldest positive lines first."""
    debts = sum(i["amount"] for i in items if i["amount"] > 0) + max(carry, 0.0)
    credit = sum(-i["amount"] for i in items if i["amount"] < 0) + max(-carry, 0.0)
    pot = round(credit - max(carry, 0.0), 2)              # what is left for the lines we can see
    out, given = [], max(-carry, 0.0)
    for i in items:
        r = dict(i)
        if i["amount"] > 0:
            take = min(max(pot, 0.0), i["amount"])
            pot = round(pot - take, 2)
            r["left"] = round(i["amount"] - take, 2)
            r["status"] = "paid" if r["left"] <= 0 else ("part" if take > 0 else "owed")
        else:
            given = round(given - i["amount"], 2)
            r["left"] = 0
            r["status"] = "credit"
            r["used_up"] = given <= debts + 0.005
        out.append(r)
    return out


def _tidy(card: dict) -> None:
    """Fold all but the 5 newest crossed-out lines and the 5 newest used-up payments into carry."""
    rows = allocate(card["items"], card["carry"])
    paid = [r["id"] for r in rows if r["status"] == "paid"]
    spent = [r["id"] for r in rows if r["status"] == "credit" and r["used_up"]]
    drop = set(paid[:-KEEP] if len(paid) > KEEP else []) | set(spent[:-KEEP] if len(spent) > KEEP else [])
    if drop:
        card["carry"] = round(card["carry"] + sum(i["amount"] for i in card["items"] if i["id"] in drop), 2)
        card["items"] = [i for i in card["items"] if i["id"] not in drop]


def _save(conn, card: dict) -> None:
    _tidy(card)
    set_value(conn, KEY, json.dumps(card))


def get_card(conn) -> dict:
    """{"limit", "used", "free", "carry", "items": [{"id", "date" (a date), "amount", "name", "kind"}],
    "rows": items plus "status", "left", "removable"}."""
    card = _load(conn)
    items = [dict(i, date=date.fromisoformat(i["date"])) for i in card["items"]]
    rows = allocate(items, card["carry"])
    for r in rows:
        r["removable"] = r["status"] != "paid"
    used = round(card["carry"] + sum(i["amount"] for i in items), 2)
    return {"limit": card["limit"], "items": items, "rows": rows, "carry": card["carry"], "used": used,
            "free": round(card["limit"] - used, 2)}


def add_card(conn, d: date, amount: float, name: str, kind: str = "") -> None:
    """A spend on the card (amount > 0) or money paid off it (amount < 0)."""
    card = _load(conn)
    card["items"].append({"id": card["next"], "date": d.isoformat(), "amount": round(float(amount), 2),
                          "name": name.strip()[:60], "kind": kind or ("spend" if amount > 0 else "paid")})
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


def set_used(conn, d: date, amount: float) -> None:
    """The user typed what the card owes now (the Used box): a Correction line makes the total match."""
    diff = round(float(amount) - get_card(conn)["used"], 2)
    if diff != 0:
        add_card(conn, d, diff, "Correction", kind="correction")


set_balance = set_used                                    # the name the page and phone used first
