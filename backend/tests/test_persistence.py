"""
Persistence Layer Tests
=======================

Verifies SQLite-backed persistence for ``TimeEntryStore`` and ``TaskStore``:
1. Data survives a fresh store instance pointed at the same DB file.
2. Daily-total only counts today's entries (created_at filter works).
3. Legacy public API shapes are unchanged after the RAM→SQLite migration.
4. ``value_chf`` remains a computed field, never persisted (Goodhart guard).

Each test isolates its DB via ``NEXUS_PERSISTENCE_DB`` + tmp_path. The
persistence module's schema cache is cleared between tests so a fresh path
triggers fresh DDL.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from core import persistence
from services.task_manager import Priority, Task, TaskStatus, TaskStore
from services.time_capture import TimeEntry, TimeEntryStore


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """Point persistence at a fresh tmp SQLite file and reset the schema cache."""
    db_path = tmp_path / "nexus_test.sqlite"
    monkeypatch.setenv("NEXUS_PERSISTENCE_DB", str(db_path))
    persistence.reset_schema_cache()
    yield db_path
    persistence.reset_schema_cache()


# --- Restart durability ---

def test_time_entries_survive_restart(tmp_db):
    """Logging then re-instantiating the store retrieves the same entry."""
    first = TimeEntryStore()
    entry = TimeEntry(
        matter="Müller v Credit Suisse",
        description="Contract review",
        duration_minutes=90,
        hourly_rate_chf=450.0,
    )
    first.log_time_entry(entry)

    # Brand-new store against the same DB — proves data is on disk.
    second = TimeEntryStore()
    retrieved = second.get_time_entries()

    assert len(retrieved) == 1
    got = retrieved[0]
    assert got.id == entry.id
    assert got.matter == "Müller v Credit Suisse"
    assert got.duration_minutes == 90
    assert got.value_chf == 675.0  # 90 / 60 * 450


def test_tasks_survive_restart(tmp_db):
    """Adding a task then re-instantiating TaskStore retrieves the same task."""
    first = TaskStore()
    task = Task(
        id="task_persist_001",
        title="Draft NDA",
        description="For ACME engagement",
        assignee="Andre",
        deadline=date(2026, 5, 15),
        priority=Priority.HIGH,
        status=TaskStatus.PENDING,
    )
    first.add(task)

    second = TaskStore()
    found = second.find("task_persist_001")

    assert found is not None
    assert found.title == "Draft NDA"
    assert found.assignee == "Andre"
    assert found.deadline == date(2026, 5, 15)
    assert found.priority == Priority.HIGH
    assert found.status == TaskStatus.PENDING


# --- Daily total filter ---

def test_get_daily_total_only_counts_today(tmp_db):
    """get_daily_total_chf must filter by UTC calendar day."""
    store = TimeEntryStore()

    today_entry = TimeEntry(
        matter="Today",
        description="Today work",
        duration_minutes=60,
        hourly_rate_chf=450.0,
    )
    store.log_time_entry(today_entry)

    yesterday_entry = TimeEntry(
        matter="Yesterday",
        description="Yesterday work",
        duration_minutes=120,
        hourly_rate_chf=450.0,
    )
    store.log_time_entry(yesterday_entry)

    # Backdate the yesterday row directly via SQL — only way to simulate
    # an entry from a previous calendar day without time-travel.
    yesterday_iso = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    with persistence.get_connection() as conn:
        conn.execute(
            "UPDATE time_entries SET created_at = ? WHERE id = ?",
            (yesterday_iso, yesterday_entry.id),
        )

    total = store.get_daily_total_chf()
    assert total["entry_count"] == 1
    assert total["total_minutes"] == 60
    assert total["total_chf"] == 450.0
    assert total["hourly_rate_chf"] == 450.0


# --- Legacy public-API shape ---

def test_legacy_interface_unchanged(tmp_db):
    """Public methods return the same shapes/types as the RAM POC."""
    store = TimeEntryStore()

    entry = TimeEntry(
        matter="Initial",
        description="First pass",
        duration_minutes=30,
        hourly_rate_chf=450.0,
    )
    logged = store.log_time_entry(entry)
    assert isinstance(logged, TimeEntry)
    assert logged.id == entry.id

    listed = store.get_time_entries()
    assert isinstance(listed, list)
    assert all(isinstance(e, TimeEntry) for e in listed)
    assert len(listed) == 1

    updated_matter = store.update_matter(entry.id, "Corrected matter")
    assert isinstance(updated_matter, TimeEntry)
    assert updated_matter.matter == "Corrected matter"

    updated_transcript = store.update_transcript(entry.id, "new transcript text")
    assert isinstance(updated_transcript, TimeEntry)
    assert updated_transcript.raw_transcript == "new transcript text"

    daily = store.get_daily_total_chf()
    assert isinstance(daily, dict)
    for key in (
        "entry_count", "total_minutes", "total_hours",
        "hourly_rate_chf", "total_chf", "total_value_chf",
    ):
        assert key in daily

    # update_matter on missing id returns None (legacy contract)
    assert store.update_matter("does_not_exist", "x") is None
    assert store.update_transcript("does_not_exist", "x") is None


def test_value_chf_is_recomputed_not_persisted(tmp_db):
    """value_chf is a Pydantic computed_field — derived on read, never stored."""
    store = TimeEntryStore(default_rate_chf=450.0)
    entry = TimeEntry(
        matter="Goodhart",
        description="Computed-field guard",
        duration_minutes=60,
        hourly_rate_chf=450.0,
    )
    store.log_time_entry(entry)

    retrieved = store.get_time_entries()[0]
    assert retrieved.value_chf == 450.0  # 60 / 60 * 450 = 450

    # A fresh store instance with a different default rate must still
    # recompute correctly from the row's own ``hourly_rate_chf``.
    other = TimeEntryStore(default_rate_chf=999.0)
    retrieved_again = other.get_time_entries()[0]
    assert retrieved_again.value_chf == 450.0
    assert retrieved_again.hourly_rate_chf == 450.0

    # Schema sanity: time_entries table has no value_chf column.
    with persistence.get_connection() as conn:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(time_entries)")}
    assert "value_chf" not in cols
