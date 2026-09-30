import copy
from datetime import date

import pytest

from fintrack.checks import check_statement
from fintrack.models import Txn
from fintrack.parse import parse_statement
from fintrack.store import (get_items, import_statement, item_key, load_txns, open_db,
                            set_item, statement_rows)
from tests.conftest import DATA

FILES = ("statement_2024_08.pdf", "statement_2024_09.pdf", "statement_2024_10.pdf")


def statements():
    return [parse_statement(DATA / n) for n in FILES]


def filled(conn):
    for st in statements():
        assert import_statement(conn, st, check_statement(st)) is True


def test_import_load_and_order():
    conn = open_db(":memory:")
    filled(conn)
    want = sorted((t for st in statements() for t in st.txns), key=lambda t: t.date)
    got = load_txns(conn)
    assert len(got) == len(want)
    assert [t.date for t in got] == sorted(t.date for t in got)
    assert sorted((t.date, t.type, t.description, t.detail, round(t.amount, 2)) for t in got) == \
           sorted((t.date, t.type, t.description, t.detail, round(t.amount, 2)) for t in want)
    assert all(isinstance(t, Txn) and isinstance(t.date, date) for t in got)


def test_same_statement_is_only_stored_once():
    conn = open_db(":memory:")
    filled(conn)
    st = statements()[1]
    st.file = "copy_of_sep.PDF"
    assert import_statement(conn, st, []) is False
    assert len(statement_rows(conn)) == 3
    assert len(load_txns(conn)) == sum(len(s.txns) for s in statements())


def test_statement_without_dates_is_not_stored():
    conn = open_db(":memory:")
    st = statements()[0]
    st.end = None
    assert import_statement(conn, st, []) is False
    assert statement_rows(conn) == [] and load_txns(conn) == []


def test_it_survives_closing_and_reopening(tmp_path):
    path = tmp_path / "tracker.db"
    conn = open_db(path)
    filled(conn)
    set_item(conn, "SO|SAM PARKER|RENT", "regular", "Rent")
    conn.close()
    again = open_db(path)
    assert len(statement_rows(again)) == 3
    assert len(load_txns(again)) == sum(len(s.txns) for s in statements())
    assert get_items(again)["SO|SAM PARKER|RENT"] == {"kind": "regular", "label": "Rent", "source": "user"}
    filled_again = statements()
    assert import_statement(again, filled_again[0], []) is False


def test_statement_rows_keep_problems_and_counts():
    conn = open_db(":memory:")
    good, bad = statements()[0], statements()[1]
    bad.txns[2].amount = round(bad.txns[2].amount - 5, 2)
    assert import_statement(conn, good, check_statement(good))
    assert import_statement(conn, bad, check_statement(bad))
    rows = statement_rows(conn)
    assert [r["file"] for r in rows] == ["statement_2024_08.pdf", "statement_2024_09.pdf"]
    assert rows[0]["problems"] == "" and rows[1]["problems"] != ""
    assert rows[0]["start"] == "2024-07-22" and rows[0]["end"] == "2024-08-22"
    assert rows[0]["payments"] == len(good.txns)
    assert rows[0]["opening"] == pytest.approx(good.opening)


def T(typ, desc, detail="", amt=-10.0):
    return Txn(date(2024, 1, 1), typ, desc, detail, amt)


def test_item_key():
    assert item_key(T("SO", "SAM PARKER", "Rent")) == "SO|SAM PARKER|RENT"
    assert item_key(T("SO", "SAM PARKER", "Food")) == "SO|SAM PARKER|FOOD"
    assert item_key(T("BP", "SAM PARKER", "Food and bil")) == "BP|SAM PARKER|FOOD AND BIL"
    assert item_key(T("DD", "GYM CLUB")) == "DD|GYM CLUB|"
    assert item_key(T("DD", "E.ON NEXT LTD", "FIRST PAYMENT")) == "DD|E.ON NEXT|"
    assert item_key(T("DD", "e.on next", "")) == "DD|E.ON NEXT|"
    assert item_key(T("VIS", "CORNER SHOP 12", "YORK")) == "CARD|CORNER SHOP|"
    assert item_key(T(")))", "Tesco Stores 5314", "HUNTINGDON")) == "CARD|TESCO STORES|"
    assert item_key(T("ATM", "CASH NOTEMAC JAN04", "JAMES HALL @17:36")) == "CASH|CASH NOTEMAC JAN|"
    assert item_key(T("CR", "ACME MOTORS PLC", "PAYROLL", 2400)) == "IN|ACME MOTORS PLC|"
    assert item_key(T("VIS", "INT'L 0093267280", "AWS EMEA aws.amazon.co")) == "CARD|AWS EMEA AWS.AMAZON.CO|"


def test_set_and_get_items():
    conn = open_db(":memory:")
    set_item(conn, "DD|GYM CLUB|", "regular", "Gym", source="suggested")
    set_item(conn, "DD|GYM CLUB|", "common", "Gym fees")          # update
    set_item(conn, "CARD|CAR DEALER|", "oneoff")
    items = get_items(conn)
    assert items["DD|GYM CLUB|"] == {"kind": "common", "label": "Gym fees", "source": "user"}
    assert items["CARD|CAR DEALER|"] == {"kind": "oneoff", "label": "", "source": "user"}
    with pytest.raises(ValueError):
        set_item(conn, "x", "banana")
