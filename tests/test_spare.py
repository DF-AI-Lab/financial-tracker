"""Step 6 of SPEC.md: expected spare (this cycle) and expected vs actual (the last finished cycle). Fake data only."""
from datetime import date

import pytest

from fintrack.common import analyse
from fintrack.cycles import build_cycles
from fintrack.models import Analysis, Txn
from fintrack.spare import (balance_before, expected_bills, expected_spare, format_expected, format_last_cycle,
                            last_cycle_check)

PAYER = "ACME MOTORS PLC"


def fake_txns():
    """Wages of 2,000 on 28 Jan, Feb, Mar, Apr -> 3 finished cycles and the current one.
    Each cycle: rent 500 (SO), energy 80 (DD; 95 in the 3rd cycle), a shop (100, 200, 150; 50 now).
    3rd cycle also: a 60 refund in and a 1,200 TV (one-off). One payment per day, so every payment has a balance.
    Balance 100 on 20 Jan. Balance before each payday: 28 Feb 1,420; 28 Mar 2,640; 28 Apr 2,755."""
    rows = [(1, 20, "VIS", "CORNER SHOP", -10.0)]
    shop = [100.0, 200.0, 150.0, 50.0]
    energy = [80.0, 80.0, 95.0, 80.0]
    for k in range(4):
        m = k + 1
        rows += [(m, 28, "CR", PAYER, 2000.0),
                 (m + 1, 1, "SO", "LANDLORD", -500.0),
                 (m + 1, 2, "DD", "ENERGY CO", -energy[k]),
                 (m + 1, 3, "VIS", "CORNER SHOP", -shop[k])]
        if k == 2:
            rows += [(m + 1, 4, "CR", "REFUND CO", 60.0), (m + 1, 5, "VIS", "BIG TV STORE", -1200.0)]
    txns, bal = [], 110.0
    for mo, d, typ, desc, amt in rows:
        bal += amt
        txns.append(Txn(date(2024, mo, d), typ, desc, "RENT" if desc == "LANDLORD" else "", amt, round(bal, 2)))
    return txns


def cycles():
    return build_cycles(fake_txns(), payer=PAYER)


# ---- pieces ---------------------------------------------------------------------------------------

def test_balance_before():
    tx = fake_txns()
    assert balance_before(tx, date(2024, 1, 28)) == pytest.approx(100)
    assert balance_before(tx, date(2024, 3, 28)) == pytest.approx(2640)
    assert balance_before(tx, date(2024, 4, 28)) == pytest.approx(2755)
    assert balance_before(tx, date(2024, 1, 1)) is None                     # nothing before it
    no_bal = [Txn(t.date, t.type, t.description, t.detail, t.amount) for t in tx]
    assert balance_before(no_bal, date(2024, 3, 28)) is None


def test_expected_bills_uses_last_month_and_counts_stopped_ones_at_their_average():
    a = Analysis(3, {"RENT": {"average": 500.0, "last": 520.0, "kind": "bill", "cycles": 3, "total": 1500.0},
                     "TV": {"average": 13.0, "last": 0, "kind": "bill", "cycles": 2, "total": 39.0}}, 513.0, 0.0, [])
    assert expected_bills(a) == pytest.approx(533)


# ---- this cycle: expected spare after typing the wage ----------------------------------------------

def test_expected_spare_this_cycle():
    cs = cycles()
    a = analyse(cs)
    e = expected_spare(cs, a, 2500.0)
    assert e["start"] == date(2024, 4, 28)
    assert e["left_over"] == pytest.approx(2755)
    assert e["wage"] == pytest.approx(2500)
    assert e["bills"] == pytest.approx(595)                 # rent 500 + energy 95 (last month)
    assert e["normal"] == pytest.approx(150)                # (100 + 200 + 150) / 3, TV left out
    assert e["expected"] == pytest.approx(4510)
    assert e["cycles_used"] == 3 and e["yearly"] == []


def test_expected_spare_with_a_yearly_bill_due():
    cs = cycles()
    due = [{"key": "DD|AVIVA|", "label": "AVIVA", "amount": 180.0, "paid": date(2023, 4, 30)}]
    e = expected_spare(cs, analyse(cs), 2500.0, yearly=due)
    assert e["yearly"] == [{"label": "AVIVA", "amount": 180.0, "paid": date(2023, 4, 30),
                            "spare_if_paid": pytest.approx(4330)}]


def test_format_expected():
    cs = cycles()
    due = [{"key": "DD|AVIVA|", "label": "AVIVA", "amount": 180.0, "paid": date(2023, 4, 30)}]
    lines = format_expected(expected_spare(cs, analyse(cs), 2500.0, yearly=due))
    assert lines == [
        "IF YOUR PAY IS 2,500.00   (this cycle, from 28 Apr 2024)",
        f"  {'Left over from last month':<28}{'2,755.00':>10}   (balance just before this payday)",
        f"+ {'Wage':<28}{'2,500.00':>10}",
        f"- {'Bills':<28}{'595.00':>10}   (last month's amount of each bill)",
        f"- {'Normal spending':<28}{'150.00':>10}   (3-cycle average, no one-offs)",
        f"= {'Expected spare':<28}{'4,510.00':>10}",
        "WARNING Possible yearly bill: AVIVA 180.00, paid Apr 2023",
        f"  {'Expected spare if paid':<28}{'4,330.00':>10}",
    ]
    assert all(line.isascii() for line in lines)


def test_unknown_left_over_counts_as_zero():
    tx = [Txn(t.date, t.type, t.description, t.detail, t.amount) for t in fake_txns()]   # no balances
    cs = build_cycles(tx, payer=PAYER)
    e = expected_spare(cs, analyse(cs), 2500.0)
    assert e["left_over"] is None and e["expected"] == pytest.approx(1755)
    assert format_expected(e)[1] == f"  {'Left over from last month':<28}{'unknown':>10}   (counted as 0)"


def test_not_enough_finished_cycles():
    cs = build_cycles([Txn(date(2024, 1, 28), "CR", PAYER, "", 2000.0)], payer=PAYER)
    e = expected_spare(cs, analyse(cs), 2000.0)
    assert format_expected(e) == ["Not enough finished paydays yet to work out the expected spare."]


# ---- the last finished cycle: expected vs actual ---------------------------------------------------

def test_last_cycle_expected_vs_actual():
    c = last_cycle_check(cycles())
    assert c["start"] == date(2024, 3, 28) and c["end"] == date(2024, 4, 27)
    assert c["left_over"] == pytest.approx(2640)
    assert c["wage"] == pytest.approx(2000)
    # what was expected at its start: the bills of the cycle before it and the average of the cycles before it
    assert c["bills"] == pytest.approx(580)                 # rent 500 + energy 80
    assert c["normal"] == pytest.approx(150)                # (100 + 200) / 2
    assert c["expected"] == pytest.approx(3910)
    # what really happened
    assert c["other_in"] == pytest.approx(60)
    assert c["money_out"] == pytest.approx(1945)            # 500 + 95 + 150 + 1,200
    assert c["actual"] == pytest.approx(2755)               # = the balance just before the next payday
    assert c["missing"] == pytest.approx(1155)


def test_last_cycle_uses_answers_and_rules():
    answers = {"CARD|CORNER SHOP|": {"kind": "oneoff", "label": "", "source": "user"}}
    c = last_cycle_check(cycles(), answers=answers)
    assert c["normal"] == pytest.approx(0)                  # the shop is now a one-off
    assert c["missing"] == pytest.approx(1305)


def test_last_cycle_needs_a_finished_cycle_before_it():
    two = [t for t in fake_txns() if t.date < date(2024, 3, 28)]      # cycles: Jan (done), Feb (so far)
    assert last_cycle_check(build_cycles(two, payer=PAYER)) is None


def test_format_last_cycle():
    lines = format_last_cycle(last_cycle_check(cycles()))
    assert lines == [
        "LAST CYCLE: EXPECTED vs ACTUAL   (28 Mar 2024 to 27 Apr 2024)",
        f"  {'Left over from last month':<28}{'2,640.00':>10}",
        f"+ {'Wage':<28}{'2,000.00':>10}",
        f"- {'Bills':<28}{'580.00':>10}",
        f"- {'Normal spending':<28}{'150.00':>10}",
        f"= {'Expected spare':<28}{'3,910.00':>10}",
        "",
        f"  {'Left over from last month':<28}{'2,640.00':>10}",
        f"+ {'Wage':<28}{'2,000.00':>10}",
        f"+ {'Other money in':<28}{'60.00':>10}",
        f"- {'All money out':<28}{'1,945.00':>10}",
        f"= {'Actual spare':<28}{'2,755.00':>10}   (your balance at the end of the cycle)",
        "",
        f"  {'Missing':<28}{'1,155.00':>10}   (expected - actual)",
    ]


def test_format_last_cycle_good_month():
    c = dict(last_cycle_check(cycles()), missing=-150.0)
    assert format_last_cycle(c)[-1] == f"  {'Better than expected by':<28}{'150.00':>10}"
    assert format_last_cycle(None) == []
