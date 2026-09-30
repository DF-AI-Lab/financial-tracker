"""Made-up rent-by-transfer history for the payday-transfer rule tests. Everything invented.

Six complete cycles: payday (wage) on the 28th of Jan..Jun 2024. BP = bill payment to SAM PARKER.
  k1 550 "RENT"  +1 day       k2 550 "FOOD" +1 day (reference not changed)   k3 550 "RENT" +2 days
  k4 590 "RENT"  +1 day (a rise within 10%)   k5 550 "RENT" +5 days (too late)   k6 650 "RENT" +1 day (18% over)
  plus a small top-up every cycle, 8 days after payday.
"""
from datetime import date, timedelta

from fintrack.models import Cycle, Txn

PAYER = "SAM PARKER"
TOPUPS = [20, 35, 50, 25, 40, 15]
RENTS = [(550, "RENT", 1), (550, "FOOD", 1), (550, "RENT", 2), (590, "RENT", 1), (550, "RENT", 5), (650, "RENT", 1)]


def payday(k):
    return date(2024, k, 28)


def bp(d, detail, amt):
    return Txn(d, "BP", PAYER, detail, -float(amt))


def cycle_txns(k):
    p = payday(k)
    amt, ref, days = RENTS[k - 1]
    return [Txn(p, "CR", "ACME MOTORS PLC", "PAYROLL", 2400.0),
            bp(p + timedelta(days=days), ref, amt),
            bp(p + timedelta(days=8), "Food and bil", TOPUPS[k - 1])]


def cycles(extra=None):
    """The six cycles (all complete). extra = {k: [Txn, ...]} adds payments to cycle k."""
    out = []
    for k in range(1, 7):
        txns = cycle_txns(k) + list((extra or {}).get(k, []))
        out.append(Cycle(payday(k), payday(k) + timedelta(days=27), 2400.0, txns, True))
    return out


def all_txns(cs=None):
    return sorted((t for c in (cs or cycles()) for t in c.txns), key=lambda t: t.date)


def paydays(cs=None):
    return [c.start for c in (cs or cycles())]


RULE = {"payer": PAYER, "usual": 550.0, "label": "Rent", "kind": "common", "max_days": 2, "tolerance": 0.10, "source": "user"}
