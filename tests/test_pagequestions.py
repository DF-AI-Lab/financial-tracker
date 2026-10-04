"""No. 6c (user, 3 Oct 2026): the last terminal questions on the home page: 'Same bill?', 'Is this your rent?'
and typed spends not found in the statements. Same rules and answers as run.py. Fake data only."""
from datetime import date

import pytest

from fintrack.pagequestions import questions, answer
from fintrack.store import (add_spend, get_items, get_rules, get_same_bills, get_spends, open_db)
from tests.rentdata import PAYER, all_txns, paydays
from tests.test_samebill import saved_conn, txns_chloe_katie


def test_same_bill_question_and_answers():
    conn = saved_conn()
    q = [x for x in questions(conn, txns_chloe_katie(), []) if x["type"] == "same"]
    assert len(q) == 2
    car = next(x for x in q if "CAR" in x["big"])
    assert car["big_label"] == "Car loan" and car["small_label"] == "Chloe extra"
    answer(conn, {"type": "same", "big": car["big"], "small": car["small"], "yes": True}, txns_chloe_katie(), [])
    assert get_items(conn)[car["small"]]["label"] == "Car loan"                    # joined to the big one
    other = next(x for x in q if x is not car)
    answer(conn, {"type": "same", "big": other["big"], "small": other["small"], "yes": False}, txns_chloe_katie(), [])
    assert get_same_bills(conn)[frozenset({other["big"], other["small"]})] is False
    assert [x for x in questions(conn, txns_chloe_katie(), []) if x["type"] == "same"] == []


def test_rent_question_and_answers():
    conn = open_db(":memory:")
    q = [x for x in questions(conn, all_txns(), paydays()) if x["type"] == "rent"]
    assert len(q) == 1 and q[0]["payer"] == PAYER and q[0]["label"] == "Rent" and len(q[0]["examples"]) == 4
    answer(conn, {"type": "rent", "payer": PAYER, "usual": q[0]["usual"], "yes": True, "label": "My rent"},
           all_txns(), paydays())
    rules = get_rules(conn)
    assert len(rules) == 1 and rules[0]["label"] == "My rent" and rules[0]["kind"] == "common"
    assert [x for x in questions(conn, all_txns(), paydays()) if x["type"] == "rent"] == []
    conn2 = open_db(":memory:")
    answer(conn2, {"type": "rent", "payer": PAYER, "usual": q[0]["usual"], "yes": False}, all_txns(), paydays())
    assert get_rules(conn2)[0]["kind"] == "declined"


def test_typed_spends_matched_or_asked():
    from fintrack.models import Txn
    conn = open_db(":memory:")
    txns = [Txn(date(2024, 5, 3), "VIS", "COSTA", "", -12.5), Txn(date(2024, 5, 20), "VIS", "SHOP", "", -1.0)]
    add_spend(conn, date(2024, 5, 2), 12.5, "Costa", None)                       # in the statement: matched
    add_spend(conn, date(2024, 5, 4), 30.0, "Market", None)                      # not in it: asked
    add_spend(conn, date(2024, 5, 25), 8.0, "Later", None)                       # after the statement: not asked
    q = [x for x in questions(conn, txns, []) if x["type"] == "spend"]
    assert [s["name"] for s in get_spends(conn)] == ["Market", "Later"]          # the matched one is removed
    assert [x["name"] for x in q] == ["Market"]
    answer(conn, {"type": "spend", "id": q[0]["id"], "keep": True}, txns, [])
    assert [x for x in questions(conn, txns, []) if x["type"] == "spend"] == []   # kept: not asked again
    assert [s["name"] for s in get_spends(conn)] == ["Market", "Later"]
    add_spend(conn, date(2024, 5, 5), 9.0, "Chips", None)
    q = [x for x in questions(conn, txns, []) if x["type"] == "spend"]
    answer(conn, {"type": "spend", "id": q[0]["id"], "keep": False}, txns, [])
    assert [s["name"] for s in get_spends(conn)] == ["Market", "Later"]


def test_bad_answers_change_nothing():
    conn = saved_conn()
    before = get_items(conn)
    for a in ({"type": "nope"}, {"type": "same", "big": "X", "small": "Y", "yes": True},
              {"type": "rent", "payer": "", "usual": "x", "yes": True}, {"type": "spend", "id": "x"}):
        answer(conn, a, txns_chloe_katie(), [])
    assert get_items(conn) == before and get_rules(conn) == []
