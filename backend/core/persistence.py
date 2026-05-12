"""
SQLite-backed Persistence for NEXUS
===================================

Stdlib-only SQLite persistence layer for time entries, tasks, matters, and
matter-document membership. Mirrors the discipline of ``audit_chain.py`` —
no SQLAlchemy, no migrations framework, just ``sqlite3`` + ``fcntl`` for
cross-process safety.

Concurrency choice
------------------
We use the standard ``with conn:`` context manager pattern for write
transactions. This relies on SQLite's default deferred transaction model
combined with WAL journaling for concurrent readers. Simpler than manual
``BEGIN IMMEDIATE`` and sufficient for the POC's expected load.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Optional

DEFAULT_DB_PATH = Path.home() / "nexus-poc" / "data" / "persistence.sqlite"

_TABLE_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS matters (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        client TEXT NOT NULL DEFAULT '',
        notes TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        archived_at TEXT,
        user_id TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS time_entries (
        id TEXT PRIMARY KEY,
        matter TEXT NOT NULL DEFAULT '',
        matter_id TEXT,
        description TEXT NOT NULL DEFAULT '',
        duration_minutes INTEGER NOT NULL DEFAULT 0,
        hourly_rate_chf REAL NOT NULL DEFAULT 450.0,
        created_at TEXT NOT NULL,
        raw_transcript TEXT NOT NULL DEFAULT '',
        billable INTEGER NOT NULL DEFAULT 1,
        FOREIGN KEY (matter_id) REFERENCES matters(id) ON DELETE SET NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tasks (
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
        raw_transcript TEXT NOT NULL DEFAULT '',
        FOREIGN KEY (matter_id) REFERENCES matters(id) ON DELETE SET NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS matter_documents (
        matter_id TEXT NOT NULL,
        document_id TEXT NOT NULL,
        added_at TEXT NOT NULL,
        PRIMARY KEY (matter_id, document_id),
        FOREIGN KEY (matter_id) REFERENCES matters(id) ON DELETE CASCADE
    )
    """,
)

# Indexes run AFTER _backfill_user_id_columns so legacy tables (created
# before MT W5 added the user_id column) gain the column before any index
# references it. Combining indexes into _TABLE_DDL with the tables crashes
# legacy DBs at index creation time and surfaces as HTTP 500 on every
# /api/time/* endpoint (and any other endpoint that lazily inits the schema).
_INDEX_DDL: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS idx_matters_archived ON matters(archived_at)",
    "CREATE INDEX IF NOT EXISTS idx_matters_user_id ON matters(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_time_entries_created ON time_entries(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_time_entries_matter_id ON time_entries(matter_id)",
    "CREATE INDEX IF NOT EXISTS idx_tasks_assignee ON tasks(assignee)",
    "CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)",
    "CREATE INDEX IF NOT EXISTS idx_tasks_matter_id ON tasks(matter_id)",
)

_SCHEMA_DDL = _TABLE_DDL + _INDEX_DDL

_schema_initialised = False


def _resolve_db_path(override: Optional[Path] = None) -> Path:
    """Pick the active database path: explicit > env > default."""
    if override is not None:
        return Path(override)
    env_value = os.environ.get("NEXUS_PERSISTENCE_DB")
    if env_value:
        return Path(env_value)
    return DEFAULT_DB_PATH


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Return a fresh SQLite connection with WAL mode and Row factory.

    A new connection is returned on each call so callers don't share
    state across threads — the typical SQLite recommendation.
    """
    path = _resolve_db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


_USER_ID_BACKFILL_TABLES = ("matters", "time_entries", "tasks", "matter_documents")


def _backfill_user_id_columns(conn: sqlite3.Connection) -> None:
    """Add ``user_id`` to legacy tables created before multi-tenancy.

    ``CREATE TABLE IF NOT EXISTS`` doesn't add columns to existing tables.
    For every table that pre-dates the schema bump, we ALTER it to gain
    a ``user_id`` column (default ``''`` so legacy rows remain readable
    by the migration window — they're filtered out by the tenant guard
    once the column exists).
    """
    for table in _USER_ID_BACKFILL_TABLES:
        try:
            conn.execute(
                f"ALTER TABLE {table} ADD COLUMN user_id TEXT NOT NULL DEFAULT ''"
            )
        except sqlite3.OperationalError:
            # Column already exists (schema ran fresh, or this is the
            # 2nd init call). Either way, nothing to do.
            pass


def init_schema(db_path: Optional[Path] = None, force: bool = False) -> None:
    """Idempotently create all tables. First call performs the work; later
    calls (without ``force``) are a no-op so the import path stays cheap.
    """
    global _schema_initialised
    # When an explicit path is supplied (tests), always run the DDL — the
    # module-level cache only protects the default path.
    if _schema_initialised and not force and db_path is None:
        return
    with get_connection(db_path) as conn:
        # Phase 1: create tables (idempotent — CREATE TABLE IF NOT EXISTS).
        for stmt in _TABLE_DDL:
            conn.execute(stmt)
        # Phase 2: backfill user_id on tables that pre-date MT W5. Must
        # happen BEFORE any index referencing user_id is created.
        _backfill_user_id_columns(conn)
        # Phase 3: create indexes — now safe because every legacy table
        # has the user_id column either from the table DDL (fresh DB) or
        # from the backfill ALTER (legacy DB).
        for stmt in _INDEX_DDL:
            conn.execute(stmt)
    if db_path is None:
        _schema_initialised = True


def reset_schema_cache() -> None:
    """Drop the in-process flag so a new DB path triggers fresh DDL.

    Tests call this between fixtures because ``NEXUS_PERSISTENCE_DB`` may
    point to a fresh tmp_path on each test.
    """
    global _schema_initialised
    _schema_initialised = False
