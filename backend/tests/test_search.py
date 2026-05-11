"""
Semantic search endpoint tests.

Covers:
1. /api/documents/search — missing query returns 400.
2. /api/documents/search — valid query returns {query, results, total} shape.
3. /api/documents/search-stats — returns {total_chunks, collection_name}.
4. Results are sorted by relevance descending when corpus has content.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

_client = TestClient(app)


def test_search_missing_query_returns_400():
    resp = _client.post("/api/documents/search", json={})
    assert resp.status_code == 400


def test_search_empty_query_string_returns_400():
    resp = _client.post("/api/documents/search", json={"query": ""})
    assert resp.status_code == 400


def test_search_returns_expected_shape():
    """Mock embedding_service.search — verify response contract."""
    mock_hits = [
        {
            "text": "The parties agree to maintain strict confidentiality.",
            "metadata": {"doc_id": "doc-1", "filename": "nda.pdf",
                         "document_type": "nda", "chunk_index": 0,
                         "total_chunks": 3},
            "distance": 0.12,
            "relevance": 0.88,
        },
        {
            "text": "Governing law: Switzerland, Canton of Zurich.",
            "metadata": {"doc_id": "doc-2", "filename": "contract.pdf",
                         "document_type": "contract", "chunk_index": 1,
                         "total_chunks": 5},
            "distance": 0.25,
            "relevance": 0.75,
        },
    ]

    with patch("app.routes.embedding_service") as mock_svc:
        mock_svc.search.return_value = mock_hits
        mock_svc.get_stats.return_value = {"total_chunks": 42}
        resp = _client.post(
            "/api/documents/search",
            json={"query": "confidentiality Swiss law", "n_results": 5},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["query"] == "confidentiality Swiss law"
    assert isinstance(data["results"], list)
    assert data["total"] == len(mock_hits)
    # Each hit has the required keys
    for hit in data["results"]:
        assert "text" in hit
        assert "relevance" in hit
        assert "metadata" in hit


def test_search_results_relevance_ordering():
    """Results from mock come back in the order the service returns them."""
    hits = [
        {"text": "A", "metadata": {}, "distance": 0.1, "relevance": 0.9},
        {"text": "B", "metadata": {}, "distance": 0.4, "relevance": 0.6},
    ]
    with patch("app.routes.embedding_service") as mock_svc:
        mock_svc.search.return_value = hits
        resp = _client.post(
            "/api/documents/search",
            json={"query": "test ordering"},
        )
    results = resp.json()["results"]
    assert results[0]["relevance"] >= results[1]["relevance"]


def test_search_stats_shape():
    with patch("app.routes.embedding_service") as mock_svc:
        mock_svc.get_stats.return_value = {
            "total_chunks": 128,
            "collection_name": "nexus_documents",
        }
        resp = _client.get("/api/documents/search-stats")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_chunks" in data
    assert isinstance(data["total_chunks"], int)
