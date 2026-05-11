"""
NEXUS Legal Intelligence Platform — FastAPI Backend
"""

import collections
import json
import logging
import sys
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("nexus")

# Add backend root to sys.path for local imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Bridge project-root .env into os.environ so SDKs (Groq, Anthropic) that
# read env vars at construction time find their keys even when only .env
# is populated. pydantic-settings handles its own model loading separately.
load_dotenv(Path(__file__).parent.parent.parent / ".env")

from app.routes import (  # noqa: E402
    documents,
    entities,
    matters,
    routing,
    sharepoint,
    sops,
    tasks,
    time_capture,
    voice_router,
)
from app.routes_calendar import calendar_router  # noqa: E402
from app.routes_drafting import drafting  # noqa: E402
from app.routes_email import email_router  # noqa: E402
from app.routes_export import export_router  # noqa: E402
from app.routes_idr import idrs  # noqa: E402
from app.routes_search import search_router  # noqa: E402
from app.routes_summary import summary_router  # noqa: E402

TELEMETRY_LOG = Path(__file__).parent.parent.parent / "data" / "telemetry.jsonl"
TELEMETRY_LOG.parent.mkdir(parents=True, exist_ok=True)
_CORPUS_DIR = Path(__file__).parent.parent.parent / "test_corpus"


def _seed_corpus_if_empty() -> None:
    """Index test_corpus/ into ChromaDB on fresh deployments so search works immediately."""
    from app.routes import embedding_service  # noqa: PLC0415

    if embedding_service.get_stats()["total_chunks"] > 0:
        return
    if not _CORPUS_DIR.exists():
        return

    corpus_files = list(_CORPUS_DIR.glob("*.txt")) + list(_CORPUS_DIR.glob("*.pdf"))
    if not corpus_files:
        return

    logger.info("Seeding search corpus from %s (%d files)", _CORPUS_DIR, len(corpus_files))
    for path in corpus_files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            embedding_service.index_document(
                doc_id=f"corpus_{path.stem}",
                text=text,
                metadata={"filename": path.name, "document_type": "other", "source": "corpus"},
            )
            logger.info("Indexed corpus file: %s", path.name)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to index %s: %s", path.name, exc)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _seed_corpus_if_empty()
    yield


class TimingMiddleware(BaseHTTPMiddleware):
    """Log request timing and source to telemetry JSONL for the QA dashboard."""

    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000

        source = "tunnel" if "trycloudflare" in (request.headers.get("host", "")) or \
            "grip-web.com" in (request.headers.get("host", "")) else "local"

        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "ms": round(elapsed_ms, 1),
            "source": source,
            "client": request.client.host if request.client else "unknown",
            "size": response.headers.get("content-length", "0"),
        }

        if request.url.path not in ("/health", "/favicon.ico"):
            with open(TELEMETRY_LOG, "a") as f:
                f.write(json.dumps(entry) + "\n")

        return response


_rate_windows: dict[str, list] = collections.defaultdict(list)
_rate_lock = threading.Lock()
_RATE_LIMIT_UPLOAD = 10
_RATE_LIMIT_DEFAULT = 120


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        ip = request.client.host if request.client else "unknown"
        is_upload = request.url.path == "/api/documents/upload"
        key = f"{ip}:upload" if is_upload else f"{ip}:global"
        limit = _RATE_LIMIT_UPLOAD if is_upload else _RATE_LIMIT_DEFAULT
        now = time.monotonic()
        cutoff = now - 60.0

        with _rate_lock:
            timestamps = _rate_windows[key]
            while timestamps and timestamps[0] < cutoff:
                timestamps.pop(0)
            if len(timestamps) >= limit:
                return JSONResponse(
                    {"detail": "Too many requests. Please slow down."},
                    status_code=429,
                    headers={"Retry-After": "60"},
                )
            timestamps.append(now)

        return await call_next(request)


app = FastAPI(
    title="NEXUS Legal Intelligence Platform",
    description="AI-powered legal document management, entity analysis, and workflow automation",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(TimingMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3100",
        "http://localhost:3201",
        "http://localhost:3000",
        "http://localhost:3847",
        "https://try.grip-web.com",
        "https://free.donnaoss.com",
        "https://donnaoss.com",
        "https://www.donnaoss.com",
        "https://chiefofstaff.pro",
        "https://www.chiefofstaff.pro",
        "https://nexus.grip-web.com",
    ],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount route groups
app.include_router(documents)
app.include_router(routing)
app.include_router(entities)
app.include_router(sops)
app.include_router(idrs)
app.include_router(time_capture)
app.include_router(tasks)
app.include_router(matters)
app.include_router(drafting)
app.include_router(sharepoint)
app.include_router(voice_router)
# W4 / W5 / W6 — Leandro Phase 1 gap closure
app.include_router(summary_router)
app.include_router(search_router)
app.include_router(email_router)
app.include_router(calendar_router)
app.include_router(export_router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "nexus-backend"}
