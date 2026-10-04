"""Change a bill for this pay cycle only (3 Oct 2026): kept in the kv table with the cycle start, so it is
forgotten by itself at the next payday. The bills themselves are not changed. Fake data only."""
from datetime import date

from fintrack.billchange import get_changes, set_change, clear_change
from fintrack.store import open_db, get_items

START = date(2024, 9, 28)


def test_set_get_and_clear(tmp_path):
    conn = open_db(tmp_path / "t.db")
    assert get_changes(conn, START) == {}
    set_change(conn, START, "DD|TESCO MOBILE|", 151.0)
    set_change(conn, START, "DD|SKY|", 60.0)
    assert get_changes(conn, START) == {"DD|TESCO MOBILE|": 151.0, "DD|SKY|": 60.0}
    clear_change(conn, START, "DD|SKY|")
    assert get_changes(conn, START) == {"DD|TESCO MOBILE|": 151.0}
    assert get_items(conn) == {}                                   # nothing saved about the bills themselves


def test_forgotten_at_the_next_payday(tmp_path):
    conn = open_db(tmp_path / "t.db")
    set_change(conn, START, "DD|TESCO MOBILE|", 151.0)
    assert get_changes(conn, date(2024, 10, 28)) == {}
    set_change(conn, date(2024, 10, 28), "DD|SKY|", 60.0)           # a new cycle starts afresh
    assert get_changes(conn, date(2024, 10, 28)) == {"DD|SKY|": 60.0}


# ---- left from last month (3 Oct 2026): typed on the home page, added to the spare cash, until next payday ----

from fintrack.billchange import get_left, set_left, clear_left


def test_left_from_last_month(tmp_path):
    conn = open_db(tmp_path / "t.db")
    assert get_left(conn, START) == 0.0
    set_left(conn, START, 220.0)
    assert get_left(conn, START) == 220.0
    assert get_left(conn, date(2024, 10, 28)) == 0.0                # forgotten at the next payday
    clear_left(conn, START)                                         # the x
    assert get_left(conn, START) == 0.0
