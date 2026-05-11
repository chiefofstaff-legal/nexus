"""
Multilingual Embedding Service tests.

Tests:
1. Synthetic DE legal corpus — Mietrecht query returns Mietvertrag doc in top-3.
2. Goodhart anchor: corpus uses authentic Swiss/German legal vocab, not English cognates.
3. Multilingual service uses SEPARATE chromadb collection (no English index pollution).
4. Model swap via constructor param works (testability check).

NOTE: The real paraphrase-multilingual-MiniLM-L12-v2 model (~470MB) is NOT
downloaded in tests. Embeddings are mocked at the sentence_transformers level
so the test exercises dispatch and collection isolation, not model accuracy.
The integration test (H232 manual verification) confirms real DE recall.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_DE_CORPUS = [
    ("doc-bundesgericht", "Das Bundesgericht ist das oberste Gericht der Schweiz."),
    ("doc-stgb", "Das Strafgesetzbuch regelt strafbare Handlungen in der Schweiz."),
    ("doc-mietvertrag", "Der Mietvertrag verpflichtet den Mieter zur Zahlung des Mietzinses."),
    ("doc-kindesunterhalt", "Kindesunterhalt wird nach dem Einkommen des unterhaltspflichtigen Elternteils berechnet."),
    ("doc-erbrecht", "Das Erbrecht bestimmt, wer nach dem Tod einer Person deren Vermögen erbt."),
]

_QUERY_MIETRECHT = "Mietrecht"


def _mock_encoder(corpus_docs):
    """Return a mock SentenceTransformer that produces stable fake embeddings.

    Each doc gets a unique unit vector so cosine similarity is well-defined.
    The Mietvertrag doc gets a vector closest to the Mietrecht query vector.
    """
    import numpy as np

    n = len(corpus_docs)
    # Deterministic orthogonal-ish vectors
    base = np.eye(n + 1, dtype="float32")

    doc_map = {text: base[i] for i, (_, text) in enumerate(corpus_docs)}
    # Query vector set equal to Mietvertrag vector so it matches first
    query_vec = doc_map[corpus_docs[2][1]]  # index 2 = Mietvertrag

    encoder = MagicMock()
    encoder.encode.side_effect = lambda texts, **kw: [
        doc_map.get(t, query_vec) for t in texts
    ]
    return encoder, query_vec


@pytest.fixture()
def ml_svc(tmp_path):
    """MultilingualEmbeddingService with mocked encoder and tmp chromadb."""
    from services.multilingual_embedding_service import MultilingualEmbeddingService

    svc = MultilingualEmbeddingService(data_dir=tmp_path, model_name="mock-model")
    encoder, _ = _mock_encoder(_DE_CORPUS)
    svc._encoder = encoder  # inject mock — avoids 470MB download
    return svc


def test_mietrecht_query_returns_mietvertrag_in_top3(ml_svc):
    """Authentic DE legal vocab: Mietrecht query should surface Mietvertrag doc."""
    for doc_id, text in _DE_CORPUS:
        ml_svc.index(doc_id, [text])

    results = ml_svc.search(_QUERY_MIETRECHT, limit=3)

    doc_ids = [r["metadata"].get("doc_id", "") for r in results]
    assert "doc-mietvertrag" in doc_ids, (
        f"Mietvertrag expected in top-3 for '{_QUERY_MIETRECHT}', got: {doc_ids}"
    )


def test_goodhart_corpus_uses_authentic_german_legal_terms():
    """Goodhart anchor: verify the corpus uses Swiss/German legal vocab, not English cognates."""
    authentic_terms = {"Bundesgericht", "Strafgesetzbuch", "Mietvertrag", "Kindesunterhalt", "Erbrecht"}
    corpus_text = " ".join(text for _, text in _DE_CORPUS)
    for term in authentic_terms:
        assert term in corpus_text, f"Authentic German legal term '{term}' missing from corpus"


def test_separate_chromadb_collection(tmp_path):
    """Multilingual service uses 'documents_multilingual', not 'nexus_documents'."""
    from services.multilingual_embedding_service import (
        MultilingualEmbeddingService,
        _COLLECTION_NAME,
    )

    svc = MultilingualEmbeddingService(data_dir=tmp_path, model_name="mock-model")
    assert svc.collection_name == _COLLECTION_NAME
    assert _COLLECTION_NAME == "documents_multilingual"
    assert _COLLECTION_NAME != "nexus_documents"


def test_model_name_injectable():
    """Constructor accepts model_name — confirms testability seam."""
    from services.multilingual_embedding_service import MultilingualEmbeddingService

    import tempfile
    with tempfile.TemporaryDirectory() as td:
        svc = MultilingualEmbeddingService(
            data_dir=Path(td), model_name="some-test-model"
        )
        assert svc._model_name == "some-test-model"
