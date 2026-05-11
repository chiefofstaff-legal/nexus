"""FastAPI dependency factories for service-layer injection.

Each `get_*` function is decorated with `@lru_cache(maxsize=None)` so it
behaves as a singleton under normal operation while remaining override-able
via `app.dependency_overrides` in tests — the cache is bypassed entirely
when FastAPI substitutes a different callable.

Usage in endpoints:
    from fastapi import Depends
    from app.dependencies import get_embedding_service

    @router.post("/search")
    async def search(body: dict, svc: EmbeddingService = Depends(get_embedding_service)):
        ...

Usage in tests:
    from app.dependencies import get_embedding_service
    app.dependency_overrides[get_embedding_service] = lambda: mock_svc
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths (kept in sync with routes.py DATA_DIR)
# ---------------------------------------------------------------------------

_DATA_DIR = Path.home() / "nexus-poc" / "data"
_SOP_DIR = _DATA_DIR / "sops"


# ---------------------------------------------------------------------------
# Lazy Anthropic helpers (avoid import cost if not needed)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def get_anthropic_client():
    try:
        import anthropic
        return anthropic.Anthropic()
    except Exception:
        return None


@lru_cache(maxsize=None)
def get_async_anthropic_client():
    try:
        import anthropic
        return anthropic.AsyncAnthropic()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# IDR store — shared singleton from routes_idr
# ---------------------------------------------------------------------------

def get_idr_store():
    from app.routes_idr import _store
    return _store


# ---------------------------------------------------------------------------
# Service factories
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def get_doc_processor():
    from services.document_processor import DocumentProcessor
    return DocumentProcessor(
        _DATA_DIR,
        get_async_anthropic_client(),
        idr_store=get_idr_store(),
    )


@lru_cache(maxsize=None)
def get_entity_extractor():
    from services.entity_extractor import EntityExtractor
    return EntityExtractor(get_async_anthropic_client())


@lru_cache(maxsize=None)
def get_embedding_service():
    from services.embedding_service import EmbeddingService
    return EmbeddingService(_DATA_DIR)


@lru_cache(maxsize=None)
def get_llm_router():
    from services.llm_router import LLMRouter
    return LLMRouter(_DATA_DIR, get_anthropic_client())


@lru_cache(maxsize=None)
def get_audit_chain():
    from core.audit_chain import AuditChain
    return AuditChain(log_path=_DATA_DIR / "audit" / "audit.jsonl")


@lru_cache(maxsize=None)
def get_council():
    from services.council import Council
    return Council(
        get_idr_store(),
        async_anthropic_client=get_async_anthropic_client(),
        timeout_per_call_s=15.0,
    )


@lru_cache(maxsize=None)
def get_sensitivity_classifier():
    from services.sensitivity_classifier import SensitivityClassifier
    return SensitivityClassifier(get_council())


@lru_cache(maxsize=None)
def get_sop_engine():
    from services.sop_engine import SOPEngine, create_sample_sops
    create_sample_sops(_SOP_DIR)
    return SOPEngine(_SOP_DIR)
