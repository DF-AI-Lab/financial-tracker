"""DD / SO are bills by default (user, 3 Oct 2026): a direct debit or standing order paid in 2+ months is saved as
Common (a bill) without a question; one paid only once is still asked. Saved answers are never changed. Fake data."""
from datetime import date

from fintrack.models import Txn
from fintrack.questions import auto_bills, review
from fintrack.store import open_db, get_items, set_item


def T(m, typ, desc, amt, detail=""):
    return Txn(date(2024, m, 3), typ, desc, detail, -amt)


def txns():
    return [T(1, "DD", "ENERGY CO", 80), T(2, "DD", "ENERGY CO", 95), T(3, "DD", "ENERGY CO", 90),
            T(1, "SO", "SAM PARKER", 550, "RENT"), T(2, "SO", "SAM PARKER", 550, "RENT"),
            T(2, "DD", "NEW GYM", 30),                                     # only once: still asked
            T(1, "VIS", "CORNER SHOP", 12), T(2, "VIS", "CORNER SHOP", 9)]  # card: still asked


def test_dd_and_so_paid_in_two_months_are_saved_as_bills(tmp_path):
    conn = open_db(tmp_path / "t.db")
    set_item(conn, "DD|OLD PHONE|", "random", "Old phone", "user")       # an answer of the user's stays
    n = auto_bills(conn, txns())
    items = get_items(conn)
    auto = {k: v for k, v in items.items() if v["source"] == "auto"}
    assert n == 2 and sorted(auto) == ["DD|ENERGY CO|", "SO|SAM PARKER|RENT"]
    assert all(v["kind"] == "common" for v in auto.values())
    assert items["SO|SAM PARKER|RENT"]["label"] == "Rent"
    assert items["DD|OLD PHONE|"]["kind"] == "random"
    assert auto_bills(conn, txns()) == 0                                 # nothing new the second time


def test_the_question_list_only_asks_about_the_rest(tmp_path):
    conn = open_db(tmp_path / "t.db")
    lines = []
    review(conn, txns(), ask=lambda p: "stop", out=lines.append)
    shown = [l for l in lines if l.startswith("  ") and "suggest:" in l]
    assert len(shown) == 2 and any("NEW GYM" in l for l in shown) and any("CORNER SHOP" in l for l in shown)
    assert any("2 direct debits / standing orders saved as bills" in l for l in lines)
