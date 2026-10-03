"""Step 7 of SPEC.md: "Where did it go?" for the last finished cycle. Fake data only."""
import shutil
from datetime import date

import pytest

import run
from fintrack.common import analyse
from fintrack.cycles import build_cycles
from fintrack.models import Txn
from fintrack.spare import last_cycle_check
from fintrack.where import format_where, show_lines, where_did_it_go
from tests.conftest import DATA

PAYER = "ACME MOTORS PLC"


def fake_txns(good=False):
    """Wages of 2,000 on 28 Jan..May: finished cycles Jan, Feb, Mar (the 'before' window) and Apr (the one
    explained), then May (so far).
    Before (each): rent 500 (SO), energy 80 (DD), Tesco 80/120/100, Shell 50/70/60, Costa 8/12/10 -> all random.
    Bad Apr: rent 500, energy 110, Tesco 280, Shell 20, Costa 15, CURRYS 1,299 (one-off), 100 to savings (BP),
             60 refund in.
    Good Apr: rent 500, energy 60, Tesco 20, Shell 60, Costa 40, 60 refund in."""
    T = lambda m, d, typ, desc, amt, det="": Txn(date(2024, m, d), typ, desc, det, amt)
    tx = [T(m, 28, "CR", PAYER, 2000.0) for m in range(1, 6)]
    for m, (tesco, shell, costa) in zip((2, 3, 4), [(80, 50, 8), (120, 70, 12), (100, 60, 10)]):
        tx += [T(m, 1, "SO", "LANDLORD", -500.0, "RENT"), T(m, 2, "DD", "ENERGY CO", -80.0),
               T(m, 3, "VIS", "TESCO STORES", -float(tesco)), T(m, 4, "VIS", "SHELL", -float(shell)),
               T(m, 5, "VIS", "COSTA", -float(costa))]
    if good:
        tx += [T(5, 1, "SO", "LANDLORD", -500.0, "RENT"), T(5, 2, "DD", "ENERGY CO", -60.0),
               T(5, 3, "VIS", "TESCO STORES", -20.0), T(5, 4, "VIS", "SHELL", -60.0),
               T(5, 5, "VIS", "COSTA", -40.0), T(5, 6, "CR", "REFUND CO", 60.0)]
    else:
        tx += [T(5, 1, "SO", "LANDLORD", -500.0, "RENT"), T(5, 2, "DD", "ENERGY CO", -110.0),
               T(5, 3, "VIS", "TESCO STORES", -280.0), T(5, 4, "VIS", "SHELL", -20.0),
               T(5, 5, "VIS", "COSTA", -15.0), T(5, 2, "VIS", "CURRYS", -1299.0),
               T(5, 7, "BP", "MY SAVINGS", -100.0, "SAVINGS"), T(5, 6, "CR", "REFUND CO", 60.0)]
    tx.append(T(6, 1, "SO", "LANDLORD", -500.0, "RENT"))
    tx.sort(key=lambda t: t.date)
    return tx


def cycles(good=False):
    return build_cycles(fake_txns(good), payer=PAYER)


def money(x):
    return f"{x:,.2f}"


# ---- analyse() now keeps the payments behind its numbers ------------------------------------------

def test_analyse_keeps_common_and_random_payments():
    a = analyse(cycles())
    assert sorted(a.common_txns) == sorted(a.common)
    for key, entry in a.common.items():
        assert sum(-t.amount for t in a.common_txns[key]) == pytest.approx(entry["total"])
    assert sum(-t.amount for t in a.random_txns) == pytest.approx(a.random_per_cycle * a.cycles_used)
    assert all(t.description != "CURRYS" for t in a.random_txns)          # a one-off is not random


# ---- the reasons --------------------------------------------------------------------------------

def test_reasons_add_up_to_the_missing_money():
    cs = cycles()
    w = where_did_it_go(cs)
    assert w["start"] == date(2024, 4, 28) and w["end"] == date(2024, 5, 27)
    assert w["missing"] == pytest.approx(last_cycle_check(cs)["missing"]) == pytest.approx(1514)
    got = {(r["kind"], r["name"]): r["amount"] for r in w["reasons"]}
    assert got == {("oneoff", "CURRYS"): pytest.approx(1299),
                   ("category", "Food shopping"): pytest.approx(180),
                   ("moved", "Savings/Transfers"): pytest.approx(100),
                   ("bill", "ENERGY CO"): pytest.approx(30),
                   ("category", "Unsorted"): pytest.approx(5),
                   ("category", "Car"): pytest.approx(-40),
                   ("other_in", "Other money in"): pytest.approx(-60)}
    assert sum(r["amount"] for r in w["reasons"]) == pytest.approx(w["missing"])


def test_good_month_reasons_add_up_too():
    cs = cycles(good=True)
    w = where_did_it_go(cs)
    assert w["missing"] == pytest.approx(-130)
    assert sum(r["amount"] for r in w["reasons"]) == pytest.approx(-130)
    assert ("category", "Car") not in {(r["kind"], r["name"]) for r in w["reasons"]}   # exactly as usual


def test_saved_answers_change_the_reasons():
    answers = {"CARD|COSTA|": {"kind": "oneoff", "label": "", "source": "user"}}
    w = where_did_it_go(cycles(), answers=answers)
    names = {(r["kind"], r["name"]) for r in w["reasons"]}
    assert ("oneoff", "COSTA") in names and ("category", "Unsorted") not in names
    assert sum(r["amount"] for r in w["reasons"]) == pytest.approx(w["missing"])


def test_nothing_to_explain_without_a_finished_cycle_before():
    assert where_did_it_go(build_cycles(fake_txns()[:12], payer=PAYER)) is None
    assert format_where(None) == []


# ---- what is printed ----------------------------------------------------------------------------

def test_format_where_bad_month():
    assert format_where(where_did_it_go(cycles())) == [
        "WHERE DID THE 1,514.00 GO?   (28 Apr 2024 to 27 May 2024)",
        f"  1. {'One-off: CURRYS':<34}{'1,299.00':>10}   (2 May)",
        f"  2. {'Food shopping over normal':<34}{'180.00':>10}   (280.00 vs usual 100.00)",
        f"  3. {'Moved out (Savings/Transfers)':<34}{'100.00':>10}   (100.00 vs usually 0.00)",
        f"  4. {'ENERGY CO went up':<34}{'30.00':>10}   (110.00 vs 80.00 last month)",
        f"  5. {'Small bits (under 20 each)':<34}{'5.00':>10}",
        f"     {'Spent LESS than normal':<34}{'-40.00':>10}   (Car -40.00)",
        f"     {'Other money in':<34}{'-60.00':>10}",
        f"     {'-' * 44}",
        f"     {'Adds up to':<34}{'1,514.00':>10}",
        "  To see the payments behind a line:  run.py show 1",
    ]


def test_format_where_good_month():
    assert format_where(where_did_it_go(cycles(good=True))) == [
        "WHERE DID THE EXTRA 130.00 COME FROM?   (28 Apr 2024 to 27 May 2024)",
        f"  1. {'Food shopping under normal':<34}{'80.00':>10}   (20.00 vs usual 100.00)",
        f"  2. {'Other money in':<34}{'60.00':>10}",
        f"  3. {'ENERGY CO went down':<34}{'20.00':>10}   (60.00 vs 80.00 last month)",
        f"     {'Spent MORE than normal':<34}{'-30.00':>10}   (Unsorted -30.00)",
        f"     {'-' * 44}",
        f"     {'Adds up to':<34}{'130.00':>10}",
        "  To see the payments behind a line:  run.py show 1",
    ]


def test_format_where_when_nothing_is_missing():
    w = dict(where_did_it_go(cycles()), missing=0.001, reasons=[])
    assert format_where(w) == ["WHERE DID IT GO?   Nothing missing: the cycle went as expected."]


def test_more_than_five_big_reasons_are_lumped():
    w = dict(where_did_it_go(cycles()), missing=600.0, reasons=[
        {"kind": "category", "name": f"Cat{i}", "amount": 100.0, "now": 100.0, "usual": 0.0, "txns": []}
        for i in range(6)])
    lines = format_where(w)
    assert lines[5] == f"  5. {'Everything else':<34}{'200.00':>10}"
    assert lines[-2] == f"     {'Adds up to':<34}{'600.00':>10}"


# ---- show N -------------------------------------------------------------------------------------

def test_show_lines():
    w = where_did_it_go(cycles())
    assert show_lines(w, 1) == ["LINE 1: One-off: CURRYS",
                                f"  02 May 2024  {'CURRYS':<30}{'-1,299.00':>10}"]
    assert show_lines(w, 2) == ["LINE 2: Food shopping over normal",
                                f"  03 May 2024  {'TESCO STORES':<30}{'-280.00':>10}"]
    assert show_lines(w, 5) == ["LINE 5: Small bits (under 20 each)",
                                f"  05 May 2024  {'COSTA':<30}{'-15.00':>10}"]
    assert show_lines(w, 9) == ["There is no line 9. Pick 1 to 5."]


# ---- run.py -------------------------------------------------------------------------------------

def test_run_prints_where_and_show_command(tmp_path, capsys):
    inbox = tmp_path / "statements"
    inbox.mkdir()
    for n in ("statement_2024_08.pdf", "statement_2024_09.pdf", "statement_2024_10.pdf"):
        shutil.copy(DATA / n, inbox / n)
    run.main(in_dir=inbox, out_dir=tmp_path / "output", ask=lambda p: "2500", wage_payer=PAYER,
             ask_items=lambda p: "")
    text = capsys.readouterr().out
    assert "LAST CYCLE: EXPECTED vs ACTUAL" in text
    assert text.index("LAST CYCLE") < text.index("WHERE DID") < text.index("IF YOUR PAY IS")

    db = tmp_path / "tracker.db"
    lines = []
    assert run.run_command(["show", "1"], out=lines.append, db_path=db, in_dir=inbox, wage_payer=PAYER) is True
    assert lines and lines[0].startswith("LINE 1: ")
    lines = []
    assert run.run_command(["show"], out=lines.append, db_path=db, in_dir=inbox, wage_payer=PAYER) is True
    assert lines == ["Usage: run.py show <number>   (the numbers are in the WHERE DID list)"]
    lines = []
    assert run.run_command(["show", "1"], out=lines.append, db_path=tmp_path / "x.db", in_dir=inbox,
                           wage_payer=PAYER) is True
    assert lines == ["No database yet. Run run.py first."]


def test_small_extra_payment_from_the_employer_is_other_money_in():
    # Real data has a 235 PAYROLL credit from the employer: under 500, so not a wage. It must still add up.
    tx = fake_txns() + [Txn(date(2024, 5, 8), "CR", PAYER, "PAYROLL", 235.0)]
    tx.sort(key=lambda t: t.date)
    w = where_did_it_go(build_cycles(tx, payer=PAYER))
    other = next(r for r in w["reasons"] if r["kind"] == "other_in")
    assert other["amount"] == pytest.approx(-295)
    assert sorted(t.amount for t in other["txns"]) == [60.0, 235.0]
    assert sum(r["amount"] for r in w["reasons"]) == pytest.approx(w["missing"]) == pytest.approx(1279)
