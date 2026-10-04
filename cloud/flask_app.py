"""Step 10 of SPEC.md: the online copy for the phone (runs on PythonAnywhere, not on the PC).

It knows nothing about banks. It only keeps:
  page.html     the home page the PC sent (only the PC writes it)
  changes.json  spends added/removed on the phone, waiting for the PC (only the phone writes them)
  key.txt       the PC's secret key (the first key it sees is kept)
  pin.json      the PIN, salted and hashed (sent by the PC)
"""
import hashlib
import hmac
import json
import secrets
import time
from datetime import date, timedelta
from pathlib import Path

from flask import Flask, jsonify, redirect, request, session

MAX_TRIES = 5
LOCK_SECONDS = 15 * 60

PIN_PAGE = """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Wage Tracker</title>
<style>
 :root { --bg:#f6f7f9; --card:#fff; --text:#1a1a1a; --accent:#0b63ce; --bad:#c62828; }
 @media (prefers-color-scheme: dark) { :root { --bg:#15171a; --card:#1f2226; --text:#f2f2f2; --accent:#5aa2ff; --bad:#ff7a7a; } }
 body { margin:0; background:var(--bg); color:var(--text); font:17px/1.5 system-ui,-apple-system,sans-serif; }
 .box { max-width:340px; margin:60px auto; padding:24px 16px; text-align:center; background:var(--card); border-radius:14px; }
 input { font-size:28px; width:100%; text-align:center; letter-spacing:8px; padding:10px; border-radius:10px; border:1px solid #888; box-sizing:border-box; }
 button { margin-top:14px; width:100%; padding:12px; font-size:18px; border:0; border-radius:10px; background:var(--accent); color:#fff; }
 .msg { color:var(--bad); margin-top:12px; }
</style></head><body><div class="box"><h2>💷 Wage Tracker</h2>MSG_HERE</div></body></html>"""

PIN_FORM = """<form method="post" action="login"><p>Your PIN</p>
<input name="pin" type="password" inputmode="numeric" autocomplete="current-password" autofocus>
<button type="submit">Open</button></form>"""


def create_app(data_dir=None, secure=True):
    data = Path(data_dir) if data_dir else Path(__file__).parent / "data"
    data.mkdir(parents=True, exist_ok=True)

    secret = data / "secret.txt"
    if not secret.exists():
        secret.write_text(secrets.token_hex(32))

    app = Flask(__name__)
    app.secret_key = secret.read_text().strip()
    app.config.update(SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_SECURE=secure,
                      SESSION_COOKIE_HTTPONLY=True, PERMANENT_SESSION_LIFETIME=timedelta(days=30),
                      MAX_CONTENT_LENGTH=5 * 1024 * 1024)

    def read(name, default):
        try:
            return json.loads((data / name).read_text())
        except (OSError, ValueError):
            return default

    def write(name, value):
        tmp = data / (name + ".tmp")
        tmp.write_text(json.dumps(value))
        tmp.replace(data / name)

    def pin_page(msg):
        return PIN_PAGE.replace("MSG_HERE", msg)

    def pc_ok():
        """True if the request carries the PC's key. The very first key is kept."""
        given = request.headers.get("X-Key", "")
        if len(given) < 32:
            return False
        keyfile = data / "key.txt"
        if not keyfile.exists():
            keyfile.write_text(given)
            return True
        return hmac.compare_digest(keyfile.read_text().strip(), given)

    def logged_in():
        return session.get("ok") is True and session.get("pin") == read("pin.json", {}).get("hash")

    # ---- the phone ----------------------------------------------------------------------------

    @app.route("/")
    def home():
        page = data / "page.html"
        if not page.exists():
            return pin_page("<p>Waiting for your PC to send a copy.</p>")
        if not read("pin.json", {}).get("hash"):
            return pin_page("<p>Set a PIN on your PC first:</p><p><b>run.py pin 1234</b></p>")
        if not logged_in():
            return pin_page(PIN_FORM)
        return page.read_text(encoding="utf-8")

    @app.route("/login", methods=["POST"])
    def login():
        pin = read("pin.json", {})
        lock = read("lock.json", {"fails": 0, "until": 0})
        if lock["until"] > time.time():
            return pin_page(PIN_FORM + f'<p class="msg">Locked. Try again in {int((lock["until"] - time.time()) / 60) + 1} minutes.</p>')
        given = request.form.get("pin", "")
        want = pin.get("hash", "")
        got = hashlib.sha256((pin.get("salt", "") + given).encode()).hexdigest()
        if want and hmac.compare_digest(want, got):
            write("lock.json", {"fails": 0, "until": 0})
            session.permanent = True
            session["ok"] = True
            session["pin"] = want
            return redirect("./", code=303)
        fails = lock["fails"] + 1
        if fails >= MAX_TRIES:
            write("lock.json", {"fails": 0, "until": time.time() + LOCK_SECONDS})
            return pin_page(PIN_FORM + '<p class="msg">Locked for 15 minutes.</p>')
        write("lock.json", {"fails": fails, "until": 0})
        return pin_page(PIN_FORM + f'<p class="msg">Wrong PIN. {MAX_TRIES - fails} tries left.</p>')

    @app.route("/pending")
    def pending():
        if not logged_in():
            return jsonify(error="login"), 401
        return jsonify(changes=read("changes.json", []))

    @app.route("/send", methods=["POST"])
    def send():
        if not logged_in():
            return jsonify(error="login"), 401
        new = (request.get_json(silent=True) or {}).get("changes")
        if not isinstance(new, list) or not all(valid(c) for c in new):
            return jsonify(error="bad change"), 400
        changes = read("changes.json", [])
        have = {c["cid"] for c in changes}
        changes += [c for c in new if c["cid"] not in have]
        write("changes.json", changes)
        return jsonify(changes=changes)

    @app.route("/cancel", methods=["POST"])
    def cancel():
        if not logged_in():
            return jsonify(error="login"), 401
        cid = (request.get_json(silent=True) or {}).get("cid")
        changes = [c for c in read("changes.json", []) if c["cid"] != cid]
        write("changes.json", changes)
        return jsonify(changes=changes)

    # ---- the PC -------------------------------------------------------------------------------

    @app.route("/api/upload", methods=["POST"])
    def api_upload():
        if not pc_ok():
            return jsonify(error="key"), 403
        body = request.get_json(silent=True) or {}
        if not isinstance(body.get("html"), str):
            return jsonify(error="no page"), 400
        (data / "page.html").write_text(body["html"], encoding="utf-8")
        write("pin.json", {"salt": str(body.get("pin_salt", "")), "hash": str(body.get("pin_hash", ""))})
        return jsonify(ok=True)

    @app.route("/api/changes")
    def api_changes():
        if not pc_ok():
            return jsonify(error="key"), 403
        return jsonify(changes=read("changes.json", []))

    @app.route("/api/clear", methods=["POST"])
    def api_clear():
        if not pc_ok():
            return jsonify(error="key"), 403
        done = set((request.get_json(silent=True) or {}).get("cids", []))
        write("changes.json", [c for c in read("changes.json", []) if c["cid"] not in done])
        return jsonify(ok=True)

    return app


def valid(c):
    """A phone change: add {cid, date, amount, name} or remove {cid, id, name, amount}."""
    if not isinstance(c, dict) or not isinstance(c.get("cid"), str) or not 0 < len(c["cid"]) <= 40:
        return False
    if not isinstance(c.get("name"), str) or not 0 < len(c["name"].strip()) <= 60:
        return False
    amount = c.get("amount")
    if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not 0 < amount < 1_000_000:
        return False
    if c.get("type") == "add":
        try:
            date.fromisoformat(c.get("date"))
        except (TypeError, ValueError):
            return False
        return True
    if c.get("type") == "remove":
        return isinstance(c.get("id"), int) and not isinstance(c.get("id"), bool)
    return False


app = create_app()
