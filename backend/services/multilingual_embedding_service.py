"""
Multilingual Embedding Service
================================

Mirrors EmbeddingService but uses paraphrase-multilingual-MiniLM-L12-v2
and a SEPARATE ChromaDB collection so the English index is never polluted.

Opt-in by construction — callers must instantiate this class explicitly.
The existing EmbeddingService remains untouched.
"""

from __future__ import annotations

from pathlib import Path

import chromadb
from chromadb.config import Settings

_DEFAULT_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
_COLLECTION_NAME = "documents_multilingual"


class MultilingualEmbeddingService:
    """Semantic search for non-English (and mixed-language) corpora."""

    def __init__(self, data_dir: Path, model_name: str = _DEFAULT_MODEL) -> None:
        self._model_name = model_name
        db_path = data_dir / "chromadb_multilingual"
        db_path.mkdir(parents=True, exist_ok=True)

        self._client = chromadb.PersistentClient(
            path=str(db_path),
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        self._encoder = None  # lazy-load on first use

    def _get_encoder(self):
        if self._encoder is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._encoder = SentenceTransformer(self._model_name)
            except Exception as exc:
                raise RuntimeError(
                    f"Could not load multilingual model '{self._model_name}': {exc}. "
                    "Ensure sentence-transformers is installed and the model is downloadable."
                ) from exc
        return self._encoder

    def index(self, doc_id: str, chunks: list[str]) -> int:
        """Embed and upsert chunks. Returns number of chunks indexed."""
        if not chunks:
            return 0
        encoder = self._get_encoder()
        embeddings = encoder.encode(chunks, convert_to_list=True)
        ids = [f"{doc_id}_chunk_{i}" for i in range(len(chunks))]
        metadatas = [{"doc_id": doc_id, "chunk_index": i} for i in range(len(chunks))]
        self._collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=chunks,
            metadatas=metadatas,
        )
        return len(chunks)

    def search(self, query: str, limit: int = 10) -> list[dict]:
        """Return cosine-ranked results from the multilingual collection."""
        count = self._collection.count()
        if count == 0:
            return []
        encoder = self._get_encoder()
        query_embedding = encoder.encode([query], convert_to_list=True)[0]
        safe_n = min(limit, count)
        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=safe_n,
            include=["documents", "metadatas", "distances"],
        )
        hits = []
        if results and results["documents"]:
            for i, doc in enumerate(results["documents"][0]):
                distance = results["distances"][0][i] if results["distances"] else 0.0
                hits.append({
                    "text": doc,
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": distance,
                    "relevance": round(1.0 - distance, 3),
                    "collection": _COLLECTION_NAME,
                })
        return hits

    @property
    def collection_name(self) -> str:
        return _COLLECTION_NAME
