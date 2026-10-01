"""Step 3 of SPEC.md: yearly bills (fake data only)."""
from datetime import date

from fintrack.common import analyse
from fintrack.cycles import build_cycles
from fintrack.models import Txn
from fintrack.questions import KIND_NAMES, parse_answer
from fintrack.store import get_items, open_db, set_item
from fintrack.yearly import yearly_due, yearly_lines
from tests.synth import PAYER, synth_txns


def T(d, desc, amount, type_="DD", detail=""):
    return Txn(d, type_, desc, detail, amount)


# ---- Answering "yearly" ----------------------------------------------------------------------

def test_yearly_is_a_kind():
    conn = open_db(":memory:")
    set_item(conn, "DD|AVIVA|", "yearly", "Car insurance")
    assert get_items(conn)["DD|AVIVA|"]["kind"] == "yearly"
    assert KIND_NAMES["yearly"] == "Yearly"


def test_parse_yearly():
    r = parse_answer("yearly 3  oneoff 4", 10)
    assert r["error"] is None and r["kinds"] == {3: "yearly", 4: "oneoff"}
    r = parse_answer("label 2 Car insurance yearly 2", 10)
    assert r["labels"] == {2: "Car insurance"} and r["kinds"] == {2: "yearly"}
    assert parse_answer("yearly", 10)["error"]


# ---- Left out of the averages, like a one-off ----------------------------------------------------

def test_yearly_is_left_out_like_a_one_off():
    txns = synth_txns()
    cycles = build_cycles(txns, payer=PAYER)
    as_oneoff = analyse(cycles, answers={"CARD|BARBER|": {"kind": "oneoff", "label": "Barber", "source": "user"}})
    as_yearly = analyse(cycles, answers={"CARD|BARBER|": {"kind": "yearly", "label": "Barber", "source": "user"}})
    assert as_yearly.one_offs == as_oneoff.one_offs and as_yearly.one_offs
    assert as_yearly.common_per_cycle == as_oneoff.common_per_cycle
    assert as_yearly.random_per_cycle == as_oneoff.random_per_cycle


# ---- When is one due? ---------------------------------------------------------------------------

ITEMS = {"DD|AVIVA|": {"kind": "yearly", "label": "Car insurance", "source": "user"},
         "DD|TV LICENCE|": {"kind": "yearly", "label": "", "source": "user"},
         "DD|GYM|": {"kind": "common", "label": "Gym", "source": "user"}}

TXNS = [
    T(date(2023, 10, 3), "AVIVA", -170.00),
    T(date(2024, 10, 15), "AVIVA", -180.00),        # the latest AVIVA payment counts
    T(date(2025, 3, 1), "TV LICENCE", -169.50),
    T(date(2024, 10, 1), "GYM", -30.00),             # not yearly: never warned about
]


def test_not_due_before_11_months():
    assert yearly_due(TXNS, ITEMS, today=date(2025, 8, 31)) == []


def test_due_from_11_months():
    due = yearly_due(TXNS, ITEMS, today=date(2025, 9, 1))
    assert due == [{"key": "DD|AVIVA|", "label": "Car insurance", "amount": 180.00, "paid": date(2024, 10, 15)}]


def test_several_due_sorted_by_date_and_name_used_when_no_label():
    due = yearly_due(TXNS, ITEMS, today=date(2026, 2, 1))
    assert [d["key"] for d in due] == ["DD|TV LICENCE|"]            # AVIVA is now 15 months: stopped warning
    assert due[0]["label"] == "TV LICENCE"
    due = yearly_due(TXNS, ITEMS, today=date(2025, 11, 20))
    assert [d["key"] for d in due] == ["DD|AVIVA|"]                   # 13 months: still warned; TV LICENCE only 8


def test_warning_window_is_11_to_13_months():
    # months counted by calendar month: Oct 2024 -> Sep 2025 = 11, Nov 2025 = 13, Dec 2025 = 14
    assert yearly_due(TXNS, ITEMS, today=date(2025, 11, 30))[0]["key"] == "DD|AVIVA|"
    assert yearly_due(TXNS, ITEMS, today=date(2025, 12, 1)) == []


def test_lines_are_plain_text():
    due = yearly_due(TXNS, ITEMS, today=date(2025, 9, 1))
    assert yearly_lines(due) == ["WARNING Possible yearly bill: Car insurance 180.00, paid Oct 2024"]
    assert yearly_lines([]) == []
