from datetime import timedelta

import pytest

from fintrack.common import analyse
from fintrack.models import Txn
from tests.rentdata import PAYER, RULE, bp, cycles, payday

# window = all 6 cycles. Rule (550, 2 days, 10%) covers k1 550, k2 550 (reference FOOD), k3 550, k4 590.
# Not covered: k5 550 (5 days late) and k6 650 (18% over), plus the six small top-ups (185).


def test_rule_makes_the_transfers_common_whatever_the_reference():
    a = analyse(cycles(), rules=[RULE])
    assert set(a.common) == {"Rent"}
    rent = a.common["Rent"]
    assert rent["total"] == pytest.approx(2240.0) and rent["cycles"] == 4 and rent["kind"] == "other"
    assert rent["average"] == pytest.approx(2240 / 6)
    assert a.common_per_cycle == pytest.approx(2240 / 6)
    assert a.random_per_cycle == pytest.approx((185 + 550 + 650) / 6)    # top-ups + the late one + the big one
    assert a.one_offs == []


def test_a_rule_beats_an_item_answer():
    answers = {"BP|SAM PARKER|FOOD": {"kind": "random", "label": "", "source": "user"}}
    a = analyse(cycles(), answers=answers, rules=[RULE])
    assert a.common["Rent"]["total"] == pytest.approx(2240.0)            # the FOOD-reference payment is still rent


def test_declined_rule_and_other_payer_do_nothing():
    assert "Rent" not in analyse(cycles(), rules=[dict(RULE, kind="declined")]).common
    assert "Rent" not in analyse(cycles(), rules=[dict(RULE, payer="SOMEONE ELSE")]).common
    assert "Rent" not in analyse(cycles(), rules=[]).common and "Rent" not in analyse(cycles(), rules=None).common


def test_rule_label_merges_with_an_item_answer_of_the_same_label():
    extra = {5: [Txn(payday(5) + timedelta(days=2), "SO", "LANDLORD", "RENT", -550.0)],
             6: [Txn(payday(6) + timedelta(days=2), "SO", "LANDLORD", "RENT", -550.0)]}
    answers = {"SO|LANDLORD|RENT": {"kind": "common", "label": "Rent", "source": "user"}}
    a = analyse(cycles(extra), answers=answers, rules=[RULE])
    rent = a.common["Rent"]
    assert rent["total"] == pytest.approx(2240 + 1100) and rent["cycles"] == 6 and rent["kind"] == "bill"


def test_a_covered_payment_is_never_a_one_off():
    big = {1: [bp(payday(1) + timedelta(days=1), "RENT", 1200)]}
    rule = dict(RULE, usual=1200.0)
    a = analyse(cycles(big), rules=[rule])
    assert a.one_offs == [] and a.common["Rent"]["total"] == pytest.approx(1200.0)
    assert [t.amount for t in analyse(cycles(big)).one_offs] == [-1200.0]      # without the rule it is a one-off


def test_empty_label_falls_back_to_the_payer():
    a = analyse(cycles(), rules=[dict(RULE, label="")])
    assert PAYER in a.common and a.common[PAYER]["total"] == pytest.approx(2240.0)
