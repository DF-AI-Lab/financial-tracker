"""Step 4 of SPEC.md: the six-month picture (fake data only)."""
from datetime import date

import pytest

from fintrack.common import analyse
from fintrack.cycles import build_cycles
from fintrack.models import Txn
from fintrack.picture import format_picture, six_month_picture

PAYER = "ACME MOTORS PLC"


def T(m, d, type_, desc, amount, detail=""):
    return Txn(date(2024, m, d), type_, desc, detail, amount)


def fake_txns():
    """6 wages -> 5 complete cycles. Rent every cycle; energy goes up in the last cycle; the TV licence
    stops in the last cycle; Netflix by card every cycle; a corner shop at random amounts; one big one-off."""
    tx = [T(i, 28, "CR", PAYER, w) for i, w in enumerate([2000, 2000, 2100, 2000, 2000, 2000], 1)]
    shop = [20, 70, 150, 5, 40]
    for i in range(1, 6):
        m = i + 1
        tx += [T(m, 5, "SO", "LANDLORD", -500, "RENT"),
               T(m, 5, "DD", "ENERGY CO", -(95 if i == 5 else 80)),
               T(m, 6, "VIS", "NETFLIX", -10),
               T(m, 7, "VIS", "CORNER SHOP", -shop[i - 1])]
        if i <= 4:
            tx.append(T(m, 5, "DD", "TV LICENCE", -13))
        if i == 3:
            tx.append(T(m, 9, "VIS", "BIG TV STORE", -1200))
    tx.sort(key=lambda t: t.date)
    return tx


def cycles():
    return build_cycles(fake_txns(), payer=PAYER)


# ---- analyse() now knows each common item's last-cycle amount and payment type -------------------

def test_common_items_have_last_and_type():
    a = analyse(cycles())
    assert a.common["LANDLORD - RENT"]["last"] == pytest.approx(500)
    assert a.common["LANDLORD - RENT"]["type"] == "SO"
    assert a.common["ENERGY CO"]["last"] == pytest.approx(95)          # went up in the last cycle
    assert a.common["ENERGY CO"]["type"] == "DD"
    assert a.common["TV LICENCE"]["last"] == 0                         # not paid in the last cycle
    assert a.common["NETFLIX"]["last"] == pytest.approx(10)
    assert a.common["NETFLIX"]["type"] == "VIS"
    # nothing else changed
    assert a.common["ENERGY CO"]["average"] == pytest.approx(83.0)
    assert a.common_per_cycle == pytest.approx(603.4) and a.random_per_cycle == pytest.approx(57.0)


def test_last_adds_up_when_answers_merge_items():
    answers = {"DD|ENERGY CO|": {"kind": "common", "label": "Gas & TV", "source": "user"},
               "DD|TV LICENCE|": {"kind": "common", "label": "Gas & TV", "source": "user"}}
    a = analyse(cycles(), answers=answers)
    assert a.common["Gas & TV"]["last"] == pytest.approx(95)
    assert a.common["Gas & TV"]["average"] == pytest.approx((415 + 52) / 5)
    assert a.common["Gas & TV"]["type"] == "DD"


# ---- The picture ------------------------------------------------------------------------------

def test_picture_numbers():
    cy = cycles()
    p = six_month_picture(cy, analyse(cy))
    assert p["cycles_used"] == 5
    assert p["wage_avg"] == pytest.approx(2020.0)          # wage only, last complete cycles
    assert p["bills_avg"] == pytest.approx(603.4)           # all common items (DECISIONS: bills = DD + SO + common)
    assert p["normal_avg"] == pytest.approx(57.0)           # random spending, no one-offs
    assert p["oneoffs_total"] == pytest.approx(1200.0)
    assert p["unsorted_avg"] == pytest.approx(57.0)         # only the corner shop has no category (one-off left out)


def test_picture_lists():
    cy = cycles()
    p = six_month_picture(cy, analyse(cy))
    assert [r["name"] for r in p["bills"]] == ["LANDLORD - RENT", "ENERGY CO", "TV LICENCE"]     # biggest avg first
    energy = p["bills"][1]
    assert energy == {"name": "ENERGY CO", "type": "DD", "avg": pytest.approx(83.0),
                      "last": pytest.approx(95.0), "stopped": False}
    tv = p["bills"][2]
    assert tv["last"] is None and tv["stopped"] is True
    assert [r["name"] for r in p["other_regular"]] == ["NETFLIX"]


def test_saved_category_counts_for_unsorted():
    cy = cycles()
    p = six_month_picture(cy, analyse(cy), categories={"CARD|CORNER SHOP|": "Food shopping"})
    assert p["unsorted_avg"] == pytest.approx(0.0)


def test_format_picture():
    cy = cycles()
    lines = format_picture(six_month_picture(cy, analyse(cy)))
    text = "\n".join(lines)
    assert "SIX-MONTH PICTURE" in text and "based on 5 cycles" in text
    for money in ("2,020.00", "603.40", "57.00", "1,200.00"):
        assert money in text
    energy = next(l for l in lines if "ENERGY CO" in l)
    assert "83.00" in energy and "95.00" in energy and "DD" in energy
    tv = next(l for l in lines if "TV LICENCE" in l)
    assert "STOPPED?" in tv
    assert text.index("OTHER REGULAR") < text.index("NETFLIX")
    assert text.index("BILLS") < text.index("TV LICENCE") < text.index("OTHER REGULAR")
    text.encode("ascii")                                      # plain text for the Windows terminal


def test_one_cycle_and_none():
    tx = [T(1, 28, "CR", PAYER, 2000), T(2, 5, "SO", "LANDLORD", -500, "RENT"), T(2, 28, "CR", PAYER, 2000)]
    cy = build_cycles(tx, payer=PAYER)
    assert "based on 1 cycle)" in "\n".join(format_picture(six_month_picture(cy, analyse(cy))))
    none = build_cycles([T(1, 28, "CR", PAYER, 2000)], payer=PAYER)
    assert format_picture(six_month_picture(none, analyse(none))) == [
        "SIX-MONTH PICTURE: not enough finished paydays yet."]
