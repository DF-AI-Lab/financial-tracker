from datetime import date

import pytest

from fintrack.common import analyse, payee_key
from fintrack.cycles import build_cycles
from fintrack.models import Cycle, Txn
from tests.synth import PAYER, synth_txns


def cs():
    return build_cycles(synth_txns(), payer=PAYER)


def T(desc, amt, typ="VIS", detail=""):
    return Txn(date(2024, 1, 1), typ, desc, detail, amt)


def test_payee_key():
    assert payee_key(T("CORNER SHOP 12", -5, ")))")) == "CORNER SHOP"
    assert payee_key(T("Tesco Stores 5314", -5, ")))")) == "TESCO STORES"
    assert payee_key(T("BIG SHOP LTD", -5)) == "BIG SHOP"
    assert payee_key(T("INT'L 0093267280", -5, "VIS", "AWS EMEA aws.amazon.co")) == "AWS EMEA AWS.AMAZON.CO"
    assert payee_key(T("GYM CLUB", -50, "DD")) == "GYM CLUB"
    assert payee_key(T("LANDLORD", -550, "SO", "RENT")) == "LANDLORD - RENT"
    assert payee_key(T("E.ON NEXT LTD", -150, "DD", "FIRST PAYMENT")) == "E.ON NEXT"


def test_common_random_and_one_off_on_synthetic_history():
    a = analyse(cs())          # 7 complete cycles, window = the last 6 (cycles 2..7)
    assert a.cycles_used == 6
    assert set(a.common) == {"LANDLORD - RENT", "GYM CLUB", "ENERGY CO", "STREAM VIDEO", "CASH MACHINE"}
    assert a.common["LANDLORD - RENT"]["kind"] == "bill"
    assert a.common["LANDLORD - RENT"]["average"] == pytest.approx(550.0)
    assert a.common["ENERGY CO"]["kind"] == "bill"      # varies more than 15% but it is a bill
    assert a.common["ENERGY CO"]["average"] == pytest.approx(1025 / 6)
    assert a.common["STREAM VIDEO"]["kind"] == "other"
    assert a.common["CASH MACHINE"]["cycles"] == 4      # in 4 of the 6 cycles, always 50
    assert a.common["CASH MACHINE"]["total"] == pytest.approx(200.0)
    assert a.common_per_cycle == pytest.approx(4902.94 / 6)
    assert a.random_per_cycle == pytest.approx(163 / 6)  # corner shop 123 + barber 40
    assert [(t.description, t.amount) for t in a.one_offs] == [("CAR DEALER", -10377.0)]


def test_unfinished_cycle_is_ignored_and_input_not_needed_sorted():
    a = analyse(cs())
    b = analyse([c for c in cs() if c.complete])
    assert a.common_per_cycle == pytest.approx(b.common_per_cycle)
    assert a.random_per_cycle == pytest.approx(b.random_per_cycle)


def test_short_history_needs_every_cycle():
    a = analyse(cs()[:3])      # cycles 1..3: needed = min(4, 3) = 3
    assert a.cycles_used == 3
    assert "LANDLORD - RENT" in a.common and "STREAM VIDEO" in a.common
    assert "BARBER" not in a.common                     # only in 2 of 3 cycles


def test_no_complete_cycles():
    a = analyse([])
    assert a.cycles_used == 0 and a.common == {} and a.common_per_cycle == 0 and a.random_per_cycle == 0
    assert a.one_offs == []
    only_open = [Cycle(date(2024, 1, 28), date(2024, 2, 5), 2400.0, [], False)]
    assert analyse(only_open).cycles_used == 0


def cycles_with(key_amounts):
    out = []
    for k, amt in enumerate(key_amounts, start=1):
        wage = Txn(date(2024, k, 1), "CR", "ACME", "", 2400.0)
        pay = Txn(date(2024, k, 5), "VIS", "GAME SHOP", "", -float(amt))
        out.append(Cycle(date(2024, k, 1), date(2024, k, 28), 2400.0, [wage, pay], True))
    return out


def test_similar_amount_rule_uses_median_and_15_percent():
    assert "GAME SHOP" not in analyse(cycles_with([100, 100, 100, 140, 250, 60])).common   # only 3 similar
    a = analyse(cycles_with([100, 105, 95, 100, 110, 180]))                                 # 5 similar
    assert "GAME SHOP" in a.common
    assert a.common["GAME SHOP"]["total"] == pytest.approx(690.0)   # all payments count once common


def test_big_payment_of_a_common_payer_is_not_a_one_off():
    a = analyse(cycles_with([1000, 1000, 1000, 1000, 1000, 1000]))
    assert "GAME SHOP" in a.common and a.one_offs == []
