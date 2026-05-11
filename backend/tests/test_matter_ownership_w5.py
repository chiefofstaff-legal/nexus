"""W5 — matter resource ownership: cross-tenant access returns 404."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def two_users(tmp_path, monkeypatch):
    """Boot the app with isolated state and return (client, alice_id, bob_id).

    The TestClient holds the most-recent session cookie — call
    ``client.cookies.clear()`` then re-login to switch identities.
    """
    monkeypatch.setenv("NEXUS_SESSION_SECRET", "test-secret-only-for-pytest")
    monkeypatch.setenv("NEXUS_SESSION_SECURE", "false")
    monkeypatch.setenv("NEXUS_PERSISTENCE_DB", str(tmp_path / "persistence.sqlite"))
    monkeypatch.setenv("NEXUS_SKIP_CORPUS_SEED", "true")

    import app.auth as auth_module
    auth_module._SIGNING_KEY = None

    from core.persistence import reset_schema_cache
    reset_schema_cache()

    from app.routes import _matter_store
    _matter_store._initialised = False
    _matter_store.documents._initialised = False

    from app.main import app
    from app.auth import get_data_dir, get_user_store
    from services.user_store import UserStore

    users = UserStore(tmp_path)
    app.dependency_overrides[get_user_store] = lambda: users
    app.dependency_overrides[get_data_dir] = lambda: tmp_path
    app.state.data_dir = tmp_path

    with TestClient(app) as client:
        alice = client.post("/api/auth/signup", json={"email": "alice@test.com", "password": "longenough"})
        assert alice.status_code == 200
        alice_id = alice.json()["id"]
        alice_cookie = client.cookies.get("nexus-session")

        client.cookies.clear()
        bob = client.post("/api/auth/signup", json={"email": "bob@test.com", "password": "longenough"})
        assert bob.status_code == 200
        bob_id = bob.json()["id"]
        bob_cookie = client.cookies.get("nexus-session")

        yield client, alice_id, alice_cookie, bob_id, bob_cookie

    app.dependency_overrides.clear()
    reset_schema_cache()


def _as(client, cookie):
    client.cookies.clear()
    client.cookies.set("nexus-session", cookie)


def test_alice_creates_matter_bob_cannot_see_it_in_list(two_users):
    client, _alice_id, alice_cookie, _bob_id, bob_cookie = two_users

    _as(client, alice_cookie)
    created = client.post("/api/matters", json={"name": "Alice v Acme"})
    assert created.status_code == 201
    matter_id = created.json()["id"]

    _as(client, bob_cookie)
    listing = client.get("/api/matters")
    assert listing.status_code == 200
    assert not any(m["id"] == matter_id for m in listing.json()["matters"])


def test_bob_get_alice_matter_returns_404(two_users):
    client, _alice_id, alice_cookie, _bob_id, bob_cookie = two_users

    _as(client, alice_cookie)
    matter_id = client.post("/api/matters", json={"name": "Alice v Acme"}).json()["id"]

    _as(client, bob_cookie)
    r = client.get(f"/api/matters/{matter_id}")
    assert r.status_code == 404, "cross-tenant GET must 404, not 403, to avoid leaking existence"


def test_bob_patch_alice_matter_returns_404(two_users):
    client, _alice_id, alice_cookie, _bob_id, bob_cookie = two_users

    _as(client, alice_cookie)
    matter_id = client.post("/api/matters", json={"name": "Alice v Acme"}).json()["id"]

    _as(client, bob_cookie)
    r = client.patch(f"/api/matters/{matter_id}", json={"name": "Bob took over"})
    assert r.status_code == 404


def test_bob_archive_alice_matter_returns_404(two_users):
    client, _alice_id, alice_cookie, _bob_id, bob_cookie = two_users

    _as(client, alice_cookie)
    matter_id = client.post("/api/matters", json={"name": "Alice v Acme"}).json()["id"]

    _as(client, bob_cookie)
    r = client.delete(f"/api/matters/{matter_id}")
    assert r.status_code == 404


def test_bob_attach_document_to_alice_matter_returns_404(two_users):
    client, _alice_id, alice_cookie, _bob_id, bob_cookie = two_users

    _as(client, alice_cookie)
    matter_id = client.post("/api/matters", json={"name": "Alice v Acme"}).json()["id"]

    _as(client, bob_cookie)
    r = client.post(f"/api/matters/{matter_id}/documents", json={"document_id": "doc-x"})
    assert r.status_code == 404


def test_alice_can_still_access_her_own_matter(two_users):
    client, _alice_id, alice_cookie, *_ = two_users

    _as(client, alice_cookie)
    matter_id = client.post("/api/matters", json={"name": "Alice v Acme"}).json()["id"]

    got = client.get(f"/api/matters/{matter_id}")
    assert got.status_code == 200
    assert got.json()["id"] == matter_id
