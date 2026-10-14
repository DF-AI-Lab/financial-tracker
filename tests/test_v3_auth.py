"""v3 sign-in by email code (14 Oct 2026). Fake data only; codes are caught with app.config["V3_SEND"]."""
import json
import re
from datetime import datetime, timedelta

import pytest

from tests.v3_helpers import v3_data, v3_app, v3_client, ACME  # noqa: F401

pytest.importorskip("flask")
from fintrack.v3 import auth  # noqa: E402

EMAIL = "darren@example.com"


@pytest.fixture
def app(v3_app):
    v3_app.config["V3_SETTINGS"]["email"] = EMAIL
    v3_app.config["SENT"] = []
    v3_app.config["V3_SEND"] = lambda to, code: v3_app.config["SENT"].append((to, code))
    return v3_app


@pytest.fixture
def clock(monkeypatch):
    """Move time by hand: clock["t"] += timedelta(...)."""
    c = {"t": datetime(2026, 10, 14, 9, 0)}
    monkeypatch.setattr(auth, "now", lambda: c["t"])
    return c


def ask_code(client, email=EMAIL):
    return client.post("/signin", data={"email": email})


def sign_in(app, client):
    ask_code(client)
    code = app.config["SENT"][-1][1]
    return client.post("/signin/code", data={"code": code})


def kv_text(app):
    from fintrack.store import open_db
    conn = open_db(app.config["V3_DATA_DIR"] / "tracker.db")
    try:
        return " ".join(str(r[1]) for r in conn.execute("SELECT key, value FROM kv WHERE key LIKE 'auth%'"))
    finally:
        conn.close()


def test_not_signed_in_goes_to_signin(app):
    c = app.test_client()
    r = c.get("/")
    assert r.status_code in (302, 303) and r.headers["Location"].endswith("/signin")
    assert c.post("/add", data={"amount": "1", "name": "x"}).status_code == 401
    assert c.get("/signin").status_code == 200


def test_static_and_manifest_are_open(app):
    c = app.test_client()
    assert c.get("/manifest.json").status_code == 200
    assert c.get("/static/look.css").status_code == 200


def test_wrong_email_same_answer_nothing_sent(app):
    c = app.test_client()
    wrong = ask_code(c, "someone@else.com").get_data(as_text=True)
    assert app.config["SENT"] == []
    right = ask_code(c, "  Darren@Example.COM ").get_data(as_text=True)
    assert len(app.config["SENT"]) == 1 and app.config["SENT"][0][0] == EMAIL
    assert "If that's your address, a code is on its way" in wrong
    assert "If that's your address, a code is on its way" in right
    assert 'autocomplete="one-time-code"' in wrong and 'autocomplete="one-time-code"' in right


def test_right_code_signs_in(app, clock):
    c = app.test_client()
    ask_code(c)
    to, code = app.config["SENT"][0]
    assert re.fullmatch(r"\d{6}", code)
    assert code not in kv_text(app)                         # only a hash is kept
    r = c.post("/signin/code", data={"code": code})
    assert r.status_code in (302, 303) and not r.headers["Location"].endswith("/signin")
    cookie = r.headers["Set-Cookie"]
    assert auth.COOKIE in cookie and "HttpOnly" in cookie and "SameSite=Lax" in cookie
    token = c.get_cookie(auth.COOKIE).value
    assert token not in kv_text(app)
    assert c.get("/").status_code == 200
    # the code works once
    c2 = app.test_client()
    assert c2.post("/signin/code", data={"code": code}).status_code == 200
    assert c2.get("/").status_code in (302, 303)


def test_device_runs_out_after_30_days(app, clock):
    c = app.test_client()
    sign_in(app, c)
    clock["t"] += timedelta(days=29)
    assert c.get("/").status_code == 200
    clock["t"] += timedelta(days=2)
    assert c.get("/").status_code in (302, 303)


def test_five_wrong_tries_lock(app, clock):
    c = app.test_client()
    ask_code(c)
    code = app.config["SENT"][-1][1]
    bad = "000000" if code != "000000" else "111111"
    for _ in range(5):
        c.post("/signin/code", data={"code": bad})
    r = c.post("/signin/code", data={"code": code})
    page = r.get_data(as_text=True)
    assert "Too many tries. Try again at 09:15." in page
    assert c.get("/").status_code in (302, 303)
    clock["t"] += timedelta(minutes=16)
    ask_code(c)
    r = c.post("/signin/code", data={"code": app.config["SENT"][-1][1]})
    assert r.status_code in (302, 303) and c.get("/").status_code == 200


def test_expired_code_refused(app, clock):
    c = app.test_client()
    ask_code(c)
    code = app.config["SENT"][-1][1]
    clock["t"] += timedelta(minutes=11)
    r = c.post("/signin/code", data={"code": code})
    assert "run out" in r.get_data(as_text=True)
    assert c.get("/").status_code in (302, 303)


def test_at_most_five_codes_an_hour(app, clock):
    c = app.test_client()
    for _ in range(7):
        ask_code(c)
        clock["t"] += timedelta(minutes=1)
    assert len(app.config["SENT"]) == 5
    clock["t"] += timedelta(hours=1)
    ask_code(c)
    assert len(app.config["SENT"]) == 6


def test_backup_codes_work_once(app, clock):
    c = app.test_client()
    sign_in(app, c)
    page = c.post("/settings/codes").get_data(as_text=True)
    codes = re.findall(r"<li>([a-z2-9]{4}-[a-z2-9]{4})</li>", page)
    assert len(set(codes)) == 8
    assert "Each works once" in page
    assert codes[0] not in kv_text(app)
    other = app.test_client()
    r = other.post("/signin/backup", data={"code": codes[0].upper()})
    assert r.status_code in (302, 303) and other.get("/").status_code == 200
    third = app.test_client()
    third.post("/signin/backup", data={"code": codes[0]})
    assert third.get("/").status_code in (302, 303)
    # new codes replace the old ones
    c.post("/settings/codes")
    fourth = app.test_client()
    fourth.post("/signin/backup", data={"code": codes[1]})
    assert fourth.get("/").status_code in (302, 303)


def test_wrong_backup_codes_count_toward_lock(app, clock):
    c = app.test_client()
    for _ in range(3):
        c.post("/signin/backup", data={"code": "aaaa-bbbb"})
    ask_code(c)
    code = app.config["SENT"][-1][1]
    bad = "000000" if code != "000000" else "111111"
    for _ in range(2):
        c.post("/signin/code", data={"code": bad})
    assert "Too many tries" in c.post("/signin/code", data={"code": code}).get_data(as_text=True)


def test_settings_codes_needs_sign_in(app):
    assert app.test_client().post("/settings/codes").status_code == 401


def test_sign_out_forgets_the_device(app, clock):
    a, b = app.test_client(), app.test_client()
    sign_in(app, a)
    sign_in(app, b)
    r = a.post("/signout")
    assert r.status_code in (302, 303) and r.headers["Location"].endswith("/signin")
    assert a.get("/").status_code in (302, 303)
    assert b.get("/").status_code == 200
    sign_in(app, a)
    a.post("/signout/all")
    assert a.get("/").status_code in (302, 303) and b.get("/").status_code in (302, 303)


def test_make_device_and_client_fixture(v3_client, v3_app):
    assert v3_client.get("/").status_code == 200
    c = v3_app.test_client()
    c.set_cookie(auth.COOKIE, auth.make_device(v3_app))
    assert c.get("/").status_code == 200


def test_empty_email_says_put_it_in(v3_data):
    import v3app
    s = json.loads((v3_data / "v3_settings.json").read_text()) if (v3_data / "v3_settings.json").exists() else {}
    s["email"] = ""
    (v3_data / "v3_settings.json").write_text(json.dumps(s))
    app = v3app.make_app(v3_data, wage_payer=ACME, updater=lambda: {}, restart=lambda: None)
    sent = []
    app.config["V3_SEND"] = lambda to, code: sent.append(code)
    c = app.test_client()
    assert "v3_settings.json" in c.get("/signin").get_data(as_text=True)
    assert "v3_settings.json" in c.post("/signin", data={"email": ""}).get_data(as_text=True)
    assert sent == []


def test_console_code_when_no_mail_settings(app, capsys, clock):
    app.config.pop("V3_SEND")
    ask_code(app.test_client())
    out = capsys.readouterr().out
    assert re.search(r"Sign-in code: \d{6}", out)
