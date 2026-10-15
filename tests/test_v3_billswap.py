"""v3 (14 Oct 2026): a new payment can REPLACE a bill you already have (e.g. a new car insurer). Fake data only.

Data: tests.test_spare (wages 28 Jan/Feb/Mar/Apr -> 3 finished cycles + the running one from 28 Apr) plus
OLD INSURER (DD 40) on 10 Feb, 10 Mar, 10 Apr and the new AVIVA (DD 27.10) from 5 Apr (and 5 May).
Statement 1 = up to 31 Mar (AVIVA not in it yet), statement 2 = from 1 Apr."""
import json
from datetime import date

import pytest

from fintrack.common import analyse
from fintrack.cycles import build_cycles
from fintrack.home import home_data, txns_and_paydays
from fintrack.models import Statement, Txn
from fintrack.pagequestions import answer, questions
from fintrack.spare import pay_block
from fintrack.store import get_categories, get_items, get_rules, get_value, import_statement, open_db
from tests.test_spare import PAYER, fake_txns

AVIVA = "DD|AVIVA|"
OLD = "DD|OLD INSURER|"
OLD_BILL = "Old Insurer"          # auto_bills' label for OLD INSURER = the bill's key
NEW_BILL = "Aviva"


def extra():
    return [Txn(date(2024, 2, 10), "DD", "OLD INSURER", "", -40.0),
            Txn(date(2024, 3, 10), "DD", "OLD INSURER", "", -40.0),
            Txn(date(2024, 4, 5), "DD", "AVIVA", "", -27.10),
            Txn(date(2024, 4, 10), "DD", "OLD INSURER", "", -40.0),     # after the swap: not counted any more
            Txn(date(2024, 5, 5), "DD", "AVIVA", "", -27.10)]


def add_statement(conn, txns, start, end):
    import_statement(conn, Statement(f"s{start}.pdf", start, end, 0.0, 0.0, txns), [])


def first_db(path):
    """Statement 1 only, and the page opened once (auto bills saved, nothing asked)."""
    conn = open_db(path)
    tx = sorted(fake_txns() + extra(), key=lambda t: t.date)
    add_statement(conn, [t for t in tx if t.date <= date(2024, 3, 31)], date(2024, 1, 20), date(2024, 3, 31))
    return conn


def second_statement(conn):
    tx = sorted(fake_txns() + extra(), key=lambda t: t.date)
    add_statement(conn, [t for t in tx if t.date > date(2024, 3, 31)], date(2024, 4, 1), date(2024, 5, 5))


def newbills(d):
    return [q for q in d["more"] if q["type"] == "newbill"]


def bill(d, key):
    return next((b for b in d["pay"]["bills"] if b["key"] == key), None)


def ask(conn, a):
    txns, paydays, payers = txns_and_paydays(conn, PAYER)
    return answer(conn, a, txns, paydays, payers=payers)


@pytest.fixture
def conn(tmp_path):
    c = first_db(tmp_path / "tracker.db")
    d = home_data(c, wage_payer=PAYER)
    assert d["ready"] and newbills(d) == []          # the first run asks nothing for the bills already there
    second_statement(c)
    return c


# ---- the question ----------------------------------------------------------------------------------

def test_first_run_asks_nothing_for_existing_auto_bills(tmp_path):
    c = first_db(tmp_path / "t.db")
    d = home_data(c, wage_payer=PAYER)
    assert newbills(d) == []
    assert OLD in json.loads(get_value(c, "newbill_seen"))
    assert newbills(home_data(c, wage_payer=PAYER)) == []


def test_a_new_dd_is_asked_once_with_the_current_bills(conn):
    d = home_data(conn, wage_payer=PAYER)
    q = newbills(d)
    assert len(q) == 1 and q[0]["key"] == AVIVA and q[0]["name"] == "AVIVA" and q[0]["amount"] == pytest.approx(27.10)
    keys = [b["key"] for b in q[0]["bills"]]
    assert OLD_BILL in keys and NEW_BILL not in keys
    assert len(newbills(home_data(conn, wage_payer=PAYER))) == 1     # still waiting until answered


def test_answer_new_bill_stops_the_question(conn):
    home_data(conn, wage_payer=PAYER)
    assert ask(conn, {"type": "newbill", "key": AVIVA, "into": ""}) is True
    assert get_items(conn)[AVIVA]["label"] == NEW_BILL                  # nothing joined
    d = home_data(conn, wage_payer=PAYER)
    assert newbills(d) == []
    assert bill(d, NEW_BILL) is not None and bill(d, OLD_BILL) is not None
    assert ask(conn, {"type": "newbill", "key": AVIVA, "into": ""}) is False   # not open any more


def test_answer_replaces_joins_the_bill(conn):
    before = home_data(conn, wage_payer=PAYER)
    assert bill(before, OLD_BILL)["last"] == pytest.approx(40) and bill(before, NEW_BILL)["last"] == pytest.approx(27.10)
    cat = get_categories(conn)[AVIVA]
    assert ask(conn, {"type": "newbill", "key": AVIVA, "into": OLD_BILL}) is True
    items = get_items(conn)
    assert items[AVIVA]["label"] == OLD_BILL
    assert get_categories(conn)[AVIVA] == get_categories(conn)[OLD]
    swaps = json.loads(get_value(conn, "bill_swaps"))
    assert swaps == [{"bill": OLD_BILL, "new": [AVIVA], "old": [OLD], "from": "2024-04-05",
                      "labels": {AVIVA: NEW_BILL}, "cats": {AVIVA: cat}}]
    d = home_data(conn, wage_payer=PAYER)
    assert newbills(d) == []
    assert bill(d, NEW_BILL) is None                                     # one row, the old name
    b = bill(d, OLD_BILL)
    assert b["last"] == pytest.approx(27.10)                             # only the new payee in the swap month
    assert b["avg"] == pytest.approx((40 + 40 + 27.10) / 3)              # history from both
    assert b["new"] is False and b["stopped"] is False
    assert d["pay"]["bills_last"] == pytest.approx(before["pay"]["bills_last"] - 40)
    assert d["last"]["money_out"] == pytest.approx(before["last"]["money_out"])    # other cards unchanged


def test_replaces_must_pick_a_real_bill(conn):
    home_data(conn, wage_payer=PAYER)
    assert ask(conn, {"type": "newbill", "key": AVIVA, "into": "No Such Bill"}) is False
    assert get_items(conn)[AVIVA]["label"] == NEW_BILL
    assert len(newbills(home_data(conn, wage_payer=PAYER))) == 1


def test_no_swaps_pay_block_is_unchanged(conn):
    d = home_data(conn, wage_payer=PAYER)
    txns, paydays, payers = txns_and_paydays(conn, PAYER)
    cs = build_cycles(txns, payer=payers)
    items = get_items(conn)
    p = pay_block(cs, analyse(cs, answers=items, rules=get_rules(conn)), d["pay"]["wage"],
                  categories=get_categories(conn), items=items)
    assert d["pay"]["bills_last"] == pytest.approx(p["bills_last"])
    assert d["pay"]["bills_avg"] == pytest.approx(p["bills_avg"])
    assert d["pay"]["spare"] == pytest.approx(p["spare"])
    assert sorted((b["key"], round(b["used"], 2)) for b in d["pay"]["bills"]) == \
        sorted((b["key"], round(b["used"], 2)) for b in p["bills"])


def test_other_questions_still_work(conn):
    home_data(conn, wage_payer=PAYER)
    txns, paydays, payers = txns_and_paydays(conn, PAYER)
    assert {q["type"] for q in questions(conn, txns, paydays, payers=payers)} == {"newbill"}
    assert answer(conn, {"type": "nonsense"}, txns, paydays) is False


# ---- the website: join from the ⋯ menu, split back out -----------------------------------------

@pytest.fixture
def client(tmp_path):
    pytest.importorskip("flask")
    import v3app
    data = tmp_path / "v3data"
    data.mkdir()
    c = first_db(data / "tracker.db")
    home_data(c, wage_payer=PAYER)
    second_statement(c)
    home_data(c, wage_payer=PAYER)
    c.close()
    app = v3app.make_app(data, wage_payer=PAYER, updater=lambda: {"changed": [], "version": "t"},
                         restart=lambda: None)
    app.testing = True
    cl = app.test_client()
    try:
        from fintrack.v3 import auth
        auth.sign_in_for_tests(app, cl)
    except ImportError:                       # no sign-in yet
        pass
    cl.db = data / "tracker.db"
    return cl


def test_page_shows_the_question(client):
    html = client.get("/").get_data(as_text=True)
    assert "AVIVA" in html and "what is it?" in html and "New bill" in html and "Replaces" in html


def test_join_from_the_menu_then_split_back_out(client):
    c = open_db(client.db)
    before = home_data(c, wage_payer=PAYER)
    cat = get_categories(c)[AVIVA]
    r = client.post("/bill/join", data={"key": NEW_BILL, "into": OLD_BILL})
    assert r.status_code == 303 and r.headers["Location"].endswith("/")
    d = home_data(c, wage_payer=PAYER)
    assert bill(d, NEW_BILL) is None
    b = bill(d, OLD_BILL)
    assert b["last"] == pytest.approx(27.10) and b["swapped"] is True
    assert json.loads(get_value(c, "bill_swaps"))[0]["from"] == "2024-04-05"   # first payment of the joined bill
    assert 'Split back out' in client.get("/").get_data(as_text=True)

    r = client.post("/bill/split", data={"key": OLD_BILL}, headers={"X-Requested-With": "fetch"})
    assert r.status_code == 204
    assert get_items(c)[AVIVA]["label"] == NEW_BILL
    assert get_categories(c)[AVIVA] == cat
    assert json.loads(get_value(c, "bill_swaps")) == []
    after = home_data(c, wage_payer=PAYER)
    assert bill(after, NEW_BILL)["last"] == pytest.approx(27.10) and bill(after, OLD_BILL)["last"] == pytest.approx(40)
    assert after["pay"]["bills_last"] == pytest.approx(before["pay"]["bills_last"])


def test_split_restores_the_old_category(client):
    c = open_db(client.db)
    from fintrack.store import set_category
    set_category(c, AVIVA, "Car")
    set_category(c, OLD, "Insurance")
    client.post("/bill/join", data={"key": NEW_BILL, "into": OLD_BILL})
    assert get_categories(c)[AVIVA] == "Insurance"
    client.post("/bill/split", data={"key": OLD_BILL})
    assert get_categories(c)[AVIVA] == "Car" and get_items(c)[AVIVA]["label"] == NEW_BILL


def test_join_refuses_nonsense(client):
    c = open_db(client.db)
    assert client.post("/bill/join", data={"key": NEW_BILL, "into": NEW_BILL}).status_code == 303
    assert client.post("/bill/join", data={"key": "Nope", "into": OLD_BILL}).status_code == 303
    assert client.post("/bill/split", data={"key": OLD_BILL}).status_code == 303     # nothing to split
    assert get_items(c)[AVIVA]["label"] == NEW_BILL and get_value(c, "bill_swaps") in (None, "[]")


def test_old_payment_earlier_in_the_swap_cycle_is_not_counted(tmp_path):
    from fintrack.store import set_value
    from fintrack.v3.billswap import bill_txns, cut_day
    c = open_db(tmp_path / "t.db")
    set_value(c, "bill_swaps", json.dumps([{"bill": OLD_BILL, "new": [AVIVA], "old": [OLD], "from": "2024-04-05",
                                             "labels": {}, "cats": {}}]))
    tx = [Txn(date(2024, 3, 10), "DD", "OLD INSURER", "", -40.0),
          Txn(date(2024, 4, 1), "DD", "OLD INSURER", "", -40.0),        # same pay cycle as the swap, but before it
          Txn(date(2024, 4, 5), "DD", "AVIVA", "", -27.10)]
    paydays = [date(2024, 2, 28), date(2024, 3, 28), date(2024, 4, 28)]
    assert cut_day(date(2024, 4, 5), paydays) == date(2024, 3, 28)
    kept = bill_txns(c, tx, paydays)
    assert [(t.date, t.description) for t in kept] == [(date(2024, 3, 10), "OLD INSURER"), (date(2024, 4, 5), "AVIVA")]
    assert cut_day(date(2024, 4, 5), []) == date(2024, 4, 5)                  # no paydays: from the day itself
