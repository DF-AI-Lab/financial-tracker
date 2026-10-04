"""No. 4 (user, 3 Oct 2026): a new job spotted by itself. When no wage from a known payer has come for 35+ days
but another payer has paid in 500 or more in 2+ different months since, ask once: 'Is X your new job?'.
Yes = saved as a wage payer (like `run.py wage NAME`); No = not asked about again. Fake data only."""
from datetime import date

from fintrack.models import Txn
from fintrack.newjob import new_job_candidates
from fintrack.pagequestions import answer, questions
from fintrack.store import open_db
from fintrack.wages import all_payers

OLD = "ACME MOTORS PLC"


def wage(m, d, who, amt):
    return Txn(date(2024, m, d), "CR", who, "", amt)


def txns(last_old_month=3):
    tx = [wage(m, 28, OLD, 2000.0) for m in range(1, last_old_month + 1)]
    tx += [wage(m, 28, "PENDRAGON PAYROLL 0042", 2600.0) for m in (4, 5, 6)]
    tx += [wage(5, 10, "HMRC REFUND", 600.0)]                                  # only once: not a job
    tx += [Txn(date(2024, 6, 30), "VIS", "SHOP", "", -5.0)]                  # statements end 30 Jun
    return sorted(tx, key=lambda t: t.date)


def test_a_new_payer_after_the_wage_stops_is_found():
    c = new_job_candidates(txns(), [OLD], [])
    assert [(x["name"], x["count"]) for x in c] == [("PENDRAGON PAYROLL", 3)]
    assert c[0]["usual"] == 2600.0 and c[0]["first"] == date(2024, 4, 28)


def test_nothing_while_the_old_wage_still_comes():
    tx = txns(last_old_month=6)
    assert new_job_candidates(tx, [OLD], []) == []


def test_declined_and_known_payers_are_not_asked():
    assert new_job_candidates(txns(), [OLD], ["PENDRAGON PAYROLL"]) == []
    assert new_job_candidates(txns(), [OLD, "PENDRAGON PAYROLL"], []) == []


def test_yes_saves_the_new_payer_and_no_is_remembered():
    conn = open_db(":memory:")
    q = [x for x in questions(conn, txns(), [], payers=[OLD]) if x["type"] == "job"]
    assert len(q) == 1 and q[0]["name"] == "PENDRAGON PAYROLL"
    answer(conn, {"type": "job", "name": "PENDRAGON PAYROLL", "yes": True}, txns(), [], payers=[OLD])
    assert all_payers(conn, OLD) == [OLD, "PENDRAGON PAYROLL"]
    conn2 = open_db(":memory:")
    answer(conn2, {"type": "job", "name": "PENDRAGON PAYROLL", "yes": False}, txns(), [], payers=[OLD])
    assert all_payers(conn2, OLD) == [OLD]
    assert [x for x in questions(conn2, txns(), [], payers=[OLD]) if x["type"] == "job"] == []
    assert answer(conn2, {"type": "job", "name": "MADE UP", "yes": True}, txns(), [], payers=[OLD]) is False
