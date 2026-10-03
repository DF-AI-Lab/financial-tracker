"""The pay block (Oct 2026, the user's own layout): every-month bills with 6-month avg and last month,
then SPARE CASH (No. 1), then last month's spending that is not bills (No. 2). Fake data only."""
from datetime import date

import pytest

from fintrack.common import analyse
from fintrack.cycles import build_cycles
from fintrack.models import Txn
from fintrack.spare import format_pay_block, pay_block
from tests.test_spare import PAYER, fake_txns


def txns():
    """test_spare's data (rent 500, energy 80/80/95, corner shop 100/200/150, wages 2,000 on the 28th of Jan..Apr)
    plus Tesco 20 in the 2nd cycle and 40 in the 3rd (the last finished one)."""
    tx = fake_txns() + [Txn(date(2024, 3, 10), "VIS", "TESCO STORES", "", -20.0),
                        Txn(date(2024, 4, 10), "VIS", "TESCO STORES", "", -40.0)]
    tx.sort(key=lambda t: t.date)
    return tx


def block(**kw):
    cs = build_cycles(kw.pop("tx", None) or txns(), payer=PAYER)
    return pay_block(cs, analyse(cs, answers=kw.pop("answers", None)), 2500.0, **kw)


def test_pay_block_numbers():
    p = block()
    assert [(b["name"], b["avg"], b["last"]) for b in p["bills"]] == [
        ("LANDLORD - RENT", pytest.approx(500), pytest.approx(500)), ("ENERGY CO", pytest.approx(85), pytest.approx(95))]
    assert p["bills_avg"] == pytest.approx(585) and p["bills_last"] == pytest.approx(595)
    assert p["left_over"] == pytest.approx(2755) and p["wage"] == 2500.0
    assert p["spare"] == pytest.approx(1905)                     # 2,500 - 595 (left over not added, 3 Oct 2026)
    assert [(s["category"], s["last"], s["avg"], s["labels"]) for s in p["spending"]] == [
        ("Unsorted", pytest.approx(150), pytest.approx(150), ["Corner Shop"]),
        ("Food shopping", pytest.approx(40), pytest.approx(20), ["Tesco Stores"])]
    assert p["spending_last"] == pytest.approx(190) and p["spending_avg"] == pytest.approx(170)
    assert p["left_usual"] == pytest.approx(1735)                # spare cash - average spending


def test_format_pay_block():
    due = [{"key": "DD|AVIVA|", "label": "AVIVA", "amount": 180.0, "paid": date(2023, 4, 30)}]
    assert format_pay_block(block(yearly=due)) == [
        "IF YOUR PAY IS 2,500.00   (this cycle, from 28 Apr 2024)",
        "",
        f"{'BILLS (every month)':<34}{'3-mth avg':>10}  {'Last month':>10}",
        f"  {'LANDLORD - RENT':<32}{'500.00':>10}  {'500.00':>10}",
        f"  {'ENERGY CO':<32}{'85.00':>10}  {'95.00':>10}",
        f"  {'Bills total':<32}{'585.00':>10}  {'595.00':>10}",
        "",
        f"  {'Pay':<32}{'2,500.00':>10}",
        f"- {'Bills (last month amounts)':<32}{'595.00':>10}",
        f"= {'SPARE CASH':<32}{'1,905.00':>10}",
        "",
        f"{'LAST MONTH SPENDING (not bills)':<34}{'Last month':>10}  {'3-mth avg':>10}",
        f"  {'Unsorted':<32}{'150.00':>10}  {'150.00':>10}   (Corner Shop)",
        f"  {'Food shopping':<32}{'40.00':>10}  {'20.00':>10}   (Tesco Stores)",
        f"  {'Total':<32}{'190.00':>10}  {'170.00':>10}",
        "",
        "WARNING Possible yearly bill: AVIVA 180.00, paid Apr 2023",
        f"  {'If that is paid too, left':<32}{'1,725.00':>10}",
    ]


def test_a_bill_not_paid_last_month_shows_a_dash_and_counts_at_its_average():
    tx = [t for t in txns() if not (t.description == "ENERGY CO" and t.date == date(2024, 4, 2))]
    answers = {"DD|ENERGY CO|": {"kind": "common", "label": "ENERGY CO", "source": "user"}}
    p = block(tx=tx, answers=answers)
    energy = next(b for b in p["bills"] if b["name"] == "ENERGY CO")
    assert energy["last"] == 0 and energy["avg"] == pytest.approx(160 / 3)
    assert p["bills_last"] == pytest.approx(500 + 160 / 3)       # energy counted at its average
    assert energy["used"] == pytest.approx(160 / 3) and energy["estimated"] is True and energy["diff"] is None
    lines = format_pay_block(p)
    line = next(l for l in lines if l.startswith("  ENERGY CO"))
    assert line == f"  {'ENERGY CO':<32}{'53.33':>10}  {'53.33':>10}*"       # the average, with a * (user, 3 Oct 2026)
    assert "  * not paid last month, average used" in lines


def test_labels_are_the_three_biggest_last_month():
    tx = txns() + [Txn(date(2024, 4, 11), "VIS", "ASDA", "", -5.0), Txn(date(2024, 4, 12), "VIS", "ALDI", "", -60.0),
                   Txn(date(2024, 4, 13), "VIS", "LIDL", "", -30.0)]
    tx.sort(key=lambda t: t.date)
    food = next(s for s in block(tx=tx)["spending"] if s["category"] == "Food shopping")
    assert food["labels"] == ["Aldi", "Tesco Stores", "Lidl"]


def test_unknown_left_over_and_not_enough_cycles():
    no_bal = [Txn(t.date, t.type, t.description, t.detail, t.amount) for t in txns()]
    lines = format_pay_block(block(tx=no_bal))
    assert not any("Left over" in l for l in lines)             # left over is no longer used
    cs = build_cycles([Txn(date(2024, 1, 28), "CR", PAYER, "", 2000.0)], payer=PAYER)
    assert format_pay_block(pay_block(cs, analyse(cs), 2000.0)) == [
        "Not enough finished paydays yet to work out the spare cash."]


def test_the_average_columns_say_how_many_cycles():
    # Real oddity (Oct 2026): the headers said "3-mth avg" on 6 cycles of real data (it was hard-coded)
    p = dict(block(), cycles_used=6)
    lines = format_pay_block(p)
    assert lines[2].endswith("6-mth avg  Last month")
    assert any(l.startswith("LAST MONTH SPENDING") and l.endswith("6-mth avg") for l in lines)
    assert not any("spend like usual" in l for l in lines)      # dropped 3 Oct 2026


def test_each_bill_has_a_diff_last_month_minus_average():
    p = block()
    rent, energy = p["bills"]
    assert (rent["diff"], energy["diff"]) == (pytest.approx(0), pytest.approx(10))      # 95 - 85
    assert energy["key"] and energy["used"] == pytest.approx(95) and energy["estimated"] is False
    assert energy["changed"] is False


def test_a_bill_changed_for_this_cycle_is_used_for_the_spare_cash():
    # 3 Oct 2026: the user knows next month's phone bill (151); changing it here is for this cycle only
    energy_key = next(b["key"] for b in block()["bills"] if b["name"] == "ENERGY CO")
    p = block(changes={energy_key: 151.0})
    energy = next(b for b in p["bills"] if b["name"] == "ENERGY CO")
    assert energy["used"] == pytest.approx(151) and energy["changed"] is True and energy["last"] == pytest.approx(95)
    assert energy["diff"] == pytest.approx(151 - 85)
    assert p["bills_last"] == pytest.approx(651) and p["spare"] == pytest.approx(2500 - 651)
    line = next(l for l in format_pay_block(p) if l.startswith("  ENERGY CO"))
    assert line == f"  {'ENERGY CO':<32}{'85.00':>10}  {'151.00':>10}  (changed)"
    assert block(changes={"NOT A BILL": 5.0})["bills_last"] == pytest.approx(595)       # unknown keys are ignored
