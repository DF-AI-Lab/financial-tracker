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


def upload(conn, html, http=http_json, stamp=None) -> bool:
    """Send the PC's copy of the page (and the PIN hash) up. False if not set up or no internet."""
    s = settings(conn)
    if s is None:
        return False
    body = {"html": html, "pin_salt": get_value(conn, "phone_pin_salt") or "",
            "pin_hash": get_value(conn, "phone_pin_hash") or "",
            "stamp": str(stamp) if stamp is not None else str(__import__('time').time())}
    try:
        http("POST", s[0] + "/api/upload", s[1], body)
        return True
    except OSError:
        return False


def apply_changes(conn, changes, wage_payer) -> int:
    """Apply phone changes (add, remove, pay, left, bill, sort, ask, card types).
    Returns how many were done. Never raises on bad input."""
    from fintrack.home import home_data
    from fintrack.billchange import set_change, clear_change, set_left, clear_left
    from fintrack.sortpage import save_answers
    from fintrack.pagequestions import answer as answer_question

    ids = {s["id"] for s in get_spends(conn)}
    done = 0
    for c in changes:
        cid = c.get("cid")
        ctype = c.get("type")
        try:
            if ctype == "add":
                if not isinstance(c.get("amount"), (int, float)) or isinstance(c.get("amount"), bool):
                    continue
                if c.get("amount") <= 0:
                    continue
                try:
                    d = date.fromisoformat(c.get("date", ""))
                except (TypeError, ValueError):
                    continue
                name = c.get("name", "")
                if not name:
                    continue
                add_spend(conn, d, float(c["amount"]), name, guess_category(name))
                done += 1
            elif ctype == "remove":
                if not isinstance(c.get("id"), int) or isinstance(c.get("id"), bool):
                    continue
                if c["id"] in ids:
                    delete_spend(conn, c["id"])
                    done += 1
            elif ctype == "pay":
                amount = c.get("amount")
                if not isinstance(amount, (int, float)) or isinstance(amount, bool) or amount <= 0:
                    continue
                from fintrack.store import set_value, clear_spends
                set_value(conn, "pay", str(float(amount)))
                if c.get("clear") is True:
                    clear_spends(conn)
                done += 1
            elif ctype == "left":
                d = home_data(conn, wage_payer=wage_payer)
                if not d.get("ready"):
                    continue
                amount = c.get("amount")
                if amount is None:
                    clear_left(conn, d["cycle_start"])
                    done += 1
                elif isinstance(amount, (int, float)) and not isinstance(amount, bool):
                    set_left(conn, d["cycle_start"], float(amount))
                    done += 1
            elif ctype == "bill":
                d = home_data(conn, wage_payer=wage_payer)
                if not d.get("ready"):
                    continue
                key = c.get("key")
                valid_keys = [b["key"] for b in d["pay"]["bills"]]
                if key not in valid_keys:
                    continue
                # Handle stopped flag
                if "stopped" in c:
                    from fintrack.billchange import set_stopped
                    stopped_val = c.get("stopped")
                    if isinstance(stopped_val, bool):
                        set_stopped(conn, key, stopped_val, date.today())
                        done += 1
                else:
                    # Handle amount change
                    amount = c.get("amount")
                    if amount is None:
                        clear_change(conn, d["cycle_start"], key)
                        done += 1
                    elif isinstance(amount, (int, float)) and not isinstance(amount, bool):
                        set_change(conn, d["cycle_start"], key, float(amount))
                        done += 1
            elif ctype == "sort":
                answers = c.get("answers")
                if isinstance(answers, list):
                    save_answers(conn, answers)
                    done += 1
            elif ctype == "card":
                from fintrack import creditcard
                action, amount = c.get("action"), c.get("amount")
                is_num = isinstance(amount, (int, float)) and not isinstance(amount, bool)
                if action == "add" and is_num and amount != 0 and str(c.get("name", "")).strip():
                    try:
                        d = date.fromisoformat(c.get("date", ""))
                    except (TypeError, ValueError):
                        continue
                    creditcard.add_card(conn, d, float(amount), str(c["name"]))
                    done += 1
                elif action == "remove" and isinstance(c.get("id"), int) and not isinstance(c.get("id"), bool):
                    if creditcard.remove_card(conn, c["id"]):
                        done += 1
                elif action == "balance" and is_num and amount >= 0:
                    try:
                        d = date.fromisoformat(c.get("date", ""))
                    except (TypeError, ValueError):
                        continue
                    creditcard.set_balance(conn, d, float(amount))
                    done += 1
                elif action == "limit" and is_num and amount > 0:
                    creditcard.set_limit(conn, float(amount))
                    done += 1
            elif ctype == "ask":
                d = home_data(conn, wage_payer=wage_payer)
                if not d.get("ready"):
                    continue
                from fintrack.home import txns_and_paydays
                txns, paydays, payers = txns_and_paydays(conn, wage_payer)
                answer_data = c.get("answer")
                if isinstance(answer_data, dict):
                    answer_question(conn, answer_data, txns, paydays, payers=payers)
                    done += 1
        except Exception:
            # Silently ignore any errors processing this change
            pass
    return done


def sync_once(conn, wage_payer, http=http_json):
    """Fetch and apply all phone changes, then clear them online.
    Returns count done (0+) or None if offline/not set up."""
    if settings(conn) is None:
        return None
    changes = fetch_changes(conn, http)
    if changes is None:
        return None
    if not changes:
        return 0
    # Changes already done (the clear may have failed last time) are never done twice
    try:
        done_cids = json.loads(get_value(conn, "phone_done") or "[]")
    except ValueError:
        done_cids = []
    todo = [c for c in changes if c.get("cid") not in done_cids]
    done = apply_changes(conn, todo, wage_payer)
    set_value(conn, "phone_done", json.dumps((done_cids + [c.get("cid") for c in todo])[-500:]))
    clear_changes(conn, [c.get("cid") for c in changes], http)
    return done


def sync_terminal(conn, out=print, http=http_json, wage_payer=None):
    """Terminal output only, no user interaction. Never asks, never raises."""
    if settings(conn) is None:
        return
    try:
        n = sync_once(conn, wage_payer, http)
    except Exception:
        out("Phone sync skipped (no internet).")
        return
    if n is None:
        out("Phone sync skipped (no internet).")
    elif n >= 1:
        msg = f"Phone: {n} change from your phone done."
        if n != 1:
            msg = f"Phone: {n} changes from your phone done."
        out(msg)
