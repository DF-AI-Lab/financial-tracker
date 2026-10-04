"""Step 10 of SPEC.md: the phone copy, PC side.

The PC sends its home page up (upload) and takes the phone's changes down (fetch_changes),
but only does them after the user says yes. The PC has the final say.
Settings live in the kv table: phone_url, phone_key, phone_pin_salt, phone_pin_hash.
"""
import hashlib
import json
import secrets
import urllib.request
from datetime import date
from pathlib import Path

from fintrack.categories import guess_category
from fintrack.store import add_spend, delete_spend, get_spends, get_value, set_value

OFFLINE = "Phone sync skipped (no internet)."
# One secret key per PC (outside the code folder), so the test database and the real one share it:
# the site only ever accepts the first key it sees.
KEY_FILE = Path.home() / ".financial_tracker_phone_key.txt"


def hash_pin(pin, salt):
    return hashlib.sha256((salt + pin).encode()).hexdigest()


def set_pin(conn, pin) -> bool:
    """Save a 4-8 digit PIN (salted hash only). False if it is not 4-8 digits."""
    pin = pin.strip()
    if not (pin.isdigit() and 4 <= len(pin) <= 8):
        return False
    salt = secrets.token_hex(16)
    set_value(conn, "phone_pin_salt", salt)
    set_value(conn, "phone_pin_hash", hash_pin(pin, salt))
    return True


def connect(conn, url):
    """Save the site address and the PC's secret key (made once, kept in KEY_FILE)."""
    set_value(conn, "phone_url", url.strip().rstrip("/"))
    try:
        key = KEY_FILE.read_text().strip()
    except OSError:
        key = ""
    if len(key) < 32:
        key = get_value(conn, "phone_key") or secrets.token_hex(24)
        KEY_FILE.write_text(key)
    set_value(conn, "phone_key", key)


def settings(conn):
    """(url, key), or None if the phone copy is not set up."""
    url, key = get_value(conn, "phone_url"), get_value(conn, "phone_key")
    return (url, key) if url and key else None


def http_json(method, url, key, body=None):
    """One request to the site. Raises OSError (no internet, refused...)."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"X-Key": key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=6) as r:
            return json.loads(r.read().decode() or "{}")
    except ValueError as e:
        raise OSError(str(e))


def fetch_changes(conn, http=http_json):
    """The phone's changes waiting online. [] if not set up, None if the site can't be reached."""
    s = settings(conn)
    if s is None:
        return []
    try:
        return http("GET", s[0] + "/api/changes", s[1])["changes"]
    except (OSError, KeyError, TypeError):
        return None


def clear_changes(conn, cids, http=http_json) -> bool:
    s = settings(conn)
    if s is None or not cids:
        return False
    try:
        http("POST", s[0] + "/api/clear", s[1], {"cids": list(cids)})
        return True
    except OSError:
        return False


def upload(conn, html, http=http_json) -> bool:
    """Send the PC's copy of the page (and the PIN hash) up. False if not set up or no internet."""
    s = settings(conn)
    if s is None:
        return False
    body = {"html": html, "pin_salt": get_value(conn, "phone_pin_salt") or "",
            "pin_hash": get_value(conn, "phone_pin_hash") or ""}
    try:
        http("POST", s[0] + "/api/upload", s[1], body)
        return True
    except OSError:
        return False


def describe(c) -> str:
    if c["type"] == "add":
        return f"Add    {c['amount']:>7.2f}  {c['name']}  ({date.fromisoformat(c['date']):%d %b})"
    return f"Remove {c['amount']:>7.2f}  {c['name']}"


def apply_changes(conn, changes, skip=()) -> int:
    """Do the changes not in skip (a set of cids). A remove whose spend is already gone is ignored.
    Returns how many were done."""
    ids = {s["id"] for s in get_spends(conn)}
    done = 0
    for c in changes:
        if c["cid"] in skip:
            continue
        if c["type"] == "add":
            add_spend(conn, date.fromisoformat(c["date"]), float(c["amount"]), c["name"], guess_category(c["name"]))
            done += 1
        elif c["type"] == "remove" and c["id"] in ids:
            delete_spend(conn, c["id"])
            done += 1
    return done


def sync_terminal(conn, ask=input, out=print, http=http_json):
    """run.py start: list the phone's changes, Enter = do them all, numbers = skip those.
    Every listed change is then cleared online (skipped ones are dropped: the PC has the final say)."""
    if settings(conn) is None:
        return
    changes = fetch_changes(conn, http)
    if changes is None:
        out(OFFLINE)
        return
    if not changes:
        return
    out("")
    out("FROM YOUR PHONE")
    for i, c in enumerate(changes, 1):
        out(f"  {i:>2}  {describe(c)}")
    try:
        answer = ask("Enter = do them all, or type the numbers to skip (e.g. 2 3): ")
    except (EOFError, OSError):
        out("(No keyboard available, phone changes left for next time.)")
        return
    skip = set()
    for word in answer.replace(",", " ").split():
        if word.isdigit() and 1 <= int(word) <= len(changes):
            skip.add(changes[int(word) - 1]["cid"])
    done = apply_changes(conn, changes, skip)
    clear_changes(conn, [c["cid"] for c in changes], http)
    out(f"Done {done} from your phone" + (f", skipped {len(skip)}." if skip else "."))
