"""Changing jobs: more than one wage payer name."""
from datetime import date

import run
from fintrack.cycles import build_cycles, is_wage
from fintrack.models import Txn
from fintrack.store import open_db
from fintrack.wages import add_payer, all_payers


def T(d, desc, amt):
    return Txn(d, "CR" if amt > 0 else "DD", desc, "", amt)


def test_is_wage_takes_a_list_of_payers():
    t = T(date(2026, 5, 1), "NEW JOB LTD", 2500)
    assert is_wage(t, payer=["OLD JOB PLC", "NEW JOB LTD"])
    assert not is_wage(t, payer=["OLD JOB PLC"])
    assert not is_wage(T(date(2026, 5, 1), "NEW JOB LTD", 100), payer=["NEW JOB LTD"])


def test_cycles_carry_on_after_a_job_change():
    txns = [
        T(date(2026, 1, 30), "OLD JOB PLC", 2400), T(date(2026, 2, 10), "TESCO", -50),
        T(date(2026, 2, 27), "OLD JOB PLC", 2400), T(date(2026, 3, 10), "TESCO", -50),
        T(date(2026, 3, 31), "OLD JOB PLC", 2400),
        T(date(2026, 4, 25), "NEW JOB LTD", 1200),   # first part-month pay at the new job
        T(date(2026, 5, 29), "NEW JOB LTD", 2600), T(date(2026, 6, 5), "TESCO", -50),
    ]
    old_only = build_cycles(txns, payer="OLD JOB PLC")
    assert old_only[-1].start == date(2026, 3, 31)          # the bug: stuck at the old job
    cs = build_cycles(txns, payer=["OLD JOB PLC", "NEW JOB LTD"])
    assert [c.start for c in cs] == [date(2026, 1, 30), date(2026, 2, 27), date(2026, 3, 31),
                                     date(2026, 4, 25), date(2026, 5, 29)]
    assert cs[-1].wage == 2600


def test_payers_are_saved_and_the_default_stays_first():
    conn = open_db(":memory:")
    assert all_payers(conn, "OLD JOB PLC") == ["OLD JOB PLC"]
    assert add_payer(conn, "  New Job Ltd ") == "NEW JOB LTD"
    add_payer(conn, "new job ltd")                           # no duplicates
    assert all_payers(conn, "OLD JOB PLC") == ["OLD JOB PLC", "NEW JOB LTD"]


def test_wage_command_adds_and_lists(tmp_path):
    db = tmp_path / "tracker.db"
    open_db(db).close()
    lines = []
    assert run.run_command(["wage", "New", "Job", "Ltd"], out=lines.append, db_path=db,
                           in_dir=tmp_path, wage_payer="OLD JOB PLC") is True
    assert any("NEW JOB LTD" in l for l in lines)
    lines.clear()
    run.run_command(["wage"], out=lines.append, db_path=db, in_dir=tmp_path, wage_payer="OLD JOB PLC")
    text = "\n".join(lines)
    assert "OLD JOB PLC" in text and "NEW JOB LTD" in text
    assert all_payers(open_db(db), "OLD JOB PLC") == ["OLD JOB PLC", "NEW JOB LTD"]
