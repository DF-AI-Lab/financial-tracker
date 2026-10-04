"""New and stopped bills (user, 4 Oct 2026, DECISIONS.md 'new and stopped bills'). Fake data only.

test_spare's data: wages on 28 Jan/Feb/Mar/Apr -> 3 finished cycles + the running one (from 28 Apr);
rent 500 (SO) and energy (DD) are paid in every cycle, also in the running one (1 and 2 May)."""
import shutil
from datetime import date

import pytest

import run
from fintrack import phone
from fintrack.common import analyse
from fintrack.cycles import build_cycles
from fintrack.models import Txn
from fintrack.questions import auto_bills
from fintrack.spare import pay_block
from fintrack.store import get_items, open_db, set_item
from tests.conftest import DATA
from tests.test_spare import PAYER, fake_txns

ZOPA = "DD|ZOPA CREDIT CARDS|"
GYM = "DD|GYM CLUB|"


def block(extra, answers=None, stopped=None):
    tx = sorted(fake_txns() + extra, key=lambda t: t.date)
    cs = build_cycles(tx, payer=PAYER)
    answers = answers or {}
    return pay_block(cs, analyse(cs, answers=answers), 2500.0, items=answers, stopped=stopped)


def bill(p, key):
    return next((b for b in p["bills"] if b["key"] == key), None)


def common(label):
    return {"kind": "common", "label": label, "source": "auto"}


# ---- every DD / SO goes straight in --------------------------------------------------------------

def test_a_dd_paid_once_is_saved_as_a_bill(tmp_path):
    conn = open_db(tmp_path / "t.db")
    tx = [Txn(date(2024, 5, 14), "DD", "ZOPA CREDIT CARDS", "", -100.0),
          Txn(date(2024, 5, 15), "VIS", "CARD SHOP", "", -100.0)]
    assert auto_bills(conn, tx) == 1
    items = get_items(conn)
    assert items[ZOPA]["kind"] == "common" and "VIS|CARD SHOP|" not in items      # card payments are still asked


# ---- a new bill shows at once, even in the running cycle ----------------------------------------

def test_new_bill_in_the_running_cycle_shows_and_counts():
    p = block([Txn(date(2024, 5, 14), "DD", "ZOPA CREDIT CARDS", "", -100.0)], answers={ZOPA: common("Zopa")})
    z = bill(p, ZOPA)
    assert z is not None
    assert (z["name"], z["last"], z["used"], z["new"], z["stopped"]) == ("Zopa", pytest.approx(100), pytest.approx(100), True, False)
    assert p["bills_last"] == pytest.approx(500 + 95 + 100)          # rent + energy (95 last finished cycle) + Zopa


def test_new_bill_paid_once_in_the_last_finished_cycle_is_marked_new():
    p = block([Txn(date(2024, 4, 14), "DD", "GYM CLUB", "", -30.0),
               Txn(date(2024, 5, 4), "DD", "GYM CLUB", "", -30.0)], answers={GYM: common("Gym")})
    g = bill(p, GYM)
    assert g["new"] is True and g["stopped"] is False                # new until paid in 2 FINISHED cycles
    assert bill(p, "SO|LANDLORD|RENT")["new"] is False


# ---- a stopped bill drops out --------------------------------------------------------------------

def test_bill_not_paid_in_the_last_finished_cycle_is_stopped_and_not_counted():
    old = [Txn(date(2024, 2, 10), "DD", "OLD INSURER", "", -40.0), Txn(date(2024, 3, 10), "DD", "OLD INSURER", "", -40.0)]
    key = "DD|OLD INSURER|"
    p = block(old, answers={key: common("Old car insurance")})
    o = bill(p, key)
    assert o is not None and o["stopped"] is True and o["used"] == 0
    assert p["bills_last"] == pytest.approx(sum(b["used"] for b in p["bills"]))
    assert key not in [b["key"] for b in p["bills"] if not b["stopped"]]
    assert p["bills_avg"] == pytest.approx(sum(b["avg"] for b in p["bills"] if not b["stopped"]))


def test_bill_late_but_paid_in_the_running_cycle_is_not_stopped():
    tx = [Txn(date(2024, 2, 10), "DD", "LATE CO", "", -40.0), Txn(date(2024, 3, 10), "DD", "LATE CO", "", -40.0),
          Txn(date(2024, 5, 5), "DD", "LATE CO", "", -40.0)]
    p = block(tx, answers={"DD|LATE CO|": common("Late co")})
    assert bill(p, "DD|LATE CO|")["stopped"] is False


def test_tapped_stopped_drops_a_bill_until_it_is_paid_again():
    p = block([], stopped={"DD|ENERGY CO|": "2024-05-03"})
    e = bill(p, "DD|ENERGY CO|")
    assert e["stopped"] is True and e["used"] == 0                    # last paid 2 May, before the tap
    p = block([Txn(date(2024, 5, 20), "DD", "ENERGY CO", "", -80.0)], stopped={"DD|ENERGY CO|": "2024-05-03"})
    assert bill(p, "DD|ENERGY CO|")["stopped"] is False                # paid again after the tap


def test_stopped_kept_in_the_database(tmp_path):
    from fintrack.billchange import get_stopped, set_stopped
    conn = open_db(tmp_path / "t.db")
    set_stopped(conn, "DD|ENERGY CO|", True, date(2024, 5, 3))
    assert get_stopped(conn) == {"DD|ENERGY CO|": "2024-05-03"}
    set_stopped(conn, "DD|ENERGY CO|", False, date(2024, 5, 4))
    assert get_stopped(conn) == {}


# ---- the page and the phone ----------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    inbox = tmp_path / "statements"
    inbox.mkdir()
    for n in ("statement_2024_08.pdf", "statement_2024_09.pdf", "statement_2024_10.pdf"):
        shutil.copy(DATA / n, inbox / n)
    run.main(in_dir=inbox, out_dir=tmp_path / "output", ask=lambda p: "2500", wage_payer="ACME MOTORS PLC",
             ask_items=lambda p: "")
    return tmp_path / "tracker.db"


def test_pc_page_stopped_button(db):
    pytest.importorskip("flask")
    import web
    from fintrack.billchange import get_stopped
    c = open_db(db)
    d = web.home_data(c, wage_payer="ACME MOTORS PLC", today=date(2024, 10, 25))
    key = d["pay"]["bills"][0]["key"]
    app = web.create_app(db, wage_payer="ACME MOTORS PLC", today=date(2024, 10, 25))
    app.testing = True
    client = app.test_client()
    assert 'class="small stopbtn"' in client.get("/").data.decode()
    client.post("/stopped", data={"key": key, "stopped": "1"})
    assert key in get_stopped(open_db(db))
    page = client.get("/").data.decode()
    assert "🛑 stopped" in page
    client.post("/stopped", data={"key": key, "stopped": "0"})
    assert key not in get_stopped(open_db(db))


def test_phone_can_tap_stopped(db):
    from fintrack.billchange import get_stopped
    import web
    c = open_db(db)
    key = web.home_data(c, wage_payer="ACME MOTORS PLC", today=date(2024, 10, 25))["pay"]["bills"][0]["key"]
    assert phone.apply_changes(c, [{"cid": "s", "type": "bill", "key": key, "stopped": True}],
                               wage_payer="ACME MOTORS PLC") == 1
    assert key in get_stopped(c)
    phone.apply_changes(c, [{"cid": "t", "type": "bill", "key": key, "stopped": False}], wage_payer="ACME MOTORS PLC")
    assert key not in get_stopped(c)
