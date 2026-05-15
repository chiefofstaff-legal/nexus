"""Service layer Protocol interfaces (W4 ISP fix).

Python structural typing via ``typing.Protocol`` (PEP 544).  Concrete service
classes satisfy these protocols automatically — no inheritance needed.  Callers
(routes, tests) can declare narrow dependencies on these types instead of
importing the full concrete class.

Design intent: each Protocol contains only the methods that one caller group
actually uses.  Splitting a fat interface into narrow Protocols is the ISP fix.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Document processing
# ---------------------------------------------------------------------------

@runtime_checkable
class DocumentExtractorProtocol(Protocol):
    """Used by: upload_document, ingest_folder — text extraction only."""

    async def extract_text(self, file_path: Path):
        ...


@runtime_checkable
class DocumentProcessorProtocol(Protocol):
    """Used by: upload_document, batch_upload, ingest_folder."""

    async def extract_text(self, file_path: Path):
        ...

    async def process(self, file_path: Path, *, extraction=None):
        ...

    async def classify(self, text: str, filename: str = ""):
        ...


# ---------------------------------------------------------------------------
# Semantic search
# ---------------------------------------------------------------------------

@runtime_checkable
class SearchProtocol(Protocol):
    """Used by: search_documents, upload_document."""

    def index_document(self, doc_id: str, text: str, metadata: Optional[dict] = None) -> int:
        ...

    def search(self, query: str, n_results: int = 5, doc_id: Optional[str] = None) -> list[dict]:
        ...

    def get_stats(self) -> dict:
        ...


# ---------------------------------------------------------------------------
# Entity extraction
# ---------------------------------------------------------------------------

@runtime_checkable
class EntityExtractorProtocol(Protocol):
    """Used by: upload_document, ingest_folder, get_graph, list_entities."""

    async def process_document(self, text: str, doc_id: str) -> None:
        ...

    async def extract_entities_spacy(self, text: str, source_doc: str = "") -> list:
        ...


# ---------------------------------------------------------------------------
# LLM routing
# ---------------------------------------------------------------------------

@runtime_checkable
class LLMRouterProtocol(Protocol):
    """Used by: route_query (force_model branch)."""

    async def route_and_call(
        self,
        prompt: str,
        system: str = "",
        task_type: str = "general",
        force_model: Optional[str] = None,
    ) -> tuple:
        ...

    def classify_sensitivity(self, text: str) -> tuple:
        ...

    def get_provider_status(self) -> dict:
        ...


# ---------------------------------------------------------------------------
# Sensitivity classification (council-based)
# ---------------------------------------------------------------------------

@runtime_checkable
class SensitivityClassifierProtocol(Protocol):
    """Used by: _route_via_council, classify_sensitivity endpoint."""

    async def classify(self, text: str, filename: str = ""):
        ...


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

@runtime_checkable
class AuditProtocol(Protocol):
    """Used by: all endpoints that write audit events.

    Per-tenant partitioning (2026-05-12): ``sign_and_append`` REQUIRES a
    ``user_id`` to physically isolate each tenant's chain on disk. Reads
    via ``verify`` are scoped to that user's chain.
    """

    def sign_and_append(
        self, entry: dict, user_id: str = "", payload: Optional[dict] = None
    ) -> dict:
        ...

    def verify(self, user_id: str = "") -> dict:
        ...
