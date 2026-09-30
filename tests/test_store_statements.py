from datetime import date

from fintrack.checks import check_statement
from fintrack.parse import parse_statement
from fintrack.store import import_statement, load_statements, open_db
from tests.conftest import DATA

FILES = ("statement_2024_10.pdf", "statement_2024_08.pdf", "realstyle_2024_06.pdf")   # imported out of order


def test_load_statements_round_trip():
    conn = open_db(":memory:")
    originals = {n: parse_statement(DATA / n) for n in FILES}
    for n in FILES:
        assert import_statement(conn, originals[n], check_statement(originals[n]))
    got = load_statements(conn)
    assert [s.file for s in got] == ["realstyle_2024_06.pdf", "statement_2024_08.pdf", "statement_2024_10.pdf"]
    for s in got:
        o = originals[s.file]
        assert (s.start, s.end) == (o.start, o.end) and isinstance(s.start, date)
        assert round(s.opening, 2) == round(o.opening, 2) and round(s.closing, 2) == round(o.closing, 2)
        assert [(t.date, t.type, t.description, t.detail, round(t.amount, 2)) for t in s.txns] == \
               [(t.date, t.type, t.description, t.detail, round(t.amount, 2)) for t in o.txns]
        assert check_statement(s) == []          # stored statements still add up


def test_load_statements_empty():
    assert load_statements(open_db(":memory:")) == []
