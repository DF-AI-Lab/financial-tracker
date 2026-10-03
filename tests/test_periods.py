"""Totals for the last 6 months, the last 12 months and this year so far (Oct 2026, the user asked for them under
the six-month picture). Fake data only."""
from datetime import date

import pytest

from fintrack.cycles import build_cycles
from fintrack.models import Txn
from fintrack.periods import period_totals

PAYER = "ACME MOTORS PLC"


def txns():
    """Wages of 2,000 on the 28th, Jul 2023 .. Jun 2025: finished cycles Jul 2023 .. May 2025 (i = 0 .. 22).
    Each cycle: rent 500 (SO) and a shop of 100 (even i) or 300 (odd i): random, never common.
    Cycle Sep 2024 (i = 14): a 1,500 TV (one-off). Cycle Apr 2025 (i = 21): a 50 refund in."""
    tx, i = [], 0
    y, m = 2023, 7
    while (y, m) <= (2025, 6):
        tx.append(Txn(date(y, m, 28), "CR", PAYER, "", 2000.0))
        if (y, m) < (2025, 6):
            ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
            tx += [Txn(date(ny, nm, 1), "SO", "LANDLORD", "RENT", -500.0),
                   Txn(date(ny, nm, 3), "VIS", "CORNER SHOP", "", -(100.0 if i % 2 == 0 else 300.0))]
            if i == 14:
                tx.append(Txn(date(ny, nm, 5), "VIS", "BIG TV STORE", "", -1500.0))
            if i == 21:
                tx.append(Txn(date(ny, nm, 6), "CR", "REFUND CO", "", 50.0))
        i += 1
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return tx


def test_period_totals():
    got = period_totals(build_cycles(txns(), payer=PAYER))
    want = [("Last 6 months", 6, 12000, 50, 3000, 1200, 0, 7850),
            ("Last 12 months", 12, 24000, 50, 6000, 2400, 1500, 14150),
            ("2025 so far", 5, 10000, 50, 2500, 600, 0, 6950)]
    assert [(p["name"], p["cycles"]) for p in got] == [(w[0], w[1]) for w in want]
    for p, w in zip(got, want):
        assert (p["wage"], p["other_in"], p["bills"], p["spending"], p["oneoffs"], p["left"]) == pytest.approx(w[2:]), p["name"]


def test_answers_decide_what_is_what():
    answers = {"CARD|BIG TV STORE|": {"kind": "random", "label": "", "source": "user"}}
    twelve = period_totals(build_cycles(txns(), payer=PAYER), answers=answers)[1]
    assert twelve["oneoffs"] == 0 and twelve["spending"] == pytest.approx(3900)


def test_few_cycles_use_what_is_there():
    few = [t for t in txns() if t.date < date(2023, 11, 1)]          # finished cycles Jul, Aug, Sep 2023
    got = period_totals(build_cycles(few, payer=PAYER))
    assert [(p["name"], p["cycles"]) for p in got] == [("Last 6 months", 3), ("Last 12 months", 3), ("2023 so far", 3)]
    assert period_totals(build_cycles([Txn(date(2024, 1, 28), "CR", PAYER, "", 2000.0)], payer=PAYER)) == []
