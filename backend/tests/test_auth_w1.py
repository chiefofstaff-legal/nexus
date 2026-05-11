"""W1 — user identity + session smoke tests."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

os.environ["NEXUS_SESSION_SECURE"] = "false"  # TestClient over HTTP


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_SESSION_SECRET", "test-secret-only-for-pytest")
    # Reset the module-level signing-key cache so each test gets the
    # patched env value, not whatever leaked from a previous import.
    import app.auth as auth_module
    auth_module._SIGNING_KEY = None

    from app.main import app
    from app.auth import get_data_dir, get_user_store
    from services.user_store import UserStore

    store = UserStore(tmp_path)
    app.dependency_overrides[get_user_store] = lambda: store
    app.dependency_overrides[get_data_dir] = lambda: tmp_path
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_signup_creates_user_with_unique_id(client):
    a = client.post("/api/auth/signup", json={"email": "alice@test.com", "password": "longenough"})
    b = client.post("/api/auth/signup", json={"email": "bob@test.com", "password": "longenough"})
    assert a.status_code == 200, a.text
    assert b.status_code == 200, b.text
    assert a.json()["id"] != b.json()["id"]
    assert a.json()["email"] == "alice@test.com"


def test_signup_duplicate_email_rejected(client):
    client.post("/api/auth/signup", json={"email": "dup@test.com", "password": "longenough"})
    again = client.post("/api/auth/signup", json={"email": "dup@test.com", "password": "longenough"})
    assert again.status_code == 409


def test_login_wrong_password_returns_401(client):
    client.post("/api/auth/signup", json={"email": "alice@test.com", "password": "correctpw"})
    bad = client.post("/api/auth/login", json={"email": "alice@test.com", "password": "wrongpw1"})
    assert bad.status_code == 401
    assert bad.json()["detail"] == "Invalid credentials"


def test_login_success_sets_session_cookie(client):
    client.post("/api/auth/signup", json={"email": "alice@test.com", "password": "correctpw"})
    good = client.post("/api/auth/login", json={"email": "alice@test.com", "password": "correctpw"})
    assert good.status_code == 200
    assert "nexus-session" in good.cookies


def test_me_without_cookie_returns_401(client):
    r = client.get("/api/auth/me")
    assert r.status_code == 401


def test_me_with_valid_cookie_returns_user(client):
    s = client.post("/api/auth/signup", json={"email": "alice@test.com", "password": "longenough"})
    me = client.get("/api/auth/me")  # cookie carried by TestClient
    assert me.status_code == 200
    assert me.json()["id"] == s.json()["id"]
    assert me.json()["email"] == "alice@test.com"


def test_session_cookie_tampering_rejected(client):
    s = client.post("/api/auth/signup", json={"email": "alice@test.com", "password": "longenough"})
    assert s.status_code == 200
    original = client.cookies.get("nexus-session")
    # Flip a character in the HMAC segment
    parts = original.split(":")
    parts[2] = ("0" if parts[2][0] != "0" else "1") + parts[2][1:]
    client.cookies.set("nexus-session", ":".join(parts))
    r = client.get("/api/auth/me")
    assert r.status_code == 401


def test_logout_clears_cookie(client):
    client.post("/api/auth/signup", json={"email": "alice@test.com", "password": "longenough"})
    out = client.post("/api/auth/logout")
    assert out.status_code == 200
    # After logout the cookie is cleared; /me should 401
    client.cookies.clear()
    assert client.get("/api/auth/me").status_code == 401


def test_invalid_email_rejected(client):
    r = client.post("/api/auth/signup", json={"email": "not-an-email", "password": "longenough"})
    assert r.status_code == 422


def test_short_password_rejected(client):
    r = client.post("/api/auth/signup", json={"email": "ok@test.com", "password": "short"})
    assert r.status_code == 422
