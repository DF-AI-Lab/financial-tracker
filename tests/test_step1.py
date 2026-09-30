"""Step 1: statement info, balance check, duplicates, per-statement report, big items."""
import shutil
from collections import defaultdict
from datetime import date

import pytest

from fintrack.checks import check_statement
from fintrack.dedupe import unique_statements
from fintrack.models import Statement, Txn
from fintrack.parse import parse_statement
from fintrack.sort import big_items, bill_key, statement_report
from tests.conftest import DATA, load_expected

ALL = [(n, s) for n in ("expected.json", "expected_real_style.json") for s in load_expected(n)]
IDS = [s["file"] for _, s in ALL]


def parsed(st):
    return parse_statement(DATA / st["file"])


@pytest.mark.parametrize("name,st", ALL, ids=IDS)
def test_statement_info(name, st):
    p = parsed(st)
    assert p.file == st["file"]
    assert p.start == date.fromisoformat(st["start"])
    assert p.end == date.fromisoformat(st["end"])
    assert p.opening == pytest.approx(st["opening"], abs=0.005)
    assert p.closing == pytest.approx(st["closing"], abs=0.005)
    assert len(p.txns) == len(st["transactions"])


@pytest.mark.parametrize("name,st", ALL, ids=IDS)
def test_check_passes_on_good_statement(name, st):
    assert check_statement(parsed(st)) == []


def test_check_finds_wrong_amount_and_names_it():
    st = parsed(ALL[0][1])
    victim = st.txns[3]
    victim.amount = round(victim.amount - 5.00, 2)
    problems = check_statement(st)
    assert problems, "a payment that is £5 out must be reported"
    assert any(victim.description in p or victim.date.strftime("%d") in p for p in problems)


def test_check_reports_missing_opening_balance():
    st = parsed(ALL[0][1])
    st.opening = None
    assert check_statement(st)


def test_duplicates_are_skipped(tmp_path):
    src = DATA / ALL[1][1]["file"]
    shutil.copy(src, tmp_path / "a.pdf")
    shutil.copy(src, tmp_path / "b_copy.pdf")
    other = DATA / ALL[2][1]["file"]
    shutil.copy(other, tmp_path / "c.pdf")
    sts = [parse_statement(tmp_path / n) for n in ("a.pdf", "b_copy.pdf", "c.pdf")]
    kept, skipped = unique_statements(sts)
    assert [s.file for s in kept] == ["a.pdf", "c.pdf"]
    assert [s.file for s in skipped] == ["b_copy.pdf"]


def test_statement_without_dates_is_never_a_duplicate():
    a = Statement("a", None, None, None, None, [])
    b = Statement("b", None, None, None, None, [])
    kept, skipped = unique_statements([a, b])
    assert len(kept) == 2 and skipped == []


def test_statement_report_per_statement():
    sts = [parsed(s) for _, s in ALL if s["file"].startswith("statement_")]
    rows = statement_report(list(reversed(sts)))  # order must not matter
    assert [r["file"] for r in rows] == ["statement_2024_08.pdf", "statement_2024_09.pdf", "statement_2024_10.pdf"]
    assert [r["label"] for r in rows] == ["Aug 2024", "Sep 2024", "Oct 2024"]
    assert rows[0]["end"] == "2024-08-22"
    for row, st in zip(rows, sts):
        inc = sum(t.amount for t in st.txns if t.amount > 0)
        bills = sum(-t.amount for t in st.txns if t.amount < 0 and t.type in ("DD", "SO"))
        rnd = sum(-t.amount for t in st.txns if t.amount < 0 and t.type not in ("DD", "SO"))
        assert row["income"] == pytest.approx(inc, abs=0.005)
        assert row["bills"] == pytest.approx(bills, abs=0.005)
        assert row["random"] == pytest.approx(rnd, abs=0.005)
        assert row["spare"] == pytest.approx(inc - bills - rnd, abs=0.005)


def test_statement_report_skips_statement_with_no_end_date():
    assert statement_report([Statement("x", None, None, None, None, [])]) == []


def test_big_items(all_expected_txns):
    got = big_items(all_expected_txns)
    want = sorted((t for t in all_expected_txns if abs(t.amount) >= 1000), key=lambda t: t.date)
    assert [(t.date, t.description, t.amount) for t in got] == [(t.date, t.description, t.amount) for t in want]
    assert got and all(abs(t.amount) >= 1000 for t in got)
    assert big_items(all_expected_txns, limit=200) != got


def T(desc, detail=""):
    return Txn(date(2024, 1, 1), "DD", desc, detail, -10.0)


def test_bill_key_merges_name_variants():
    assert bill_key(T("E.ON NEXT LTD")) == bill_key(T("E.ON NEXT")) == "E.ON NEXT"
    assert bill_key(T("E.ON NEXT LTD", "FIRST PAYMENT")) == "E.ON NEXT"
    assert bill_key(T("e.on next ltd", "first payment")) == "E.ON NEXT"
    assert bill_key(T("SAM PARKER", "RENT")) == "SAM PARKER - RENT"
    assert bill_key(T("GYM CLUB", "MEMBERSHIP")) == "GYM CLUB - MEMBERSHIP"
    assert bill_key(T("ACME PLC")) == "ACME"


def test_run_script_end_to_end(tmp_path, capsys):
    import run
    inbox, out = tmp_path / "statements", tmp_path / "output"
    inbox.mkdir()
    for n in ("statement_2024_08.pdf", "statement_2024_09.pdf", "realstyle_2024_06.pdf"):
        shutil.copy(DATA / n, inbox / n)
    shutil.copy(DATA / "statement_2024_09.pdf", inbox / "copy_of_sep.PDF")
    run.main(in_dir=inbox, out_dir=out)
    text = capsys.readouterr().out
    assert "copy_of_sep.PDF" in text and "duplicate" in text.lower()
    assert text.count("OK") >= 3   # balance check passed for the three real statements
    for name in ("bills.csv", "statements.csv", "big_items.csv"):
        assert (out / name).exists(), name
    assert "£" not in text and all(ord(c) < 128 for c in text), "keep console output plain ASCII (Windows console)"
