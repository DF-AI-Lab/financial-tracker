"""Paid early: a payment made a few days before payday that belongs to the next month (e.g. rent
sent the day before the wage). `run.py early` lists them; `run.py early N` moves one (again = undo).
A moved payment is dated on that payday, so it counts in the new cycle and not in "left over"."""
from datetime import timedelta
from typing import List, Set

from fintrack.cycles import is_wage
from fintrack.models import Txn
from fintrack.store import get_value, load_txns, set_value

KEY = "moved_early"
DAYS = 3        # how many days before payday count as "early"
MIN = 20.0      # smaller payments are not listed


def key(t: Txn) -> str:
    return f"{t.date.isoformat()}|{t.type}|{t.description}|{t.detail}|{t.amount:.2f}"


def moved_keys(conn) -> Set[str]:
    return {k for k in (get_value(conn, KEY) or "").split("\n") if k}


def toggle(conn, t: Txn) -> bool:
    """Move t (or undo the move). Returns True if it is moved now."""
    keys = moved_keys(conn)
    k = key(t)
    now = k not in keys
    keys = keys | {k} if now else keys - {k}
    set_value(conn, KEY, "\n".join(sorted(keys)))
    return now


def _paydays(txns: List[Txn], payers) -> list:
    return sorted({t.date for t in txns if is_wage(t, payers)})


def candidates(txns: List[Txn], payers) -> list:
    """(txn, payday) for money out of MIN or more paid 1..DAYS days before a payday, newest first."""
    paydays = _paydays(txns, payers)
    found = []
    for t in txns:
        if t.amount > -MIN:
            continue
        nxt = next((p for p in paydays if p > t.date), None)
        if nxt is not None and (nxt - t.date).days <= DAYS:
            found.append((t, nxt))
    found.sort(key=lambda x: x[0].date, reverse=True)
    return found


def apply_moves(txns: List[Txn], keys: Set[str], payers) -> List[Txn]:
    """A new list where each moved payment is dated on its next payday and placed right after the
    wage(s) of that day. If it carried the day's balance, the payment before it (same day, no balance)
    gets the balance from just before it, so the end-of-day balance stays right."""
    if not keys:
        return list(txns)
    paydays = _paydays(txns, payers)
    out = list(txns)
    moving = []
    for i, t in enumerate(txns):
        if key(t) not in keys:
            continue
        nxt = next((p for p in paydays if p > t.date), None)
        if nxt is None:
            continue
        if t.balance is not None and i > 0 and txns[i - 1].date == t.date and txns[i - 1].balance is None:
            prev = txns[i - 1]
            out[out.index(prev)] = Txn(prev.date, prev.type, prev.description, prev.detail, prev.amount,
                                       round(t.balance - t.amount, 2))
        out.remove(t)
        moving.append(Txn(nxt, t.type, t.description, t.detail, t.amount, None))
    for m in moving:
        pos = max(i for i, x in enumerate(out) if x.date == m.date and is_wage(x, payers)) + 1
        out.insert(pos, m)
    return out


def load_moved(conn, payers) -> List[Txn]:
    """load_txns with the moves applied."""
    return apply_moves(load_txns(conn), moved_keys(conn), payers)
