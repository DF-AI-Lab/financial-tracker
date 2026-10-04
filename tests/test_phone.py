"""Step 10 of SPEC.md: the phone copy. Fake data only, no real network."""
import json
import shutil
from datetime import date

import pytest

import run
from fintrack import phone
from fintrack.store import add_spend, get_spends, get_value, open_db
from tests.conftest import DATA

flask = pytest.importorskip("flask")
import web  # noqa: E402
from cloud import flask_app  # noqa: E402

ACME = "ACME MOTORS PLC"
KEY = "k" * 32


# ---- the online site (cloud/flask_app.py) ---------------------------------------------------------

@pytest.fixture
def site(tmp_path):
    app = flask_app.create_app(tmp_path / "online", secure=False)
    app.testing = True
    return app.test_client()


def upload(site, html="<p>MY PAGE</p>", pin="4821", key=KEY):
    salt = "salt"
    body = {"html": html, "pin_salt": salt, "pin_hash": phone.hash_pin(pin, salt) if pin else ""}
    return site.post("/api/upload", json=body, headers={"X-Key": key})


def login(site, pin="4821"):
    return site.post("/login", data={"pin": pin})


def test_site_waits_for_the_pc_first(site):
    assert b"Waiting for your PC" in site.get("/").data


def test_site_keeps_the_first_key_and_refuses_others(site):
    assert upload(site).status_code == 200
    assert upload(site, key="x" * 32).status_code == 403
    assert site.get("/api/changes", headers={"X-Key": "x" * 32}).status_code == 403
    assert site.get("/api/changes").status_code == 403


def test_site_shows_nothing_without_a_pin(site):
    upload(site, pin="")
    page = site.get("/").data
    assert b"MY PAGE" not in page and b"run.py pin" in page


def test_site_needs_the_pin(site):
    upload(site)
    assert b"MY PAGE" not in site.get("/").data
    assert b"Wrong PIN" in login(site, "1111").data
    assert b"MY PAGE" not in site.get("/").data
    login(site)
    assert b"MY PAGE" in site.get("/").data


def test_site_locks_after_5_wrong_pins(site):
    upload(site)
    for _ in range(5):
        login(site, "0000")
    assert b"Locked" in login(site).data
    assert b"MY PAGE" not in site.get("/").data


def test_phone_changes_wait_online_until_the_pc_takes_them(site):
    upload(site)
    add = {"cid": "a1", "type": "add", "date": "2026-10-04", "amount": 250, "name": "Argos"}
    rem = {"cid": "r1", "type": "remove", "id": 3, "name": "Costa", "amount": 12.5}
    assert site.post("/send", json={"changes": [add]}).status_code == 401   # not logged in
    login(site)
    assert site.post("/send", json={"changes": [add, rem]}).get_json()["changes"] == [add, rem]
    assert site.get("/pending").get_json()["changes"] == [add, rem]
    site.post("/cancel", json={"cid": "r1"})
    assert site.get("/pending").get_json()["changes"] == [add]
    assert site.get("/api/changes", headers={"X-Key": KEY}).get_json()["changes"] == [add]
    site.post("/api/clear", json={"cids": ["a1"]}, headers={"X-Key": KEY})
    assert site.get("/pending").get_json()["changes"] == []


@pytest.mark.parametrize("bad", [
    {"cid": "a", "type": "add", "date": "2026-10-04", "amount": -5, "name": "X"},
    {"cid": "a", "type": "add", "date": "2026-10-04", "amount": 5, "name": ""},
    {"cid": "a", "type": "add", "date": "not a date", "amount": 5, "name": "X"},
    {"cid": "a", "type": "remove", "id": "x", "name": "X", "amount": 5},
    {"cid": "a", "type": "rename", "name": "X"},
])
def test_site_refuses_bad_changes(site, bad):
    upload(site)
    login(site)
    assert site.post("/send", json={"changes": [bad]}).status_code == 400
    assert site.get("/pending").get_json()["changes"] == []


# ---- the PC side (fintrack/phone.py) --------------------------------------------------------------

@pytest.fixture
def conn(tmp_path):
    return open_db(tmp_path / "t.db")


def test_pin_must_be_4_to_8_digits(conn):
    assert not phone.set_pin(conn, "12a4")
    assert not phone.set_pin(conn, "123")
    assert phone.set_pin(conn, "4821")
    salt = get_value(conn, "phone_pin_salt")
    assert get_value(conn, "phone_pin_hash") == phone.hash_pin("4821", salt)
    assert "4821" not in (get_value(conn, "phone_pin_hash") + salt)


def test_connect_saves_the_address_and_a_secret_key(conn):
    phone.connect(conn, "https://darren.pythonanywhere.com/")
    url, key = phone.settings(conn)
    assert url == "https://darren.pythonanywhere.com" and len(key) >= 32
    phone.connect(conn, "https://other.pythonanywhere.com")
    assert phone.settings(conn)[1] == key            # same key, new address


def test_no_phone_set_up_means_no_network(conn):
    def boom(*a, **k):
        raise AssertionError("no network call expected")
    assert phone.fetch_changes(conn, http=boom) == []
    assert phone.upload(conn, "<p>x</p>", http=boom) is False


def test_offline_returns_none(conn):
    phone.connect(conn, "https://x.pythonanywhere.com")
    def offline(*a, **k):
        raise OSError("no internet")
    assert phone.fetch_changes(conn, http=offline) is None
    assert phone.upload(conn, "<p>x</p>", http=offline) is False


def test_apply_changes(conn):
    add_spend(conn, date(2026, 10, 1), 12.5, "Costa", "Eating out")
    costa = get_spends(conn)[0]["id"]
    changes = [
        {"cid": "a", "type": "add", "date": "2026-10-04", "amount": 250.0, "name": "Argos TV"},
        {"cid": "b", "type": "add", "date": "2026-10-04", "amount": 9.99, "name": "Skipped"},
        {"cid": "c", "type": "remove", "id": costa, "name": "Costa", "amount": 12.5},
        {"cid": "d", "type": "remove", "id": 999, "name": "Gone", "amount": 1.0},
    ]
    assert phone.apply_changes(conn, changes, skip={"b"}) == 2
    assert [(s["date"], s["amount"], s["name"]) for s in get_spends(conn)] == [(date(2026, 10, 4), 250.0, "Argos TV")]


def test_describe():
    assert phone.describe({"type": "add", "date": "2026-10-04", "amount": 250, "name": "Argos"}) == "Add     250.00  Argos  (04 Oct)"
    assert phone.describe({"type": "remove", "id": 1, "amount": 12.5, "name": "Costa"}) == "Remove   12.50  Costa"


class FakeOnline:
    def __init__(self, changes):
        self.changes = changes
        self.calls = []

    def __call__(self, method, url, key, body=None):
        self.calls.append((method, url.rsplit("/", 1)[1], body))
        if url.endswith("/api/changes"):
            return {"changes": self.changes}
        return {"ok": True}


def test_terminal_sync_enter_does_them_all(conn):
    phone.connect(conn, "https://x.pythonanywhere.com")
    online = FakeOnline([{"cid": "a", "type": "add", "date": "2026-10-04", "amount": 250.0, "name": "Argos"},
                         {"cid": "b", "type": "add", "date": "2026-10-04", "amount": 5.0, "name": "Greggs"}])
    lines = []
    phone.sync_terminal(conn, ask=lambda p: "", out=lines.append, http=online)
    assert [s["name"] for s in get_spends(conn)] == ["Argos", "Greggs"]
    assert ("POST", "clear", {"cids": ["a", "b"]}) in online.calls
    assert any("FROM YOUR PHONE" in l for l in lines)


def test_terminal_sync_skips_numbers_but_clears_them_too(conn):
    phone.connect(conn, "https://x.pythonanywhere.com")
    online = FakeOnline([{"cid": "a", "type": "add", "date": "2026-10-04", "amount": 250.0, "name": "Argos"},
                         {"cid": "b", "type": "add", "date": "2026-10-04", "amount": 5.0, "name": "Greggs"}])
    phone.sync_terminal(conn, ask=lambda p: "2", out=lambda l: None, http=online)
    assert [s["name"] for s in get_spends(conn)] == ["Argos"]
    assert ("POST", "clear", {"cids": ["a", "b"]}) in online.calls


def test_terminal_sync_offline_carries_on(conn):
    phone.connect(conn, "https://x.pythonanywhere.com")
    def offline(*a, **k):
        raise OSError
    lines = []
    phone.sync_terminal(conn, ask=lambda p: pytest.fail("no question"), out=lines.append, http=offline)
    assert lines == ["Phone sync skipped (no internet)."]


def test_terminal_sync_nothing_set_up_says_nothing(conn):
    lines = []
    phone.sync_terminal(conn, ask=lambda p: pytest.fail("no question"), out=lines.append, http=None)
    assert lines == []


# ---- the PC home page and the phone page (web.py) -------------------------------------------------

@pytest.fixture
def db(tmp_path):
    inbox = tmp_path / "statements"
    inbox.mkdir()
    for n in ("statement_2024_08.pdf", "statement_2024_09.pdf", "statement_2024_10.pdf"):
        shutil.copy(DATA / n, inbox / n)
    run.main(in_dir=inbox, out_dir=tmp_path / "output", ask=lambda p: "2500", wage_payer=ACME, ask_items=lambda p: "")
    return tmp_path / "tracker.db"


def test_phone_page_is_the_home_page_in_phone_mode(db):
    c = open_db(db)
    add_spend(c, date(2024, 10, 20), 12.5, "Costa", "Eating out")
    html = web.phone_page(db, wage_payer=ACME, today=date(2024, 10, 25), now="Sat 4 Oct, 19:42")
    assert "From PC: Sat 4 Oct, 19:42" in html
    assert 'action="/pay"' not in html and 'action="/add"' not in html   # phone = spends only, done by JS
    assert "Bills (every month)" in html                                  # same page as the PC
    data = json.loads(html.split('<script id="pcdata" type="application/json">')[1].split("</script>")[0])
    assert [(s["name"], s["amount"], s["date"]) for s in data["spends"]] == [("Costa", 12.5, "2024-10-20")]
    assert data["money"] == pytest.approx(web.home_data(c, wage_payer=ACME, today=date(2024, 10, 25))["money_for_spending"])


def test_pc_home_page_shows_phone_changes_and_takes_the_ticked_ones(db):
    c = open_db(db)
    phone.connect(c, "https://x.pythonanywhere.com")
    online = FakeOnline([{"cid": "a", "type": "add", "date": "2024-10-24", "amount": 250.0, "name": "Argos"},
                         {"cid": "b", "type": "add", "date": "2024-10-24", "amount": 5.0, "name": "Greggs"}])
    app = web.create_app(db, wage_payer=ACME, today=date(2024, 10, 25), phone_http=online)
    app.testing = True
    client = app.test_client()
    page = client.get("/").data.decode()
    assert "From your phone" in page and "Argos" in page and "Greggs" in page
    client.post("/phone", data={"take": ["a"], "seen": ["a", "b"]})
    assert [s["name"] for s in get_spends(open_db(db))] == ["Argos"]
    assert ("POST", "clear", {"cids": ["a", "b"]}) in online.calls
    assert any(name == "upload" for _, name, _ in online.calls)       # fresh copy sent up


def test_pc_add_sends_a_fresh_copy_up(db):
    c = open_db(db)
    phone.connect(c, "https://x.pythonanywhere.com")
    online = FakeOnline([])
    app = web.create_app(db, wage_payer=ACME, today=date(2024, 10, 25), phone_http=online)
    app.testing = True
    app.test_client().post("/add", data={"amount": "12.50", "name": "Costa"})
    uploads = [b for _, name, b in online.calls if name == "upload"]
    assert len(uploads) == 1 and "Costa" in uploads[0]["html"]


# ---- the whole loop: PC -> site -> phone -> site -> PC --------------------------------------------

def test_whole_loop(db, tmp_path):
    online_app = flask_app.create_app(tmp_path / "online", secure=False)
    online_app.testing = True
    pc_client = online_app.test_client()
    phone_client = online_app.test_client()

    def http(method, url, key, body=None):
        path = "/" + url.split("/", 3)[3]
        r = pc_client.open(path, method=method, json=body, headers={"X-Key": key})
        if r.status_code >= 400:
            raise OSError(r.status_code)
        return r.get_json()

    c = open_db(db)
    phone.connect(c, "https://x.pythonanywhere.com")
    phone.set_pin(c, "4821")
    assert phone.upload(c, web.phone_page(db, wage_payer=ACME, today=date(2024, 10, 25)), http=http)

    login(phone_client)
    assert b"pcdata" in phone_client.get("/").data
    phone_client.post("/send", json={"changes": [
        {"cid": "z", "type": "add", "date": "2024-10-24", "amount": 300.0, "name": "Halfords"}]})

    phone.sync_terminal(c, ask=lambda p: "", out=lambda l: None, http=http)
    assert [s["name"] for s in get_spends(c)] == ["Halfords"]
    assert phone_client.get("/pending").get_json()["changes"] == []


def test_test_and_real_databases_share_one_key(tmp_path):
    a, b = open_db(tmp_path / "test.db"), open_db(tmp_path / "real.db")
    phone.connect(a, "https://x.pythonanywhere.com")
    phone.connect(b, "https://x.pythonanywhere.com")
    assert phone.settings(a)[1] == phone.settings(b)[1]
