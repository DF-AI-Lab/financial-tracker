from datetime import date

import pytest

from fintrack.cycles import build_cycles, cycle_report, is_wage
from fintrack.models import Txn
from tests.synth import PAYER, synth_txns


def cycles():
    return build_cycles(synth_txns(), payer=PAYER)


def test_is_wage():
    t = lambda desc, amt: Txn(date(2024, 1, 1), "CR", desc, "", amt)
    assert is_wage(t("ACME MOTORS PLC", 2400), payer=PAYER)
    assert is_wage(t("acme motors plc", 2400), payer=PAYER)
    assert not is_wage(t("ACME MOTORS PLC", 300), payer=PAYER)      # too small
    assert not is_wage(t("ACME MOTORS PLC", -2400), payer=PAYER)    # money out
    assert not is_wage(t("SOMEONE ELSE", 2400), payer=PAYER)
    assert is_wage(t("VERTU MOTORS PLC", 2400))                      # default payer


def test_eight_cycles_and_dates():
    cs = cycles()
    assert len(cs) == 8
    assert cs[0].start == date(2024, 1, 28) and cs[0].end == date(2024, 2, 27)
    assert cs[1].start == date(2024, 2, 28) and cs[1].end == date(2024, 3, 27)
    assert [c.complete for c in cs] == [True] * 7 + [False]
    assert cs[-1].start == date(2024, 8, 28) and cs[-1].end == date(2024, 9, 8)
    assert cs[0].label == "28 Jan 2024"


def test_payments_before_first_wage_are_dropped_and_none_lost():
    cs = cycles()
    all_in = [t for c in cs for t in c.txns]
    assert not any(t.description == "EARLY SHOP" for t in all_in)
    wanted = [t for t in synth_txns() if t.date >= date(2024, 1, 28)]
    assert len(all_in) == len(wanted)
    for c in cs:
        assert all(c.start <= t.date <= c.end for t in c.txns)


def test_extra_wage_within_10_days_stays_in_same_cycle():
    cs = cycles()
    assert len(cs) == 8
    assert cs[4].wage == pytest.approx(3000.00)   # 2400 + 600 bonus
    assert any(t.detail == "BONUS" for t in cs[4].txns)
    assert cs[2].wage == pytest.approx(2400.00)   # the 300 credit is not a wage


def test_no_wage_gives_no_cycles():
    assert build_cycles(synth_txns(), payer="NOBODY LTD") == []


def test_cycle_report_rows():
    rows = cycle_report(cycles())
    assert len(rows) == 8
    r = rows[1]
    assert r["label"] == "28 Feb 2024" and r["start"] == "2024-02-28" and r["end"] == "2024-03-27"
    assert r["complete"] is True
    assert r["wage"] == pytest.approx(2400.00)
    assert r["other_in"] == pytest.approx(0.0)
    assert r["bills"] == pytest.approx(790.00)      # rent 550 + gym 50 + energy 190
    assert r["random"] == pytest.approx(92.99)      # stream 12.99 + corner 30 + cash 50
    assert r["spare"] == pytest.approx(1517.01)
    r5 = rows[4]
    assert r5["wage"] == pytest.approx(3000.00)
    assert r5["other_in"] == pytest.approx(4800.00)
    assert r5["bills"] == pytest.approx(755.00)
    assert r5["random"] == pytest.approx(41.99)
    assert r5["spare"] == pytest.approx(7003.01)
    assert rows[-1]["complete"] is False
