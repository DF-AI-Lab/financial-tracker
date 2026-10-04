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


def test_apply_spend_changes(conn):
    add_spend(conn, date(2026, 10, 1), 12.5, "Costa", "Eating out")
    costa = get_spends(conn)[0]["id"]
    changes = [
        {"cid": "a", "type": "add", "date": "2026-10-04", "amount": 250.0, "name": "Argos TV"},
        {"cid": "c", "type": "remove", "id": costa, "name": "Costa", "amount": 12.5},
        {"cid": "d", "type": "remove", "id": 999, "name": "Gone", "amount": 1.0},
        {"cid": "e", "type": "rename", "name": "Unknown types are ignored"},
        {"cid": "f", "type": "pay", "amount": "not money"},
    ]
    assert phone.apply_changes(conn, changes, wage_payer=ACME) == 2
    assert [(s["date"], s["amount"], s["name"]) for s in get_spends(conn)] == [(date(2026, 10, 4), 250.0, "Argos TV")]


class FakeOnline:
    def __init__(self, changes):
        self.changes = changes
        self.calls = []

    def __call__(self, method, url, key, body=None):
        self.calls.append((method, url.rsplit("/", 1)[1], body))
        if url.endswith("/api/changes"):
            return {"changes": self.changes}
        return {"ok": True}


def test_sync_once_does_everything_straight_away(conn):
    phone.connect(conn, "https://x.pythonanywhere.com")
    online = FakeOnline([{"cid": "a", "type": "add", "date": "2026-10-04", "amount": 250.0, "name": "Argos"},
                         {"cid": "b", "type": "add", "date": "2026-10-04", "amount": 5.0, "name": "Greggs"}])
    assert phone.sync_once(conn, wage_payer=ACME, http=online) == 2
    assert [s["name"] for s in get_spends(conn)] == ["Argos", "Greggs"]
    assert ("POST", "clear", {"cids": ["a", "b"]}) in online.calls


def test_sync_once_offline_or_not_set_up(conn):
    def offline(*a, **k):
        raise OSError
    assert phone.sync_once(conn, wage_payer=ACME, http=offline) is None      # not set up: no network either
    phone.connect(conn, "https://x.pythonanywhere.com")
    assert phone.sync_once(conn, wage_payer=ACME, http=offline) is None


def test_terminal_sync_asks_nothing_and_says_how_many(conn):
    phone.connect(conn, "https://x.pythonanywhere.com")
    online = FakeOnline([{"cid": "a", "type": "add", "date": "2026-10-04", "amount": 250.0, "name": "Argos"}])
    lines = []
    phone.sync_terminal(conn, out=lines.append, http=online, wage_payer=ACME)
    assert [s["name"] for s in get_spends(conn)] == ["Argos"]
    assert lines == ["Phone: 1 change from your phone done."]


def test_terminal_sync_offline_carries_on(conn):
    phone.connect(conn, "https://x.pythonanywhere.com")
    def offline(*a, **k):
        raise OSError
    lines = []
    phone.sync_terminal(conn, out=lines.append, http=offline, wage_payer=ACME)
    assert lines == ["Phone sync skipped (no internet)."]


def test_terminal_sync_nothing_set_up_says_nothing(conn):
    lines = []
    phone.sync_terminal(conn, out=lines.append, http=None, wage_payer=ACME)
    assert lines == []


def test_upload_sends_a_stamp(conn):
    phone.connect(conn, "https://x.pythonanywhere.com")
    online = FakeOnline([])
    assert phone.upload(conn, "<p>x</p>", http=online, stamp="123.4")
    assert online.calls[0][2]["stamp"] == "123.4"


# ---- the PC home page and the phone page (web.py) -------------------------------------------------

@pytest.fixture
def db(tmp_path):
    inbox = tmp_path / "statements"
    inbox.mkdir()
    for n in ("statement_2024_08.pdf", "statement_2024_09.pdf", "statement_2024_10.pdf"):
        shutil.copy(DATA / n, inbox / n)
    run.main(in_dir=inbox, out_dir=tmp_path / "output", ask=lambda p: "2500", wage_payer=ACME, ask_items=lambda p: "")
    return tmp_path / "tracker.db"


def pcdata(html):
    return json.loads(html.split('<script id="pcdata" type="application/json">')[1].split("</script>")[0])


def test_phone_page_is_the_home_page_in_phone_mode(db):
    c = open_db(db)
    add_spend(c, date(2024, 10, 20), 12.5, "Costa", "Eating out")
    html = web.phone_page(db, wage_payer=ACME, today=date(2024, 10, 25), now="Sat 4 Oct, 19:42", stamp="777")
    assert "From PC: Sat 4 Oct, 19:42" in html
    assert "Bills (every month)" in html                                  # same page as the PC
    data = pcdata(html)
    assert [(s["name"], s["amount"], s["date"]) for s in data["spends"]] == [("Costa", 12.5, "2024-10-20")]
    assert data["money"] == pytest.approx(web.home_data(c, wage_payer=ACME, today=date(2024, 10, 25))["money_for_spending"])
    assert data["stamp"] == "777"


def test_phone_changes_pay_left_and_bills(db):
    c = open_db(db)
    from fintrack.billchange import get_changes, get_left
    d = web.home_data(c, wage_payer=ACME, today=date(2024, 10, 25))
    key = d["pay"]["bills"][0]["key"]
    start = d["cycle_start"]
    add_spend(c, date(2024, 10, 20), 12.5, "Costa", "Eating out")
    n = phone.apply_changes(c, [
        {"cid": "1", "type": "pay", "amount": 2600.0, "clear": True},
        {"cid": "2", "type": "left", "amount": 220.0},
        {"cid": "3", "type": "bill", "key": key, "amount": 99.0},
        {"cid": "4", "type": "bill", "key": "NOT|A|BILL", "amount": 5.0},
    ], wage_payer=ACME)
    assert n == 3
    assert get_value(c, "pay") == "2600.0" and get_spends(c) == []          # clear = the typed spends go
    assert get_left(c, start) == 220.0
    assert get_changes(c, start) == {key: 99.0}
    phone.apply_changes(c, [{"cid": "5", "type": "left", "amount": None},
                            {"cid": "6", "type": "bill", "key": key, "amount": None}], wage_payer=ACME)
    assert get_left(c, start) == 0 and get_changes(c, start) == {}


def test_phone_answers_new_items(tmp_path):
    from fintrack.inbox import import_pdf
    from fintrack.store import get_items
    c = open_db(tmp_path / "fresh.db")                    # statements read in, no questions answered yet
    for n in ("statement_2024_08.pdf", "statement_2024_09.pdf", "statement_2024_10.pdf"):
        import_pdf(c, tmp_path / "statements", n, (DATA / n).read_bytes())
    d = web.home_data(c, wage_payer=ACME, today=date(2024, 10, 25))
    assert d["sort"]
    item = d["sort"][0]
    phone.apply_changes(c, [{"cid": "s", "type": "sort", "answers": [
        {"key": item["key"], "kind": "oneoff", "label": "Sofa", "category": "Household"}]}], wage_payer=ACME)
    assert get_items(c)[item["key"]]["label"] == "Sofa"


def test_pc_home_page_does_phone_changes_by_itself(db):
    c = open_db(db)
    phone.connect(c, "https://x.pythonanywhere.com")
    online = FakeOnline([{"cid": "a", "type": "add", "date": "2024-10-24", "amount": 250.0, "name": "Argos"}])
    app = web.create_app(db, wage_payer=ACME, today=date(2024, 10, 25), phone_http=online)
    app.testing = True
    page = app.test_client().get("/").data.decode()
    assert "Argos" in page and "From your phone" not in page              # no box to tick any more
    assert [s["name"] for s in get_spends(open_db(db))] == ["Argos"]
    assert ("POST", "clear", {"cids": ["a"]}) in online.calls
    assert any(name == "upload" for _, name, _ in online.calls)           # fresh copy sent up


def test_pc_add_sends_a_fresh_copy_up(db):
    c = open_db(db)
    phone.connect(c, "https://x.pythonanywhere.com")
    online = FakeOnline([])
    app = web.create_app(db, wage_payer=ACME, today=date(2024, 10, 25), phone_http=online)
    app.testing = True
    app.test_client().post("/add", data={"amount": "12.50", "name": "Costa"})
    uploads = [b for _, name, b in online.calls if name == "upload"]
    assert len(uploads) == 1 and "Costa" in uploads[0]["html"]


def test_engine_tick_takes_phone_changes_and_new_downloads(db, tmp_path):
    c = open_db(db)
    phone.connect(c, "https://x.pythonanywhere.com")
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    online = FakeOnline([{"cid": "a", "type": "add", "date": "2024-10-24", "amount": 5.0, "name": "Greggs"}])
    r = web.engine_tick(db, wage_payer=ACME, statements_dir=tmp_path / "statements", downloads_dir=downloads,
                        http=online, today=date(2024, 10, 25))
    assert r == {"changes": 1, "imported": []}
    assert sum(1 for _, name, _ in online.calls if name == "upload") == 1
    online.calls.clear()
    online.changes = []
    r = web.engine_tick(db, wage_payer=ACME, statements_dir=tmp_path / "statements", downloads_dir=downloads,
                        http=online, today=date(2024, 10, 25))
    assert r == {"changes": 0, "imported": []}
    assert not any(name == "upload" for _, name, _ in online.calls)       # nothing new = nothing sent


# ---- Downloads: HSBC statements are moved in by themselves (fintrack/downloads.py) ----------------

def test_downloads_moves_new_statements_in(tmp_path):
    from fintrack.downloads import scan_downloads
    from fintrack.store import load_statements
    c = open_db(tmp_path / "t.db")
    downloads, statements = tmp_path / "Downloads", tmp_path / "statements"
    downloads.mkdir()
    shutil.copy(DATA / "statement_2024_08.pdf", downloads / "2024-08-22_Statement.pdf")
    (downloads / "holiday_statement.pdf").write_bytes(b"%PDF-1.4 not really a statement")
    (downloads / "Statement.txt").write_text("not a pdf")
    (downloads / "invoice.pdf").write_bytes((DATA / "statement_2024_09.pdf").read_bytes())   # no 'statement' in name
    assert scan_downloads(c, downloads, statements) == ["2024-08-22_Statement.pdf"]
    assert not (downloads / "2024-08-22_Statement.pdf").exists()          # moved, not copied
    assert (statements / "2024-08-22_Statement.pdf").exists()
    assert len(load_statements(c)) == 1
    assert (downloads / "holiday_statement.pdf").exists()                 # not a statement: left alone
    assert (downloads / "invoice.pdf").exists()                           # name does not say statement: left alone
    assert scan_downloads(c, downloads, statements) == []                 # the bad one is not read again


def test_downloads_removes_a_statement_already_stored(tmp_path):
    from fintrack.downloads import scan_downloads
    c = open_db(tmp_path / "t.db")
    downloads, statements = tmp_path / "Downloads", tmp_path / "statements"
    downloads.mkdir()
    shutil.copy(DATA / "statement_2024_08.pdf", downloads / "a_Statement.pdf")
    scan_downloads(c, downloads, statements)
    shutil.copy(DATA / "statement_2024_08.pdf", downloads / "a_Statement (1).pdf")   # downloaded twice
    assert scan_downloads(c, downloads, statements) == []
    assert not (downloads / "a_Statement (1).pdf").exists()
    assert sorted(p.name for p in statements.iterdir()) == ["a_Statement.pdf"]


def test_downloads_folder_missing_is_fine(tmp_path):
    from fintrack.downloads import scan_downloads
    assert scan_downloads(open_db(tmp_path / "t.db"), tmp_path / "nope", tmp_path / "statements") == []


# ---- the online site: more kinds of change, and the stamp -----------------------------------------

def test_site_takes_the_new_kinds_of_change(site):
    upload(site)
    login(site)
    good = [{"cid": "p", "type": "pay", "amount": 2600, "clear": False},
            {"cid": "l", "type": "left", "amount": None},
            {"cid": "b", "type": "bill", "key": "DD|SKY|", "amount": 48},
            {"cid": "s", "type": "sort", "answers": [{"key": "CARD|X|", "kind": "bill"}]},
            {"cid": "q", "type": "ask", "answer": {"type": "job", "name": "X", "yes": True}}]
    assert site.post("/send", json={"changes": good}).status_code == 200
    assert [c["cid"] for c in site.get("/pending").get_json()["changes"]] == ["p", "l", "b", "s", "q"]
    huge = {"cid": "h", "type": "sort", "answers": [{"key": "x" * 100}] * 500}
    assert site.post("/send", json={"changes": [huge]}).status_code == 400


def test_site_stamp(site):
    salt = "salt"
    site.post("/api/upload", json={"html": "<p>x</p>", "pin_salt": salt, "pin_hash": phone.hash_pin("4821", salt),
                                   "stamp": "42.5"}, headers={"X-Key": KEY})
    assert site.get("/stamp").status_code == 401
    login(site)
    assert site.get("/stamp").get_json() == {"stamp": "42.5"}


# ---- run.py small fixes ---------------------------------------------------------------------------

def test_wage_ignores_the_word_test(tmp_path):
    from fintrack.wages import all_payers
    folder = tmp_path / "statements"
    folder.mkdir()
    open_db(tmp_path / "tracker.db").close()
    run.run_command(["wage", "NEW JOB LTD", "test"], out=lambda l: None, in_dir=folder)
    assert "NEW JOB LTD" in all_payers(open_db(tmp_path / "tracker.db"), ACME)
    assert "NEW JOB LTD test" not in all_payers(open_db(tmp_path / "tracker.db"), ACME)


def test_real_database_found_without_a_statements_folder(tmp_path):
    from run import pick_folder
    real = tmp_path / "statements"                 # does not exist
    open_db(tmp_path / "tracker.db").close()       # but the real database sits there
    got = pick_folder([], real_dir=real, test_dir=tmp_path / "code" / "statements", saved_file=tmp_path / "none.txt")
    assert got == real and real.is_dir()


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

    phone.sync_terminal(c, out=lambda l: None, http=http, wage_payer=ACME)
    assert [s["name"] for s in get_spends(c)] == ["Halfords"]
    assert phone_client.get("/pending").get_json()["changes"] == []


def test_test_and_real_databases_share_one_key(tmp_path):
    a, b = open_db(tmp_path / "test.db"), open_db(tmp_path / "real.db")
    phone.connect(a, "https://x.pythonanywhere.com")
    phone.connect(b, "https://x.pythonanywhere.com")
    assert phone.settings(a)[1] == phone.settings(b)[1]
