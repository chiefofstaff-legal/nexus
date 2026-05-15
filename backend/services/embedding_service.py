"""
Embedding & Semantic Search Service
=====================================

Chunks documents, generates embeddings via all-MiniLM-L6-v2,
stores in ChromaDB, and provides semantic search.
"""

from pathlib import Path
from typing import Optional

import chromadb
from chromadb.config import Settings


class EmbeddingService:
    """Document embedding and semantic search via ChromaDB."""

    CHUNK_SIZE = 512  # tokens (approx chars / 4)
    CHUNK_OVERLAP = 50

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        db_path = data_dir / "chromadb"
        db_path.mkdir(parents=True, exist_ok=True)

        self.client = chromadb.PersistentClient(
            path=str(db_path),
            settings=Settings(anonymized_telemetry=False),
        )
        self.collection = self.client.get_or_create_collection(
            name="nexus_documents",
            metadata={"hnsw:space": "cosine"},
        )

    def chunk_text(self, text: str) -> list[str]:
        """Split text into overlapping chunks."""
        # Approximate token-to-char ratio: 1 token ~ 4 chars
        chunk_chars = self.CHUNK_SIZE * 4
        overlap_chars = self.CHUNK_OVERLAP * 4

        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_chars

            # Try to break at paragraph or sentence boundary
            if end < len(text):
                # Look for paragraph break
                para_break = text.rfind("\n\n", start + chunk_chars // 2, end)
                if para_break > start:
                    end = para_break
                else:
                    # Look for sentence break
                    sent_break = text.rfind(". ", start + chunk_chars // 2, end)
                    if sent_break > start:
                        end = sent_break + 1

            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)

            start = end - overlap_chars
            if start >= len(text):
                break

        return chunks

    def index_document(
        self,
        doc_id: str,
        text: str,
        user_id: str,
        metadata: Optional[dict] = None,
    ) -> int:
        """Chunk and index a document for ``user_id``.

        The ``user_id`` is stamped into every chunk's metadata so the
        ChromaDB ``where`` filter on retrieval can prove tenant
        isolation. Returns number of chunks indexed.
        """
        if not user_id:
            raise ValueError("user_id is required for tenant-scoped indexing")
        chunks = self.chunk_text(text)
        if not chunks:
            return 0

        ids = []
        documents = []
        metadatas = []

        base_meta = metadata or {}

        for i, chunk in enumerate(chunks):
            chunk_id = f"{user_id}_{doc_id}_chunk_{i}"
            ids.append(chunk_id)
            documents.append(chunk)
            metadatas.append({
                **base_meta,
                "user_id": user_id,
                "doc_id": doc_id,
                "chunk_index": i,
                "total_chunks": len(chunks),
            })

        self.collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
        )

        return len(chunks)

    def search(
        self,
        query: str,
        user_id: str,
        n_results: int = 5,
        doc_id: Optional[str] = None,
    ) -> list[dict]:
        """Semantic search restricted to ``user_id``'s chunks."""
        if not user_id:
            raise ValueError("user_id is required for tenant-scoped search")
        count = self.collection.count()
        if count == 0:
            return []

        # ChromaDB raises if n_results > collection size
        safe_n = min(n_results, count)
        where: dict = {"user_id": user_id}
        if doc_id:
            where = {"$and": [{"user_id": user_id}, {"doc_id": doc_id}]}

        results = self.collection.query(
            query_texts=[query],
            n_results=safe_n,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        hits = []
        if results and results["documents"]:
            for i, doc in enumerate(results["documents"][0]):
                hits.append({
                    "text": doc,
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": results["distances"][0][i] if results["distances"] else 0,
                    "relevance": round(1 - (results["distances"][0][i] if results["distances"] else 0), 3),
                })

        return hits

    def get_stats(self) -> dict:
        """Get collection statistics."""
        count = self.collection.count()
        return {
            "total_chunks": count,
            "collection_name": "nexus_documents",
        }


# --- Search IDR logging (moved from app/routes.py, W1 SRP fix) ---------------

def log_search_idr(
    query: str,
    results: list[dict],
    n_results: int,
    idr_store,
    user_id: str,
) -> None:
    """Append a SEMANTIC_SEARCH IDR for one retrieval, stamped with the
    caller's ``user_id`` in ``metadata.tenant_id`` so /api/idrs/* can
    filter by tenant. Swallows errors so search never fails on
    audit-chain issues.
    """
    try:
        from core.intent_decision_record import (
            DecisionPoint,
            IntentDecisionRecord,
            SynthesisMethod,
        )
        top_hit = results[0] if results else None
        top_meta = (top_hit or {}).get("metadata", {})
        top_relevance = float((top_hit or {}).get("relevance", 0.0))
        idr = IntentDecisionRecord(
            decision_point=DecisionPoint.SEMANTIC_SEARCH,
            input_hash=IntentDecisionRecord.hash_input(query),
            input_summary=f"semantic search: {query[:200]}",
            decision=top_meta.get("filename", "no_results"),
            confidence=top_relevance,
            confidence_rationale=(
                f"top hit relevance {top_relevance:.3f} across {len(results)} results"
            ),
            reasoning=(
                "query returned " + str(len(results)) + " chunks; top filenames: "
                + ", ".join(r.get("metadata", {}).get("filename", "?") for r in results[:3])
            ),
            synthesis_method=SynthesisMethod.DETERMINISTIC,
            falsification_criterion=(
                "A human reviewer searching the same corpus would expect "
                f"different top results for '{query[:60]}' — either a "
                "more-relevant chunk was missed (recall failure) or an "
                "irrelevant chunk was surfaced (precision failure)."
            ),
            metadata={
                # tenant_id is injected by IDRStore.append (single DRY
                # injection point) — do not stamp it here too.
                "query": query,
                "n_results": n_results,
                "hit_doc_ids": [r.get("metadata", {}).get("doc_id") for r in results],
                "hit_filenames": [r.get("metadata", {}).get("filename") for r in results],
                "relevances": [r.get("relevance", 0.0) for r in results],
            },
        )
        idr_store.append(idr, user_id=user_id)
    except Exception:
        pass
