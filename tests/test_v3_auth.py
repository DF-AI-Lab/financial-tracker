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
    auth.set_pin(v3_app, PIN)                               # the passcode is already chosen (its own tests below)
    return v3_app


@pytest.fixture
def clock(monkeypatch):
    """Move time by hand: clock["t"] += timedelta(...)."""
    c = {"t": datetime(2026, 10, 14, 9, 0)}
    monkeypatch.setattr(auth, "now", lambda: c["t"])
    return c


PIN = "246810"


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


def test_device_runs_out_after_7_days(app, clock):
    c = app.test_client()
    sign_in(app, c)
    clock["t"] += timedelta(days=6)
    assert c.get("/").headers["Location"].endswith("/unlock")     # passcode only, no email code
    c.post("/unlock", data={"pin": PIN})
    assert c.get("/").status_code == 200
    clock["t"] += timedelta(days=2)
    assert c.get("/").headers["Location"].endswith("/signin")     # a week: the email code again


def test_five_wrong_tries_lock(app, clock):
    c = app.test_client()
    ask_code(c)
    code = app.config["SENT"][-1][1]
    bad = "000000" if code != "000000" else "111111"
    for _ in range(5):
        c.post("/signin/code", data={"code": bad})
    r = c.post("/signin/code", data={"code": code})
    page = r.get_data(as_text=True)
    assert f"Too many tries. Try again at {auth.clock(datetime(2026, 10, 14, 9, 15))}." in page
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
    assert c.get("/").headers["Location"].endswith("/unlock")     # a device alone still needs the passcode


# ---- the passcode (user, 15 Oct 2026) -------------------------------------------------------------------------------

def test_first_email_sign_in_asks_for_a_passcode(v3_app, clock):
    v3_app.config["V3_SETTINGS"]["email"] = EMAIL
    sent = []
    v3_app.config["V3_SEND"] = lambda to, code: sent.append(code)
    c = v3_app.test_client()
    c.post("/signin", data={"email": EMAIL})
    r = c.post("/signin/code", data={"code": sent[-1]})
    assert r.headers["Location"].endswith("/pin/new")
    assert c.get("/").headers["Location"].endswith("/pin/new")
    page = c.post("/pin/new", data={"pin": "123456", "again": "123456"}).get_data(as_text=True)
    assert "too easy" in page
    assert "not the same" in c.post("/pin/new", data={"pin": "135792", "again": "135790"}).get_data(as_text=True)
    assert "6 numbers" in c.post("/pin/new", data={"pin": "1357", "again": "1357"}).get_data(as_text=True)
    r = c.post("/pin/new", data={"pin": "135792", "again": "135792"})
    assert r.headers["Location"].endswith("/") and c.get("/").status_code == 200
    assert "135792" not in kv_text(v3_app)
    assert c.get("/pin/new").headers["Location"].endswith("/")    # can't be changed without the email code


def test_passcode_again_after_15_minutes_idle(app, clock):
    c = app.test_client()
    sign_in(app, c)
    clock["t"] += timedelta(minutes=10)
    assert c.get("/").status_code == 200                            # still using it
    clock["t"] += timedelta(minutes=14)
    assert c.get("/").status_code == 200                            # 14 minutes since the last use
    clock["t"] += timedelta(minutes=16)
    assert c.get("/").headers["Location"].endswith("/unlock")
    assert c.post("/add", data={"amount": "1", "name": "x"}).status_code == 401
    assert "not right" in c.post("/unlock", data={"pin": "000000"}).get_data(as_text=True)
    assert c.post("/unlock", data={"pin": PIN}).headers["Location"].endswith("/")
    assert c.get("/").status_code == 200


def test_new_browser_session_needs_the_passcode(app, clock):
    c = app.test_client()
    sign_in(app, c)
    token = c.get_cookie(auth.COOKIE).value
    fresh = app.test_client()                                       # same device cookie, browser closed and opened
    fresh.set_cookie(auth.COOKIE, token)
    assert fresh.get("/").headers["Location"].endswith("/unlock")


def test_five_wrong_passcodes_lock(app, clock):
    c = app.test_client()
    sign_in(app, c)
    clock["t"] += timedelta(minutes=20)
    for _ in range(5):
        c.post("/unlock", data={"pin": "000000"})
    assert "Too many tries" in c.post("/unlock", data={"pin": PIN}).get_data(as_text=True)
    clock["t"] += timedelta(minutes=16)
    assert c.post("/unlock", data={"pin": PIN}).headers["Location"].endswith("/")


def test_forgot_passcode_signs_in_by_email_then_new_passcode(app, clock):
    c = app.test_client()
    sign_in(app, c)
    clock["t"] += timedelta(minutes=20)
    r = c.post("/unlock/forgot")
    assert r.headers["Location"].endswith("/signin")
    assert c.get("/").headers["Location"].endswith("/signin")       # the device is forgotten
    r = sign_in(app, c)
    assert r.headers["Location"].endswith("/pin/new")
    c.post("/pin/new", data={"pin": "975310", "again": "975310"})
    assert auth.pin_ok(app, "975310") and not auth.pin_ok(app, PIN)


def test_empty_email_says_put_it_in(v3_data):
    import v3app
    s = json.loads((v3_data / "v3_settings.json").read_text()) if (v3_data / "v3_settings.json").exists() else {}
    s["email"] = ""
    (v3_data / "v3_settings.json").write_text(json.dumps(s))
    app = v3app.make_app(v3_data, wage_payer=ACME, updater=lambda: {}, restart=lambda: None)
    sent = []
    app.config["V3_SEND"] = lambda to, code: sent.append(code)
    c = app.test_client()
    far = {"REMOTE_ADDR": "8.8.8.8"}                                  # from the internet: edit the file
    assert "v3_settings.json" in c.get("/signin", environ_base=far).get_data(as_text=True)
    assert "v3_settings.json" in c.post("/signin", data={"email": ""}, environ_base=far).get_data(as_text=True)
    assert sent == []


def test_console_code_when_no_mail_settings(app, capsys, clock):
    app.config.pop("V3_SEND")
    ask_code(app.test_client())
    out = capsys.readouterr().out
    assert re.search(r"Sign-in code: \d{6}", out)


def test_email_typed_into_the_file_later_is_read_again(v3_data):
    import v3app
    app = v3app.make_app(v3_data, wage_payer=ACME)
    app.testing = True
    c = app.test_client()
    assert "Your email" in c.get("/signin").get_data(as_text=True)          # no email yet: the setup box (local)
    s = json.loads((v3_data / "v3_settings.json").read_text())
    s["email"] = "me@example.com"
    (v3_data / "v3_settings.json").write_text("﻿" + json.dumps(s), encoding="utf-8")   # Notepad's hidden mark
    page = c.get("/signin").get_data(as_text=True)
    assert "Send me a code" in page and "setup-email" not in page


def test_email_can_be_set_on_the_page_on_this_computer_only(v3_data):
    import v3app
    app = v3app.make_app(v3_data, wage_payer=ACME)
    app.testing = True
    c = app.test_client()
    c.post("/signin/setup", data={"email": "me@example.com"}, environ_base={"REMOTE_ADDR": "8.8.8.8"})
    assert json.loads((v3_data / "v3_settings.json").read_text())["email"] == ""          # from the internet: no
    c.post("/signin/setup", data={"email": "me@example.com"})
    assert json.loads((v3_data / "v3_settings.json").read_text())["email"] == "me@example.com"
    c.post("/signin/setup", data={"email": "thief@example.com"})                          # once set, never again
    assert json.loads((v3_data / "v3_settings.json").read_text())["email"] == "me@example.com"


def test_a_broken_settings_file_is_never_written_over(v3_data):
    import v3app
    (v3_data / "v3_settings.json").write_text('{"email": "me@example.com",,}', encoding="utf-8")
    v3app.load_settings(v3_data)
    assert (v3_data / "v3_settings.json").read_text() == '{"email": "me@example.com",,}'


def test_pc_test_page_says_the_code_is_in_the_black_window(v3_data, capsys):
    import v3app
    s = json.loads((v3_data / "v3_settings.json").read_text()) if (v3_data / "v3_settings.json").exists() else {}
    v3app.load_settings(v3_data)
    s = json.loads((v3_data / "v3_settings.json").read_text())
    s["email"] = "me@example.com"
    (v3_data / "v3_settings.json").write_text(json.dumps(s))
    app = v3app.make_app(v3_data, wage_payer=ACME)
    page = app.test_client().post("/signin", data={"email": "me@example.com"}).get_data(as_text=True)
    assert "Testing on your PC: your code is" in page and "Sign-in code:" in capsys.readouterr().out


def test_pc_test_shows_the_code_on_the_page_only_on_this_computer(v3_data):
    import v3app
    v3app.load_settings(v3_data)
    s = json.loads((v3_data / "v3_settings.json").read_text())
    s["email"] = "me@example.com"
    (v3_data / "v3_settings.json").write_text(json.dumps(s))
    app = v3app.make_app(v3_data, wage_payer=ACME)
    c = app.test_client()
    page = c.post("/signin", data={"email": "me@example.com"}).get_data(as_text=True)
    code = re.search(r"your code is <b>(\d{6})</b>", page).group(1)
    assert c.post("/signin/code", data={"code": code}).status_code in (302, 303)
    far = c.post("/signin", data={"email": "me@example.com"}, environ_base={"REMOTE_ADDR": "8.8.8.8"})
    assert "your code is" not in far.get_data(as_text=True)                         # never shown over the internet
    wrong = c.post("/signin", data={"email": "other@example.com"}).get_data(as_text=True)
    assert "your code is" not in wrong                                              # nor for another address


def test_email_fails_then_the_code_goes_in_a_file(v3_app, clock, monkeypatch):
    import smtplib
    v3_app.config["V3_SETTINGS"].update({"email": EMAIL, "smtp_user": EMAIL, "smtp_password": "x" * 16})
    tried = []

    class Broken:
        def __init__(self, host, port, timeout=None):
            tried.append(port)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self):
            pass

        def login(self, u, p):
            raise smtplib.SMTPServerDisconnected("Connection unexpectedly closed")

    monkeypatch.setattr(smtplib, "SMTP", Broken)
    monkeypatch.setattr(smtplib, "SMTP_SSL", Broken)
    c = v3_app.test_client()
    page = c.post("/signin", data={"email": EMAIL}, environ_base={"REMOTE_ADDR": "8.8.8.8"}).get_data(as_text=True)
    assert tried == [587, 465]
    assert "signin_code.txt" in page and 'name="code"' in page
    f = v3_app.config["V3_DATA_DIR"] / "signin_code.txt"
    code = re.search(r"code: (\d{6})", f.read_text()).group(1)
    r = c.post("/signin/code", data={"code": code}, environ_base={"REMOTE_ADDR": "8.8.8.8"})
    assert r.status_code in (302, 303) and not f.exists()               # used, and the file is gone
