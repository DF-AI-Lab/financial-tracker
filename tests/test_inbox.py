"""No. 6 (user, 3 Oct 2026): drop statement PDFs on the home page and sort new items on the page (buttons, or
'Copy for AI' / 'Paste answers'). Fake PDFs and data only."""
import shutil
from datetime import date

import pytest

from fintrack.inbox import import_pdf
from fintrack.sortpage import pending_for_page, save_answers, ai_prompt, parse_ai, category_names, KINDS
from fintrack.models import Txn
from fintrack.store import open_db, load_statements, get_items, get_categories, set_item, set_category
from tests.conftest import DATA


# ---- 6a: a dropped PDF is saved in the statements folder, read, checked and stored --------------------

def test_import_a_dropped_pdf(tmp_path):
    conn = open_db(tmp_path / "tracker.db")
    folder = tmp_path / "statements"
    data = (DATA / "statement_2024_08.pdf").read_bytes()
    r = import_pdf(conn, folder, "statement_2024_08.pdf", data)
    assert r["new"] is True and r["payments"] > 0 and r["problems"] == [] and r["start"] and r["end"]
    assert (folder / "statement_2024_08.pdf").read_bytes() == data
    assert len(load_statements(conn)) == 1
    again = import_pdf(conn, folder, "copy.pdf", data)                    # the same statement again
    assert again["new"] is False and len(load_statements(conn)) == 1
    assert not (folder / "copy.pdf").exists()                             # a duplicate is not kept


def test_a_bad_file_is_refused_and_nothing_is_saved(tmp_path):
    conn = open_db(tmp_path / "tracker.db")
    folder = tmp_path / "statements"
    r = import_pdf(conn, folder, "notes.txt", b"hello")
    assert "error" in r and not folder.exists() or not any(folder.iterdir())
    r = import_pdf(conn, folder, "broken.pdf", b"%PDF-1.4 rubbish")
    assert "error" in r and not (folder / "broken.pdf").exists()
    r = import_pdf(conn, folder, "../../evil.pdf", (DATA / "statement_2024_08.pdf").read_bytes())
    assert r.get("new") is True and (folder / "evil.pdf").exists()        # only the file name is used


# ---- 6b: the questions on the page ---------------------------------------------------------------

def T(m, typ, desc, amt, detail=""):
    return Txn(date(2024, m, 3), typ, desc, detail, -amt)


TX = [T(1, "VIS", "CORNER SHOP", 12), T(2, "VIS", "CORNER SHOP", 9), T(3, "VIS", "CORNER SHOP", 30),
      T(2, "DD", "NEW GYM", 30), T(3, "VIS", "CURRYS", 1299), T(1, "VIS", "TINY", 1.0),
      T(1, "DD", "ENERGY CO", 80), T(2, "DD", "ENERGY CO", 95)]


def test_pending_items_for_the_page(tmp_path):
    conn = open_db(tmp_path / "t.db")
    items = pending_for_page(conn, TX)
    assert [i["name"] for i in items] == ["Currys", "Corner Shop"]                  # biggest first; tiny skipped
    assert "DD|ENERGY CO|" in get_items(conn)                                       # DDs are saved as bills,
    assert get_items(conn)["DD|NEW GYM|"]["kind"] == "common"                       # even paid once (4 Oct 2026)
    currys = items[0]
    assert (currys["n"], currys["kind"], currys["group"]) == (1, "oneoff", "Card")
    assert set(KINDS) == {"bill", "random", "oneoff", "yearly"}


def test_save_answers_from_the_page(tmp_path):
    conn = open_db(tmp_path / "t.db")
    items = pending_for_page(conn, TX)
    save_answers(conn, [{"key": items[0]["key"], "kind": "oneoff", "label": "New telly", "category": "Shopping"},
                        {"key": items[1]["key"], "kind": "bill", "label": "", "category": "Food shopping"},
                        {"key": "X|BAD|", "kind": "nonsense", "label": "", "category": ""}])
    saved = get_items(conn)
    assert saved[items[0]["key"]] == {"kind": "oneoff", "label": "New telly", "source": "user"}
    assert saved[items[1]["key"]]["kind"] == "common" and saved[items[1]["key"]]["label"] == "Corner Shop"
    assert get_categories(conn)[items[0]["key"]] == "Shopping"
    assert "X|BAD|" not in saved
    assert pending_for_page(conn, TX) == []


def test_category_names_include_the_users_own(tmp_path):
    conn = open_db(tmp_path / "t.db")
    set_item(conn, "BP|BENNETT JONES|", "oneoff", "IVA", "user")
    set_category(conn, "BP|BENNETT JONES|", "Debt")
    names = category_names(conn)
    assert "Debt" in names and "Household" in names and names.count("Household") == 1


def test_copy_for_ai_and_paste_the_answers_back(tmp_path):
    conn = open_db(tmp_path / "t.db")
    items = pending_for_page(conn, TX)
    text = ai_prompt(items, ["Household", "Shopping", "Food shopping"])
    assert "1. Currys" in text and "bill, random, oneoff or yearly" in text and "Food shopping" in text
    reply = """Sure! Here you go:
1 oneoff Shopping
2. Random - food shopping
3) BILL Household
4 bill Household
"""
    got = parse_ai(reply, len(items), ["Household", "Shopping", "Food shopping"])
    assert got == {1: {"kind": "oneoff", "category": "Shopping"},
                   2: {"kind": "random", "category": "Food shopping"}}               # 3 and 4 are not items: ignored
    assert parse_ai("1 one-off\n2 common Gym stuff", 3, ["Household"]) == {
        1: {"kind": "oneoff", "category": ""}, 2: {"kind": "bill", "category": "Gym stuff"}}
