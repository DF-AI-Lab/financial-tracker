"""v3 fingerprint unlock (Darren, 15 Oct 2026): a passkey (WebAuthn, the phone's own fingerprint reader) instead of
typing the 6-digit passcode. The passcode stays as the fallback; the weekly email code is unchanged (a passkey only
unlocks a device that is already signed in).

Settings → 👆 Fingerprint (/passkey/setup) turns it on for the phone in your hand. The unlock page then asks for the
fingerprint at once, with the passcode box below it. Needs the 'webauthn' package (pip install webauthn); without it
the fingerprint parts stay hidden and the passcode works as before.

kv keys (JSON text):
  auth_passkeys      [{"id", "key", "count", "created"}]   credential id + PUBLIC key (base64url), sign counter
  auth_pk_challenge  {"c", "until", "kind"}                the last challenge: works once, for 5 minutes
Wrong answers count toward the same 5-tries lock as passcodes. Asking (or cancelling the phone's box) does not.
"""
import base64
import json
import secrets
from datetime import datetime, timedelta

from flask import jsonify, redirect, request

from fintrack.v3 import auth

try:
    import webauthn
    from webauthn.helpers.structs import (AuthenticatorAttachment, AuthenticatorSelectionCriteria,
                                          PublicKeyCredentialDescriptor, ResidentKeyRequirement,
                                          UserVerificationRequirement)
    AVAILABLE = True
except ImportError:                                         # the package is not installed: passcode only
    AVAILABLE = False

CHALLENGE_MINUTES = 5
USER_ID = b"wheres-my-money"                                # one user: the same phone keeps one passkey for the site


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def saved(app) -> list:
    return auth._get(app, "auth_passkeys", [])


def ready(app) -> bool:
    """True when the unlock page should offer the fingerprint."""
    return AVAILABLE and bool(saved(app))


def _rp_id() -> str:
    return request.host.split(":")[0]


def _origins() -> list:
    return [f"https://{request.host}", f"http://{request.host}"]


def _new_challenge(app, kind: str) -> bytes:
    c = secrets.token_bytes(32)
    auth._set(app, "auth_pk_challenge", {"c": _b64(c), "kind": kind,
                                         "until": (auth.now() + timedelta(minutes=CHALLENGE_MINUTES)).isoformat()})
    return c


def _take_challenge(app, kind: str):
    """The waiting challenge (bytes), used up now; None when there is none, it is the other kind, or it ran out."""
    ch = auth._get(app, "auth_pk_challenge", {})
    auth._set(app, "auth_pk_challenge", {})
    if not ch.get("c") or ch.get("kind") != kind or auth.now() > datetime.fromisoformat(ch["until"]):
        return None
    return _unb64(ch["c"])


def _json(text: str):
    resp = jsonify(json.loads(text))
    resp.headers["Cache-Control"] = "no-store"
    return resp


def register(app) -> None:

    @app.route("/passkey/setup", methods=["GET"])
    def passkey_setup():
        return auth._page(app, "passkey", passkeys=saved(app), passkey_lib=AVAILABLE)

    @app.route("/passkey/new/start", methods=["POST"])
    def passkey_new_start():
        if not AVAILABLE:
            return ("Fingerprint is not set up on the server.", 503)
        opts = webauthn.generate_registration_options(
            rp_id=_rp_id(), rp_name="Where's My Money?", user_id=USER_ID,
            user_name=auth._allowed_email(app) or "me", user_display_name="Where's My Money?",
            challenge=_new_challenge(app, "create"),
            authenticator_selection=AuthenticatorSelectionCriteria(
                authenticator_attachment=AuthenticatorAttachment.PLATFORM,
                resident_key=ResidentKeyRequirement.PREFERRED,
                user_verification=UserVerificationRequirement.REQUIRED),
            exclude_credentials=[PublicKeyCredentialDescriptor(id=_unb64(k["id"])) for k in saved(app)])
        return _json(webauthn.options_to_json(opts))

    @app.route("/passkey/new", methods=["POST"])
    def passkey_new():
        if not AVAILABLE:
            return ("Fingerprint is not set up on the server.", 503)
        challenge = _take_challenge(app, "create")
        try:
            if challenge is None:
                raise ValueError("no challenge")
            v = webauthn.verify_registration_response(
                credential=request.get_json(force=True), expected_challenge=challenge, expected_rp_id=_rp_id(),
                expected_origin=_origins(), require_user_verification=True)
        except Exception:                                   # any bad answer is simply "no"
            return jsonify({"error": "That didn't work. Try again."}), 400
        keys = [k for k in saved(app) if k["id"] != _b64(v.credential_id)]
        keys.append({"id": _b64(v.credential_id), "key": _b64(v.credential_public_key), "count": v.sign_count,
                     "created": auth.now().isoformat()})
        auth._set(app, "auth_passkeys", keys)
        return jsonify({"ok": True})

    @app.route("/passkey/start", methods=["POST"])
    def passkey_start():
        if not ready(app):
            return ("No fingerprint set up.", 404)
        opts = webauthn.generate_authentication_options(
            rp_id=_rp_id(), challenge=_new_challenge(app, "get"),
            allow_credentials=[PublicKeyCredentialDescriptor(id=_unb64(k["id"])) for k in saved(app)],
            user_verification=UserVerificationRequirement.REQUIRED)
        return _json(webauthn.options_to_json(opts))

    @app.route("/passkey/unlock", methods=["POST"])
    def passkey_unlock():
        until = auth.locked_until(app)
        if until:
            return jsonify({"error": auth._lock_text(until)}), 429
        if not ready(app):
            return ("No fingerprint set up.", 404)
        challenge = _take_challenge(app, "get")
        keys = saved(app)
        try:
            answer = request.get_json(force=True)
            key = next(k for k in keys if k["id"] == answer.get("id"))
            if challenge is None:
                raise ValueError("no challenge")
            v = webauthn.verify_authentication_response(
                credential=answer, expected_challenge=challenge, expected_rp_id=_rp_id(),
                expected_origin=_origins(), credential_public_key=_unb64(key["key"]),
                credential_current_sign_count=key["count"], require_user_verification=True)
        except Exception:
            auth._add_fail(app)
            until = auth.locked_until(app)
            return jsonify({"error": auth._lock_text(until) if until else
                            "Fingerprint not recognised. Use your passcode."}), 400
        key["count"] = v.new_sign_count
        auth._set(app, "auth_passkeys", keys)
        auth._set(app, "auth_fails", {})
        auth._unlock(app, request.cookies.get(auth.COOKIE))
        return jsonify({"ok": True, "go": "/"})

    @app.route("/passkey/forget", methods=["POST"])
    def passkey_forget():
        auth._set(app, "auth_passkeys", [])
        return redirect("/passkey/setup", code=303)
