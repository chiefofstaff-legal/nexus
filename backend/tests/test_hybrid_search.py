"""
Hybrid Search (RRF) tests.

Tests:
1. Doc appearing in both semantic + keyword lists ranks first.
2. Goodhart anchor: hybrid beats either source alone on the double-ranked doc.
3. Alpha param is accepted without error (reserved for future weighted RRF).
"""

from __future__ import annotations

from unittest.mock import MagicMock

from services.hybrid_search import HybridSearchService


def _make_semantic_hit(doc_id, chunk_index=0, filename="f.pdf", text="content"):
    return {"text": text, "metadata": {"doc_id": doc_id, "chunk_index": chunk_index,
                                        "filename": filename}, "distance": 0.1, "relevance": 0.9}


def _make_keyword_hit(doc_id, chunk_index=0, filename="f.pdf", content="content"):
    return {"doc_id": doc_id, "chunk_index": str(chunk_index),
            "filename": filename, "content": content, "rank": 1}


def _build_service(semantic_hits, keyword_hits):
    embed_svc = MagicMock()
    embed_svc.search.return_value = semantic_hits
    kw_svc = MagicMock()
    kw_svc.search.return_value = keyword_hits
    return HybridSearchService(embed_svc, kw_svc)


def test_doc_in_both_lists_ranks_first():
    """docB appears in both lists — RRF should rank it above docA (semantic-only)."""
    semantic = [
        _make_semantic_hit("docA", text="alpha content"),
        _make_semantic_hit("docB", text="beta content"),
        _make_semantic_hit("docC", text="gamma content"),
    ]
    keyword = [
        _make_keyword_hit("docB", content="beta content"),
        _make_keyword_hit("docD", content="delta content"),
    ]
    svc = _build_service(semantic, keyword)
    results = svc.search("beta", k=60, limit=10)

    assert results, "Expected non-empty results"
    assert results[0]["doc_id"] == "docB", (
        f"docB (in both lists) should rank first, got {results[0]['doc_id']}"
    )


def test_rrf_score_beats_single_source():
    """Goodhart anchor: docB's RRF score must exceed docA's (semantic rank 1, keyword absent)."""
    k = 60
    # semantic: docA=rank1, docB=rank2 → scores 1/61, 1/62
    # keyword:  docB=rank1             → score  1/61
    # docB total ≈ 1/62 + 1/61 ≈ 0.0328; docA ≈ 1/61 ≈ 0.0164
    semantic = [
        _make_semantic_hit("docA"),
        _make_semantic_hit("docB"),
        _make_semantic_hit("docC"),
    ]
    keyword = [
        _make_keyword_hit("docB"),
        _make_keyword_hit("docD"),
    ]
    svc = _build_service(semantic, keyword)
    results = svc.search("query", k=k, limit=10)

    scores = {r["doc_id"]: r["score"] for r in results}
    assert "docB" in scores and "docA" in scores
    assert scores["docB"] > scores["docA"], (
        f"docB RRF={scores['docB']:.6f} should exceed docA RRF={scores['docA']:.6f}"
    )
    # docB sources must include both
    docb = next(r for r in results if r["doc_id"] == "docB")
    assert "semantic" in docb["sources"]
    assert "keyword" in docb["sources"]


def test_alpha_param_accepted():
    """alpha is accepted without error (reserved for future weighted RRF)."""
    svc = _build_service([], [])
    results = svc.search("test", alpha=0.7, k=60, limit=5)
    assert isinstance(results, list)
