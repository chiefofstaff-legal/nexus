"""W4 — IDR tenant filter: Alice cannot read Bob's audit trail."""

from __future__ import annotations

import pytest


def test_belongs_to_matches_tenant_id():
    from app.routes_idr import _belongs_to

    entry = {"metadata": {"tenant_id": "alice-uid"}}
    assert _belongs_to(entry, "alice-uid") is True
    assert _belongs_to(entry, "bob-uid") is False


def test_belongs_to_rejects_legacy_idr_without_tenant_id():
    from app.routes_idr import _belongs_to

    # Pre-multi-tenancy IDRs have no tenant_id — they're invisible to
    # every new account by design.
    entry = {"metadata": {"query": "anything"}}
    assert _belongs_to(entry, "alice-uid") is False
    assert _belongs_to(entry, "") is False


def test_belongs_to_handles_missing_metadata():
    from app.routes_idr import _belongs_to

    assert _belongs_to({}, "alice-uid") is False
    assert _belongs_to({"metadata": None}, "alice-uid") is False


def test_log_search_idr_stamps_tenant_id(tmp_path):
    """The write path tags every IDR with the caller's user_id so the
    read filter has something to match against."""
    from core.idr_store import IDRStore
    from services.embedding_service import log_search_idr

    store = IDRStore(tmp_path)
    log_search_idr(
        query="liability clause",
        results=[{"metadata": {"doc_id": "x", "filename": "foo.pdf"}, "relevance": 0.9}],
        n_results=1,
        idr_store=store,
        user_id="alice-uid",
    )
    entries = store.list_recent(limit=10)
    assert entries, "search IDR should have been appended"
    assert entries[0]["metadata"]["tenant_id"] == "alice-uid"


def test_idr_recent_route_filters_by_tenant(tmp_path, monkeypatch):
    """End-to-end via TestClient: signup Alice, write a search IDR as
    Alice, signup Bob in the same store, assert Bob's /api/idrs/recent
    is empty (no shared visibility)."""
    monkeypatch.setenv("NEXUS_SESSION_SECRET", "test-secret-only-for-pytest")
    monkeypatch.setenv("NEXUS_SESSION_SECURE", "false")
    import app.auth as auth_module
    auth_module._SIGNING_KEY = None

    # Use a fresh IDR store backed by tmp_path so we don't pollute the
    # real ~/nexus-poc/data chain.
    from core.idr_store import IDRStore
    from services.embedding_service import log_search_idr
    isolated_store = IDRStore(tmp_path)

    from fastapi.testclient import TestClient
    from app import routes_idr
    from app.main import app
    from app.auth import get_data_dir, get_user_store
    from services.user_store import UserStore

    monkeypatch.setattr(routes_idr, "_store", isolated_store)
    users = UserStore(tmp_path)
    app.dependency_overrides[get_user_store] = lambda: users
    app.dependency_overrides[get_data_dir] = lambda: tmp_path
    # The FastAPI lifespan sets app.state.user_store ONCE and reuses it
    # across every later TestClient(app) (app is a module singleton).
    # Pin + restore app.state directly so a prior test's torn-down
    # UserStore can't bleed in and 401 the session verify here.
    _saved_user_store = getattr(app.state, "user_store", None)
    _saved_data_dir = getattr(app.state, "data_dir", None)
    app.state.user_store = users
    app.state.data_dir = tmp_path

    try:
        with TestClient(app) as client:
            app.state.user_store = users
            alice = client.post("/api/auth/signup", json={"email": "alice@test.com", "password": "longenough"})
            assert alice.status_code == 200
            alice_id = alice.json()["id"]

            # Write an IDR as Alice.
            log_search_idr(
                query="liability clause",
                results=[],
                n_results=0,
                idr_store=isolated_store,
                user_id=alice_id,
            )

            # Alice sees her IDR.
            r_alice = client.get("/api/idrs/recent?limit=20")
            assert r_alice.status_code == 200
            assert r_alice.json()["count"] >= 1
            assert all(
                e["metadata"]["tenant_id"] == alice_id
                for e in r_alice.json()["entries"]
            )

            # Switch to Bob in a fresh client (no cookies carried over).
            client.cookies.clear()
            bob = client.post("/api/auth/signup", json={"email": "bob@test.com", "password": "longenough"})
            assert bob.status_code == 200
            bob_id = bob.json()["id"]
            assert bob_id != alice_id

            r_bob = client.get("/api/idrs/recent?limit=20")
            assert r_bob.status_code == 200
            assert r_bob.json()["count"] == 0, (
                f"Bob should see zero IDRs, got {r_bob.json()}"
            )
    finally:
        app.dependency_overrides.clear()
        app.state.user_store = _saved_user_store
        app.state.data_dir = _saved_data_dir
