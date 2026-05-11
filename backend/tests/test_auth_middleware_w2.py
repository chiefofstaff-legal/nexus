"""W2 — every non-auth route 401s without a session cookie."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.routing import Route

PUBLIC_PATHS = {
    "/health",
    "/openapi.json",
    "/docs",
    "/redoc",
    "/favicon.ico",
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_SESSION_SECRET", "test-secret-only-for-pytest")
    monkeypatch.setenv("NEXUS_SESSION_SECURE", "false")
    import app.auth as auth_module
    auth_module._SIGNING_KEY = None
    from app.main import app
    from app.auth import get_data_dir, get_user_store
    from services.user_store import UserStore
    store = UserStore(tmp_path)
    app.dependency_overrides[get_user_store] = lambda: store
    app.dependency_overrides[get_data_dir] = lambda: tmp_path
    # The middleware reads from app.state.data_dir at request time, so
    # point it at tmp_path BEFORE the TestClient enters lifespan.
    app.state.data_dir = tmp_path
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _collect_routes():
    from app.main import app
    seen: set[tuple[str, str]] = set()
    for route in app.routes:
        if not isinstance(route, Route):
            continue
        for method in route.methods or set():
            if method in ("HEAD", "OPTIONS"):
                continue
            seen.add((method, route.path))
    return sorted(seen)


def test_health_remains_public(client):
    assert client.get("/health").status_code == 200


def test_auth_routes_remain_public(client):
    # Hitting these without a cookie should NOT be the 401 from the middleware —
    # they get to handle their own validation.
    assert client.post("/api/auth/login", json={"email": "x@y.z", "password": "longenough"}).status_code in (401, 422)
    assert client.post("/api/auth/signup", json={"email": "x@y.z", "password": "longenough"}).status_code in (200, 409)


def test_every_other_route_requires_session(client):
    """Mechanical enumeration: every registered route except the
    whitelisted ones must return 401 to an unauthenticated caller."""
    failures: list[tuple[str, str, int]] = []
    for method, path in _collect_routes():
        if path in PUBLIC_PATHS:
            continue
        if path.startswith(("/api/auth/", "/docs", "/redoc")):
            continue
        # Path parameters: substitute a dummy value so the route matches.
        concrete = path
        while "{" in concrete and "}" in concrete:
            i = concrete.index("{")
            j = concrete.index("}", i)
            concrete = concrete[:i] + "x" + concrete[j + 1 :]
        if method == "GET":
            r = client.get(concrete)
        elif method == "POST":
            r = client.post(concrete, json={})
        elif method == "DELETE":
            r = client.delete(concrete)
        elif method == "PUT":
            r = client.put(concrete, json={})
        elif method == "PATCH":
            r = client.patch(concrete, json={})
        else:
            continue
        if r.status_code != 401:
            failures.append((method, concrete, r.status_code))
    assert not failures, f"Routes reachable without auth: {failures[:10]}"


def test_authenticated_request_passes_middleware(client):
    sign = client.post(
        "/api/auth/signup",
        json={"email": "alice@test.com", "password": "longenough"},
    )
    assert sign.status_code == 200
    # The same client now has the session cookie; protected route should
    # no longer 401 (404 or other status is fine — we only care the
    # middleware let it through).
    r = client.get("/api/idrs/recent")
    assert r.status_code != 401


def test_tampered_cookie_blocked(client):
    sign = client.post(
        "/api/auth/signup",
        json={"email": "alice@test.com", "password": "longenough"},
    )
    assert sign.status_code == 200
    token = client.cookies.get("nexus-session")
    parts = token.split(":")
    parts[2] = ("0" if parts[2][0] != "0" else "1") + parts[2][1:]
    client.cookies.set("nexus-session", ":".join(parts))
    r = client.get("/api/idrs/recent")
    assert r.status_code == 401
