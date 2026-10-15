"""v3 sign-in by email code (14 Oct 2026).

Only one email (settings["email"]) may sign in. POST /signin sends a 6-digit code (10 minutes, at most 5 an hour);
the right code (or an unused backup code) gives this device a token in the COOKIE cookie for 7 days (user, 15 Oct:
the email code once a week).
On top, a 6-digit PASSCODE (user, 15 Oct): chosen once after the first email sign-in, asked whenever the site is
opened again (a new browser session, or 15 minutes without use). "Forgot passcode?" = sign in by email, then choose
a new one. 5 wrong tries (codes, backup codes or passcodes) lock for 15 minutes. Every other page needs both.
Only HMAC hashes of codes and tokens are kept (kv table). Plain codes and tokens are never stored or logged.

kv keys (JSON text):
  auth_code     {"hash", "expires"}            the last code sent
  auth_sent     [ISO time, ...]                 codes sent in the last hour
  auth_fails    {"count", "until"}             wrong tries, and the lock end time
  auth_devices  {token hash: created ISO}       signed-in devices
  auth_backup   [hash, ...]                     unused backup codes
  auth_pin      {"salt", "hash"}                the passcode (PBKDF2)
The unlocked state is in Flask's signed session cookie: {"unlocked": last use ISO, "device": device hash}.
"""
import hashlib
import hmac
import json
import secrets
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage

from flask import make_response, redirect, render_template, request, session

from fintrack.appversion import VERSION
from fintrack.store import open_db, get_value, set_value

COOKIE = "wmm_device"
CODE_MINUTES = 10
CODES_PER_HOUR = 5
MAX_TRIES = 5
LOCK_MINUTES = 15
DEVICE_DAYS = 7
IDLE_MINUTES = 15                                       # passcode again after this long without using the site
PIN_ITERATIONS = 200_000
BACKUP_COUNT = 8
BACKUP_LETTERS = "abcdefghjkmnpqrstuvwxyz23456789"      # no 0/o, 1/l/i look-alikes

OPEN_PATHS = ("/signin", "/signin/code", "/signin/backup", "/signin/setup", "/manifest.json")
PIN_PATHS = ("/unlock", "/unlock/forgot", "/pin/new", "/passkey/start", "/passkey/unlock")   # + fingerprint
QUIET_PATHS = ("/stamp",)                               # the page's own checks: signed in, but not "using it"    # need a signed-in device, but no passcode yet


def clock(t: datetime) -> str:
    """HH:MM in UK time for messages (PythonAnywhere runs on UTC; the PC may lack time zone data: then as is)."""
    try:
        from zoneinfo import ZoneInfo
        return f"{t.astimezone().astimezone(ZoneInfo('Europe/London')):%H:%M}"
    except Exception:
        return f"{t:%H:%M}"


def now() -> datetime:
    """The time now (tests replace this)."""
    return datetime.now()


# --- small helpers -------------------------------------------------------------------------------------------------

def _hash(app, text: str) -> str:
    key = app.secret_key.encode() if isinstance(app.secret_key, str) else app.secret_key
    return hmac.new(key, text.encode(), hashlib.sha256).hexdigest()


def _db(app):
    return open_db(app.config["V3_DATA_DIR"] / "tracker.db")


def _get(app, key, default):
    conn = _db(app)
    try:
        raw = get_value(conn, key)
    finally:
        conn.close()
    try:
        return json.loads(raw) if raw else default
    except ValueError:
        return default


def _set(app, key, value) -> None:
    conn = _db(app)
    try:
        set_value(conn, key, json.dumps(value))
    finally:
        conn.close()


def _allowed_email(app) -> str:
    email = (app.config["V3_SETTINGS"].get("email") or "").strip().lower()
    if not email and app.config.get("V3_DATA_DIR"):           # typed into the file after the start: read it again
        import v3app
        fresh = v3app.load_settings(app.config["V3_DATA_DIR"])
        if fresh.get("email"):
            app.config["V3_SETTINGS"]["email"] = fresh["email"]
            email = fresh["email"].strip().lower()
    return email


def _console(app) -> bool:
    """No Gmail set up (the PC test): codes are printed in the black window, not emailed."""
    s = app.config["V3_SETTINGS"]
    return not app.config.get("V3_SEND") and not (s.get("smtp_user") and s.get("smtp_password"))


def _local() -> bool:
    """The page is opened on this computer itself (the PC test), never from the internet."""
    return request.remote_addr in ("127.0.0.1", "::1") and not request.headers.get("X-Forwarded-For")


# --- devices -------------------------------------------------------------------------------------------------------

def make_device(app) -> str:
    """Make a device token, keep its hash with the time, and give back the token (for the cookie)."""
    token = secrets.token_urlsafe(32)
    devices = _get(app, "auth_devices", {})
    devices[_hash(app, token)] = now().isoformat()
    _set(app, "auth_devices", devices)
    return token


def device_ok(app, token) -> bool:
    """True when the token belongs to a device signed in within the last 30 days."""
    if not token:
        return False
    created = _get(app, "auth_devices", {}).get(_hash(app, token))
    if not created:
        return False
    return now() < datetime.fromisoformat(created) + timedelta(days=DEVICE_DAYS)


def _forget_device(app, token) -> None:
    devices = _get(app, "auth_devices", {})
    if token and devices.pop(_hash(app, token), None) is not None:
        _set(app, "auth_devices", devices)


def _signed_in_response(app):
    """A new device cookie, and unlocked (the email code proves it is you). No passcode yet, or "Forgot passcode?":
    choose one first."""
    token = make_device(app)
    forgot = session.pop("forgot", False)
    _unlock(app, token)
    if forgot or not pin_is_set(app):
        session["new_pin_until"] = (now() + timedelta(minutes=CODE_MINUTES)).isoformat()
    resp = redirect("/pin/new" if session.get("new_pin_until") else "/", code=303)
    resp.set_cookie(COOKIE, token, max_age=DEVICE_DAYS * 24 * 3600, httponly=True, samesite="Lax",
                    secure=request.is_secure)
    return resp


# --- passcode ------------------------------------------------------------------------------------------------------

def _pin_hash(pin: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt), PIN_ITERATIONS).hex()


def pin_is_set(app) -> bool:
    return bool(_get(app, "auth_pin", {}).get("hash"))


def set_pin(app, pin: str) -> None:
    salt = secrets.token_hex(16)
    _set(app, "auth_pin", {"salt": salt, "hash": _pin_hash(pin, salt)})


def pin_ok(app, pin: str) -> bool:
    saved = _get(app, "auth_pin", {})
    return bool(saved.get("hash")) and hmac.compare_digest(_pin_hash(pin or "", saved["salt"]), saved["hash"])


def pin_problem(pin: str, again: str) -> str:
    """'' when the new passcode is fine, else what is wrong (plain words)."""
    if not (len(pin) == 6 and pin.isdigit()):
        return "The passcode must be 6 numbers."
    if pin != again:
        return "The two passcodes are not the same. Try again."
    if len(set(pin)) == 1 or pin in "0123456789" or pin in "9876543210":
        return "That passcode is too easy to guess. Pick another."
    return ""


def _unlock(app, token) -> None:
    session["unlocked"] = now().isoformat()
    session["device"] = _hash(app, token)


def unlocked(app, token) -> bool:
    """This browser typed the passcode (or signed in by email) for this device, and used the site in the last
    15 minutes."""
    last = session.get("unlocked")
    if not last or session.get("device") != _hash(app, token):
        return False
    return now() < datetime.fromisoformat(last) + timedelta(minutes=IDLE_MINUTES)


def sign_in_for_tests(app, client, pin: str = "246810") -> None:
    """Tests: a signed-in device with a passcode set and this client unlocked."""
    token = make_device(app)
    if not pin_is_set(app):
        set_pin(app, pin)
    client.set_cookie(COOKIE, token)
    with client.session_transaction() as s:
        s["unlocked"] = now().isoformat()
        s["device"] = _hash(app, token)


# --- wrong tries ---------------------------------------------------------------------------------------------------

def locked_until(app):
    """The lock end time, or None when not locked."""
    until = _get(app, "auth_fails", {}).get("until")
    if until and now() < datetime.fromisoformat(until):
        return datetime.fromisoformat(until)
    return None


def _add_fail(app) -> None:
    fails = _get(app, "auth_fails", {})
    if fails.get("until") and now() >= datetime.fromisoformat(fails["until"]):
        fails = {}                                          # an old lock is over: start counting again
    fails["count"] = fails.get("count", 0) + 1
    if fails["count"] >= MAX_TRIES:
        fails = {"count": 0, "until": (now() + timedelta(minutes=LOCK_MINUTES)).isoformat()}
    _set(app, "auth_fails", fails)


def _lock_text(until) -> str:
    return f"Too many tries. Try again at {clock(until)}."


# --- codes ---------------------------------------------------------------------------------------------------------

def send_code(app, to: str, code: str) -> None:
    """Send the code: the test hook, Gmail, or (no mail settings, on the PC) the console window."""
    hook = app.config.get("V3_SEND")
    if hook:
        hook(to, code)
        return
    s = app.config["V3_SETTINGS"]
    if s.get("smtp_user") and s.get("smtp_password"):
        msg = EmailMessage()
        msg["Subject"] = "Your Where's My Money? code"
        msg["From"] = s["smtp_user"]
        msg["To"] = to
        msg.set_content(f"Your Where's My Money? code is {code}. It works for {CODE_MINUTES} minutes.")
        try:                                               # Gmail's usual way first...
            with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as smtp:
                smtp.starttls()
                smtp.login(s["smtp_user"], s["smtp_password"])
                smtp.send_message(msg)
            return
        except (OSError, smtplib.SMTPException):
            pass
        try:                                               # ...then its other door (SSL on 465)
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
                smtp.login(s["smtp_user"], s["smtp_password"])
                smtp.send_message(msg)
            return
        except (OSError, smtplib.SMTPException):
            code_to_file(app, code)                        # plan B: Darren reads it in PythonAnywhere's Files tab
            raise CodeInFile()
    print(f"Sign-in code: {code}", flush=True)


class CodeInFile(Exception):
    """Email failed; the code was saved in the data folder instead."""


CODE_FILE = "signin_code.txt"


def code_to_file(app, code: str) -> None:
    """Plan B when email fails (15 Oct 2026): the code goes in <data folder>/signin_code.txt, which only Darren can
    open (PythonAnywhere → Files → wmm-data). It still runs out after 10 minutes and works once."""
    (app.config["V3_DATA_DIR"] / CODE_FILE).write_text(
        f"Your Where's My Money? code: {code}\nIt works for {CODE_MINUTES} minutes, once.\n", encoding="utf-8")


def _sent_last_hour(app) -> list:
    hour_ago = now() - timedelta(hours=1)
    return [t for t in _get(app, "auth_sent", []) if datetime.fromisoformat(t) > hour_ago]


def new_code(app) -> str:
    """Make a 6-digit code, keep its hash and expiry, count it. Give back the plain code (to send only)."""
    code = f"{secrets.randbelow(1_000_000):06d}"
    _set(app, "auth_code", {"hash": _hash(app, code),
                            "expires": (now() + timedelta(minutes=CODE_MINUTES)).isoformat()})
    _set(app, "auth_sent", _sent_last_hour(app) + [now().isoformat()])
    return code


def make_backup_codes(app) -> list:
    """8 new one-time codes like k3f9-x2m7. Old ones stop working. Only hashes are kept."""
    def one():
        return "-".join("".join(secrets.choice(BACKUP_LETTERS) for _ in range(4)) for _ in range(2))
    codes = [one() for _ in range(BACKUP_COUNT)]
    _set(app, "auth_backup", [_hash(app, c) for c in codes])
    return codes


def _clean_backup(text: str) -> str:
    t = "".join((text or "").lower().split()).replace("-", "")
    return f"{t[:4]}-{t[4:]}" if len(t) == 8 else t


# --- pages ---------------------------------------------------------------------------------------------------------

def _page(app, step="email", error="", sent=False, codes=None, status=200, test_code="", **extra):
    if not _allowed_email(app) and step not in ("unlock", "newpin", "passkey"):
        step = "noemail"
    from fintrack.v3 import passkey
    html = render_template("signin.html", step=step, error=error, sent=sent, codes=codes or [],
                           app_version=VERSION, local=_local(), console=_console(app), test_code=test_code,
                           fingerprint=step == "unlock" and passkey.ready(app),
                           settings_file=str(app.config.get("V3_DATA_DIR", "")) + "/v3_settings.json", **extra)
    return make_response(html, status)


def register(app) -> None:

    @app.before_request
    def need_sign_in():
        path = request.path
        if path in OPEN_PATHS or path.startswith("/static/"):
            return None
        page = request.method == "GET" and path not in QUIET_PATHS   # a page (redirect) or a check (401)
        token = request.cookies.get(COOKIE)
        if not device_ok(app, token):
            if page:
                return redirect("/signin")
            return ("Please sign in again.", 401)
        if path in PIN_PATHS:
            return None
        if not pin_is_set(app):
            session["new_pin_until"] = session.get("new_pin_until") or (now() + timedelta(minutes=CODE_MINUTES)).isoformat()
            return redirect("/pin/new") if page else ("Choose a passcode first.", 401)
        if not unlocked(app, token):
            return redirect("/unlock") if page else ("Type your passcode again.", 401)
        if path not in QUIET_PATHS:
            session["unlocked"] = now().isoformat()           # still using it: the 15 minutes start again
        return None

    @app.route("/signin", methods=["GET"])
    def signin():
        if device_ok(app, request.cookies.get(COOKIE)):
            return redirect("/")
        step = "backup" if request.args.get("backup") else "email"
        return _page(app, step)

    @app.route("/signin/setup", methods=["POST"])
    def signin_setup():
        """First start on the PC: type the email on the page instead of editing the file (this computer only)."""
        email = (request.form.get("email") or "").strip()
        if _allowed_email(app) or not _local() or "@" not in email or " " in email or len(email) > 120:
            return redirect("/signin")
        import v3app
        settings = app.config["V3_SETTINGS"]
        settings["email"] = email
        v3app.save_settings(app.config["V3_DATA_DIR"], settings)
        return redirect("/signin")

    @app.route("/signin", methods=["POST"])
    def signin_ask():
        allowed = _allowed_email(app)
        if not allowed:
            return _page(app)
        typed = (request.form.get("email") or "").strip().lower()
        if typed and hmac.compare_digest(typed, allowed):
            if len(_sent_last_hour(app)) >= CODES_PER_HOUR:
                first = min(datetime.fromisoformat(t) for t in _sent_last_hour(app))
                return _page(app, "code", error=f"That's a lot of codes. Use the last one, or ask again at "
                                                f"{clock(first + timedelta(hours=1))}.")
            code = new_code(app)
            try:
                send_code(app, allowed, code)
            except CodeInFile:
                return _page(app, "code", error="The email didn't send. Your code is in PythonAnywhere: "
                                                "Files → wmm-data → signin_code.txt")
            except (OSError, smtplib.SMTPException):
                return _page(app, "email", error="The email could not be sent. Check the Gmail settings "
                                                 "in v3_settings.json.")
            if _console(app) and _local():              # the PC test with no Gmail: show it on the page too
                return _page(app, "code", sent=True, test_code=code)
        return _page(app, "code", sent=True)

    @app.route("/signin/code", methods=["POST"])
    def signin_code():
        until = locked_until(app)
        if until:
            return _page(app, "code", error=_lock_text(until))
        typed = "".join((request.form.get("code") or "").split())
        saved = _get(app, "auth_code", {})
        if not saved.get("hash"):
            return _page(app, "email", error="Ask for a code first.")
        if now() > datetime.fromisoformat(saved["expires"]):
            return _page(app, "email", error="That code has run out. Ask for a new one.")
        if hmac.compare_digest(_hash(app, typed), saved["hash"]):
            _set(app, "auth_code", {})                      # each code works once
            try:
                (app.config["V3_DATA_DIR"] / CODE_FILE).unlink()      # plan B file: gone once used
            except OSError:
                pass
            _set(app, "auth_fails", {})
            return _signed_in_response(app)
        _add_fail(app)
        until = locked_until(app)
        return _page(app, "code", error=_lock_text(until) if until else "That code is not right. Try again.")

    @app.route("/signin/backup", methods=["POST"])
    def signin_backup():
        until = locked_until(app)
        if until:
            return _page(app, "backup", error=_lock_text(until))
        h = _hash(app, _clean_backup(request.form.get("code")))
        left = _get(app, "auth_backup", [])
        match = next((x for x in left if hmac.compare_digest(x, h)), None)
        if match:
            left.remove(match)                              # used up
            _set(app, "auth_backup", left)
            _set(app, "auth_fails", {})
            return _signed_in_response(app)
        _add_fail(app)
        until = locked_until(app)
        return _page(app, "backup", error=_lock_text(until) if until else "That backup code is not right.")

    @app.route("/unlock", methods=["GET", "POST"])
    def unlock():
        token = request.cookies.get(COOKIE)
        if request.method == "GET":
            if unlocked(app, token):
                return redirect("/")
            return _page(app, "unlock")
        until = locked_until(app)
        if until:
            return _page(app, "unlock", error=_lock_text(until))
        if pin_ok(app, "".join((request.form.get("pin") or "").split())):
            _set(app, "auth_fails", {})
            _unlock(app, token)
            return redirect("/", code=303)
        _add_fail(app)
        until = locked_until(app)
        return _page(app, "unlock", error=_lock_text(until) if until else "That passcode is not right. Try again.")

    @app.route("/unlock/forgot", methods=["POST"])
    def unlock_forgot():
        """Forgot the passcode: sign in by email again, then choose a new one."""
        _forget_device(app, request.cookies.get(COOKIE))
        session.clear()
        session["forgot"] = True
        resp = redirect("/signin", code=303)
        resp.delete_cookie(COOKIE)
        return resp

    @app.route("/pin/new", methods=["GET", "POST"])
    def pin_new():
        """Choose the passcode: the first time, or just after an email sign-in (Forgot / Change passcode)."""
        until = session.get("new_pin_until")
        allowed = not pin_is_set(app) or (until and now() < datetime.fromisoformat(until))
        if not allowed:
            return redirect("/")
        if request.method == "GET":
            return _page(app, "newpin")
        pin = "".join((request.form.get("pin") or "").split())
        problem = pin_problem(pin, "".join((request.form.get("again") or "").split()))
        if problem:
            return _page(app, "newpin", error=problem)
        set_pin(app, pin)
        session.pop("new_pin_until", None)
        _unlock(app, request.cookies.get(COOKIE))
        return redirect("/", code=303)

    @app.route("/settings/pin", methods=["POST"])
    def change_pin():
        """Change passcode (from Settings): sign in by email first, then choose a new one."""
        return unlock_forgot()

    @app.route("/settings/codes", methods=["POST"])
    def backup_codes():
        resp = _page(app, "codes", codes=make_backup_codes(app))
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.route("/signout", methods=["POST"])
    def signout():
        _forget_device(app, request.cookies.get(COOKIE))
        session.clear()
        resp = redirect("/signin", code=303)
        resp.delete_cookie(COOKIE)
        return resp

    @app.route("/signout/all", methods=["POST"])
    def signout_all():
        _set(app, "auth_devices", {})
        session.clear()
        resp = redirect("/signin", code=303)
        resp.delete_cookie(COOKIE)
        return resp
