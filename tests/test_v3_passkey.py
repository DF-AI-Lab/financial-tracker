"""v3 fingerprint unlock (passkey, WebAuthn) instead of typing the passcode (Darren, 15 Oct 2026). Fake data only.

A fake fingerprint reader (FakeReader) makes real WebAuthn answers with its own EC key, so the server checks them
exactly as it would a phone's. The passcode keeps working; the weekly email code is unchanged.
"""
import base64
import hashlib
import json
import struct
from datetime import datetime, timedelta

import pytest

from tests.v3_helpers import v3_data, v3_app, ACME  # noqa: F401

pytest.importorskip("flask")
pytest.importorskip("webauthn")
from cryptography.hazmat.primitives import hashes  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402
import cbor2  # noqa: E402

from fintrack.v3 import auth, passkey  # noqa: E402

PIN = "246810"
HOST = "localhost"                  # Flask's test client


def b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


class FakeReader:
    """A phone's fingerprint reader: one key, a counter, and the flags it sets (UP=1, UV=4)."""

    def __init__(self, cred_id=b"fake-credential-1", verified=True):
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.cred_id = cred_id
        self.count = 0
        self.verified = verified

    def _flags(self, extra=0):
        return 0x01 | (0x04 if self.verified else 0) | extra

    def _client_data(self, kind, challenge, origin):
        return json.dumps({"type": kind, "challenge": challenge, "origin": origin, "crossOrigin": False}).encode()

    def create(self, options, origin=f"http://{HOST}"):
        nums = self.key.public_key().public_numbers()
        cose = cbor2.dumps({1: 2, 3: -7, -1: 1, -2: nums.x.to_bytes(32, "big"), -3: nums.y.to_bytes(32, "big")})
        rp_hash = hashlib.sha256(options["rp"]["id"].encode()).digest()
        auth_data = (rp_hash + bytes([self._flags(0x40)]) + struct.pack(">I", self.count) + bytes(16)
                     + struct.pack(">H", len(self.cred_id)) + self.cred_id + cose)
        cd = self._client_data("webauthn.create", options["challenge"], origin)
        att = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
        return {"id": b64(self.cred_id), "rawId": b64(self.cred_id), "type": "public-key",
                "response": {"clientDataJSON": b64(cd), "attestationObject": b64(att)}}

    def get(self, options, origin=f"http://{HOST}", rp_id=HOST):
        self.count += 1
        auth_data = hashlib.sha256(rp_id.encode()).digest() + bytes([self._flags()]) + struct.pack(">I", self.count)
        cd = self._client_data("webauthn.get", options["challenge"], origin)
        sig = self.key.sign(auth_data + hashlib.sha256(cd).digest(), ec.ECDSA(hashes.SHA256()))
        return {"id": b64(self.cred_id), "rawId": b64(self.cred_id), "type": "public-key",
                "response": {"clientDataJSON": b64(cd), "authenticatorData": b64(auth_data),
                             "signature": b64(sig), "userHandle": None}}


@pytest.fixture
def clock(monkeypatch):
    c = {"t": datetime(2026, 10, 15, 9, 0)}
    monkeypatch.setattr(auth, "now", lambda: c["t"])
    return c


@pytest.fixture
def app(v3_app, clock):
    v3_app.config["V3_SETTINGS"]["email"] = "darren@example.com"
    return v3_app


@pytest.fixture
def client(app):
    c = app.test_client()
    auth.sign_in_for_tests(app, c, PIN)                    # device + passcode + unlocked
    return c


def lock(client):
    """Like opening the site again later: signed-in device, but the passcode (or fingerprint) is needed."""
    with client.session_transaction() as s:
        s.pop("unlocked", None)


def add_reader(client, reader=None):
    reader = reader or FakeReader()
    opts = client.post("/passkey/new/start").get_json()
    r = client.post("/passkey/new", json=reader.create(opts))
    assert r.status_code == 200 and r.get_json()["ok"], r.data
    return reader


def try_unlock(client, reader, **kw):
    opts = client.post("/passkey/start").get_json()
    return client.post("/passkey/unlock", json=reader.get(opts, **kw))


# --- turning it on ---------------------------------------------------------------------------------------------------

def test_setup_page_needs_unlock(app, client):
    assert client.get("/passkey/setup").status_code == 200
    lock(client)
    assert client.get("/passkey/setup").headers["Location"].endswith("/unlock")
    assert client.post("/passkey/new/start").status_code == 401


def test_setup_page_has_the_button_and_settings_links_to_it(client):
    page = client.get("/passkey/setup").get_data(as_text=True)
    assert "Turn on fingerprint" in page
    assert 'href="/passkey/setup"' in client.get("/").get_data(as_text=True)


def test_register_options_ask_for_this_phone_and_a_real_fingerprint(client):
    opts = client.post("/passkey/new/start").get_json()
    assert opts["rp"]["id"] == HOST
    assert opts["authenticatorSelection"]["authenticatorAttachment"] == "platform"
    assert opts["authenticatorSelection"]["userVerification"] == "required"
    assert len(unb64(opts["challenge"])) >= 16


def test_register_saves_only_the_public_key(app, client):
    add_reader(client)
    keys = passkey.saved(app)
    assert len(keys) == 1 and keys[0]["id"] == b64(b"fake-credential-1")
    assert set(keys[0]) >= {"id", "key", "count", "created"}


def test_register_twice_same_reader_is_refused_by_options(client):
    reader = add_reader(client)
    opts = client.post("/passkey/new/start").get_json()
    assert [c["id"] for c in opts["excludeCredentials"]] == [b64(reader.cred_id)]


def test_register_with_wrong_challenge_refused(app, client):
    client.post("/passkey/new/start")
    r = client.post("/passkey/new", json=FakeReader().create({"rp": {"id": HOST}, "challenge": b64(b"x" * 32)}))
    assert r.status_code == 400 and passkey.saved(app) == []


def test_register_from_another_site_refused(app, client):
    opts = client.post("/passkey/new/start").get_json()
    r = client.post("/passkey/new", json=FakeReader().create(opts, origin="https://evil.example"))
    assert r.status_code == 400 and passkey.saved(app) == []


def test_register_without_fingerprint_check_refused(app, client):
    opts = client.post("/passkey/new/start").get_json()
    r = client.post("/passkey/new", json=FakeReader(verified=False).create(opts))
    assert r.status_code == 400 and passkey.saved(app) == []


# --- unlocking -------------------------------------------------------------------------------------------------------

def test_unlock_page_without_passkeys_has_no_fingerprint_button(client):
    lock(client)
    page = client.get("/unlock").get_data(as_text=True)
    assert "Use fingerprint" not in page and 'name="pin"' in page


def test_unlock_page_with_passkey_offers_fingerprint_and_passcode(client):
    add_reader(client)
    lock(client)
    page = client.get("/unlock").get_data(as_text=True)
    assert "Use fingerprint" in page and 'name="pin"' in page


def test_fingerprint_unlocks(app, client):
    reader = add_reader(client)
    lock(client)
    assert client.get("/").status_code in (302, 303)
    opts = client.post("/passkey/start").get_json()
    assert opts["rpId"] == HOST and [c["id"] for c in opts["allowCredentials"]] == [b64(reader.cred_id)]
    assert opts["userVerification"] == "required"
    r = client.post("/passkey/unlock", json=reader.get(opts))
    assert r.status_code == 200 and r.get_json() == {"ok": True, "go": "/"}
    assert client.get("/").status_code == 200
    assert passkey.saved(app)[0]["count"] == 1


def test_passcode_still_works_with_a_passkey(client):
    add_reader(client)
    lock(client)
    client.post("/unlock", data={"pin": PIN})
    assert client.get("/").status_code == 200


def test_start_without_passkeys_says_none(client):
    lock(client)
    assert client.post("/passkey/start").status_code == 404


def test_fingerprint_needs_a_signed_in_device(app, client):
    reader = add_reader(client)
    other = app.test_client()                               # a browser that never had the email code
    assert other.post("/passkey/start").status_code == 401
    assert other.post("/passkey/unlock", json=reader.get({"challenge": b64(b"y" * 32)})).status_code == 401


def test_challenge_works_once(client):
    reader = add_reader(client)
    lock(client)
    opts = client.post("/passkey/start").get_json()
    answer = reader.get(opts)
    assert client.post("/passkey/unlock", json=answer).status_code == 200
    lock(client)
    assert client.post("/passkey/unlock", json=answer).status_code == 400


def test_challenge_runs_out_after_5_minutes(client, clock):
    reader = add_reader(client)
    lock(client)
    opts = client.post("/passkey/start").get_json()
    clock["t"] += timedelta(minutes=6)
    assert client.post("/passkey/unlock", json=reader.get(opts)).status_code == 400


def test_unknown_reader_refused(client):
    add_reader(client)
    lock(client)
    r = try_unlock(client, FakeReader(cred_id=b"someone-else"))
    assert r.status_code == 400 and client.get("/").status_code in (302, 303)


def test_wrong_site_refused(client):
    reader = add_reader(client)
    lock(client)
    assert try_unlock(client, reader, origin="https://evil.example").status_code == 400
    assert try_unlock(client, reader, rp_id="evil.example").status_code == 400


def test_no_fingerprint_check_refused(client):
    reader = add_reader(client)
    reader.verified = False
    lock(client)
    assert try_unlock(client, reader).status_code == 400


def test_wrong_tries_count_toward_the_lock(app, client):
    add_reader(client)
    lock(client)
    for _ in range(auth.MAX_TRIES):
        try_unlock(client, FakeReader(cred_id=b"nope"))
    assert auth.locked_until(app)
    good = FakeReader()                                     # even a right answer waits for the lock
    r = client.post("/passkey/unlock", json=good.get({"challenge": b64(b"z" * 32)}))
    assert r.status_code == 429


def test_cancelled_fingerprint_does_not_count(app, client):
    """Closing the phone's fingerprint box sends nothing: no wrong try is counted for just asking."""
    add_reader(client)
    lock(client)
    for _ in range(auth.MAX_TRIES + 1):
        client.post("/passkey/start")
    assert not auth.locked_until(app)


# --- forgetting ------------------------------------------------------------------------------------------------------

def test_forget_fingerprints(app, client):
    add_reader(client)
    r = client.post("/passkey/forget")
    assert r.status_code in (302, 303) and passkey.saved(app) == []
    lock(client)
    assert "Use fingerprint" not in client.get("/unlock").get_data(as_text=True)

