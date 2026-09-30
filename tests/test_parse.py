import pytest

from fintrack.parse import parse_pdf
from tests.conftest import DATA, load_expected, to_txn


@pytest.mark.parametrize("st", load_expected(), ids=lambda s: s["file"])
def test_parse_matches_expected_exactly(st):
    got = parse_pdf(DATA / st["file"])
    want = [to_txn(t) for t in st["transactions"]]
    assert len(got) == len(want), "wrong number of transactions (junk lines or missed lines?)"
    for g, w in zip(got, want):
        assert (g.date, g.type, g.description, g.detail) == (w.date, w.type, w.description, w.detail)
        assert round(g.amount, 2) == round(w.amount, 2), f"{w.description}: paid in/out or amount wrong"
        if w.balance is None:
            assert g.balance is None
        else:
            assert round(g.balance, 2) == round(w.balance, 2)


@pytest.mark.parametrize("st", load_expected(), ids=lambda s: s["file"])
def test_balance_maths(st):
    got = parse_pdf(DATA / st["file"])
    running = st["opening"]
    for t in got:
        running = round(running + t.amount, 2)
        if t.balance is not None:
            assert round(t.balance, 2) == running
    assert running == pytest.approx(st["closing"], abs=0.005)
