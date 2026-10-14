"""v3 (14 Oct 2026): a new payment can REPLACE a bill you already have (e.g. a new car insurer).

- Every new bill (a DD/SO saved by auto_bills, source "auto") is asked once on the page: New bill, or Replaces <bill>.
  kv "newbill_seen" = items already seen. The first time it is filled with every saved item, so nothing old is asked.
- Replaces = the new item joins the old bill: it takes that bill's label (so spare.common_key gives the same key) and
  category. From the swap on (the new item's first payment) only the new payee counts: the old payee's payments on or
  after that day are left out of the bills (bill_txns). Everything else on the page is unchanged.
- kv "bill_swaps": [{"bill", "new": [items], "old": [items], "from": ISO date, "labels": {item: label before},
  "cats": {item: category before}}]. Split back out undoes the latest swap of a bill.
Only Replaces, no "adds to": a genuine extra bill is just New bill.
"""
import json
from datetime import date

from fintrack.questions import item_stats
from fintrack.store import get_categories, get_items, get_value, item_key, set_category, set_item, set_value

SEEN = "newbill_seen"
SWAPS = "bill_swaps"
COMMON = ("common", "regular")


def _load(conn, key, default):
    try:
        v = get_value(conn, key)
        return default if v is None else json.loads(v)
    except ValueError:
        return default


def get_swaps(conn) -> list:
    return _load(conn, SWAPS, [])


def bill_of(key, item) -> str:
    """The bill key of a saved common item (same as spare.common_key): its label, else the item key."""
    return item.get("label") or key


def items_of(items, bill) -> list:
    """The saved common items behind a bill key."""
    return sorted(k for k, v in items.items() if v["kind"] in COMMON and bill_of(k, v) == bill)


# ---- the question ----------------------------------------------------------------------------------

def new_bill_questions(conn, txns) -> list:
    """{"type": "newbill", "key", "name", "amount", "bill", "bills": []} for every new auto bill not seen yet.
    "bills" (the bills it could replace) is filled in by home_data."""
    items = get_items(conn)
    seen = _load(conn, SEEN, None)
    if seen is None:                                   # first run: everything saved so far counts as seen
        set_value(conn, SEEN, json.dumps(sorted(items)))
        return []
    seen = set(seen)
    stats = item_stats(txns)
    out = []
    for k in sorted(items):
        it = items[k]
        if k in seen or it["source"] != "auto" or it["kind"] not in COMMON or k not in stats:
            continue
        bill = bill_of(k, it)
        if items_of(items, bill) != [k]:               # already part of a bill with other payees
            continue
        out.append({"type": "newbill", "key": k, "name": stats[k]["name"], "amount": stats[k]["amounts"][-1],
                    "bill": bill, "bills": []})
    return out


def _mark_seen(conn, key) -> None:
    seen = set(_load(conn, SEEN, None) or [])
    set_value(conn, SEEN, json.dumps(sorted(seen | {key})))


def answer_new_bill(conn, a: dict, txns) -> bool:
    """{"key": item, "into": "" (New bill) or a bill key (Replaces)}. False when it is not an open question."""
    key, into = a.get("key"), str(a.get("into") or "")
    if key not in [q["key"] for q in new_bill_questions(conn, txns)]:
        return False
    if into and not join_items(conn, txns, [key], into):
        return False
    _mark_seen(conn, key)
    return True


# ---- join and split ---------------------------------------------------------------------------------

def join_items(conn, txns, keys, into) -> bool:
    """Move these items into the bill `into`. From = their first payment. False (nothing saved) when it cannot."""
    items = get_items(conn)
    old = items_of(items, into)
    keys = sorted(set(keys))
    if not keys or not old or set(keys) & set(old) or any(k not in items for k in keys):
        return False
    dates = [t.date for t in txns if t.amount < 0 and item_key(t) in keys]
    if not dates:
        return False
    cats = get_categories(conn)
    cat = next((cats[k] for k in old if cats.get(k)), "")
    swap = {"bill": into, "new": keys, "old": old, "from": min(dates).isoformat(),
            "labels": {k: items[k]["label"] for k in keys}, "cats": {k: cats.get(k, "") for k in keys}}
    for k in keys:
        set_item(conn, k, items[k]["kind"], into, items[k]["source"])
        if cat:
            set_category(conn, k, cat)
    set_value(conn, SWAPS, json.dumps(get_swaps(conn) + [swap]))
    return True


def join_bills(conn, txns, key, into) -> bool:
    """The ⋯ menu: the bill `key` replaces the bill `into` (joins it)."""
    if key == into:
        return False
    return join_items(conn, txns, items_of(get_items(conn), key), into)


def split(conn, bill) -> bool:
    """Split back out: undo the latest swap of this bill (labels and categories put back)."""
    swaps = get_swaps(conn)
    i = next((i for i in range(len(swaps) - 1, -1, -1) if swaps[i]["bill"] == bill), None)
    if i is None:
        return False
    s = swaps.pop(i)
    items = get_items(conn)
    for k in s["new"]:
        if k in items:
            set_item(conn, k, items[k]["kind"], s["labels"].get(k, ""), items[k]["source"])
            set_category(conn, k, s.get("cats", {}).get(k, ""))
    set_value(conn, SWAPS, json.dumps(swaps))
    return True


# ---- the rule for the bills -----------------------------------------------------------------------

def cut_day(day: date, paydays) -> date:
    """From the start of the pay cycle the swap happens in, so the swap month never counts the bill twice
    (even when the old payee took its last payment earlier in that cycle)."""
    starts = [p for p in (paydays or []) if p <= day]
    return max(starts) if starts else day


def bill_txns(conn, txns, paydays=None) -> list:
    """The payments the bills are worked out from: the old payee's payments from the swap's pay cycle on are left
    out. No swaps: the same list, untouched."""
    swaps = get_swaps(conn)
    if not swaps:
        return txns
    cuts = [(set(s["old"]), cut_day(date.fromisoformat(s["from"]), paydays)) for s in swaps]

    def dropped(t):
        return t.amount < 0 and any(t.date >= day and item_key(t) in old for old, day in cuts)
    return [t for t in txns if not dropped(t)]


# ---- the website ------------------------------------------------------------------------------------

def register(app) -> None:
    from flask import redirect, request

    from fintrack.store import load_txns, open_db

    def db():
        from pathlib import Path
        return open_db(Path(app.config["V3_DATA_DIR"]) / "tracker.db")

    def done():
        if request.headers.get("X-Requested-With") == "fetch":
            return ("", 204)
        return redirect("/", code=303)

    def form():
        return request.get_json(silent=True) or request.form

    @app.route("/bill/join", methods=["POST"])
    def bill_join():
        f = form()
        conn = db()
        join_bills(conn, load_txns(conn), str(f.get("key", "")), str(f.get("into", "")))
        conn.close()
        return done()

    @app.route("/bill/split", methods=["POST"])
    def bill_split():
        conn = db()
        split(conn, str(form().get("key", "")))
        conn.close()
        return done()
