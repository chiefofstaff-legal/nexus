"""
Search v2 + Multilingual Voice Routes
=======================================

New routes — do NOT modify routes.py or main.py.
The orchestrator wires these routers via include_router().

Routes:
  GET  /api/documents/search-v2   — keyword | semantic | hybrid dispatch
  POST /api/voice/transcribe-multilingual — Groq Whisper with lang hint
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from services.embedding_service import EmbeddingService
from services.hybrid_search import HybridSearchService
from services.keyword_search import KeywordSearchService
from services.multilingual_embedding_service import MultilingualEmbeddingService

_DATA_DIR = Path(__file__).parent.parent.parent / "data"

_keyword_svc = KeywordSearchService()
_embed_svc = EmbeddingService(_DATA_DIR)
_hybrid_svc = HybridSearchService(_embed_svc, _keyword_svc)
_multilingual_svc = MultilingualEmbeddingService(_DATA_DIR)

search_router = APIRouter(prefix="/api", tags=["Search"])

_VALID_MODES = {"keyword", "semantic", "hybrid"}


@search_router.get("/documents/search-v2")
async def search_v2(
    q: str = Query(default=""),
    mode: str = Query(default="hybrid"),
    lang: str = Query(default="en"),
    limit: int = Query(default=10, ge=1, le=100),
):
    """Dispatch keyword / semantic / hybrid search with optional DE language."""
    if not q or not q.strip():
        raise HTTPException(status_code=400, detail="q parameter is required")
    if mode not in _VALID_MODES:
        raise HTTPException(
            status_code=422,
            detail=f"mode must be one of: {', '.join(sorted(_VALID_MODES))}",
        )

    use_multilingual = lang == "de"

    if mode == "keyword":
        results = _keyword_svc.search(q, limit=limit)
    elif mode == "semantic":
        svc = _multilingual_svc if use_multilingual else _embed_svc
        results = svc.search(q, limit=limit) if use_multilingual else svc.search(q, n_results=limit)
    else:  # hybrid
        if use_multilingual:
            hybrid = HybridSearchService(_multilingual_svc, _keyword_svc)
            results = hybrid.search(q, limit=limit)
        else:
            results = _hybrid_svc.search(q, limit=limit)

    return {"query": q, "mode": mode, "lang": lang, "results": results, "total": len(results)}


@search_router.post("/voice/transcribe-multilingual")
async def transcribe_multilingual(
    audio: UploadFile = File(...),
    lang: str = Query(default=None),
):
    """Transcribe audio with optional language hint (None = autodetect).

    Returns {transcript, detected_language, duration_seconds}.
    lang=None lets Whisper autodetect; lang='de' forces German decoding.
    """
    try:
        from groq import Groq
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="groq SDK not installed") from exc

    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="empty audio upload")

    groq_key = os.getenv("GROQ_API_KEY", "")
    if not groq_key:
        raise HTTPException(
            status_code=503,
            detail="Voice transcription unavailable: GROQ_API_KEY not configured.",
        )

    filename = audio.filename or "audio.webm"
    content_type = audio.content_type or "audio/webm"

    def _transcribe():
        client = Groq(api_key=groq_key)
        kwargs = dict(
            file=(filename, audio_bytes, content_type),
            model="whisper-large-v3",
            response_format="verbose_json",
        )
        if lang:
            kwargs["language"] = lang
        try:
            result = client.audio.transcriptions.create(**kwargs)
        except Exception as exc:
            raise RuntimeError(f"Groq transcription error: {exc}") from exc
        return result

    try:
        result = await asyncio.to_thread(_transcribe)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    transcript = getattr(result, "text", str(result)).strip()
    detected = getattr(result, "language", lang or "unknown")
    duration = getattr(result, "duration", 0.0)

    return {
        "transcript": transcript,
        "detected_language": detected,
        "duration_seconds": round(float(duration), 2),
    }
