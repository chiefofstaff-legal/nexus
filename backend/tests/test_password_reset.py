"""Forgot-password / reset — Goodhart-proof regression suite.

Five tests, each falsifiable against a specific failure mode:

1. Sign/verify roundtrip — token issued then verified returns the same email.
2. Expired token rejected — exp 1s in the past returns None (TTL is real).
3. Tampered token rejected — flipping one HMAC byte returns None
   (constant-time HMAC check is wired).
4. /forgot returns identical bytes for known vs unknown email (no
   enumeration via status, body, or headers that could leak existence).
5. /reset invalidates the previous session cookie — login, capture cookie,
   reset, the old cookie now 401s on /api/auth/me.

The AgentMail shim is monkeypatched: capture (inbox_id, to) tuples in a
list rather than hitting the network. The test then proves the shim was
called on a known-email path and NOT called on the unknown path —
without making the response shape differ, so enumeration is still
impossible from the caller's view.
"""

from __future__ import annotations

import os
import time

import pytest
from fastapi.testclient import TestClient

os.environ["NEXUS_SESSION_SECURE"] = "false"  # TestClient over HTTP


@pytest.fixture
def fresh_app(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_SESSION_SECRET", "test-secret-for-reset-pytest")
    import app.auth as auth_module
    auth_module._SIGNING_KEY = None

    from app.main import app
    from app.auth import get_data_dir, get_user_store
    from services.user_store import UserStore

    store = UserStore(tmp_path)
    app.dependency_overrides[get_user_store] = lambda: store
    app.dependency_overrides[get_data_dir] = lambda: tmp_path
    app.state.data_dir = tmp_path
    app.state.user_store = store

    sends: list[dict] = []

    def _capture_send(*, inbox_id, to, subject, html_body):
        sends.append({"inbox_id": inbox_id, "to": to, "subject": subject})
        return True

    from services import agentmail_shim
    monkeypatch.setattr(agentmail_shim, "send", _capture_send)

    from lib.rate_limit import AUTH_LIMITER
    AUTH_LIMITER.reset()

    with TestClient(app) as client:
        yield client, store, tmp_path, sends
    app.dependency_overrides.clear()


# --- Unit-level token tests ---


def test_sign_and_verify_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_SESSION_SECRET", "roundtrip-secret")
    import app.auth as auth_module
    auth_module._SIGNING_KEY = None
    from app.auth import sign_reset_token, verify_reset_token

    token = sign_reset_token("alice@example.com", tmp_path, ttl_seconds=60)
    assert verify_reset_token(token, tmp_path) == "alice@example.com"


def test_expired_token_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_SESSION_SECRET", "expiry-secret")
    import app.auth as auth_module
    auth_module._SIGNING_KEY = None
    from app.auth import sign_reset_token, verify_reset_token

    past_now = int(time.time()) - 7200
    token = sign_reset_token("alice@example.com", tmp_path, ttl_seconds=3600, now=past_now)
    # Token expired ~1h ago by the time real `now` rolls around.
    assert verify_reset_token(token, tmp_path) is None


def test_tampered_token_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_SESSION_SECRET", "tamper-secret")
    import app.auth as auth_module
    auth_module._SIGNING_KEY = None
    from app.auth import sign_reset_token, verify_reset_token

    token = sign_reset_token("alice@example.com", tmp_path, ttl_seconds=600)
    payload_b64, sig_b64 = token.split(".")
    # Flip a single character in the HMAC half — must invalidate.
    flipped_char = "A" if sig_b64[0] != "A" else "B"
    tampered = f"{payload_b64}.{flipped_char}{sig_b64[1:]}"
    assert verify_reset_token(tampered, tmp_path) is None


# --- Integration-level enumeration + invalidation tests ---


def test_forgot_unknown_email_returns_204_no_enumeration(fresh_app):
    client, _store, _data_dir, sends = fresh_app

    client.post("/api/auth/signup", json={"email": "known@example.com", "password": "longenough"})
    client.cookies.clear()
    sends.clear()  # discount the signup path's mail (none expected, but be defensive)

    known = client.post("/api/auth/forgot", json={"email": "known@example.com"})
    client.cookies.clear()
    unknown = client.post("/api/auth/forgot", json={"email": "nobody@example.com"})

    # Caller-visible surface MUST be byte-identical: status + body + content-length.
    assert known.status_code == 204
    assert unknown.status_code == 204
    assert known.content == unknown.content == b""
    assert known.headers.get("content-length") == unknown.headers.get("content-length")

    # Server-side proof the branches actually diverged: shim only called
    # for the known email. Test must keep this assertion separate from
    # the caller-visible surface above.
    assert len(sends) == 1
    assert sends[0]["to"] == "known@example.com"
    assert sends[0]["inbox_id"] == "grip-trial-out@agentmail.to"


def test_reset_updates_password_and_invalidates_old_session(fresh_app):
    client, _store, data_dir, _sends = fresh_app

    client.post("/api/auth/signup", json={"email": "alice@example.com", "password": "originalpw"})
    login = client.post("/api/auth/login", json={"email": "alice@example.com", "password": "originalpw"})
    assert login.status_code == 200
    old_cookie = client.cookies.get("nexus-session")
    assert old_cookie is not None

    # /me works with the original cookie before reset.
    assert client.get("/api/auth/me").status_code == 200

    # Mint a reset token (bypassing the email send loop is fine — the
    # send path is covered by the enumeration test above).
    from app.auth import sign_reset_token
    token = sign_reset_token("alice@example.com", data_dir, ttl_seconds=600)

    client.cookies.clear()  # simulate the user clicking the link in a fresh browser session
    reset_resp = client.post(
        "/api/auth/reset",
        json={"token": token, "new_password": "brand-new-pw-2026"},
    )
    assert reset_resp.status_code == 200, reset_resp.text

    # Old cookie MUST now be invalid — password rotation salted the HMAC.
    client.cookies.clear()
    client.cookies.set("nexus-session", old_cookie)
    stale = client.get("/api/auth/me")
    assert stale.status_code == 401

    # And the new password works on login.
    client.cookies.clear()
    new_login = client.post(
        "/api/auth/login",
        json={"email": "alice@example.com", "password": "brand-new-pw-2026"},
    )
    assert new_login.status_code == 200
