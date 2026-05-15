"""Production hardening tests: rate limit + 500 sanitisation + CORS lockdown."""

from __future__ import annotations

import os
import re
import uuid

import pytest
from fastapi.testclient import TestClient

os.environ["NEXUS_SESSION_SECURE"] = "false"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_SESSION_SECRET", "test-secret-only-for-pytest")
    import app.auth as auth_module
    auth_module._SIGNING_KEY = None

    from app.main import app
    from app.auth import get_data_dir, get_user_store
    from lib.rate_limit import AUTH_LIMITER
    from services.user_store import UserStore

    AUTH_LIMITER.reset()
    store = UserStore(tmp_path)
    app.dependency_overrides[get_user_store] = lambda: store
    app.dependency_overrides[get_data_dir] = lambda: tmp_path
    app.state.data_dir = tmp_path
    app.state.user_store = store
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


def _signup(client, n, ip="10.0.0.1"):
    return client.post(
        "/api/auth/signup",
        json={"email": f"u{n}-{uuid.uuid4().hex[:6]}@t.com", "password": "longenough"},
        headers={"X-Forwarded-For": ip},
    )


def test_rate_limit_signup_5_per_minute(client):
    responses = [_signup(client, i) for i in range(5)]
    assert all(r.status_code == 200 for r in responses), [r.status_code for r in responses]
    blocked = _signup(client, 99)
    assert blocked.status_code == 429
    assert blocked.headers.get("Retry-After") == "60"


def test_rate_limit_login_5_per_minute(client):
    _signup(client, 1, ip="10.0.0.2")
    creds = {"email": "victim@t.com", "password": "wrongpass"}
    headers = {"X-Forwarded-For": "10.0.0.99"}
    for _ in range(5):
        client.post("/api/auth/login", json=creds, headers=headers)
    blocked = client.post("/api/auth/login", json=creds, headers=headers)
    assert blocked.status_code == 429
    assert blocked.headers.get("Retry-After") == "60"


def test_rate_limit_isolated_per_ip(client):
    for _ in range(5):
        _signup(client, 0, ip="10.0.1.1")
    # IP A is blocked
    assert _signup(client, 0, ip="10.0.1.1").status_code == 429
    # IP B still has fresh budget
    fresh = _signup(client, 0, ip="10.0.1.2")
    assert fresh.status_code == 200, fresh.text


def test_500_does_not_leak_traceback(client):
    from app.main import app

    @app.get("/__test_explode")
    async def _explode():
        raise RuntimeError("secret internal detail /Users/laurie/.claude/keys.db")

    _signup(client, 1, ip="10.0.2.1")
    r = client.get("/__test_explode")
    assert r.status_code == 500
    body = r.json()
    assert body["detail"] == "Internal server error"
    raw = r.text
    assert "Traceback" not in raw
    assert "RuntimeError" not in raw
    assert "/Users/" not in raw
    assert "secret internal detail" not in raw


def test_500_includes_request_id(client):
    from app.main import app

    @app.get("/__test_explode2")
    async def _explode2():
        raise ValueError("boom")

    _signup(client, 1, ip="10.0.2.2")
    r = client.get("/__test_explode2")
    assert r.status_code == 500
    body = r.json()
    assert "request_id" in body
    uuid_re = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
    assert uuid_re.match(body["request_id"]), body["request_id"]


def test_cors_origin_allowed(client):
    r = client.options(
        "/api/auth/login",
        headers={
            "Origin": "https://free.donnaoss.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "https://free.donnaoss.com"


def test_cors_origin_rejected(client):
    r = client.options(
        "/api/auth/login",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert r.headers.get("access-control-allow-origin") != "https://evil.example.com"
