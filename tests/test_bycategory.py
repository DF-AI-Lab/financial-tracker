"""Step 5 of SPEC.md: spending by category, this cycle vs the 6-cycle average (fake data only)."""
import shutil
from datetime import date

import pytest

import run
from fintrack.bycategory import category_spending, format_categories, format_category_detail
from fintrack.cycles import build_cycles
from fintrack.models import Txn
from tests.conftest import DATA

PAYER = "ACME MOTORS PLC"


def T(m, d, type_, desc, amount, detail=""):
    return Txn(date(2024, m, d), type_, desc, detail, amount)


def fake_txns(now_extra=None, window_extra=None):
    """Wages on the 28th of Jan..Jul -> 6 complete cycles (Jan..Jun) and the current one (from 28 Jul, so far).
    Every complete cycle: rent 500 (SO, ref RENT), Tesco 100, Shell 50, Mystery Shop 30.
    Current cycle: rent 500, Tesco 180, Shell 20, Costa 12 and a 1,500 TV (big, so a one-off)."""
    tx = [T(m, 28, "CR", PAYER, 2000.0) for m in range(1, 8)]
    for m in range(1, 7):
        tx += [T(m + 1, 1, "SO", "LANDLORD", -500.0, "RENT"),
               T(m + 1, 3, "VIS", "TESCO STORES 123", -100.0),
               T(m + 1, 4, "VIS", "SHELL", -50.0),
               T(m + 1, 5, "VIS", "MYSTERY SHOP", -30.0)]
    tx += [T(8, 1, "SO", "LANDLORD", -500.0, "RENT"),
           T(8, 2, "VIS", "TESCO STORES 123", -180.0),
           T(8, 3, "VIS", "SHELL", -20.0),
           T(8, 4, "VIS", "COSTA", -12.0),
           T(8, 5, "VIS", "BIG TV STORE", -1500.0),
           T(8, 6, "CR", "REFUND CO", 25.0)]                     # money in: ignored
    tx += list(now_extra or []) + list(window_extra or [])
    tx.sort(key=lambda t: t.date)
    return tx


def spending(**kw):
    txns = fake_txns(kw.pop("now_extra", None), kw.pop("window_extra", None))
    return category_spending(build_cycles(txns, payer=PAYER), **kw)


def rows_of(res):
    return [(r["category"], r["now"], r["avg"], r["diff"]) for r in res["rows"]]


# ---- the numbers --------------------------------------------------------------------------------

def test_one_row_per_category_biggest_overspend_first():
    res = spending()
    assert res["cycles_used"] == 6
    assert res["now_start"] == date(2024, 7, 28) and res["now_complete"] is False
    assert rows_of(res) == [
        ("Food shopping", pytest.approx(180), pytest.approx(100), pytest.approx(80)),
        ("Household", pytest.approx(500), pytest.approx(500), pytest.approx(0)),
        ("Unsorted", pytest.approx(12), pytest.approx(30), pytest.approx(-18)),
        ("Car", pytest.approx(20), pytest.approx(50), pytest.approx(-30)),
    ]


def test_each_category_lists_its_labels_with_the_same_columns():
    res = spending()
    unsorted = next(r for r in res["rows"] if r["category"] == "Unsorted")
    assert [(l["label"], l["now"], l["avg"], l["diff"]) for l in unsorted["labels"]] == [
        ("Costa", pytest.approx(12), pytest.approx(0), pytest.approx(12)),
        ("Mystery Shop", pytest.approx(0), pytest.approx(30), pytest.approx(-30)),
    ]
    household = next(r for r in res["rows"] if r["category"] == "Household")
    assert [l["label"] for l in household["labels"]] == ["Rent"]          # the reference, in Title Case


def test_saved_labels_and_categories_are_used():
    items = {"CARD|MYSTERY SHOP|": {"kind": "random", "label": "Model kits", "source": "user"}}
    cats = {"CARD|MYSTERY SHOP|": "Hobbies"}
    res = spending(items=items, categories=cats)
    hobbies = next(r for r in res["rows"] if r["category"] == "Hobbies")
    assert hobbies["avg"] == pytest.approx(30) and hobbies["now"] == 0
    assert [l["label"] for l in hobbies["labels"]] == ["Model kits"]
    assert "Unsorted" in [r["category"] for r in res["rows"]]               # Costa is still unsorted


def test_one_offs_and_yearly_bills_are_left_out():
    window = [T(3, 10, "VIS", "SOFA WORLD", -400.0), T(4, 10, "DD", "AVIVA", -180.0)]
    items = {"CARD|SOFA WORLD|": {"kind": "oneoff", "label": "", "source": "user"},
             "DD|AVIVA|": {"kind": "yearly", "label": "", "source": "user"}}
    res = spending(window_extra=window, items=items)
    names = [l["label"] for r in res["rows"] for l in r["labels"]]
    assert "Sofa World" not in names and "Aviva" not in names
    assert "Big Tv Store" not in names                                      # 1,500 unanswered: a one-off too
    assert sum(r["avg"] for r in res["rows"]) == pytest.approx(680)


def test_payday_transfer_rule_counts_as_its_label():
    # Rent paid by transfer with the wrong reference, on payday, covered by the rent rule
    rule = {"payer": "SAM PARKER", "usual": 550.0, "label": "Rent", "kind": "common", "max_days": 2,
            "tolerance": 0.10, "source": "user"}
    now = [T(7, 28, "BP", "SAM PARKER", -550.0, "FOOD")]
    res = spending(now_extra=now, rules=[rule])
    household = next(r for r in res["rows"] if r["category"] == "Household")
    assert household["now"] == pytest.approx(1050)
    rent = next(l for l in household["labels"] if l["label"] == "Rent")
    assert rent["now"] == pytest.approx(1050)
    assert "Food shopping" == res["rows"][0]["category"] and res["rows"][0]["now"] == pytest.approx(180)


def test_not_enough_cycles():
    txns = [T(1, 28, "CR", PAYER, 2000.0), T(2, 1, "VIS", "TESCO", -10.0)]
    res = category_spending(build_cycles(txns, payer=PAYER))
    assert res["cycles_used"] == 0 and res["rows"] == []
    assert format_categories(res) == ["SPENDING BY CATEGORY: not enough finished paydays yet."]


# ---- what is printed ----------------------------------------------------------------------------

def test_format_categories():
    lines = format_categories(spending())
    assert lines[0] == "SPENDING BY CATEGORY   (this cycle so far, from 28 Jul 2024, vs the 6-cycle average)"
    assert lines[1] == f"     {'Category':<24}{'Now':>10}{'Avg':>10}{'+/-':>10}"
    assert lines[2] == f"  1  {'Food shopping':<24}{'180.00':>10}{'100.00':>10}{'+80.00':>10}"
    assert lines[3] == f"  2  {'Household':<24}{'500.00':>10}{'500.00':>10}{'0.00':>10}"
    assert lines[5] == f"  4  {'Car':<24}{'20.00':>10}{'50.00':>10}{'-30.00':>10}"
    assert lines[-1] == "  To see what is inside one:  run.py cat 1"
    assert all(line.isascii() for line in lines)


def test_format_category_detail():
    res = spending()
    lines = format_category_detail(res, 3)
    assert lines[0] == "UNSORTED   (this cycle so far vs the 6-cycle average)"
    assert lines[1] == f"     {'Label':<24}{'Now':>10}{'Avg':>10}{'+/-':>10}"
    assert lines[2] == f"     {'Costa':<24}{'12.00':>10}{'0.00':>10}{'+12.00':>10}"
    assert lines[3] == f"     {'Mystery Shop':<24}{'0.00':>10}{'30.00':>10}{'-30.00':>10}"
    assert format_category_detail(res, 9) == ["There is no category 9. Pick 1 to 4."]
    assert format_category_detail(res, 0) == ["There is no category 0. Pick 1 to 4."]


# ---- run.py -------------------------------------------------------------------------------------

FAKE = ("statement_2024_08.pdf", "statement_2024_09.pdf", "statement_2024_10.pdf")
ACME = "ACME MOTORS PLC"


def test_run_prints_the_category_table_and_cat_command_opens_one(tmp_path, capsys):
    inbox = tmp_path / "statements"
    inbox.mkdir()
    for n in FAKE:
        shutil.copy(DATA / n, inbox / n)
    run.main(in_dir=inbox, out_dir=tmp_path / "output", ask=lambda p: "2500", wage_payer=ACME,
             ask_items=lambda p: "")
    text = capsys.readouterr().out
    assert "SPENDING BY CATEGORY" in text
    assert text.index("SIX-MONTH PICTURE") < text.index("SPENDING BY CATEGORY") < text.index("IF YOUR PAY IS")

    lines = []
    db = tmp_path / "tracker.db"
    assert run.run_command(["cat", "1"], out=lines.append, db_path=db, in_dir=inbox, wage_payer=ACME) is True
    assert lines and "(this cycle so far vs the" in lines[0]

    lines = []
    assert run.run_command(["cat"], out=lines.append, db_path=db, in_dir=inbox, wage_payer=ACME) is True
    assert lines == ["Usage: run.py cat <number>   (the numbers are in the SPENDING BY CATEGORY list)"]

    lines = []
    assert run.run_command(["cat", "1"], out=lines.append, db_path=tmp_path / "none.db", in_dir=inbox,
                           wage_payer=ACME) is True
    assert lines == ["No database yet. Run run.py first."]
