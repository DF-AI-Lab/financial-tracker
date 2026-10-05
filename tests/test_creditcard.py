"""Credit card (user, 5 Oct 2026): Zopa card, 500 limit, spends typed in by hand and taken off again.
Two half-size tiles next to the pay box: credit card used and free. Fake data only."""
import shutil
from datetime import date

import pytest

import run
from fintrack import creditcard as cc
from fintrack import phone
from fintrack.store import open_db
from tests.conftest import DATA

flask = pytest.importorskip("flask")
import web  # noqa: E402
from cloud import flask_app  # noqa: E402

ACME = "ACME MOTORS PLC"


@pytest.fixture
def conn(tmp_path):
    return open_db(tmp_path / "t.db")


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


def test_empty_card_is_500_free(conn):
    card = cc.get_card(conn)
    assert card["limit"] == 500.0 and card["used"] == 0 and card["free"] == 500.0 and card["items"] == []


def test_spends_add_up_and_paid_off_takes_away(conn):
    cc.add_card(conn, date(2026, 10, 1), 120.0, "Tyres")
    cc.add_card(conn, date(2026, 10, 2), 30.5, "Tesco")
    cc.add_card(conn, date(2026, 10, 3), -100.0, "Paid off")
    card = cc.get_card(conn)
    assert [(i["name"], i["amount"], i["date"]) for i in card["items"]] == [
        ("Tyres", 120.0, date(2026, 10, 1)), ("Tesco", 30.5, date(2026, 10, 2)), ("Paid off", -100.0, date(2026, 10, 3))]
    assert card["used"] == pytest.approx(50.5) and card["free"] == pytest.approx(449.5)


def test_remove_one_and_ids_are_not_reused(conn):
    cc.add_card(conn, date(2026, 10, 1), 10.0, "A")
    cc.add_card(conn, date(2026, 10, 1), 20.0, "B")
    first = cc.get_card(conn)["items"][0]["id"]
    assert cc.remove_card(conn, first) is True
    assert cc.remove_card(conn, 999) is False
    cc.add_card(conn, date(2026, 10, 1), 5.0, "C")
    ids = [i["id"] for i in cc.get_card(conn)["items"]]
    assert first not in ids and len(set(ids)) == 2
    assert cc.get_card(conn)["used"] == pytest.approx(25.0)


def test_limit_can_change(conn):
    cc.add_card(conn, date(2026, 10, 1), 100.0, "A")
    cc.set_limit(conn, 750)
    card = cc.get_card(conn)
    assert card["limit"] == 750.0 and card["free"] == pytest.approx(650.0)


def test_page_shows_the_tiles_and_the_card(client):
    page = client.get("/").data.decode()
    assert "Zopa used" in page and "Zopa free" in page
    assert "💳 Credit card" in page
    assert 'action="/card/add"' in page


def test_page_add_paid_and_remove(client, db):
    client.post("/card/add", data={"amount": "120", "name": "Tyres"})
    client.post("/card/add", data={"amount": "100", "name": "", "paid": "1"})      # paid off: name may be empty
    card = cc.get_card(open_db(db))
    assert [(i["name"], i["amount"]) for i in card["items"]] == [("Tyres", 120.0), ("Paid off", -100.0)]
    assert card["used"] == pytest.approx(20.0)
    page = client.get("/").data.decode()
    assert "£20.00" in page and "£480.00" in page
    client.post("/card/remove", data={"id": str(card["items"][0]["id"])})
    assert cc.get_card(open_db(db))["used"] == pytest.approx(-100.0)
    client.post("/card/limit", data={"amount": "600"})
    assert cc.get_card(open_db(db))["limit"] == 600.0


def test_page_refuses_bad_amounts(client, db):
    r = client.post("/card/add", data={"amount": "abc", "name": "X"})
    assert r.status_code == 303 and "error=" in r.headers["Location"]
    client.post("/card/add", data={"amount": "5", "name": ""})                  # a spend needs a name
    client.post("/card/limit", data={"amount": "-5"})
    card = cc.get_card(open_db(db))
    assert card["items"] == [] and card["limit"] == 500.0


def test_phone_card_changes(db):
    c = open_db(db)
    n = phone.apply_changes(c, [
        {"cid": "1", "type": "card", "action": "add", "date": "2026-10-04", "amount": 40.0, "name": "Shell"},
        {"cid": "2", "type": "card", "action": "add", "date": "2026-10-04", "amount": -10.0, "name": "Paid off"},
        {"cid": "3", "type": "card", "action": "add", "date": "2026-10-04", "amount": 0, "name": "Zero"},
        {"cid": "4", "type": "card", "action": "limit", "amount": 550.0},
    ], wage_payer=ACME)
    assert n == 3
    card = cc.get_card(c)
    assert card["used"] == pytest.approx(30.0) and card["limit"] == 550.0
    first = card["items"][0]["id"]
    assert phone.apply_changes(c, [{"cid": "5", "type": "card", "action": "remove", "id": first}], wage_payer=ACME) == 1
    assert cc.get_card(c)["used"] == pytest.approx(-10.0)


def test_phone_page_carries_the_card(db):
    import json
    cc.add_card(open_db(db), date(2024, 10, 20), 12.5, "Costa")
    html = web.phone_page(db, wage_payer=ACME, today=date(2024, 10, 25), stamp="1")
    data = json.loads(html.split('<script id="pcdata" type="application/json">')[1].split("</script>")[0])
    assert data["card"]["limit"] == 500.0
    assert [(i["name"], i["amount"]) for i in data["card"]["items"]] == [("Costa", 12.5)]
    assert 'id="cardform"' in html


def test_site_accepts_card_changes(tmp_path):
    app = flask_app.create_app(tmp_path / "online", secure=False)
    app.testing = True
    site = app.test_client()
    salt = "salt"
    site.post("/api/upload", json={"html": "<p>x</p>", "pin_salt": salt, "pin_hash": phone.hash_pin("4821", salt)},
              headers={"X-Key": "k" * 32})
    site.post("/login", data={"pin": "4821"})
    ch = {"cid": "c1", "type": "card", "action": "add", "date": "2026-10-04", "amount": 9.99, "name": "Shell"}
    assert site.post("/send", json={"changes": [ch]}).status_code == 200


def rows(conn):
    return [(r["name"], r["amount"], r["status"], r["left"]) for r in cc.get_card(conn)["rows"]]


# ---- Paid off clears the oldest first (user, 5 Oct 2026) ------------------------------------------

def test_paid_off_clears_the_oldest_first(conn):
    cc.add_card(conn, date(2026, 10, 1), 120.0, "Tyres")
    cc.add_card(conn, date(2026, 10, 2), 50.0, "Shell")
    cc.add_card(conn, date(2026, 10, 3), -100.0, "Paid off")
    assert rows(conn) == [("Tyres", 120.0, "part", 20.0), ("Shell", 50.0, "owed", 50.0),
                          ("Paid off", -100.0, "credit", 0)]
    cc.add_card(conn, date(2026, 10, 4), -30.0, "Paid off")
    assert rows(conn)[:2] == [("Tyres", 120.0, "paid", 0), ("Shell", 50.0, "part", 40.0)]
    assert cc.get_card(conn)["used"] == pytest.approx(40.0)


def test_removing_a_payment_brings_the_items_back(conn):
    cc.add_card(conn, date(2026, 10, 1), 120.0, "Tyres")
    cc.add_card(conn, date(2026, 10, 3), -120.0, "Paid off")
    assert rows(conn)[0][2] == "paid"
    pay = cc.get_card(conn)["rows"][1]
    assert pay["removable"] and not cc.get_card(conn)["rows"][0]["removable"]   # crossed out: no Remove
    cc.remove_card(conn, pay["id"])
    assert rows(conn) == [("Tyres", 120.0, "owed", 120.0)]


# ---- Used box in the card: a Correction line makes it match, the list stays -----------------------

def test_used_box_adds_a_correction(conn):
    cc.add_card(conn, date(2026, 10, 1), 120.0, "Tyres")
    cc.add_card(conn, date(2026, 10, 2), 50.0, "Shell")
    cc.set_used(conn, date(2026, 10, 5), 150.0)                  # Zopa app says 150: -20 works like a payment
    card = cc.get_card(conn)
    assert card["used"] == pytest.approx(150.0)
    assert rows(conn) == [("Tyres", 120.0, "part", 100.0), ("Shell", 50.0, "owed", 50.0),
                          ("Correction", -20.0, "credit", 0)]
    assert card["rows"][2]["removable"]
    cc.set_used(conn, date(2026, 10, 6), 180.0)                  # +30 works like a new item
    assert rows(conn)[-1] == ("Correction", 30.0, "owed", 30.0)
    cc.set_used(conn, date(2026, 10, 6), 180.0)                  # already right: nothing added
    assert len(cc.get_card(conn)["rows"]) == 4


def test_only_the_5_newest_paid_lines_are_kept_and_the_sums_stay_right(conn):
    for n in range(8):
        cc.add_card(conn, date(2026, 10, 1), 10.0, f"Item {n}")
    cc.add_card(conn, date(2026, 10, 1), 15.0, "Still owed")
    for n in range(8):
        cc.add_card(conn, date(2026, 10, 2), -10.0, "Paid off")
    card = cc.get_card(conn)
    assert card["used"] == pytest.approx(15.0) and card["free"] == pytest.approx(485.0)
    paid = [r["name"] for r in card["rows"] if r["status"] == "paid"]
    assert paid == ["Item 3", "Item 4", "Item 5", "Item 6", "Item 7"]
    assert len([r for r in card["rows"] if r["status"] == "credit"]) == 5
    assert [r for r in card["rows"] if r["name"] == "Still owed"][0]["left"] == pytest.approx(15.0)
    cc.add_card(conn, date(2026, 10, 3), -5.0, "Paid off")
    assert cc.get_card(conn)["used"] == pytest.approx(10.0)


def test_old_saved_balance_line_still_counts(conn):
    from fintrack.store import set_value
    import json
    set_value(conn, "credit_card", json.dumps({"limit": 500, "next": 2, "items": [
        {"id": 1, "date": "2026-10-05", "amount": 230.0, "name": "Balance"}]}))
    assert cc.get_card(conn)["used"] == 230.0 and rows(conn) == [("Balance", 230.0, "owed", 230.0)]


def test_page_used_box_is_in_the_card_not_the_tiles(client, db):
    page = client.get("/").data.decode()
    tiles = page.split('class="tiles toprow"')[1].split('id="dropbar"')[0]
    assert "Zopa used" in tiles and "/card/balance" not in tiles
    assert 'action="/card/balance"' in page
    client.post("/card/add", data={"amount": "120", "name": "Tyres"})
    client.post("/card/balance", data={"amount": "100"})
    card = cc.get_card(open_db(db))
    assert card["used"] == 100.0 and [r["name"] for r in card["rows"]] == ["Tyres", "Correction"]
    client.post("/card/add", data={"amount": "100", "paid": "1"})
    page = client.get("/").data.decode()
    assert "crossed" in page                                     # Tyres is paid: line through


def test_phone_balance_change_is_a_correction(db):
    c = open_db(db)
    cc.add_card(c, date(2026, 10, 1), 50.0, "Shell")
    assert phone.apply_changes(c, [{"cid": "b", "type": "card", "action": "balance", "date": "2026-10-05",
                                    "amount": 75.0}], wage_payer=ACME) == 1
    card = cc.get_card(c)
    assert card["used"] == 75.0 and [r["name"] for r in card["rows"]] == ["Shell", "Correction"]


def test_phone_page_carries_the_carry(db):
    import json
    html = web.phone_page(db, wage_payer=ACME, today=date(2024, 10, 25), stamp="1")
    data = json.loads(html.split('<script id="pcdata" type="application/json">')[1].split("</script>")[0])
    assert data["card"]["carry"] == 0


# ---- the phone follows the PC's card order and names straight away --------------------------------

@pytest.mark.parametrize("path,body", [("/layout", {"sort": "cards", "ids": ["card", "spend"]}),
                                       ("/name", {"id": "bill:X", "name": "Rent"})])
def test_moving_or_renaming_sends_a_fresh_copy_up(db, path, body):
    c = open_db(db)
    phone.connect(c, "https://x.pythonanywhere.com")
    from tests.test_phone import FakeOnline
    online = FakeOnline([])
    app = web.create_app(db, wage_payer=ACME, today=date(2024, 10, 25), phone_http=online)
    app.testing = True
    app.test_client().post(path, json=body)
    web.wait_for_push()
    assert any(name == "upload" for _, name, _ in online.calls)
