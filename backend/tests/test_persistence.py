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


# --- Legacy schema migration (H454 regression guard) ---

def test_init_schema_migrates_legacy_db_without_user_id(tmp_path, monkeypatch):
    """Goodhart-proof regression for the /time 500 reported 2026-05-12.

    A DB created before MT W5 lacks the ``user_id`` column on ``matters``,
    ``time_entries``, ``tasks``, and ``matter_documents``. ``init_schema``
    must be able to bring this DB forward to the current schema *without*
    crashing on ``CREATE INDEX idx_matters_user_id ON matters(user_id)``.

    The bug: indexes referencing ``user_id`` were interleaved into the
    table-creation tuple, so they ran BEFORE ``_backfill_user_id_columns``
    could ALTER legacy tables to add the column. Result: every endpoint
    that lazily initialises the schema (notably ``/api/time/entries`` and
    ``/api/time/summary``) returned HTTP 500 ``sqlite3.OperationalError:
    no such column: user_id``.

    This test fails if the DDL ordering is reverted.
    """
    import sqlite3

    db_path = tmp_path / "legacy.sqlite"
    monkeypatch.setenv("NEXUS_PERSISTENCE_DB", str(db_path))
    persistence.reset_schema_cache()

    # Stand up the pre-MT-W5 schema by hand. No user_id columns anywhere.
    raw = sqlite3.connect(str(db_path))
    raw.executescript(
        """
        CREATE TABLE matters (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            client TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            archived_at TEXT
        );
        CREATE TABLE time_entries (
            id TEXT PRIMARY KEY,
            matter TEXT NOT NULL DEFAULT '',
            matter_id TEXT,
            description TEXT NOT NULL DEFAULT '',
            duration_minutes INTEGER NOT NULL DEFAULT 0,
            hourly_rate_chf REAL NOT NULL DEFAULT 450.0,
            created_at TEXT NOT NULL,
            raw_transcript TEXT NOT NULL DEFAULT '',
            billable INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE tasks (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            assignee TEXT NOT NULL,
            matter TEXT NOT NULL DEFAULT '',
            matter_id TEXT,
            deadline TEXT,
            priority TEXT NOT NULL DEFAULT 'medium',
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            raw_transcript TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE matter_documents (
            matter_id TEXT NOT NULL,
            document_id TEXT NOT NULL,
            added_at TEXT NOT NULL,
            PRIMARY KEY (matter_id, document_id)
        );
        INSERT INTO time_entries (id, matter, description, duration_minutes,
                                  hourly_rate_chf, created_at, raw_transcript, billable)
        VALUES ('legacy_001', 'Pre-MT', 'Done before MT W5', 30, 450.0,
                '2026-04-01T10:00:00+00:00', '', 1);
        """
    )
    raw.commit()
    raw.close()

    # Now run init_schema. This must NOT crash. Pre-fix it would raise
    # ``sqlite3.OperationalError: no such column: user_id`` when reaching
    # ``CREATE INDEX idx_matters_user_id ON matters(user_id)``.
    persistence.init_schema(db_path)

    # Verify migration outcome — Goodhart-proof: actual column existence
    # checked via PRAGMA, not via test internals.
    with persistence.get_connection(db_path) as conn:
        matter_cols = {r["name"] for r in conn.execute("PRAGMA table_info(matters)")}
        time_cols = {r["name"] for r in conn.execute("PRAGMA table_info(time_entries)")}
        task_cols = {r["name"] for r in conn.execute("PRAGMA table_info(tasks)")}

        # All four legacy tables now carry user_id.
        for cols in (matter_cols, time_cols, task_cols):
            assert "user_id" in cols, f"user_id missing after migration: {cols}"

        # Index that previously crashed now exists.
        idx_rows = list(conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND name='idx_matters_user_id'"
        ))
        assert len(idx_rows) == 1, "idx_matters_user_id index not created"

        # Legacy row survives migration (default empty user_id, but data
        # intact). Without the fix we'd never reach this assertion.
        rows = list(conn.execute("SELECT id, matter, user_id FROM time_entries"))
        assert len(rows) == 1
        assert rows[0]["id"] == "legacy_001"
        assert rows[0]["matter"] == "Pre-MT"
        assert rows[0]["user_id"] == ""

    # End-to-end: the actual TimeEntryStore.get_time_entries() call that
    # 500-d in production must now return the legacy entry as a TimeEntry.
    store = TimeEntryStore()
    entries = store.get_time_entries()
    assert len(entries) == 1
    assert entries[0].id == "legacy_001"
    assert entries[0].matter == "Pre-MT"
    assert entries[0].duration_minutes == 30

    persistence.reset_schema_cache()


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
