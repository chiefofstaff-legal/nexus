"""
Hybrid Search Service (Reciprocal Rank Fusion)
================================================

Merges semantic and keyword ranked lists via RRF.
Pure delegation — no state beyond the two injected services.
"""

from __future__ import annotations


class HybridSearchService:
    """Combine semantic + keyword results via Reciprocal Rank Fusion."""

    def __init__(self, embedding_service, keyword_service) -> None:
        self._embed = embedding_service
        self._kw = keyword_service

    def search(
        self,
        query: str,
        alpha: float = 0.5,  # reserved for future weighted RRF; currently pure RRF
        k: int = 60,
        limit: int = 10,
    ) -> list[dict]:
        """Return RRF-merged results.

        RRF score per document: sum(1 / (k + rank_i)) across each ranked list.
        Documents appearing in both lists score higher than those in only one.
        alpha is accepted but unused in pure RRF — preserved for API stability.
        """
        semantic_hits = self._embed.search(query, n_results=limit * 2)
        keyword_hits = self._kw.search(query, limit=limit * 2)

        scores: dict[str, float] = {}
        meta: dict[str, dict] = {}
        sources: dict[str, list[str]] = {}

        def _get(hit: dict, field: str, fallback: str = "") -> str:
            """Read field from top-level or nested metadata (handles both hit shapes)."""
            return str(hit.get(field) or hit.get("metadata", {}).get(field) or fallback)

        def _key(hit: dict) -> str:
            return f"{_get(hit, 'doc_id')}::{_get(hit, 'chunk_index', '0')}"

        def _record(hits: list[dict], source_label: str) -> None:
            for rank, hit in enumerate(hits, start=1):
                key = _key(hit)
                scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
                if key not in meta:
                    meta[key] = {
                        "doc_id": _get(hit, "doc_id"),
                        "chunk_index": _get(hit, "chunk_index", "0"),
                        "filename": _get(hit, "filename"),
                        "content": hit.get("content") or hit.get("text", ""),
                    }
                sources.setdefault(key, [])
                if source_label not in sources[key]:
                    sources[key].append(source_label)

        _record(semantic_hits, "semantic")
        _record(keyword_hits, "keyword")

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [
            {**meta[key], "score": round(score, 6), "sources": sources[key]}
            for key, score in ranked[:limit]
        ]
