"""Step 2 of SPEC.md: categories (fake data only)."""
import sqlite3

import pytest

from fintrack.categories import STARTER, category_for, guess_category
from fintrack.questions import fix_items, parse_answer, review
from fintrack.store import get_categories, get_items, open_db, set_category, set_item
from tests.synth import synth_txns

TXNS = synth_txns()


# ---- Guessing a category from a name / label -----------------------------------------------

def test_starter_list():
    assert STARTER == ["Household", "Car", "Food shopping", "Takeaways", "Subscriptions",
                       "Shopping", "Cash", "Savings/Transfers", "Unsorted"]


@pytest.mark.parametrize("name,label,group,expected", [
    ("KATIE FINCH", "Rent", "SO", "Household"),
    ("E.ON NEXT", "", "DD", "Household"),
    ("CITY OF YORK GENER", "", "DD", "Household"),        # council tax
    ("TV LICENCE MBP", "", "DD", "Household"),
    ("SKY DIGITAL", "", "DD", "Household"),
    ("TESCO MOBILE", "", "DD", "Household"),              # MOBILE wins over TESCO
    ("FORESTER LIFE", "", "DD", "Household"),             # life insurance
    ("WATER PLUS", "", "DD", "Household"),
    ("SAINSBURYS PETROL", "", "CARD", "Car"),              # PETROL wins over SAINSBURYS
    ("DVLA-YJ70ULK", "", "DD", "Car"),
    ("CHLOE AMBER FINCH", "Car Loan Payment", "SO", "Car"),
    ("SHELL", "", "CARD", "Car"),
    ("GOOGLE YOUTUBE", "", "CARD", "Subscriptions"),
    ("AUDIBLE UK", "", "CARD", "Subscriptions"),
    ("NETFLIX", "", "CARD", "Subscriptions"),
    ("AMAZON PRIME", "", "CARD", "Subscriptions"),          # PRIME wins over AMAZON
    ("JUST EAT", "", "CARD", "Takeaways"),
    ("DOMINOS PIZZA", "", "CARD", "Takeaways"),
    ("ASDA SUPERSTORE", "", "CARD", "Food shopping"),
    ("FARMFOODS", "", "CARD", "Food shopping"),
    ("TESCO STORES", "", "CARD", "Food shopping"),
    ("SAINSBURYS S/MKTS", "", "CARD", "Food shopping"),
    ("CURRYS", "", "CARD", "Shopping"),
    ("ARGOS", "", "CARD", "Shopping"),
    ("AMAZON", "", "CARD", "Shopping"),
    ("CASH NOTEMAC", "", "CASH", "Cash"),
    ("ANYTHING", "", "CASH", "Cash"),                     # every cash machine is Cash
    ("MY SAVINGS POT", "", "BP", "Savings/Transfers"),
    ("SIMPLY CHIROPRACTI", "", "CARD", "Unsorted"),
    ("", "", "CARD", "Unsorted"),
])
def test_guess_category(name, label, group, expected):
    assert guess_category(name, label, group) == expected


def test_guess_matches_whole_words_only():
    assert guess_category("CARDIFF FLOWERS", "", "CARD") == "Unsorted"     # CARDIFF is not CAR
    assert guess_category("CAR WASH", "", "CARD") == "Car"


def test_category_for_prefers_the_saved_one():
    assert category_for("SO|KATIE FINCH|RENT", "Rent", "") == "Household"           # nothing saved -> guess
    assert category_for("SO|KATIE FINCH|RENT", "Rent", "Bills") == "Bills"          # saved wins (new category ok)
    assert category_for("CASH|CASH NOTEMAC|", "", None) == "Cash"


# ---- Database -------------------------------------------------------------------------------

def test_set_and_get_categories():
    conn = open_db(":memory:")
    set_item(conn, "SO|LANDLORD|RENT", "common", "Rent")
    assert get_categories(conn) == {"SO|LANDLORD|RENT": ""}                     # none saved yet
    set_category(conn, "SO|LANDLORD|RENT", "Household")
    assert get_categories(conn) == {"SO|LANDLORD|RENT": "Household"}
    set_item(conn, "SO|LANDLORD|RENT", "common", "Rent!")                       # set_item keeps the category
    assert get_categories(conn)["SO|LANDLORD|RENT"] == "Household"
    assert get_items(conn)["SO|LANDLORD|RENT"] == {"kind": "common", "label": "Rent!", "source": "user"}


def test_old_database_gets_the_category_column(tmp_path):
    db = tmp_path / "old.db"
    c = sqlite3.connect(str(db))
    c.execute("CREATE TABLE items (key TEXT PRIMARY KEY, kind TEXT, label TEXT, source TEXT)")
    c.execute("INSERT INTO items VALUES ('SO|LANDLORD|RENT', 'common', 'Rent', 'user')")
    c.commit()
    c.close()
    conn = open_db(db)
    assert get_categories(conn) == {"SO|LANDLORD|RENT": ""}
    set_category(conn, "SO|LANDLORD|RENT", "Household")
    conn.close()
    assert get_categories(open_db(db)) == {"SO|LANDLORD|RENT": "Household"}      # reopening is safe


# ---- Typing a category in the question list ----------------------------------------------------

def test_parse_cat():
    r = parse_answer("cat 2 Food shopping  common 3", 10)
    assert r["error"] is None
    assert r["cats"] == {2: "Food shopping"} and r["kinds"] == {3: "common"}
    assert parse_answer("", 10)["cats"] == {}
    assert parse_answer("label 1 Rent cat 1 Household", 10)["labels"] == {1: "Rent"}
    assert parse_answer("label 1 Rent cat 1 Household", 10)["cats"] == {1: "Household"}


@pytest.mark.parametrize("text", ["cat", "cat Food", "cat 11 Food"])
def test_parse_cat_errors(text):
    assert parse_answer(text, 10)["error"]


def runner(*replies):
    it = iter(replies)
    calls = []

    def ask(prompt):
        calls.append(prompt)
        return next(it) if replies else ""
    ask.calls = calls
    return ask


def test_enter_saves_the_guessed_category_and_shows_it():
    conn, lines = open_db(":memory:"), []
    review(conn, TXNS, runner(), out=lines.append, size=10)
    cats = get_categories(conn)
    assert cats["SO|LANDLORD|RENT"] == "Household"
    assert cats["DD|ENERGY CO|"] == "Household"
    assert cats["CASH|CASH MACHINE|"] == "Cash"
    text = "\n".join(lines)
    assert "Household" in text and "cat 1" in text                 # guess shown, hint mentions cat


def test_typed_category_is_saved():
    conn = open_db(":memory:")
    review(conn, TXNS, runner("cat 1 Big stuff  all"), out=lambda s: None, size=10)
    cats = get_categories(conn)
    assert "Big stuff" in cats.values()                             # a brand-new category is fine


def test_fix_shows_and_changes_categories():
    conn, lines = open_db(":memory:"), []
    review(conn, TXNS, runner(), out=lambda s: None, size=10)
    assert fix_items(conn, runner("cat 1 Fun"), out=lines.append) == 1
    text = "\n".join(lines)
    assert "Household" in text                                      # categories are shown
    assert get_categories(conn)["CARD|BARBER|"] == "Fun"           # 1 = CARD|BARBER| (sorted by key)
    assert get_items(conn)["CARD|BARBER|"]["source"] == "suggested"  # only the category changed
