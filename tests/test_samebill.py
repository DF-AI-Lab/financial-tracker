"""Step 1 of SPEC.md: same bill, different name (fake data only)."""
import sqlite3
from datetime import date

from fintrack.models import Txn
from fintrack.questions import item_stats
from fintrack.samebill import ask_same_bills, similar_pairs
from fintrack.store import get_items, get_same_bills, item_key, open_db, set_item, set_same_bill


def T(type_, desc, detail="", amount=-10.0, day=date(2024, 8, 1)):
    return Txn(day, type_, desc, detail, amount)


# ---- Direct Debits ignore the reference -------------------------------------------------------

def test_dd_reference_is_ignored():
    assert item_key(T("DD", "E.ON NEXT LTD", "ACCOUNT 12345")) == "DD|E.ON NEXT|"
    assert item_key(T("DD", "E.ON NEXT LTD", "FIRST PAYMENT")) == "DD|E.ON NEXT|"
    assert item_key(T("DD", "E.ON NEXT LTD")) == "DD|E.ON NEXT|"


def test_so_and_bp_keep_the_reference():
    assert item_key(T("SO", "KATIE FINCH", "RENT")) == "SO|KATIE FINCH|RENT"
    assert item_key(T("SO", "KATIE FINCH", "BILLS")) == "SO|KATIE FINCH|BILLS"
    assert item_key(T("BP", "KATIE FINCH", "Food and bil")) == "BP|KATIE FINCH|FOOD AND BIL"


# ---- Saved answers move to the new DD key ------------------------------------------------------

def _old_db(path, rows):
    conn = open_db(path)
    for key, kind, label in rows:
        conn.execute("INSERT INTO items (key, kind, label, source) VALUES (?, ?, ?, 'user')", (key, kind, label))
    conn.commit()
    conn.close()


def test_saved_dd_answer_moves_to_new_key(tmp_path):
    db = tmp_path / "t.db"
    _old_db(db, [("DD|E.ON NEXT|ACCOUNT 1", "common", "Gas & Electric"),
                 ("SO|KATIE FINCH|RENT", "common", "Rent")])
    items = get_items(open_db(db))
    assert items["DD|E.ON NEXT|"]["label"] == "Gas & Electric"
    assert items["DD|E.ON NEXT|"]["kind"] == "common"
    assert "DD|E.ON NEXT|ACCOUNT 1" not in items
    assert items["SO|KATIE FINCH|RENT"]["label"] == "Rent"          # SO untouched


def test_existing_new_key_wins(tmp_path):
    db = tmp_path / "t.db"
    _old_db(db, [("DD|E.ON NEXT|", "common", "Energy"),
                 ("DD|E.ON NEXT|ACCOUNT 1", "random", "Old")])
    items = get_items(open_db(db))
    assert items["DD|E.ON NEXT|"]["label"] == "Energy"
    assert "DD|E.ON NEXT|ACCOUNT 1" not in items


def test_reopening_is_safe(tmp_path):
    db = tmp_path / "t.db"
    _old_db(db, [("DD|GYM|REF", "common", "Gym")])
    open_db(db).close()
    assert get_items(open_db(db))["DD|GYM|"]["label"] == "Gym"


# ---- Same-bill answers are stored ---------------------------------------------------------------

def test_same_bill_answers_saved():
    conn = open_db(":memory:")
    set_same_bill(conn, "SO|A|CAR LOAN PAYMENT", "BP|A|CAR PAYMENT OWED", True)
    set_same_bill(conn, "SO|A|X Y", "SO|A|X Z", False)
    ans = get_same_bills(conn)
    # order of the two keys does not matter
    assert ans[frozenset({"BP|A|CAR PAYMENT OWED", "SO|A|CAR LOAN PAYMENT"})] is True
    assert ans[frozenset({"SO|A|X Z", "SO|A|X Y"})] is False
    set_same_bill(conn, "SO|A|X Z", "SO|A|X Y", True)               # changing an answer
    assert get_same_bills(conn)[frozenset({"SO|A|X Z", "SO|A|X Y"})] is True


# ---- Which pairs look similar ---------------------------------------------------------------

def txns_chloe_katie():
    return [
        T("SO", "CHLOE AMBER FINCH", "CAR LOAN PAYMENT", -250.0, date(2024, 4, 5)),
        T("SO", "CHLOE AMBER FINCH", "CAR LOAN PAYMENT", -250.0, date(2024, 5, 5)),
        T("BP", "CHLOE AMBER FINCH", "CAR PAYMENT OWED", -100.0, date(2024, 6, 5)),
        T("SO", "KATIE FINCH", "RENT", -550.0),
        T("SO", "KATIE FINCH", "BILLS", -150.0),
        T("SO", "KATIE FINCH", "FOOD", -200.0),
        T("BP", "KATIE FINCH", "Food and bil", -50.0),
        T("DD", "E.ON NEXT LTD", "X", -116.0),
        T("VIS", "TESCO STORES 123", "", -40.0),
    ]


def test_similar_pairs():
    pairs = similar_pairs(item_stats(txns_chloe_katie()))
    # bigger total first in each pair; pairs ordered by combined total, biggest first
    assert pairs == [
        ("SO|CHLOE AMBER FINCH|CAR LOAN PAYMENT", "BP|CHLOE AMBER FINCH|CAR PAYMENT OWED"),   # share CAR
        ("SO|KATIE FINCH|FOOD", "BP|KATIE FINCH|FOOD AND BIL"),                             # share FOOD
    ]
    # RENT / BILLS / FOOD share no word -> never asked; PAYMENT, AND, THE, FOR never count as shared


def test_filler_words_do_not_count():
    t = [T("SO", "SAM", "RENT PAYMENT"), T("SO", "SAM", "LOAN PAYMENT")]
    assert similar_pairs(item_stats(t)) == []


def test_different_payees_never_pair():
    t = [T("SO", "SAM", "CAR LOAN"), T("SO", "JO", "CAR LOAN")]
    assert similar_pairs(item_stats(t)) == []


# ---- Asking --------------------------------------------------------------------------------------

def saved_conn():
    conn = open_db(":memory:")
    set_item(conn, "SO|CHLOE AMBER FINCH|CAR LOAN PAYMENT", "common", "Car loan")
    set_item(conn, "BP|CHLOE AMBER FINCH|CAR PAYMENT OWED", "random", "Chloe extra")
    set_item(conn, "SO|KATIE FINCH|FOOD", "common", "Food Katie")
    set_item(conn, "BP|KATIE FINCH|FOOD AND BIL", "random", "Katie top-ups")
    return conn


def answers(*replies):
    it = iter(replies)
    asked = []

    def ask(prompt):
        asked.append(prompt)
        return next(it)
    return ask, asked


def test_yes_merges_by_copying_label_and_kind():
    conn = saved_conn()
    ask, asked = answers("y", "n")
    n = ask_same_bills(conn, txns_chloe_katie(), ask, out=lambda *a: None)
    assert n == 2
    assert "Same bill?" in asked[0] and "CAR LOAN PAYMENT" in asked[0] and "CAR PAYMENT OWED" in asked[0]
    items = get_items(conn)
    owed = items["BP|CHLOE AMBER FINCH|CAR PAYMENT OWED"]
    assert (owed["kind"], owed["label"], owed["source"]) == ("common", "Car loan", "same")
    assert items["BP|KATIE FINCH|FOOD AND BIL"]["label"] == "Katie top-ups"     # "n" changes nothing
    same = get_same_bills(conn)
    assert same[frozenset({"SO|CHLOE AMBER FINCH|CAR LOAN PAYMENT", "BP|CHLOE AMBER FINCH|CAR PAYMENT OWED"})] is True
    assert same[frozenset({"SO|KATIE FINCH|FOOD", "BP|KATIE FINCH|FOOD AND BIL"})] is False


def test_never_asked_twice():
    conn = saved_conn()
    ask, _ = answers("y", "n")
    ask_same_bills(conn, txns_chloe_katie(), ask, out=lambda *a: None)
    ask2, asked2 = answers()
    assert ask_same_bills(conn, txns_chloe_katie(), ask2, out=lambda *a: None) == 0
    assert asked2 == []


def test_later_and_stop_save_nothing():
    conn = saved_conn()
    ask, asked = answers("later", "stop")
    assert ask_same_bills(conn, txns_chloe_katie(), ask, out=lambda *a: None) == 0
    assert len(asked) == 2
    assert get_same_bills(conn) == {}
    ask2, asked2 = answers("n", "n")                                     # asked again next run
    assert ask_same_bills(conn, txns_chloe_katie(), ask2, out=lambda *a: None) == 2


def test_enter_means_no_and_is_remembered():
    conn = saved_conn()
    ask, _ = answers("", "")
    assert ask_same_bills(conn, txns_chloe_katie(), ask, out=lambda *a: None) == 2
    assert set(get_same_bills(conn).values()) == {False}
    assert get_items(conn)["BP|CHLOE AMBER FINCH|CAR PAYMENT OWED"]["label"] == "Chloe extra"


def test_only_pairs_where_both_are_saved_and_labels_differ():
    conn = open_db(":memory:")
    set_item(conn, "SO|CHLOE AMBER FINCH|CAR LOAN PAYMENT", "common", "Car loan")    # other one not saved
    set_item(conn, "SO|KATIE FINCH|FOOD", "common", "Food")
    set_item(conn, "BP|KATIE FINCH|FOOD AND BIL", "random", "food")                  # same label already
    ask, asked = answers()
    assert ask_same_bills(conn, txns_chloe_katie(), ask, out=lambda *a: None) == 0
    assert asked == []
