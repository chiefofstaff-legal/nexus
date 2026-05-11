"""SQLite-backed SummaryStore — versioned matter summaries.

Mirrors the MatterStore discipline: thin class, lazy schema init via
``core.persistence``, one responsibility per method.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core.persistence import get_connection, init_schema
from models.summary import SummarySnapshot


_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS summary_snapshots (
    matter_id TEXT NOT NULL,
    version_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    source_citations TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    PRIMARY KEY (matter_id, version_id),
    FOREIGN KEY (matter_id) REFERENCES matters(id) ON DELETE CASCADE
)
"""


def _row_to_snapshot(row: sqlite3.Row) -> SummarySnapshot:
    return SummarySnapshot(
        matter_id=row["matter_id"],
        version_id=row["version_id"],
        content=row["content"],
        source_citations=json.loads(row["source_citations"]),
        created_at=datetime.fromisoformat(row["created_at"]),
    )


class SummaryStore:
    """Versioned summary store backed by SQLite.

    Each matter maintains its own incrementing version sequence starting at 1.
    Version IDs are per-matter — matter A and matter B both have version 1.
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self._db_path = db_path
        self._initialised = False

    def _ensure_init(self) -> None:
        if not self._initialised:
            init_schema(self._db_path)
            with get_connection(self._db_path) as conn:
                conn.execute(_CREATE_TABLE)
            self._initialised = True

    def _conn(self) -> sqlite3.Connection:
        self._ensure_init()
        return get_connection(self._db_path)

    def create(
        self,
        matter_id: str,
        content: str,
        source_citations: Optional[list[str]] = None,
    ) -> SummarySnapshot:
        """Insert a new snapshot, auto-incrementing version_id per matter.

        Uses BEGIN IMMEDIATE to serialise the read-then-insert against
        concurrent writers — without it, two callers could both observe
        MAX(version_id)=N and race to INSERT version N+1, hitting the
        composite PRIMARY KEY (matter_id, version_id) with IntegrityError.
        """
        citations = source_citations or []
        conn = self._conn()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT COALESCE(MAX(version_id), 0) FROM summary_snapshots"
                " WHERE matter_id = ?",
                (matter_id,),
            ).fetchone()
            next_version = row[0] + 1
            created_at = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "INSERT INTO summary_snapshots"
                " (matter_id, version_id, content, source_citations, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (matter_id, next_version, content, json.dumps(citations), created_at),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        return SummarySnapshot(
            matter_id=matter_id,
            version_id=next_version,
            content=content,
            source_citations=citations,
            created_at=datetime.fromisoformat(created_at),
        )

    def get_latest(self, matter_id: str) -> Optional[SummarySnapshot]:
        """Return the highest-version snapshot for a matter, or None."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM summary_snapshots WHERE matter_id = ?"
                " ORDER BY version_id DESC LIMIT 1",
                (matter_id,),
            ).fetchone()
        return _row_to_snapshot(row) if row else None

    def get_version(self, matter_id: str, version_id: int) -> Optional[SummarySnapshot]:
        """Return a specific version, or None if it does not exist."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM summary_snapshots"
                " WHERE matter_id = ? AND version_id = ?",
                (matter_id, version_id),
            ).fetchone()
        return _row_to_snapshot(row) if row else None

    def list_versions(self, matter_id: str) -> list[SummarySnapshot]:
        """Return all snapshots for a matter ordered ascending by version_id."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM summary_snapshots WHERE matter_id = ?"
                " ORDER BY version_id ASC",
                (matter_id,),
            ).fetchall()
        return [_row_to_snapshot(r) for r in rows]
