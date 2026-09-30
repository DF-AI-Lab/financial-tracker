"""Fake statement that copies the layout quirks of a REAL HSBC statement."""
import pytest

from fintrack.parse import parse_pdf
from fintrack.sort import bills_summary
from tests.conftest import DATA, load_expected, to_txn

STATEMENTS = load_expected("expected_real_style.json")


@pytest.mark.parametrize("st", STATEMENTS, ids=lambda s: s["file"])
def test_real_style_matches_expected_exactly(st):
    got = parse_pdf(DATA / st["file"])
    want = [to_txn(t) for t in st["transactions"]]
    assert len(got) == len(want), f"got {len(got)} payments, expected {len(want)}"
    for g, w in zip(got, want):
        assert (g.date, g.type, g.description, g.detail) == (w.date, w.type, w.description, w.detail)
        assert round(g.amount, 2) == round(w.amount, 2), f"{w.description}: amount/direction wrong"
        assert (g.balance is None) == (w.balance is None)
        if w.balance is not None:
            assert round(g.balance, 2) == round(w.balance, 2)


@pytest.mark.parametrize("st", STATEMENTS, ids=lambda s: s["file"])
def test_real_style_balance_maths(st):
    got = parse_pdf(DATA / st["file"])
    running = st["opening"]
    for t in got:
        running = round(running + t.amount, 2)
        if t.balance is not None:
            assert round(t.balance, 2) == running
    assert running == pytest.approx(st["closing"], abs=0.005)


def test_foreign_payment_adds_rate_and_fee():
    got = parse_pdf(DATA / STATEMENTS[0]["file"])
    fx = [t for t in got if t.description == "INT'L 0052056981"]
    assert len(fx) == 1 and round(fx[0].amount, 2) == -11.02


def test_date_carries_across_page_break():
    got = parse_pdf(DATA / STATEMENTS[0]["file"])
    rent = [t for t in got if t.detail == "RENT"]
    assert len(rent) == 1 and rent[0].date.isoformat() == "2024-06-02"


def test_bill_with_no_detail_uses_payee_as_key(real_style_txns):
    s = bills_summary(real_style_txns)
    assert s["GYM CLUB"] == {"months": 1, "average": 50.00}
    assert s["SAM PARKER - RENT"] == {"months": 1, "average": 550.00}
    assert s["ENERGY CO"] == {"months": 1, "average": 162.45}  # "FIRST PAYMENT" detail is ignored
