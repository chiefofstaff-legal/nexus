"""W3 — ChromaDB filter + filesystem partition isolate tenants."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest


@pytest.fixture
def emb(tmp_path):
    from services.embedding_service import EmbeddingService
    svc = EmbeddingService(tmp_path)
    yield svc
    # Tear down ChromaDB lock files in the tmp dir
    shutil.rmtree(tmp_path / "chromadb", ignore_errors=True)


def test_index_requires_user_id(emb):
    with pytest.raises(ValueError, match="user_id"):
        emb.index_document(doc_id="x", text="hello", user_id="")


def test_search_requires_user_id(emb):
    with pytest.raises(ValueError, match="user_id"):
        emb.search("hello", user_id="")


def test_cross_tenant_chunk_invisible(emb):
    alice_text = "contract clause about liability under Swiss FADP"
    bob_text = "contract clause about liability under Swiss FADP"
    emb.index_document(doc_id="alice-doc", text=alice_text, user_id="alice-uid")
    emb.index_document(doc_id="bob-doc", text=bob_text, user_id="bob-uid")

    alice_hits = emb.search("Swiss FADP liability", user_id="alice-uid", n_results=5)
    bob_hits = emb.search("Swiss FADP liability", user_id="bob-uid", n_results=5)

    assert alice_hits, "Alice should see her own indexed chunk"
    assert bob_hits, "Bob should see his own indexed chunk"

    alice_doc_ids = {h["metadata"]["doc_id"] for h in alice_hits}
    bob_doc_ids = {h["metadata"]["doc_id"] for h in bob_hits}

    assert "alice-doc" in alice_doc_ids
    assert "bob-doc" not in alice_doc_ids, "Alice must not see Bob's chunks"
    assert "bob-doc" in bob_doc_ids
    assert "alice-doc" not in bob_doc_ids, "Bob must not see Alice's chunks"


def test_filing_path_includes_user_id(tmp_path):
    from services.document_processor import DocumentProcessor
    from models.document import ClassificationResult, DocumentType

    dp = DocumentProcessor(tmp_path)
    classification = ClassificationResult(
        document_type=DocumentType.CONTRACT,
        confidence=0.9,
        parties=["Acme"],
        dates=[],
        matter_reference=None,
        jurisdiction=None,
        summary="",
    )
    fp = Path("/tmp/example.pdf")
    filing = dp.generate_filing_path(fp, classification, user_id="user-uuid-42")
    assert "user-uuid-42" in filing.new_path
    assert (tmp_path / "filed" / "user-uuid-42").exists()


def test_filing_path_requires_user_id(tmp_path):
    from services.document_processor import DocumentProcessor
    from models.document import ClassificationResult, DocumentType

    dp = DocumentProcessor(tmp_path)
    classification = ClassificationResult(
        document_type=DocumentType.CONTRACT,
        confidence=0.9,
        parties=["Acme"],
        dates=[],
        matter_reference=None,
        jurisdiction=None,
        summary="",
    )
    with pytest.raises(ValueError, match="user_id"):
        dp.generate_filing_path(Path("/tmp/example.pdf"), classification, user_id="")
