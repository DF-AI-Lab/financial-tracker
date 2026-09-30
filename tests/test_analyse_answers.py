import pytest

from fintrack.common import analyse
from fintrack.cycles import build_cycles
from tests.synth import PAYER, synth_txns


def cs():
    return build_cycles(synth_txns(), payer=PAYER)


def ans(kind, label=""):
    return {"kind": kind, "label": label, "source": "user"}


def test_no_answers_changes_nothing():
    base = analyse(cs())
    for a in (None, {}):
        x = analyse(cs(), answers=a)
        assert x.common == base.common and x.common_per_cycle == base.common_per_cycle
        assert x.random_per_cycle == base.random_per_cycle and x.one_offs == base.one_offs


def test_user_can_make_a_bill_random():
    a = analyse(cs(), answers={"DD|GYM CLUB|": ans("random")})
    assert "GYM CLUB" not in a.common
    assert a.common_per_cycle == pytest.approx(4902.94 / 6 - 50)
    assert a.random_per_cycle == pytest.approx(163 / 6 + 50)


def test_user_can_make_varying_spending_common():
    a = analyse(cs(), answers={"CARD|CORNER SHOP|": ans("common")})
    assert a.common["CARD|CORNER SHOP|"]["total"] == pytest.approx(123.0)
    assert a.common["CARD|CORNER SHOP|"]["average"] == pytest.approx(20.5)
    assert a.common["CARD|CORNER SHOP|"]["kind"] == "other"
    assert a.common_per_cycle == pytest.approx(4902.94 / 6 + 20.5)
    assert a.random_per_cycle == pytest.approx(40 / 6)          # only the barber is left


def test_regular_counts_like_common():
    a = analyse(cs(), answers={"CARD|CORNER SHOP|": ans("regular")})
    assert "CARD|CORNER SHOP|" in a.common


def test_user_can_say_the_big_one_is_not_a_one_off():
    a = analyse(cs(), answers={"CARD|CAR DEALER|": ans("random")})
    assert a.one_offs == []
    assert a.random_per_cycle == pytest.approx((163 + 10377) / 6)


def test_user_can_make_something_small_a_one_off():
    a = analyse(cs(), answers={"CARD|BARBER|": ans("oneoff")})
    assert [(t.description, t.date.isoformat()) for t in a.one_offs] == [
        ("BARBER", "2024-04-10"), ("CAR DEALER", "2024-05-15"), ("BARBER", "2024-06-10")]
    assert a.random_per_cycle == pytest.approx(123 / 6)


def test_same_label_merges_items():
    a = analyse(cs(), answers={"CARD|STREAM VIDEO|": ans("common", "Media"),
                               "CARD|CORNER SHOP|": ans("common", "Media")})
    assert set(a.common) == {"LANDLORD - RENT", "GYM CLUB", "ENERGY CO", "CASH MACHINE", "Media"}
    m = a.common["Media"]
    assert m["total"] == pytest.approx(77.94 + 123.0) and m["cycles"] == 6 and m["kind"] == "other"


def test_label_on_a_bill_makes_it_kind_bill_and_renames_it():
    a = analyse(cs(), answers={"SO|LANDLORD|RENT": ans("regular", "Rent"), "DD|GYM CLUB|": ans("regular", "Rent")})
    assert "LANDLORD - RENT" not in a.common and "GYM CLUB" not in a.common
    assert a.common["Rent"]["kind"] == "bill"
    assert a.common["Rent"]["total"] == pytest.approx(3300 + 300)


def test_answers_for_items_outside_the_window_do_nothing():
    a = analyse(cs(), answers={"CARD|EARLY SHOP|": ans("oneoff"), "DD|NOBODY|": ans("common")})
    b = analyse(cs())
    assert a.one_offs == b.one_offs and a.common_per_cycle == pytest.approx(b.common_per_cycle)
