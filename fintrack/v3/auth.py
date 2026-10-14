"""v3 sign-in by email code (14 Oct 2026).

Only one email (settings["email"]) may sign in. POST /signin sends a 6-digit code (10 minutes, at most 5 an hour);
the right code (or an unused backup code) gives this device a token in the COOKIE cookie for 30 days.
5 wrong tries lock sign-in for 15 minutes. Every other page needs a signed-in device.
Only HMAC hashes of codes and tokens are kept (kv table). Plain codes and tokens are never stored or logged.

kv keys (JSON text):
  auth_code     {"hash", "expires"}            the last code sent
  auth_sent     [ISO time, ...]                 codes sent in the last hour
  auth_fails    {"count", "until"}             wrong tries, and the lock end time
  auth_devices  {token hash: created ISO}       signed-in devices
  auth_backup   [hash, ...]                     unused backup codes
"""
import hashlib
import hmac
import json
import secrets
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage

from flask import make_response, redirect, render_template, request

from fintrack.appversion import VERSION
from fintrack.store import open_db, get_value, set_value

COOKIE = "wmm_device"
CODE_MINUTES = 10
CODES_PER_HOUR = 5
MAX_TRIES = 5
LOCK_MINUTES = 15
DEVICE_DAYS = 30
BACKUP_COUNT = 8
BACKUP_LETTERS = "abcdefghjkmnpqrstuvwxyz23456789"      # no 0/o, 1/l/i look-alikes

OPEN_PATHS = ("/signin", "/signin/code", "/signin/backup", "/manifest.json")


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
    return (app.config["V3_SETTINGS"].get("email") or "").strip().lower()


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
    """Go to the home page with a new device cookie."""
    resp = redirect("/", code=303)
    resp.set_cookie(COOKIE, make_device(app), max_age=DEVICE_DAYS * 24 * 3600, httponly=True, samesite="Lax",
                    secure=request.is_secure)
    return resp


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
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as smtp:
            smtp.starttls()
            smtp.login(s["smtp_user"], s["smtp_password"])
            smtp.send_message(msg)
        return
    print(f"Sign-in code: {code}", flush=True)


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

def _page(app, step="email", error="", sent=False, codes=None, status=200):
    if not _allowed_email(app):
        step = "noemail"
    html = render_template("signin.html", step=step, error=error, sent=sent, codes=codes or [],
                           app_version=VERSION)
    return make_response(html, status)


def register(app) -> None:

    @app.before_request
    def need_sign_in():
        path = request.path
        if path in OPEN_PATHS or path.startswith("/static/"):
            return None
        if device_ok(app, request.cookies.get(COOKIE)):
            return None
        if request.method == "GET":
            return redirect("/signin")
        return ("Please sign in again.", 401)

    @app.route("/signin", methods=["GET"])
    def signin():
        if device_ok(app, request.cookies.get(COOKIE)):
            return redirect("/")
        step = "backup" if request.args.get("backup") else "email"
        return _page(app, step)

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
            try:
                send_code(app, allowed, new_code(app))
            except (OSError, smtplib.SMTPException):
                return _page(app, "email", error="The email could not be sent. Check the Gmail settings "
                                                 "in v3_settings.json.")
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

    @app.route("/settings/codes", methods=["POST"])
    def backup_codes():
        resp = _page(app, "codes", codes=make_backup_codes(app))
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.route("/signout", methods=["POST"])
    def signout():
        _forget_device(app, request.cookies.get(COOKIE))
        resp = redirect("/signin", code=303)
        resp.delete_cookie(COOKIE)
        return resp

    @app.route("/signout/all", methods=["POST"])
    def signout_all():
        _set(app, "auth_devices", {})
        resp = redirect("/signin", code=303)
        resp.delete_cookie(COOKIE)
        return resp
