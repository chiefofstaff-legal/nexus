"""
NEXUS API Routes
=================

All endpoints for the 4 prototypes:
1. Document ingestion + auto filing
2. LLM orchestration routing
3. Entity graph
4. SOP agent
"""

import asyncio
import json as _json
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# Add backend root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.audit_chain import AuditChain
from core.intent_decision_record import (
    DecisionPoint,
    IntentDecisionRecord,
    SynthesisMethod,
)
from models.document import DocumentRecord
from models.sop import SOPExecution
from services.document_processor import DocumentProcessor
from services.entity_extractor import EntityExtractor
from services.llm_router import LLMRouter, RoutingDecision, SensitivityLevel
from services.embedding_service import EmbeddingService, log_search_idr
from services.graph_service import capped_cytoscape
from services.routing_helpers import enrich_decision_with_council, idr_summary
from services.redaction import redact as _redact_text
from services.time_capture import (
    DEFAULT_HOURLY_RATE_CHF,
    ParseError,
    TimeEntry,
    TimeEntryStore,
    build_entry_from_transcript,
)
from services.task_manager import (
    KNOWN_ASSIGNEES,
    Task,
    TaskStatus,
    TaskStore,
    delegate_from_transcript,
)
from models.matter import Matter
from services.matter_service import MatterStore
from services.sharepoint_service import (
    SharePointConfig,
    SharePointConnector,
    sharepoint_enabled,
)
from app.routes_idr import _store as idr_store
from app.dependencies import (
    get_anthropic_client,
    get_async_anthropic_client,
    get_audit_chain,
    get_council,
    get_doc_processor,
    get_embedding_service,
    get_entity_extractor,
    get_llm_router,
    get_sensitivity_classifier,
    get_sop_engine,
)

# --- Configuration ---
DATA_DIR = Path.home() / "nexus-poc" / "data"
SOP_DIR = DATA_DIR / "sops"
CORPUS_DIR = Path.home() / "nexus-poc" / "test_corpus"

_MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB
_ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".md"}


# Service singletons — backed by composition-root factories in app.dependencies.
# Endpoints that add Depends(get_*) inject fresh references; these module-level
# names remain for the remaining endpoints that close over them directly.
doc_processor = get_doc_processor()
entity_extractor = get_entity_extractor()
embedding_service = get_embedding_service()
llm_router = get_llm_router()
audit_chain = get_audit_chain()
council = get_council()
sensitivity_classifier = get_sensitivity_classifier()


def _audit_document_processed(
    record: DocumentRecord,
    filename: str,
    chunk_count: int,
    source_folder: Optional[str] = None,
) -> None:
    """Sign and append a ``document_processed`` audit entry.

    Rule-of-three DRY fix: this was duplicated across the single-upload,
    batch-upload, and parallel-folder-ingest paths. One source of truth.
    """
    entry = {
        "event": "document_processed",
        "document_id": record.id,
        "filename": filename,
        "type": record.document_type.value,
        "confidence": record.classification_confidence,
        "chunks_indexed": chunk_count,
    }
    if source_folder is not None:
        entry["source_folder"] = source_folder
    audit_chain.sign_and_append(entry)

# In-memory document store (POC)
_document_records: dict[str, DocumentRecord] = {}
_document_texts: dict[str, str] = {}  # W5: full extracted text for the viewer
_ingest_lock = asyncio.Lock()  # Protects _document_records + entity graph mutations

# Allowed base directories for folder ingestion (path traversal protection)
ALLOWED_INGEST_DIRS = {Path.home(), DATA_DIR, CORPUS_DIR}

sop_engine = get_sop_engine()

# Active SOP executions (in-memory for POC)
_active_executions: dict[str, SOPExecution] = {}

# --- Routers ---
documents = APIRouter(prefix="/api/documents", tags=["Documents"])
routing = APIRouter(prefix="/api/routing", tags=["LLM Routing"])
entities = APIRouter(prefix="/api/entities", tags=["Entity Graph"])
sops = APIRouter(prefix="/api/sops", tags=["SOP Agent"])
time_capture = APIRouter(prefix="/api/time", tags=["Time Capture"])
tasks = APIRouter(prefix="/api/tasks", tags=["Delegation"])
matters = APIRouter(prefix="/api/matters", tags=["Matters"])
sharepoint = APIRouter(prefix="/api/sharepoint", tags=["SharePoint"])

# --- Time capture store (in-memory POC) ---
_time_store = TimeEntryStore(default_rate_chf=DEFAULT_HOURLY_RATE_CHF)

# --- Task store (SQLite-backed; distinct from time entries) ---
_task_store = TaskStore()

# --- Matter store (SQLite-backed; legal-case entity) ---
_matter_store = MatterStore()

# --- SharePoint connector (stub-mode by default, toggled by env var) ---
_sharepoint = SharePointConnector()


# === DOCUMENT ROUTES ===

def _check_upload_type(suffix: str) -> None:
    if suffix not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{suffix}'. Allowed: {', '.join(sorted(_ALLOWED_EXTENSIONS))}",
        )


async def _stream_to_temp(file: UploadFile, suffix: str) -> Path:
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = Path(tmp.name)
        total = 0
        while chunk := await file.read(65536):
            total += len(chunk)
            if total > _MAX_UPLOAD_BYTES:
                tmp_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail=f"File too large. Maximum allowed is {_MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
                )
            tmp.write(chunk)
    return tmp_path


@documents.post("/upload", response_model=DocumentRecord)
async def upload_document(
    file: UploadFile = File(...),
    dp: DocumentProcessor = Depends(get_doc_processor),
    emb: EmbeddingService = Depends(get_embedding_service),
    ee: EntityExtractor = Depends(get_entity_extractor),
):
    """Upload and process a document through the full pipeline."""
    suffix = Path(file.filename or "document").suffix.lower()
    _check_upload_type(suffix)

    tmp_path = await _stream_to_temp(file, suffix)
    try:
        extraction = await dp.extract_text(tmp_path)
        record = await dp.process(tmp_path, extraction=extraction)

        chunk_count = emb.index_document(
            doc_id=record.id,
            text=extraction.text,
            metadata={
                "filename": file.filename or "",
                "document_type": record.document_type.value,
            },
        )
        record.chunk_count = chunk_count

        await ee.process_document(extraction.text, record.id)

        _document_records[record.id] = record
        _document_texts[record.id] = extraction.text
        _audit_document_processed(record, file.filename, chunk_count)

        return record
    finally:
        tmp_path.unlink(missing_ok=True)


@documents.post("/batch-upload")
async def batch_upload():
    """Process all documents in the test corpus directory."""
    results = []
    corpus_dir = CORPUS_DIR
    if not corpus_dir.exists():
        raise HTTPException(status_code=404, detail="Test corpus directory not found")

    for file_path in sorted(corpus_dir.iterdir()):
        if file_path.suffix in DocumentProcessor.SUPPORTED_EXTENSIONS:
            try:
                extraction = await doc_processor.extract_text(file_path)
                record = await doc_processor.process(file_path, extraction=extraction)

                chunk_count = embedding_service.index_document(
                    doc_id=record.id,
                    text=extraction.text,
                    metadata={
                        "filename": file_path.name,
                        "document_type": record.document_type.value,
                    },
                )
                record.chunk_count = chunk_count

                await entity_extractor.process_document(extraction.text, record.id)
                _document_records[record.id] = record

                _audit_document_processed(record, file_path.name, chunk_count)

                results.append(record.model_dump())
            except Exception as e:
                results.append({"filename": file_path.name, "error": str(e)})

    return {"processed": len(results), "documents": results}


async def _process_single_file(
    file_path: Path,
    source_folder: str,
    semaphore: asyncio.Semaphore,
) -> dict:
    """Process a single file through the full pipeline under semaphore control.

    Each stage (extract, classify, index, entity extraction) is guarded
    so a single bad file never crashes the whole batch. V>>'s walkthrough
    showed doc 3/10 failing with a cryptic 500; this version captures the
    traceback into the server log and degrades gracefully on the three
    most common failure modes: empty text, ChromaDB rejecting an empty
    document, and spaCy choking on an unexpected token stream.
    """
    import logging
    import traceback
    log = logging.getLogger("nexus.ingest")

    async with semaphore:
        try:
            extraction = await doc_processor.extract_text(file_path)
            record = await doc_processor.process(file_path, extraction=extraction)
        except Exception as e:
            log.error(
                "extract/process failed for %s: %s\n%s",
                file_path.name, e, traceback.format_exc(),
            )
            raise RuntimeError(
                f"extract/process({file_path.name}): {type(e).__name__}: {e}"
            ) from e

        record.chunk_count = await _safe_index(record, extraction, file_path, log)
        async with _ingest_lock:
            await _safe_extract_graph(extraction, record, file_path, log)
            _document_records[record.id] = record
            _document_texts[record.id] = extraction.text

        _audit_document_processed(
            record, file_path.name, chunk_count=record.chunk_count, source_folder=source_folder
        )
        return record.model_dump(mode="json")


async def _safe_index(record, extraction, file_path: Path, log) -> int:
    """ChromaDB rejects empty docs — skip indexing gracefully."""
    if not extraction.text.strip():
        return 0
    try:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: embedding_service.index_document(
                doc_id=record.id,
                text=extraction.text,
                metadata={
                    "filename": file_path.name,
                    "document_type": record.document_type.value,
                },
            ),
        )
    except Exception as e:
        log.warning("index_document failed for %s (continuing): %s", file_path.name, e)
        return 0


async def _safe_extract_graph(extraction, record, file_path: Path, log) -> None:
    """Entity extraction must never block ingestion — log and continue."""
    try:
        await entity_extractor.process_document(extraction.text, record.id)
    except Exception as e:
        log.warning(
            "entity_extractor failed for %s (continuing without graph): %s",
            file_path.name, e,
        )


@documents.post("/ingest-folder")
async def ingest_folder(body: dict):
    """Ingest all documents from a folder — streams SSE progress events."""
    folder_path = body.get("folder_path", "")
    if not folder_path:
        raise HTTPException(status_code=400, detail="folder_path required")

    target = Path(folder_path).expanduser().resolve()
    if not any(target == base or base in target.parents for base in ALLOWED_INGEST_DIRS):
        raise HTTPException(status_code=403, detail="Folder path outside allowed directories")
    if not target.exists():
        raise HTTPException(status_code=404, detail="Folder not found")
    if not target.is_dir():
        raise HTTPException(status_code=400, detail="Not a directory")

    files = sorted(
        f for f in target.iterdir()
        if f.is_file() and not f.name.startswith(".")
    )
    total = len(files)

    async def event_stream() -> AsyncGenerator[str, None]:
        yield f"data: {_json.dumps({'event': 'start', 'total': total, 'folder': str(target)})}\n\n"

        sem = asyncio.Semaphore(15)
        completed = 0
        errors = 0
        t0 = time.monotonic()

        async def process_one(fp: Path) -> tuple[str, dict]:
            try:
                result = await _process_single_file(fp, str(target), sem)
                return ("ok", {**result, "_filename": fp.name})
            except Exception as e:
                return ("error", {"_filename": fp.name, "error": str(e)})

        tasks = [asyncio.create_task(process_one(fp)) for fp in files]
        for coro in asyncio.as_completed(tasks):
            status, data = await coro
            filename = data.pop("_filename", "unknown")
            completed += 1
            elapsed = time.monotonic() - t0
            rate = completed / elapsed if elapsed > 0 else 0
            eta = (total - completed) / rate if rate > 0 else 0

            if status == "error":
                errors += 1
                yield f"data: {_json.dumps({'event': 'error', 'completed': completed, 'total': total, 'filename': filename, 'error': data.get('error', 'unknown')})}\n\n"
            else:
                yield f"data: {_json.dumps({'event': 'progress', 'completed': completed, 'total': total, 'filename': filename, 'document_type': data.get('document_type', 'unknown'), 'confidence': data.get('classification_confidence', 0), 'rate': round(rate, 2), 'eta_seconds': round(eta), 'document': data})}\n\n"

        elapsed = time.monotonic() - t0
        yield f"data: {_json.dumps({'event': 'done', 'total': total, 'processed': total - errors, 'errors': errors, 'elapsed_seconds': round(elapsed, 1)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@documents.get("/list")
async def list_documents():
    """List all processed documents."""
    return {"documents": [r.model_dump() for r in _document_records.values()]}


@documents.get("/content/{doc_id}")
async def get_document_content(doc_id: str):
    """Return the raw extracted text + metadata for the viewer modal."""
    record = _document_records.get(doc_id)
    text = _document_texts.get(doc_id)
    if record is None or text is None:
        raise HTTPException(status_code=404, detail=f"document {doc_id} not found")
    return {
        "id": record.id,
        "filename": record.original_filename,
        "document_type": record.document_type.value,
        "classification_confidence": record.classification_confidence,
        "parties": record.parties,
        "dates": record.dates,
        "summary": record.summary,
        "page_count": record.page_count,
        "extraction_method": record.extraction_method,
        "text": text,
        "char_count": len(text),
    }


async def _redact_document(doc_id: str) -> tuple[DocumentRecord, dict]:
    """Run the redaction pipeline and emit a REDACTION_POLICY IDR.

    Shared helper for the JSON endpoint and the file download endpoint.
    """
    record = _document_records.get(doc_id)
    text = _document_texts.get(doc_id)
    if record is None or text is None:
        raise HTTPException(status_code=404, detail=f"document {doc_id} not found")

    entities = await entity_extractor.extract_entities_spacy(text, source_doc=doc_id)
    result = _redact_text(text, entities)

    # Write a REDACTION_POLICY IDR so the audit chain records who
    # redacted what when (complements W3's IDR ubiquity and gives the
    # document viewer a traceable decision surface).
    try:
        idr = IntentDecisionRecord(
            decision_point=DecisionPoint.REDACTION_POLICY,
            input_hash=IntentDecisionRecord.hash_input(text),
            input_summary=f"redaction of {record.original_filename}",
            decision="redacted",
            confidence=1.0,
            confidence_rationale="deterministic regex + entity pipeline",
            reasoning=(
                f"{sum(result.counts.values())} spans replaced across "
                f"{len(result.counts)} categories"
            ),
            synthesis_method=SynthesisMethod.DETERMINISTIC,
            falsification_criterion=(
                "A reviewer reading the redacted document finds any "
                "residual PII the pipeline missed (e.g. a new currency "
                "symbol, an unusual name spelling, a statute-adjacent "
                "identifier). Add the pattern to services/redaction.py "
                "and re-run."
            ),
            metadata={
                "doc_id": record.id,
                "filename": record.original_filename,
                "counts": result.counts,
                "total_spans": len(result.spans),
            },
        )
        idr_store.append(idr)
    except Exception:
        pass  # audit chain is secondary to returning the redacted text

    return record, result.to_dict()


@documents.post("/content/{doc_id}/redact")
async def redact_document(doc_id: str):
    """Return the redacted text + span manifest + counts."""
    _, payload = await _redact_document(doc_id)
    return payload


@documents.get("/content/{doc_id}/download-redacted")
async def download_redacted(doc_id: str):
    """Return the redacted document as a plain-text download."""
    from fastapi.responses import Response
    record, payload = await _redact_document(doc_id)
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", record.original_filename or doc_id)
    stem = Path(safe_name).stem or doc_id
    filename = f"{stem}.redacted.txt"
    return Response(
        content=payload["text"],
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Redaction-Total-Spans": str(payload["span_count"]),
        },
    )




@documents.post("/search")
async def search_documents(body: dict):
    """Semantic search across all indexed documents.

    Writes a SEMANTIC_SEARCH IDR per query via log_search_idr so the
    audit chain records what a user looked for, when, and which
    documents were surfaced.
    """
    query = body.get("query", "")
    n_results = body.get("n_results", 5)
    doc_id = body.get("doc_id")
    if not query:
        raise HTTPException(status_code=400, detail="query field required")
    results = embedding_service.search(query, n_results=n_results, doc_id=doc_id)
    log_search_idr(query, results, n_results, idr_store)
    return {"query": query, "results": results, "total": len(results)}


@documents.get("/search-stats")
async def search_stats():
    """Get embedding/search statistics."""
    return embedding_service.get_stats()


@documents.post("/classify")
async def classify_text(body: dict):
    """Classify document text without uploading a file."""
    text = body.get("text", "")
    filename = body.get("filename", "")
    if not text:
        raise HTTPException(status_code=400, detail="text field required")

    result = await doc_processor.classify(text, filename)
    return result.model_dump()


# === LLM ROUTING ROUTES ===

class RoutingRequest(BaseModel):
    prompt: str
    system: str = ""
    task_type: str = "general"
    force_model: Optional[str] = None


class RoutingResponse(BaseModel):
    response: str
    decision: RoutingDecision
    idr: Optional[dict] = None




async def _route_via_council(req: RoutingRequest) -> RoutingResponse:
    """Classify via multi-LLM council, route on winning level, write IDR."""
    council_result = await sensitivity_classifier.classify(
        req.prompt,
        doc_summary=f"routing query ({len(req.prompt)} chars)",
    )
    try:
        level = SensitivityLevel(council_result.decision)
    except ValueError:
        level = SensitivityLevel.INTERNAL

    response_text, decision = await llm_router.route_and_call(
        prompt=req.prompt,
        system=req.system,
        task_type=req.task_type,
        force_level=level,
    )
    enrich_decision_with_council(decision, council_result)
    return RoutingResponse(
        response=response_text,
        decision=decision,
        idr=idr_summary(council_result),
    )


@routing.post("/query", response_model=RoutingResponse)
async def route_query(
    req: RoutingRequest,
    router_svc: LLMRouter = Depends(get_llm_router),
):
    """Route via council (default) or explicit ``force_model`` bypass."""
    if req.force_model:
        response_text, decision = await router_svc.route_and_call(
            prompt=req.prompt,
            system=req.system,
            task_type=req.task_type,
            force_model=req.force_model,
        )
        return RoutingResponse(response=response_text, decision=decision)
    return await _route_via_council(req)


@routing.post("/classify-sensitivity")
async def classify_sensitivity(body: dict):
    """Classify text sensitivity via the multi-LLM council.

    Runs the same council that ``/api/routing/query`` uses but skips the
    downstream ``route_and_call`` step — no response is generated, only
    the sensitivity decision + its IDR. The old density-regex heuristic
    is kept around as a deterministic PII floor signal (see
    ``SensitivityClassifier.pii_fingerprint``) but no longer decides the
    label.

    Why retargeted: the regex heuristic was mis-labelling private legal
    documents as ``public`` because it only counts dense PII (SSN/credit-
    card patterns). A contract full of named individuals without those
    markers reads as public to the regex but obviously internal or
    confidential to a Swiss-law-trained reviewer. V>> flagged this in the
    MVP walkthrough: the ``Classify Only`` button was returning
    ``public 29.2%`` on documents the same system routed correctly to
    ``internal`` via the council. Pointing both paths at the council
    removes the contradiction.
    """
    text = body.get("text", "")
    if not text:
        raise HTTPException(status_code=400, detail="text field required")

    council_result = await sensitivity_classifier.classify(
        text,
        doc_summary=f"classify-only request ({len(text)} chars)",
    )
    pii_fingerprint = council_result.idr.get("metadata", {}).get(
        "pii_fingerprint", []
    )
    return {
        "sensitivity_level": council_result.decision,
        "sensitivity_score": round(council_result.confidence, 3),
        "pii_types_detected": pii_fingerprint,
        "confidence_rationale": council_result.confidence_rationale,
        "reasoning": council_result.reasoning,
        "synthesis_method": council_result.synthesis_method.value,
        "idr": idr_summary(council_result),
    }


@routing.get("/providers")
async def get_providers():
    """Check which LLM providers are available."""
    return llm_router.get_provider_status()


@routing.get("/audit")
async def get_routing_audit():
    """Get the routing audit trail."""
    log_path = DATA_DIR / "audit" / "routing-audit.jsonl"
    if not log_path.exists():
        return {"entries": [], "chain_valid": True}

    entries = []
    with open(log_path) as f:
        import json
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except Exception:
                    pass

    # Verify chain
    router_audit = AuditChain(log_path=log_path)
    verification = router_audit.verify()

    return {"entries": entries[-50:], "chain_valid": verification["valid"],
            "total_entries": verification["total_entries"]}


# === ENTITY GRAPH ROUTES ===

_GRAPH_NODE_CAP = 200




@entities.get("/graph")
async def get_graph(limit: int = _GRAPH_NODE_CAP):
    """Get the knowledge graph in Cytoscape.js format (capped at *limit* nodes).

    Returns the most-connected entities first. When the graph is larger than
    *limit*, a 'capped: true' field is included so the UI can inform the user.
    """
    return capped_cytoscape(entity_extractor.graph, limit)


@entities.get("/graph/{entity_id}")
async def get_entity_subgraph(entity_id: str, depth: int = 1):
    """Get subgraph around a specific entity."""
    subgraph = entity_extractor.graph.get_connected(entity_id, depth)
    return subgraph.to_cytoscape()


@entities.get("/list")
async def list_entities():
    """List all entities."""
    return [e.model_dump() for e in entity_extractor.graph.entities]


@entities.get("/stats")
async def entity_stats():
    """Get graph statistics."""
    g = entity_extractor.graph
    type_counts = {}
    for e in g.entities:
        type_counts[e.entity_type.value] = type_counts.get(e.entity_type.value, 0) + 1

    return {
        "total_entities": len(g.entities),
        "total_relationships": len(g.relationships),
        "by_type": type_counts,
    }


# === SOP ROUTES ===

@sops.get("/list")
async def list_sops_endpoint():
    """List available SOPs."""
    return sop_engine.list_sops()


@sops.post("/start/{sop_id}")
async def start_sop(sop_id: str):
    """Start executing an SOP."""
    try:
        execution = sop_engine.start_execution(sop_id)
        import hashlib
        from datetime import datetime
        exec_id = hashlib.sha256(f"{sop_id}:{datetime.utcnow().isoformat()}".encode()).hexdigest()[:12]
        _active_executions[exec_id] = execution

        step = sop_engine.get_current_step(execution)
        return {
            "execution_id": exec_id,
            "sop_name": execution.sop_name,
            "total_steps": execution.total_steps,
            "current_step": step.model_dump() if step else None,
            "progress": execution.progress_pct,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@sops.post("/respond/{execution_id}")
async def respond_to_step(execution_id: str, body: dict):
    """Submit a response for the current SOP step."""
    execution = _active_executions.get(execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")

    response = body.get("response")
    execution = sop_engine.submit_response(execution, response)
    _active_executions[execution_id] = execution

    if execution.completed:
        output = sop_engine.generate_output(execution)
        audit_chain.sign_and_append({
            "event": "sop_completed",
            "sop_id": execution.sop_id,
            "sop_name": execution.sop_name,
            "execution_id": execution_id,
        })
        return {"completed": True, "output": output}

    if execution.halted:
        return {"halted": True, "reason": execution.halt_reason}

    step = sop_engine.get_current_step(execution)
    return {
        "current_step": step.model_dump() if step else None,
        "progress": execution.progress_pct,
        "completed": False,
    }


@sops.get("/status/{execution_id}")
async def sop_status(execution_id: str):
    """Get current status of an SOP execution."""
    execution = _active_executions.get(execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")

    step = sop_engine.get_current_step(execution)
    return {
        "sop_name": execution.sop_name,
        "progress": execution.progress_pct,
        "current_step": step.model_dump() if step else None,
        "completed": execution.completed,
        "halted": execution.halted,
        "halt_reason": execution.halt_reason,
    }


# === TIME CAPTURE ROUTES ===


class TimeCaptureRequest(BaseModel):
    audio_b64: Optional[str] = None
    transcript: str
    hourly_rate_chf: float = DEFAULT_HOURLY_RATE_CHF


class TimeLogRequest(BaseModel):
    transcript: str
    hourly_rate_chf: float = DEFAULT_HOURLY_RATE_CHF


class MatterUpdate(BaseModel):
    matter: str


class TranscriptUpdate(BaseModel):
    transcript: str


def _audit_time_entry(entry: TimeEntry, source: str) -> None:
    """Record a billable time entry to the tamper-evident audit chain."""
    try:
        audit_chain.sign_and_append({
            "event": "time_entry_logged",
            "entry_id": entry.id,
            "matter": entry.matter,
            "duration_minutes": entry.duration_minutes,
            "hourly_rate_chf": entry.hourly_rate_chf,
            "value_chf": entry.value_chf,
            "source": source,
        })
    except Exception:
        pass  # audit is secondary to returning the entry


def _capture_and_store(transcript: str, rate: float, source: str) -> TimeEntry:
    """Shared pipeline: parse transcript, build TimeEntry, store, audit."""
    try:
        entry = build_entry_from_transcript(
            transcript,
            anthropic_client=get_anthropic_client(),
            hourly_rate_chf=rate,
        )
    except ParseError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    _time_store.log_time_entry(entry)
    _audit_time_entry(entry, source)
    return entry


@time_capture.post("/capture")
async def capture_time(req: TimeCaptureRequest):
    """Voice capture endpoint. Accepts a transcript from the browser Web
    Speech API (audio_b64 is accepted for future server-side transcription
    but ignored for now) and parses it via Claude Haiku."""
    entry = _capture_and_store(req.transcript, req.hourly_rate_chf, "voice")
    return entry.model_dump()


@time_capture.post("/log")
async def log_time(req: TimeLogRequest):
    """Direct text log (no audio) — same parse pipeline, different source tag."""
    entry = _capture_and_store(req.transcript, req.hourly_rate_chf, "text")
    return entry.model_dump()


@time_capture.get("/entries")
async def list_time_entries():
    """List all time entries with derived CHF values, newest first."""
    entries = _time_store.get_time_entries()
    return {"entries": [e.model_dump(mode="json") for e in entries]}


@time_capture.patch("/entries/{entry_id}/matter")
async def update_entry_matter(entry_id: str, body: MatterUpdate):
    """Edit the matter field after capture (Claude mishears client names)."""
    updated = _time_store.update_matter(entry_id, body.matter)
    if updated is None:
        raise HTTPException(status_code=404, detail="Time entry not found")
    return updated.model_dump(mode="json")


@time_capture.patch("/entries/{entry_id}/transcript")
async def update_entry_transcript(entry_id: str, body: TranscriptUpdate):
    """Correct the raw Groq STT transcript — fixes acronyms and mishears."""
    updated = _time_store.update_transcript(entry_id, body.transcript)
    if updated is None:
        raise HTTPException(status_code=404, detail="Time entry not found")
    return updated.model_dump(mode="json")


@time_capture.get("/summary")
async def time_summary(rate: Optional[float] = None):
    """Daily billable summary at the requested CHF hourly rate."""
    return _time_store.get_daily_total_chf(rate=rate)


# === TASK / DELEGATION ROUTES ===
#
# Critical client distinction (repeat to self before editing):
#   task         = what must be done (future, unbilled, delegable)
#   time entry   = what was done and billed (past, recorded)
# The two stores NEVER overlap.

class DelegateRequest(BaseModel):
    transcript: str


class TaskCreateRequest(BaseModel):
    title: str
    description: str = ""
    assignee: str
    matter: str = ""
    deadline: Optional[str] = None  # ISO date string; empty/None allowed
    priority: str = "medium"
    raw_transcript: str = ""


class StatusUpdate(BaseModel):
    status: str


def _audit_task_event(event: str, task: Task) -> None:
    """Append a signed audit entry. Swallows errors — audit is secondary."""
    try:
        audit_chain.sign_and_append({
            "event": event,
            "task_id": task.id,
            "title": task.title,
            "assignee": task.assignee,
            "matter": task.matter,
            "priority": task.priority.value,
            "status": task.status.value,
        })
    except Exception:
        pass


def _coerce_status(raw: str) -> TaskStatus:
    try:
        return TaskStatus(raw)
    except ValueError as e:
        allowed = ", ".join(s.value for s in TaskStatus)
        raise HTTPException(
            status_code=400,
            detail=f"invalid status '{raw}' (allowed: {allowed})",
        ) from e


@tasks.post("/delegate")
async def delegate_task(req: DelegateRequest):
    """Parse a voice transcript into a preview task — does NOT persist.

    The caller (UI) shows the parsed preview for user review, then confirms
    via POST /create. That confirm step is the sole persistence point.
    Using delegate_from_transcript() here caused a double-create: delegate
    stored + confirm stored = 2 tasks. Fixed by calling parse_delegation()
    directly, which returns a ParsedDelegation without touching the store.
    """
    from services.task_manager import parse_delegation, _make_task_id
    from datetime import datetime as _dt

    transcript = req.transcript.strip()
    if not transcript:
        raise HTTPException(status_code=400, detail="transcript required")

    parsed = await parse_delegation(transcript, anthropic_client=get_async_anthropic_client())
    now = _dt.utcnow()
    preview = Task(
        id=_make_task_id(transcript, now),
        title=parsed.title,
        description=parsed.description,
        assignee=parsed.assignee,
        matter=parsed.matter,
        deadline=parsed.deadline,
        priority=parsed.priority,
        raw_transcript=transcript,
    )
    return preview.model_dump(mode="json")


@tasks.post("/create")
async def create_task(req: TaskCreateRequest):
    """Direct structured create (used by the Edit flow in the UI)."""
    from datetime import datetime as _dt, date as _date
    from services.task_manager import Priority, _make_task_id

    try:
        priority = Priority(req.priority.lower())
    except ValueError as e:
        raise HTTPException(status_code=400, detail="invalid priority") from e

    deadline: Optional[_date] = None
    if req.deadline:
        try:
            deadline = _date.fromisoformat(req.deadline)
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail="deadline must be YYYY-MM-DD",
            ) from e

    now = _dt.utcnow()
    task = Task(
        id=_make_task_id(req.title, now),
        title=req.title.strip() or "Untitled task",
        description=req.description.strip(),
        assignee=req.assignee.strip(),
        matter=req.matter.strip(),
        deadline=deadline,
        priority=priority,
        created_at=now,
        raw_transcript=req.raw_transcript,
    )
    _task_store.add(task)
    _audit_task_event("task_created", task)
    return task.model_dump(mode="json")


@tasks.get("/list")
async def list_tasks(
    assignee: Optional[str] = None,
    matter: Optional[str] = None,
    status: Optional[str] = None,
):
    """List tasks with optional filters."""
    status_enum = _coerce_status(status) if status else None
    results = _task_store.list(assignee=assignee, matter=matter, status=status_enum)
    return {"tasks": [t.model_dump(mode="json") for t in results]}


@tasks.patch("/{task_id}/status")
async def update_task_status(task_id: str, body: StatusUpdate):
    """Move a task between columns on the board."""
    status = _coerce_status(body.status)
    try:
        task = _task_store.update_status(task_id, status)
    except KeyError as e:
        raise HTTPException(status_code=404, detail="task not found") from e
    _audit_task_event("task_status_changed", task)
    return task.model_dump(mode="json")


@tasks.patch("/{task_id}/transcript")
async def update_task_transcript(task_id: str, body: TranscriptUpdate):
    """Correct the raw STT transcript on a delegated task post-creation."""
    try:
        task = _task_store.update_transcript(task_id, body.transcript)
    except KeyError as e:
        raise HTTPException(status_code=404, detail="task not found") from e
    return task.model_dump(mode="json")


@tasks.get("/assignees")
async def list_assignees():
    """Pre-populated colleague roster for the UI dropdown."""
    return {"assignees": list(KNOWN_ASSIGNEES)}


# === MATTER ROUTES ===
#
# A Matter is the legal-case anchor: documents, time entries, and tasks all
# link to it via matter_id. Soft-delete (archive) preserves billing history.

class MatterCreateRequest(BaseModel):
    name: str
    client: str = ""
    notes: str = ""


class MatterUpdateRequest(BaseModel):
    name: Optional[str] = None
    client: Optional[str] = None
    notes: Optional[str] = None


class MatterDocumentRequest(BaseModel):
    document_id: str


def _matter_or_404(matter_id: str) -> Matter:
    """Fetch a matter or raise a 404 — DRY shortcut for the route handlers."""
    matter = _matter_store.get(matter_id)
    if matter is None:
        raise HTTPException(status_code=404, detail="matter not found")
    return matter


@matters.post("", status_code=201)
async def create_matter(body: MatterCreateRequest):
    """Create a new legal matter. Returns the persisted record."""
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    matter = _matter_store.create(name=name, client=body.client, notes=body.notes)
    return matter.model_dump(mode="json")


@matters.get("")
async def list_matters(archived: bool = False):
    """List matters; pass ``archived=true`` to include soft-deleted entries."""
    rows = _matter_store.list(include_archived=archived)
    return {"matters": [m.model_dump(mode="json") for m in rows]}


@matters.get("/{matter_id}")
async def get_matter(matter_id: str):
    """Fetch a single matter by id (404 if not found)."""
    return _matter_or_404(matter_id).model_dump(mode="json")


@matters.patch("/{matter_id}")
async def update_matter(matter_id: str, body: MatterUpdateRequest):
    """Partial update — only non-None fields are applied."""
    updated = _matter_store.update(
        matter_id, name=body.name, client=body.client, notes=body.notes,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="matter not found")
    return updated.model_dump(mode="json")


@matters.delete("/{matter_id}")
async def archive_matter(matter_id: str):
    """Soft-delete: sets ``archived_at`` so historic billing remains intact."""
    _matter_or_404(matter_id)
    archived = _matter_store.archive(matter_id)
    if archived is None:  # defensive — race between get and archive
        raise HTTPException(status_code=404, detail="matter not found")
    return archived.model_dump(mode="json")


@matters.post("/{matter_id}/documents", status_code=201)
async def add_matter_document(matter_id: str, body: MatterDocumentRequest):
    """Link a document to the matter (membership table)."""
    _matter_or_404(matter_id)
    membership = _matter_store.documents.add(matter_id, body.document_id)
    return membership.model_dump(mode="json")


@matters.delete("/{matter_id}/documents/{document_id}", status_code=204)
async def remove_matter_document(matter_id: str, document_id: str):
    """Unlink a document from the matter. 204 on success."""
    removed = _matter_store.documents.remove(matter_id, document_id)
    if not removed:
        raise HTTPException(status_code=404, detail="membership not found")
    return None


@matters.get("/{matter_id}/documents")
async def list_matter_documents(matter_id: str):
    """List all documents linked to a matter."""
    _matter_or_404(matter_id)
    rows = _matter_store.documents.list(matter_id)
    return {"documents": [d.model_dump(mode="json") for d in rows]}


# === SHAREPOINT ROUTES ===
#
# Stub-mode integration. SHAREPOINT_ENABLED=false (default) returns mock
# data so the demo is reliable offline. Setting the env var to true would
# flip the connector to Graph API mode (not implemented in the POC).

class _SharePointCredentials(BaseModel):
    """Shared credential fields inherited by all SharePoint request models."""

    tenant_id: str = ""
    client_id: str = ""
    client_secret: str = ""
    site_url: str = ""
    library_name: str = "Documents"


class SharePointConnectRequest(_SharePointCredentials):
    pass


def _sp_config(body: _SharePointCredentials) -> SharePointConfig:
    """Coerce any SharePoint request body into a SharePointConfig."""
    return SharePointConfig(
        tenant_id=body.tenant_id.strip(),
        client_id=body.client_id.strip(),
        client_secret=body.client_secret,
        site_url=body.site_url.strip(),
        library_name=body.library_name.strip() or "Documents",
    )


def _audit_sharepoint(event: str, payload: dict) -> None:
    """Sign-and-append — SharePoint events join the main audit chain."""
    try:
        audit_chain.sign_and_append({"event": event, **payload})
    except Exception:
        pass


@sharepoint.get("/status")
async def sharepoint_status():
    """Report whether SharePoint is in stub mode or live Graph mode."""
    return {
        "enabled": sharepoint_enabled(),
        "stub_mode": _sharepoint.stub_mode,
        "synced_count": _sharepoint.synced_count(),
    }


@sharepoint.post("/connect")
async def sharepoint_connect(body: SharePointConnectRequest):
    """Test connection. Stub mode always succeeds with mock payload."""
    result = await _sharepoint.test_connection(_sp_config(body))
    _audit_sharepoint("sharepoint_connect", {
        "site_url": result.get("site_url", ""),
        "stub_mode": result.get("stub_mode", True),
    })
    return result


@sharepoint.get("/documents")
async def sharepoint_documents(
    tenant_id: str = "",
    client_id: str = "",
    client_secret: str = "",
    site_url: str = "",
    library_name: str = "Documents",
    folder: str = "",
):
    """List documents from the configured library (mock set in stub mode)."""
    config = SharePointConfig(
        tenant_id=tenant_id, client_id=client_id,
        client_secret=client_secret,
        site_url=site_url, library_name=library_name,
    )
    docs = await _sharepoint.list_documents(config, folder=folder)
    return {"documents": docs, "count": len(docs), "stub_mode": _sharepoint.stub_mode}


class SharePointSyncRequest(_SharePointCredentials):
    doc_id: str = ""


@sharepoint.post("/sync")
async def sharepoint_sync(body: SharePointSyncRequest):
    """Sync a single SharePoint document into NEXUS (stub flags it synced)."""
    if not body.doc_id:
        raise HTTPException(status_code=400, detail="doc_id required")
    result = await _sharepoint.sync_document(_sp_config(body), body.doc_id)
    if not result.get("synced"):
        raise HTTPException(status_code=404, detail=result.get("reason", "sync failed"))
    _audit_sharepoint("sharepoint_synced", {
        "doc_id": body.doc_id, "title": result.get("title", ""),
    })
    return result


class SharePointExportRequest(_SharePointCredentials):
    content: str = ""
    filename: str = ""
    folder: str = "NEXUS Drafts"


@sharepoint.post("/export")
async def sharepoint_export(body: SharePointExportRequest):
    """Upload a generated draft back into SharePoint Online."""
    if not body.content.strip() or not body.filename.strip():
        raise HTTPException(status_code=400, detail="content and filename required")
    result = await _sharepoint.export_document(
        _sp_config(body), body.content, body.filename.strip(), body.folder or "NEXUS Drafts"
    )
    _audit_sharepoint("sharepoint_exported", {
        "filename": body.filename,
        "folder": body.folder,
        "web_url": result.get("web_url", ""),
    })
    return result


# === VOICE TRANSCRIPTION ROUTES ===
#
# Uses Groq Whisper large-v3 — already keyed via GROQ_API_KEY in .env.
# Browser records WebM/Opus via MediaRecorder; backend transcribes and
# returns plain text. Replaces the Web Speech API (blocked by Brave).

voice_router = APIRouter(prefix="/api/voice")


@voice_router.post("/transcribe")
async def transcribe_audio(
    audio: UploadFile = File(...),
    lang: Optional[str] = None,
):
    """Transcribe browser-recorded audio using Groq Whisper large-v3.

    Accepts WebM/Opus (MediaRecorder default) or any format Whisper supports.
    Returns {"transcript": "..."}.

    Query params:
        lang: BCP-47 language code (``en``, ``de``, ``fr``, ``it``). Omit for
              Whisper autodetection — correct for multilingual DE/FR/IT clients.
    """
    try:
        from groq import Groq
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="groq SDK not installed") from exc

    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="empty audio upload")

    filename = audio.filename or "audio.webm"
    content_type = audio.content_type or "audio/webm"

    import os
    groq_key = os.getenv("GROQ_API_KEY", "")
    if not groq_key:
        raise HTTPException(
            status_code=503,
            detail="Voice transcription unavailable: GROQ_API_KEY not configured.",
        )

    def _transcribe() -> str:
        client = Groq(api_key=groq_key)
        try:
            result = client.audio.transcriptions.create(
                file=(filename, audio_bytes, content_type),
                model="whisper-large-v3",
                language=lang or None,
                response_format="text",
            )
        except Exception as exc:
            raise RuntimeError(f"Groq transcription error: {exc}") from exc
        return result if isinstance(result, str) else getattr(result, "text", str(result))

    try:
        transcript = await asyncio.to_thread(_transcribe)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"transcript": transcript.strip()}
