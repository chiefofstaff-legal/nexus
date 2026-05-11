"""
Matter Entity Tests
===================

Verifies SQLite-backed ``MatterStore`` and its document-membership helper:
1. Create + retrieve round-trips Pydantic field values.
2. ``list()`` excludes archived rows by default; ``include_archived=True``
   surfaces them.
3. Document membership add/remove/list operates on the join table.
4. ``archive()`` is a soft delete — the row remains, ``archived_at`` is set.

Each test isolates its DB via ``NEXUS_PERSISTENCE_DB`` + tmp_path.
"""

from __future__ import annotations

import pytest

from core import persistence
from services.matter_service import MatterStore


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """Point persistence at a fresh tmp SQLite file and reset the schema cache."""
    db_path = tmp_path / "nexus_matter_test.sqlite"
    monkeypatch.setenv("NEXUS_PERSISTENCE_DB", str(db_path))
    persistence.reset_schema_cache()
    yield db_path
    persistence.reset_schema_cache()


def test_matters_router_is_registered_on_app():
    """Regression guard: /api/matters routes MUST be wired into the FastAPI app.

    Catches the H204-gap pattern (handlers + UI exist but include_router is
    missing). Without this test, the W2 wiring bug shipped to production:
    `MatterStore` existed, frontend called the API, and the FastAPI router
    was defined — but `app.include_router(matters)` was absent in main.py,
    so `/api/matters` returned 404 in production despite all unit tests
    passing.

    See feedback_h204_gap_most_valuable_thing_a78ad53f.md.
    """
    from app.main import app

    paths = {route.path for route in app.routes}
    assert "/api/matters" in paths, (
        f"/api/matters not registered. Found {len(paths)} routes; "
        f"matter-related: {sorted(p for p in paths if 'matter' in p.lower())}"
    )
    assert "/api/matters/{matter_id}" in paths, (
        "/api/matters/{matter_id} detail route not registered"
    )


# --- Create / retrieve ---

def test_matter_create_and_retrieve(tmp_db):
    """A created Matter round-trips through SQLite with all fields intact."""
    store = MatterStore()
    matter = store.create(
        name="Müller divorce",
        client="Hans Müller",
        notes="Discovery call 2026-04-29",
    )
    assert matter.id.startswith("matter_")
    assert matter.archived_at is None

    fetched = store.get(matter.id)
    assert fetched is not None
    assert fetched.id == matter.id
    assert fetched.name == "Müller divorce"
    assert fetched.client == "Hans Müller"
    assert fetched.notes == "Discovery call 2026-04-29"
    assert fetched.created_at == matter.created_at
    assert fetched.archived_at is None


def test_matter_get_missing_returns_none(tmp_db):
    """Retrieving an unknown matter id returns None, not an exception."""
    store = MatterStore()
    assert store.get("matter_does_not_exist") is None


# --- list filtering ---

def test_matter_list_excludes_archived_by_default(tmp_db):
    """list() omits archived; include_archived=True surfaces them."""
    store = MatterStore()
    keep = store.create(name="Active matter", client="Client A")
    drop = store.create(name="Closed matter", client="Client B")

    archived = store.archive(drop.id)
    assert archived is not None
    assert archived.archived_at is not None

    default = store.list()
    assert len(default) == 1
    assert default[0].id == keep.id

    with_archived = store.list(include_archived=True)
    ids = {m.id for m in with_archived}
    assert ids == {keep.id, drop.id}


# --- Document membership ---

def test_matter_document_membership(tmp_db):
    """Adding then removing a document mutates the join-table list view."""
    store = MatterStore()
    matter = store.create(name="ACME contract review", client="ACME AG")

    membership = store.documents.add(matter.id, "doc_xyz")
    assert membership.matter_id == matter.id
    assert membership.document_id == "doc_xyz"

    docs = store.documents.list(matter.id)
    assert len(docs) == 1
    assert docs[0].document_id == "doc_xyz"

    removed = store.documents.remove(matter.id, "doc_xyz")
    assert removed is True

    after = store.documents.list(matter.id)
    assert after == []

    # Removing a non-existent membership returns False rather than raising.
    assert store.documents.remove(matter.id, "doc_nope") is False


# --- Soft delete ---

def test_matter_archive_is_soft_delete(tmp_db):
    """archive() leaves the row in place with archived_at populated."""
    store = MatterStore()
    matter = store.create(name="To be archived", client="Client C")

    archived = store.archive(matter.id)
    assert archived is not None
    assert archived.archived_at is not None

    # get() still returns the row (soft delete, not hard delete).
    after = store.get(matter.id)
    assert after is not None
    assert after.id == matter.id
    assert after.archived_at is not None

    # Direct DB sanity — row is still on disk.
    with persistence.get_connection() as conn:
        cur = conn.execute(
            "SELECT id, archived_at FROM matters WHERE id = ?", (matter.id,),
        ).fetchone()
    assert cur is not None
    assert cur["archived_at"] is not None
