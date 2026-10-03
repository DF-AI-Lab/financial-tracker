"""Step 9 of SPEC.md: the home page (Flask, on this PC only). Fake data only."""
import shutil
from datetime import date

import pytest

import run
from fintrack.common import analyse
from fintrack.cycles import build_cycles
from fintrack.home import home_data
from fintrack.spare import pay_block
from fintrack.store import get_items, get_rules, get_spends, get_value, load_txns, open_db, set_value
from fintrack.where import format_where, where_did_it_go, where_summary
from tests.conftest import DATA
from tests.test_where import cycles as where_cycles

flask = pytest.importorskip("flask")
import web  # noqa: E402

ACME = "ACME MOTORS PLC"


@pytest.fixture
def db(tmp_path):
    inbox = tmp_path / "statements"
    inbox.mkdir()
    for n in ("statement_2024_08.pdf", "statement_2024_09.pdf", "statement_2024_10.pdf"):
        shutil.copy(DATA / n, inbox / n)
    run.main(in_dir=inbox, out_dir=tmp_path / "output", ask=lambda p: "2500", wage_payer=ACME, ask_items=lambda p: "")
    return tmp_path / "tracker.db"


@pytest.fixture
def client(db):
    app = web.create_app(db, wage_payer=ACME, today=date(2024, 10, 25))
    app.testing = True
    return app.test_client()


def money(x):
    return f"£{x:,.2f}" if x >= 0 else f"-£{-x:,.2f}"


# ---- where.py: one summary shared by the terminal and the page ------------------------------------

def test_where_summary():
    s = where_summary(where_did_it_go(where_cycles()))
    assert (s["kind"], s["amount"]) == ("missing", pytest.approx(1514))
    assert [(l["n"], l["text"], l["value"], l["note"]) for l in s["lines"]] == [
        (1, "One-off: CURRYS", pytest.approx(1299), "(2 May)"),
        (2, "Food shopping over normal", pytest.approx(180), "(280.00 vs usual 100.00)"),
        (3, "Moved out (Savings/Transfers)", pytest.approx(100), "(100.00 vs usually 0.00)"),
        (4, "ENERGY CO went up", pytest.approx(30), "(110.00 vs 80.00 last month)"),
        (5, "Small bits (under 20 each)", pytest.approx(5), "")]
    assert [t.description for t in s["lines"][0]["txns"]] == ["CURRYS"]
    assert [(a["text"], a["value"], a["note"]) for a in s["against"]] == [
        ("Spent LESS than normal", pytest.approx(-40), "(Car -40.00)"), ("Other money in", pytest.approx(-60), "")]
    assert where_summary(where_did_it_go(where_cycles(good=True)))["kind"] == "extra"
    assert where_summary(None) is None
    assert format_where(where_did_it_go(where_cycles()))[1] == f"  1. {'One-off: CURRYS':<34}{'1,299.00':>10}   (2 May)"


# ---- home_data: everything the page shows ---------------------------------------------------------

def test_home_data_matches_the_terminal_numbers(db):
    conn = open_db(db)
    d = home_data(conn, wage_payer=ACME)
    txns = sorted(load_txns(conn), key=lambda t: t.date)
    cs = build_cycles(txns, payer=ACME)
    a = analyse(cs, answers=get_items(conn), rules=get_rules(conn))
    want = pay_block(cs, a, 2500.0)                                   # 2,500 = the pay remembered by run.py
    assert d["ready"] is True
    assert d["pay"]["wage"] == 2500.0 and d["pay"]["spare"] == pytest.approx(want["spare"])
    assert d["pay"]["left_usual"] == pytest.approx(want["left_usual"])
    assert d["last"] is not None and d["where"] is not None
    assert d["categories"]["rows"] and "active" in d["subs"]
    assert d["spends"] == [] and d["left_now"] == pytest.approx(d["money_for_spending"])
    assert d["statements_to"] == max(t.date for t in txns)
    assert [p["name"] for p in d["periods"]][:2] == ["Last 6 months", "Last 12 months"]


def test_home_data_uses_the_wage_given_and_the_typed_spends(db):
    conn = open_db(db)
    base = home_data(conn, wage_payer=ACME)
    d = home_data(conn, wage_payer=ACME, wage=3500.0)
    assert d["pay"]["spare"] == pytest.approx(base["pay"]["spare"] + 1000)
    from fintrack.store import add_spend
    add_spend(conn, date(2024, 10, 20), 40.0, "Cash", "Cash")
    d = home_data(conn, wage_payer=ACME)
    assert [s["name"] for s in d["spends"]] == ["Cash"]
    assert d["left_now"] == pytest.approx(d["money_for_spending"] - 40)


def test_home_data_without_paydays(tmp_path):
    d = home_data(open_db(tmp_path / "empty.db"), wage_payer=ACME)
    assert d["ready"] is False


# ---- the page -----------------------------------------------------------------------------------

def test_page_shows_spare_cash_first(client, db):
    html = client.get("/").get_data(as_text=True)
    d = home_data(open_db(db), wage_payer=ACME)
    assert "Spare cash" in html and money(d["pay"]["spare"]) in html
    assert html.index("Spare cash") < html.index("Bills") < html.index("Subscriptions")
    for section in ("Last month", "Where did", "Spending by category", "Add a spend", "6 months, 12 months and this year"):
        assert section in html, section
    assert "127.0.0.1" not in html                    # nothing about servers on the page


def test_pay_box_saves_the_pay(client, db):
    r = client.post("/pay", data={"pay": "£3,000"})
    assert r.status_code == 303
    assert get_value(open_db(db), "pay") == "3000.0"
    assert money(3000) in client.get("/").get_data(as_text=True)


def test_bad_pay_is_not_saved(client, db):
    r = client.post("/pay", data={"pay": "abc"}, follow_redirects=True)
    assert "Sorry, I could not read that as money." in r.get_data(as_text=True)
    assert get_value(open_db(db), "pay") == "2500.0"


def test_add_and_remove_a_spend(client, db):
    r = client.post("/add", data={"amount": "12.50", "name": "Costa coffee"})
    assert r.status_code == 303
    spends = get_spends(open_db(db))
    assert [(s["date"], s["amount"], s["name"]) for s in spends] == [(date(2024, 10, 25), 12.5, "Costa coffee")]
    assert "Costa coffee" in client.get("/").get_data(as_text=True)
    client.post("/remove", data={"id": str(spends[0]["id"])})
    assert get_spends(open_db(db)) == []


def test_bad_spend_is_not_saved(client, db):
    r = client.post("/add", data={"amount": "lots", "name": "Costa"}, follow_redirects=True)
    assert "Sorry, type an amount and a name, e.g. 12.50 and Costa." in r.get_data(as_text=True)
    assert get_spends(open_db(db)) == []


def test_page_without_data(tmp_path):
    app = web.create_app(tmp_path / "empty.db", wage_payer=ACME)
    html = app.test_client().get("/").get_data(as_text=True)
    assert "Run run.py first" in html


def test_last_month_spending_starts_with_the_bills(client, db):
    html = client.get("/").get_data(as_text=True)
    card = html.split("Last month's spending")[1].split("</table>")[0]
    assert "Bills (rent, direct debits, standing orders)" in card
    d = home_data(open_db(db), wage_payer=ACME)
    last_bills = sum(b["last"] for b in d["pay"]["bills"])
    assert money(last_bills + d["pay"]["spending_last"]) in card       # the total now includes the bills


# ---- 3 Oct 2026 changes: bills under 'Add a spend', diff column, change a bill, subscriptions ------

def test_bills_card_is_right_under_add_a_spend(client):
    html = client.get("/").get_data(as_text=True)
    assert html.index("Add a spend") < html.index("Bills (every month)") < html.index("Last month's spending")


def test_avg_then_last_month_then_diff_everywhere(client):
    html = client.get("/").get_data(as_text=True)
    for card in ("Last month's spending", "Bills (every month)"):
        part = html[html.index(card):]
        assert part.index("-mth avg") < part.index("Last month</th>") < part.index("Diff</th>"), card


def test_change_a_bill_for_this_cycle(client, db):
    d = home_data(open_db(db), wage_payer=ACME)
    bill = d["pay"]["bills"][0]
    r = client.post("/bill", data={"key": bill["key"], "amount": "999"})
    assert r.status_code == 303
    d2 = home_data(open_db(db), wage_payer=ACME)
    assert d2["pay"]["spare"] == pytest.approx(d["pay"]["spare"] - (999 - bill["used"]))
    assert d2["left_now"] == pytest.approx(d2["pay"]["spare"])
    assert money(999) in client.get("/").get_data(as_text=True)
    client.post("/bill", data={"key": bill["key"], "amount": ""})          # the x puts it back
    assert home_data(open_db(db), wage_payer=ACME)["pay"]["spare"] == pytest.approx(d["pay"]["spare"])
    r = client.post("/bill", data={"key": bill["key"], "amount": "abc"}, follow_redirects=True)
    assert "Sorry, I could not read that as money." in r.get_data(as_text=True)


def test_subscriptions_columns(client):
    html = client.get("/").get_data(as_text=True)
    part = html[html.index("Subscriptions"):]
    assert "Monthly price" in part and "Last 12 months" in part and "This year" in part
    assert "Paid so far" not in part


def test_left_from_last_month_box(client, db):
    base = home_data(open_db(db), wage_payer=ACME)
    assert client.post("/left", data={"amount": "220"}).status_code == 303
    d = home_data(open_db(db), wage_payer=ACME)
    assert d["pay"]["spare"] == pytest.approx(base["pay"]["spare"] + 220)
    assert d["left_now"] == pytest.approx(d["pay"]["spare"])
    html = client.get("/").get_data(as_text=True)
    assert "+ left £220.00" in html and "Left from last month" in html
    client.post("/left", data={"amount": ""})                                # the x
    assert home_data(open_db(db), wage_payer=ACME)["pay"]["spare"] == pytest.approx(base["pay"]["spare"])
    r = client.post("/left", data={"amount": "abc"}, follow_redirects=True)
    assert "Sorry, I could not read that as money." in r.get_data(as_text=True)


def test_bill_change_from_the_page_script_does_not_reload(client, db):
    # 3 Oct 2026: typing in a bill box updates the page as you type and saves quietly in the background
    key = home_data(open_db(db), wage_payer=ACME)["pay"]["bills"][0]["key"]
    r = client.post("/bill", data={"key": key, "amount": "123"}, headers={"X-Requested-With": "fetch"})
    assert r.status_code == 204
    assert any(b["changed"] and b["used"] == 123 for b in home_data(open_db(db), wage_payer=ACME)["pay"]["bills"])
    html = client.get("/").get_data(as_text=True)
    assert 'data-key="' in html and 'id="spare-big"' in html


# ---- 3 Oct 2026: drag cards and rows, rename rows (page only, kept for good) ----------------------

from fintrack.layout import save_order, set_name


def test_saved_row_order_and_names_are_used(db):
    conn = open_db(db)
    d = home_data(conn, wage_payer=ACME)
    ids = [b["id"] for b in d["pay"]["bills"]]
    save_order(conn, "bills", ids[::-1][:2])                          # two moved to the top, the rest after
    set_name(conn, ids[0], "My Rent")
    d2 = home_data(conn, wage_payer=ACME)
    got = [b["id"] for b in d2["pay"]["bills"]]
    assert got[:2] == ids[::-1][:2] and sorted(got) == sorted(ids)
    first = next(b for b in d2["pay"]["bills"] if b["id"] == ids[0])
    assert first["name"] == "My Rent" and first["orig"] == d["pay"]["bills"][0]["name"]
    assert d2["pay"]["spare"] == pytest.approx(d["pay"]["spare"])    # nothing but the look changes


def test_layout_routes(client, db):
    r = client.post("/layout", json={"sort": "cards", "ids": ["subs", "bills"]})
    assert r.status_code == 204
    html = client.get("/").get_data(as_text=True)
    assert html.index('data-card="subs"') < html.index('data-card="bills"')   # saved card order is used
    key = home_data(open_db(db), wage_payer=ACME)["pay"]["bills"][0]["id"]
    assert client.post("/name", json={"id": key, "name": "Phone"}).status_code == 204
    assert ">Phone<" in client.get("/").get_data(as_text=True)
    assert client.post("/layout/reset").status_code == 303
    html = client.get("/").get_data(as_text=True)
    assert html.index('data-card="bills"') < html.index('data-card="subs"')
    assert ">Phone<" in html                                           # reset order keeps the names
    assert client.post("/layout", json={"sort": "x"}).status_code == 400
