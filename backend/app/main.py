"""
NEXUS Legal Intelligence Platform — FastAPI Backend
"""

import collections
import json
import logging
import sys
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
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
from app.auth_middleware import AuthRequiredMiddleware  # noqa: E402
from app.routes_auth import router as auth_router  # noqa: E402
from app.routes_calendar import calendar_router  # noqa: E402
from app.routes_drafting import drafting  # noqa: E402
from app.routes_email import email_router  # noqa: E402
from app.routes_export import export_router  # noqa: E402
from app.routes_idr import idrs  # noqa: E402
from app.routes_search import search_router  # noqa: E402
from app.routes_summary import summary_router  # noqa: E402
from services.user_store import UserStore  # noqa: E402

TELEMETRY_LOG = Path(__file__).parent.parent.parent / "data" / "telemetry.jsonl"
TELEMETRY_LOG.parent.mkdir(parents=True, exist_ok=True)
_CORPUS_DIR = Path(__file__).parent.parent.parent / "test_corpus"
_DATA_DIR = Path(__file__).parent.parent.parent / "data"


_CORPUS_SYSTEM_USER_ID = "system-corpus"


def _seed_corpus_if_empty() -> None:
    """Index ``test_corpus/`` into ChromaDB under the system pseudo-user.

    Stamping the seeded chunks with ``user_id="system-corpus"`` means no
    real user ever surfaces them in search (the search filter is
    ``user_id == current_user.id``). Set ``NEXUS_SKIP_CORPUS_SEED=true``
    to skip this step entirely on production deployments.
    """
    import os  # noqa: PLC0415

    if os.environ.get("NEXUS_SKIP_CORPUS_SEED", "").lower() == "true":
        return

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
                user_id=_CORPUS_SYSTEM_USER_ID,
                metadata={
                    "filename": path.name,
                    "document_type": "other",
                    "source": "corpus",
                    "user_id": _CORPUS_SYSTEM_USER_ID,
                },
            )
            logger.info("Indexed corpus file: %s", path.name)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to index %s: %s", path.name, exc)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Tests pre-wire app.state before TestClient enters lifespan;
    # only initialise production defaults when nothing was pre-wired.
    if not hasattr(_app.state, "data_dir"):
        _app.state.data_dir = _DATA_DIR
    if not hasattr(_app.state, "user_store"):
        _app.state.user_store = UserStore(_app.state.data_dir)
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
app.add_middleware(AuthRequiredMiddleware)
_ALLOWED_ORIGINS = [
    "https://free.donnaoss.com",
    "https://donnaoss.com",
    "https://www.donnaoss.com",
    "https://chiefofstaff.pro",
    "https://www.chiefofstaff.pro",
    "https://try.grip-web.com",
    "https://nexus.grip-web.com",
    "http://localhost:3000",
    "http://localhost:3100",
    "http://localhost:3201",
    "http://localhost:3847",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Cookie", "X-Requested-With"],
)


@app.exception_handler(HTTPException)
async def _http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception):
    request_id = str(uuid.uuid4())
    logger.exception("unhandled-error request_id=%s path=%s", request_id, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "request_id": request_id},
    )

# Mount route groups — auth must come first so it can be whitelisted by
# the auth-required middleware that W2 will add.
app.include_router(auth_router)
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
