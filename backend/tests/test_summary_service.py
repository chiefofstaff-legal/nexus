"""W4 — SummaryStore tests.

Verifies versioned matter summary snapshots:
1. Create round-trip: persisted snapshot fields match input.
2. version_id auto-increments per matter (NOT global counter).
3. get_version returns None on miss.
4. list_versions ordered ascending by version_id.
5. source_citations round-trip via JSON.
6. Goodhart anchor: matter A and matter B both start version_id at 1.
"""

from __future__ import annotations

import pytest

from core import persistence
from services.matter_service import MatterStore
from services.summary_service import SummaryStore


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "nexus_summary_test.sqlite"
    monkeypatch.setenv("NEXUS_PERSISTENCE_DB", str(db_path))
    persistence.reset_schema_cache()
    yield db_path
    persistence.reset_schema_cache()


@pytest.fixture
def matter_id(tmp_db) -> str:
    """Create a real matter so the FK constraint is satisfied."""
    store = MatterStore()
    matter = store.create(name="Acme contract review", client="ACME AG")
    return matter.id


def test_summary_create_round_trip(matter_id):
    store = SummaryStore()
    snapshot = store.create(
        matter_id, "Initial summary content", ["doc_1", "doc_2"],
    )
    assert snapshot.matter_id == matter_id
    assert snapshot.version_id == 1
    assert snapshot.content == "Initial summary content"
    assert snapshot.source_citations == ["doc_1", "doc_2"]

    fetched = store.get_version(matter_id, 1)
    assert fetched is not None
    assert fetched.content == "Initial summary content"
    assert fetched.source_citations == ["doc_1", "doc_2"]


def test_summary_version_increments_within_matter(matter_id):
    store = SummaryStore()
    a = store.create(matter_id, "v1 content", [])
    b = store.create(matter_id, "v2 content", ["doc_a"])
    c = store.create(matter_id, "v3 content", ["doc_a", "doc_b"])
    assert (a.version_id, b.version_id, c.version_id) == (1, 2, 3)


def test_summary_version_id_independent_per_matter(tmp_db):
    """Goodhart anchor — each matter has its own version sequence.

    A global counter would make matter B's first snapshot version_id=4
    after matter A took 1,2,3. The contract is per-matter independence.
    """
    matters = MatterStore()
    a = matters.create(name="Matter A", client="A AG")
    b = matters.create(name="Matter B", client="B AG")

    store = SummaryStore()
    store.create(a.id, "A v1", [])
    store.create(a.id, "A v2", [])
    store.create(a.id, "A v3", [])

    b1 = store.create(b.id, "B v1", [])
    b2 = store.create(b.id, "B v2", [])

    assert b1.version_id == 1
    assert b2.version_id == 2
    a_versions = [s.version_id for s in store.list_versions(a.id)]
    assert a_versions == [1, 2, 3]


def test_summary_get_latest_returns_highest_version(matter_id):
    store = SummaryStore()
    store.create(matter_id, "v1", [])
    store.create(matter_id, "v2", [])
    latest = store.create(matter_id, "v3", ["doc_x"])
    fetched = store.get_latest(matter_id)
    assert fetched is not None
    assert fetched.version_id == latest.version_id == 3
    assert fetched.content == "v3"
    assert fetched.source_citations == ["doc_x"]


def test_summary_get_latest_returns_none_for_unknown_matter(tmp_db):
    store = SummaryStore()
    assert store.get_latest("matter_does_not_exist") is None


def test_summary_get_version_returns_none_for_miss(matter_id):
    store = SummaryStore()
    store.create(matter_id, "v1", [])
    assert store.get_version(matter_id, 99) is None
    assert store.get_version("nonexistent_matter", 1) is None


def test_summary_list_versions_ordered_ascending(matter_id):
    store = SummaryStore()
    store.create(matter_id, "v1", [])
    store.create(matter_id, "v2", [])
    store.create(matter_id, "v3", [])
    versions = store.list_versions(matter_id)
    assert [s.version_id for s in versions] == [1, 2, 3]


def test_summary_source_citations_default_to_empty_list(matter_id):
    """Calling create() without citations must persist [], not null."""
    store = SummaryStore()
    snapshot = store.create(matter_id, "Plain content")
    assert snapshot.source_citations == []
    fetched = store.get_version(matter_id, snapshot.version_id)
    assert fetched is not None
    assert fetched.source_citations == []
