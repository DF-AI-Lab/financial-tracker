"""Step 8 of SPEC.md: typed spends as you go, and "left now". Fake data only."""
import shutil
from datetime import date

import pytest

import run
from fintrack.models import Txn
from fintrack.store import add_spend, delete_spend, get_spends, get_value, open_db, set_value
from fintrack.typed import format_spends, match_spends, parse_add, swap_spends
from tests.conftest import DATA

ACME = "ACME MOTORS PLC"


# ---- store --------------------------------------------------------------------------------------

def test_spends_are_saved_in_date_order_and_can_be_removed():
    conn = open_db(":memory:")
    add_spend(conn, date(2024, 10, 5), 150.0, "Argos TV", "Shopping")
    add_spend(conn, date(2024, 10, 3), 40.0, "Cash", "Cash")
    got = get_spends(conn)
    assert [(s["date"], s["amount"], s["name"], s["category"]) for s in got] == [
        (date(2024, 10, 3), 40.0, "Cash", "Cash"), (date(2024, 10, 5), 150.0, "Argos TV", "Shopping")]
    delete_spend(conn, got[0]["id"])
    assert [s["name"] for s in get_spends(conn)] == ["Argos TV"]


def test_values_are_remembered():
    conn = open_db(":memory:")
    assert get_value(conn, "pay") is None
    set_value(conn, "pay", "2677")
    set_value(conn, "pay", "2700")
    assert get_value(conn, "pay") == "2700"


# ---- typing one in ------------------------------------------------------------------------------

def test_parse_add():
    assert parse_add(["150", "Argos", "TV"]) == (150.0, "Argos TV")
    assert parse_add(["£12.50", "Costa"]) == (12.5, "Costa")
    assert parse_add(["1,200", "Sofa"]) == (1200.0, "Sofa")
    assert parse_add(["150"]) is None                      # no name
    assert parse_add(["abc", "Costa"]) is None             # not money
    assert parse_add([]) is None


# ---- when the statement arrives ------------------------------------------------------------------

def spend(i, d, amount, name="X"):
    return {"id": i, "date": d, "amount": amount, "name": name, "category": "Unsorted"}


def test_match_spends_same_amount_within_a_few_days():
    txns = [Txn(date(2024, 10, 4), "VIS", "ARGOS", "", -150.0),
            Txn(date(2024, 10, 4), "VIS", "COSTA", "", -12.5),
            Txn(date(2024, 10, 20), "VIS", "COSTA", "", -12.5),
            Txn(date(2024, 10, 9), "CR", "REFUND", "", 40.0)]
    spends = [spend(1, date(2024, 10, 3), 150.0),            # paid 1 day later -> matched
              spend(2, date(2024, 10, 3), 12.5),             # matched to the 4 Oct Costa
              spend(3, date(2024, 10, 3), 12.5),             # the other Costa is 17 days later -> no
              spend(4, date(2024, 10, 9), 40.0),             # money in never matches a spend
              spend(5, date(2024, 10, 5), 150.0)]            # the Argos payment is already used
    matched, unmatched = match_spends(spends, txns)
    assert sorted(matched) == [1, 2]
    assert [s["id"] for s in unmatched] == [3, 4, 5]


def test_match_window_is_one_day_before_to_five_days_after():
    t = lambda d: [Txn(d, "VIS", "SHOP", "", -10.0)]
    s = [spend(1, date(2024, 10, 10), 10.0)]
    assert match_spends(s, t(date(2024, 10, 9)))[0] == [1]
    assert match_spends(s, t(date(2024, 10, 15)))[0] == [1]
    assert match_spends(s, t(date(2024, 10, 8)))[0] == []
    assert match_spends(s, t(date(2024, 10, 16)))[0] == []


def test_swap_removes_matches_and_asks_about_the_rest():
    conn = open_db(":memory:")
    add_spend(conn, date(2024, 10, 3), 150.0, "Argos TV", "Shopping")     # in the statement
    add_spend(conn, date(2024, 10, 4), 9.99, "Mystery", "Unsorted")       # not found -> asked, answer n
    add_spend(conn, date(2024, 10, 5), 5.0, "Keep me", "Unsorted")        # not found -> asked, Enter keeps
    add_spend(conn, date(2024, 11, 1), 20.0, "Too new", "Unsorted")       # after the statements -> not asked
    txns = [Txn(date(2024, 10, 4), "VIS", "ARGOS", "", -150.0), Txn(date(2024, 10, 21), "VIS", "SHOP", "", -1.0)]
    prompts, out = [], []
    answers = iter(["n", ""])

    def ask(p):
        prompts.append(p)
        return next(answers)

    assert swap_spends(conn, txns, ask, out=out.append) == 1
    assert [s["name"] for s in get_spends(conn)] == ["Keep me", "Too new"]
    assert prompts == ["Typed spend 9.99 Mystery (04 Oct 2024) is not in your statements. Keep it? y/n (Enter = keep) ",
                       "Typed spend 5.00 Keep me (05 Oct 2024) is not in your statements. Keep it? y/n (Enter = keep) "]
    assert out == ["Matched 1 typed spend to your statements (removed from the typed list)."]


def test_swap_keeps_everything_when_there_is_no_keyboard():
    conn = open_db(":memory:")
    add_spend(conn, date(2024, 10, 4), 9.99, "Mystery", "Unsorted")

    def ask(p):
        raise EOFError

    assert swap_spends(conn, [Txn(date(2024, 10, 21), "VIS", "SHOP", "", -1.0)], ask, out=lambda s: None) == 0
    assert len(get_spends(conn)) == 1


# ---- what is printed ----------------------------------------------------------------------------

def test_format_spends():
    spends = [spend(1, date(2024, 10, 3), 40.0, "Cash"), spend(2, date(2024, 10, 4), 25.0, "Takeaway"),
              dict(spend(3, date(2024, 10, 5), 150.0, "Argos TV"), category="Shopping")]
    assert format_spends(spends, 1450.0) == [
        "SO FAR THIS CYCLE (typed in)",
        f"   1  03 Oct  {'Cash':<22}{'40.00':>10}   (Unsorted)",
        f"   2  04 Oct  {'Takeaway':<22}{'25.00':>10}   (Unsorted)",
        f"   3  05 Oct  {'Argos TV':<22}{'150.00':>10}   (Shopping)",
        f"  {'Typed so far':<34}{'215.00':>10}",
        "",
        f"  {'Money for spending':<34}{'1,450.00':>10}   (left over + wage - bills)",
        f"  {'Left now':<34}{'1,235.00':>10}",
        "  Add one: run.py add 12.50 Costa    Remove one: run.py remove 1",
    ]


def test_format_spends_when_nothing_is_typed():
    assert format_spends([], 1450.0) == [
        "SO FAR THIS CYCLE (typed in)",
        "  (nothing typed yet)",
        f"  {'Typed so far':<34}{'0.00':>10}",
        "",
        f"  {'Money for spending':<34}{'1,450.00':>10}   (left over + wage - bills)",
        f"  {'Left now':<34}{'1,450.00':>10}",
        "  Add one: run.py add 12.50 Costa    Remove one: run.py remove 1",
    ]


# ---- run.py -------------------------------------------------------------------------------------

def setup(tmp_path):
    inbox = tmp_path / "statements"
    inbox.mkdir()
    for n in ("statement_2024_08.pdf", "statement_2024_09.pdf", "statement_2024_10.pdf"):
        shutil.copy(DATA / n, inbox / n)
    run.main(in_dir=inbox, out_dir=tmp_path / "output", ask=lambda p: "2500", wage_payer=ACME, ask_items=lambda p: "")
    return inbox, tmp_path / "tracker.db"


def cmd(argv, inbox, db, today=date(2024, 10, 25)):
    lines = []
    assert run.run_command(argv, out=lines.append, db_path=db, in_dir=inbox, wage_payer=ACME, today=today) is True
    return lines


def test_add_spends_and_remove(tmp_path, capsys):
    inbox, db = setup(tmp_path)
    assert get_value(open_db(db), "pay") == "2500.0"                 # the pay typed in run.py is remembered
    lines = cmd(["add", "150", "Argos", "TV"], inbox, db)
    assert lines[0] == "Added 150.00 Argos TV (Shopping) on 25 Oct 2024."
    assert "SO FAR THIS CYCLE (typed in)" in lines
    assert any("Left now" in l for l in lines)
    cmd(["add", "12.50", "Takeaway", "pizza"], inbox, db)
    spends = get_spends(open_db(db))
    assert [(s["name"], s["category"]) for s in spends] == [("Argos TV", "Shopping"), ("Takeaway pizza", "Takeaways")]

    lines = cmd(["spends"], inbox, db)
    assert lines[0] == "SO FAR THIS CYCLE (typed in)" and f"  {'Typed so far':<34}{'162.50':>10}" in lines

    lines = cmd(["remove", "1"], inbox, db)
    assert lines[0] == "Removed 150.00 Argos TV."
    assert [s["name"] for s in get_spends(open_db(db))] == ["Takeaway pizza"]
    assert cmd(["remove", "5"], inbox, db) == ["There is no typed spend 5. Pick 1 to 1."]


def test_left_now_uses_the_remembered_pay(tmp_path, capsys):
    inbox, db = setup(tmp_path)
    before = next(l for l in cmd(["spends"], inbox, db) if "Money for spending" in l)
    set_value(open_db(db), "pay", "3500")
    after = next(l for l in cmd(["spends"], inbox, db) if "Money for spending" in l)
    money = lambda line: float(line.split()[3].replace(",", ""))
    assert money(after) - money(before) == pytest.approx(1000)


def test_add_usage_and_no_database(tmp_path):
    inbox, db = setup(tmp_path)
    usage = ["Usage: run.py add <amount> <name>   e.g. run.py add 12.50 Costa"]
    assert cmd(["add"], inbox, db) == usage
    assert cmd(["add", "Costa"], inbox, db) == usage
    assert cmd(["add", "5", "Costa"], inbox, tmp_path / "none.db") == ["No database yet. Run run.py first."]
    assert cmd(["remove"], inbox, db) == ["Usage: run.py remove <number>   (the numbers are in the SO FAR list)"]


def test_run_swaps_typed_spends_and_shows_the_block(tmp_path, capsys):
    inbox, db = setup(tmp_path)
    cmd(["add", "61.30", "Petrol"], inbox, db, today=date(2024, 10, 9))      # the statement has PETROL STATION 7 -61.30 on 10 Oct
    cmd(["add", "7", "Bus"], inbox, db, today=date(2024, 10, 30))           # after the statements: kept, not asked
    capsys.readouterr()
    run.main(in_dir=inbox, out_dir=tmp_path / "output", ask=lambda p: "2500", wage_payer=ACME, ask_items=lambda p: "")
    text = capsys.readouterr().out
    assert "Matched 1 typed spend to your statements (removed from the typed list)." in text
    assert [s["name"] for s in get_spends(open_db(db))] == ["Bus"]
    assert text.index("IF YOUR PAY IS") < text.index("SO FAR THIS CYCLE (typed in)")
