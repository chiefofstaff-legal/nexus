"""SQLite-backed Matter and MatterDocument store.

Mirrors the discipline of ``time_capture.TimeEntryStore`` and
``task_manager.TaskStore``: a thin class wrapping ``sqlite3`` with the
schema initialised lazily on first call.

Document-membership operations are delegated to a private helper class
to keep the public ``MatterStore`` interface focused (ISP).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core.persistence import get_connection, init_schema
from models.matter import Matter, MatterDocument


def _row_to_matter(row: sqlite3.Row) -> Matter:
    return Matter(
        id=row["id"],
        name=row["name"],
        client=row["client"],
        notes=row["notes"],
        created_at=datetime.fromisoformat(row["created_at"]),
        archived_at=(
            datetime.fromisoformat(row["archived_at"])
            if row["archived_at"] else None
        ),
    )


def _row_to_membership(row: sqlite3.Row) -> MatterDocument:
    return MatterDocument(
        matter_id=row["matter_id"],
        document_id=row["document_id"],
        added_at=datetime.fromisoformat(row["added_at"]),
    )


_ALLOWED_UPDATE_FIELDS = ("name", "client", "notes")


class _ConnHolder:
    """Mixin holding the lazy schema-init contract."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self._db_path = db_path
        self._initialised = False

    def _ensure_init(self) -> None:
        if not self._initialised:
            init_schema(self._db_path)
            self._initialised = True

    def _conn(self) -> sqlite3.Connection:
        self._ensure_init()
        return get_connection(self._db_path)


class _MatterDocuments(_ConnHolder):
    """Document-membership operations split out for ISP hygiene."""

    def add(self, matter_id: str, document_id: str) -> MatterDocument:
        membership = MatterDocument(matter_id=matter_id, document_id=document_id)
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO matter_documents"
                " (matter_id, document_id, added_at) VALUES (?, ?, ?)",
                (
                    membership.matter_id, membership.document_id,
                    membership.added_at.isoformat(),
                ),
            )
        return membership

    def remove(self, matter_id: str, document_id: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM matter_documents"
                " WHERE matter_id = ? AND document_id = ?",
                (matter_id, document_id),
            )
            return cur.rowcount > 0

    def list(self, matter_id: str) -> list[MatterDocument]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM matter_documents"
                " WHERE matter_id = ? ORDER BY added_at DESC",
                (matter_id,),
            ).fetchall()
        return [_row_to_membership(r) for r in rows]


class MatterStore(_ConnHolder):
    """SQLite-backed matter store with soft-delete.

    Document-membership operations are exposed via the ``documents``
    attribute (a ``_MatterDocuments`` instance) to keep this class focused
    per the Interface Segregation Principle. Call sites use:

        store.documents.add(matter_id, document_id)
        store.documents.remove(matter_id, document_id)
        store.documents.list(matter_id)
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        super().__init__(db_path)
        self.documents = _MatterDocuments(db_path)

    def create(self, name: str, client: str = "", notes: str = "") -> Matter:
        matter = Matter(
            name=name.strip(), client=client.strip(), notes=notes.strip(),
        )
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO matters (id, name, client, notes, created_at, archived_at)"
                " VALUES (?, ?, ?, ?, ?, NULL)",
                (
                    matter.id, matter.name, matter.client, matter.notes,
                    matter.created_at.isoformat(),
                ),
            )
        return matter

    def get(self, matter_id: str) -> Optional[Matter]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM matters WHERE id = ?", (matter_id,),
            ).fetchone()
        return _row_to_matter(row) if row else None

    def list(self, include_archived: bool = False) -> list[Matter]:
        sql = "SELECT * FROM matters"
        if not include_archived:
            sql += " WHERE archived_at IS NULL"
        sql += " ORDER BY created_at DESC"
        with self._conn() as conn:
            rows = conn.execute(sql).fetchall()
        return [_row_to_matter(r) for r in rows]

    def update(self, matter_id: str, **fields) -> Optional[Matter]:
        clean = {
            k: v for k, v in fields.items()
            if k in _ALLOWED_UPDATE_FIELDS and v is not None
        }
        if not clean:
            return self.get(matter_id)
        assignments = ", ".join(f"{k} = ?" for k in clean)
        values = list(clean.values()) + [matter_id]
        with self._conn() as conn:
            cur = conn.execute(
                f"UPDATE matters SET {assignments} WHERE id = ?", values,
            )
            if cur.rowcount == 0:
                return None
        return self.get(matter_id)

    def archive(self, matter_id: str) -> Optional[Matter]:
        ts = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute(
                "UPDATE matters SET archived_at = ?"
                " WHERE id = ? AND archived_at IS NULL",
                (ts, matter_id),
            )
        return self.get(matter_id)
