"""
Keyword Search Service tests.

Tests:
1. Index 3 docs, search returns the matching one.
2. Empty query returns [] without error.
3. Special FTS5 chars (apostrophe) do not crash.
4. Goodhart anchor: indexing same (doc_id, chunk_index) twice does not duplicate results.
"""

from __future__ import annotations

import os

import pytest

from services.keyword_search import KeywordSearchService


@pytest.fixture()
def svc(tmp_path):
    """Isolated service using a dedicated tmp SQLite DB."""
    db = tmp_path / "test_fts.sqlite"
    os.environ["NEXUS_PERSISTENCE_DB"] = str(db)
    yield KeywordSearchService(db_path=db)
    del os.environ["NEXUS_PERSISTENCE_DB"]


def test_search_returns_matching_doc(svc):
    svc.index("doc-1", 0, "nda.pdf", "Both parties agree to strict confidentiality.")
    svc.index("doc-2", 0, "invoice.pdf", "Payment due within thirty days of receipt.")
    svc.index("doc-3", 0, "lease.pdf", "The tenant shall maintain the premises.")

    results = svc.search("confidentiality")

    assert len(results) >= 1
    assert results[0]["doc_id"] == "doc-1"
    assert results[0]["rank"] == 1


def test_empty_query_returns_empty_list(svc):
    svc.index("doc-1", 0, "a.pdf", "Some content here.")
    assert svc.search("") == []
    assert svc.search("   ") == []


def test_special_chars_do_not_crash(svc):
    svc.index("doc-1", 0, "brief.pdf", "Counsel for O'Brien submitted the motion.")
    # Must not raise; FTS5 apostrophe is handled by _fts5_safe
    results = svc.search("O'Brien")
    assert isinstance(results, list)


def test_duplicate_index_does_not_duplicate_results(svc):
    """Goodhart anchor: upsert semantics — same (doc_id, chunk_index) indexed twice
    must not produce two rows in search results."""
    svc.index("doc-1", 0, "contract.pdf", "Force majeure clause applies.")
    svc.index("doc-1", 0, "contract.pdf", "Force majeure clause applies.")  # repeat

    results = svc.search("force majeure")

    doc1_hits = [r for r in results if r["doc_id"] == "doc-1" and r["chunk_index"] == "0"]
    assert len(doc1_hits) == 1, "Duplicate index must not produce duplicate search hits"
