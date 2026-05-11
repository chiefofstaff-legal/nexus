"""
Keyword Search Service (FTS5)
==============================

BM25-ranked full-text search over document chunks using SQLite FTS5.
Creates its own virtual table inline — does NOT modify persistence.py schema.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from core.persistence import get_connection

_FTS_DDL = """
CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(
    doc_id,
    chunk_index,
    filename,
    content,
    tokenize = 'porter unicode61'
)
"""

_DELETE_EXISTING = "DELETE FROM chunk_fts WHERE doc_id = ? AND chunk_index = ?"
_INSERT = "INSERT INTO chunk_fts(doc_id, chunk_index, filename, content) VALUES (?, ?, ?, ?)"
_SEARCH = """
SELECT doc_id, chunk_index, filename, content, rank
FROM chunk_fts
WHERE chunk_fts MATCH ?
ORDER BY rank
LIMIT ?
"""

_PLAIN_RE = re.compile(r"^[\w\s]+$")


def _fts5_safe(query: str) -> str:
    """Wrap in double-quotes when query contains FTS5 metacharacters."""
    if _PLAIN_RE.fullmatch(query):
        return query
    return '"' + query.replace('"', '""') + '"'


class KeywordSearchService:
    """BM25 keyword search over indexed document chunks via FTS5."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self._db_path = db_path
        with get_connection(db_path) as conn:
            conn.execute(_FTS_DDL)

    def index(self, doc_id: str, chunk_index: int, filename: str, content: str) -> None:
        """Upsert a chunk (idempotent: delete-then-insert)."""
        with get_connection(self._db_path) as conn:
            conn.execute(_DELETE_EXISTING, (doc_id, str(chunk_index)))
            conn.execute(_INSERT, (doc_id, str(chunk_index), filename, content))

    def search(self, query: str, limit: int = 10) -> list[dict]:
        """Return BM25-ranked matches. Blank query returns []."""
        if not query or not query.strip():
            return []
        safe_query = _fts5_safe(query)
        with get_connection(self._db_path) as conn:
            try:
                rows = conn.execute(_SEARCH, (safe_query, limit)).fetchall()
            except Exception:
                quoted = '"' + query.replace('"', '""') + '"'
                rows = conn.execute(_SEARCH, (quoted, limit)).fetchall()
        return [
            {
                "doc_id": row["doc_id"],
                "chunk_index": row["chunk_index"],
                "filename": row["filename"],
                "content": row["content"],
                "rank": rank,
            }
            for rank, row in enumerate(rows, start=1)
        ]
