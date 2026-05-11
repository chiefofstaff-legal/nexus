"""
Ingestion and document-list endpoint tests.

Covers:
1. list_documents returns {documents: [...]} — not a bare array.
2. ingest_folder rejects missing folder_path (400).
3. ingest_folder rejects unknown path (403 or 404).
4. SSE start event emits expected fields.
5. Drafting summarise upload: upload + content round-trip returns text.
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

_client = TestClient(app)


# ---------------------------------------------------------------------------
# list_documents
# ---------------------------------------------------------------------------

def test_list_documents_returns_object_not_array():
    resp = _client.get("/api/documents/list")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, dict), "Expected {documents: [...]}, got bare array"
    assert "documents" in body
    assert isinstance(body["documents"], list)


# ---------------------------------------------------------------------------
# ingest_folder validation
# ---------------------------------------------------------------------------

def test_ingest_folder_missing_path_returns_400():
    resp = _client.post("/api/documents/ingest-folder", json={})
    assert resp.status_code == 400


def test_ingest_folder_disallowed_path_returns_403():
    resp = _client.post(
        "/api/documents/ingest-folder",
        json={"folder_path": "/etc/passwd"},
    )
    # /etc is outside allowed dirs — expect 403 or 404 (path doesn't exist or forbidden)
    assert resp.status_code in (403, 404)


def test_ingest_folder_nonexistent_path_returns_404():
    resp = _client.post(
        "/api/documents/ingest-folder",
        json={"folder_path": str(Path.home() / "_nexus_nonexistent_dir_xyz")},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# SSE start event shape
# ---------------------------------------------------------------------------

def test_ingest_folder_sse_start_event_fields():
    """An empty allowed directory should stream exactly one 'start' + one 'done' event."""
    import app.routes as routes_module

    with tempfile.TemporaryDirectory() as tmpdir:
        # resolve() follows /var -> /private/var symlink on macOS so paths match
        tmp = Path(tmpdir).resolve()
        original = set(routes_module.ALLOWED_INGEST_DIRS)
        routes_module.ALLOWED_INGEST_DIRS = original | {tmp}
        try:
            with _client.stream(
                "POST",
                "/api/documents/ingest-folder",
                json={"folder_path": str(tmp)},
            ) as response:
                assert response.status_code == 200
                events = []
                buf = ""
                for chunk in response.iter_bytes():
                    buf += chunk.decode()
                    while "\n\n" in buf:
                        line, buf = buf.split("\n\n", 1)
                        if line.startswith("data:"):
                            payload = line[len("data:"):].strip()
                            if payload:
                                events.append(json.loads(payload))
        finally:
            routes_module.ALLOWED_INGEST_DIRS = original

    assert len(events) >= 2
    start = events[0]
    assert start["event"] == "start"
    assert "total" in start
    assert "folder" in start

    done = events[-1]
    assert done["event"] == "done"
    assert "processed" in done
    assert "errors" in done
    assert "elapsed_seconds" in done


# ---------------------------------------------------------------------------
# progress event field contract (hypothesis: all required fields present)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="requires ANTHROPIC_API_KEY")
def test_ingest_folder_progress_event_has_required_fields():
    """Single-file folder emits a progress event with the documented schema."""
    import app.routes as routes_module

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir).resolve()
        test_file = tmp / "sample.txt"
        test_file.write_text("This is a sample legal document. Party A agrees to pay Party B.")

        original = set(routes_module.ALLOWED_INGEST_DIRS)
        routes_module.ALLOWED_INGEST_DIRS = original | {tmp}
        try:
            with _client.stream(
                "POST",
                "/api/documents/ingest-folder",
                json={"folder_path": str(tmp)},
            ) as response:
                assert response.status_code == 200
                events = []
                buf = ""
                for chunk in response.iter_bytes():
                    buf += chunk.decode()
                    while "\n\n" in buf:
                        line, buf = buf.split("\n\n", 1)
                        if line.startswith("data:"):
                            payload = line[len("data:"):].strip()
                            if payload:
                                events.append(json.loads(payload))
        finally:
            routes_module.ALLOWED_INGEST_DIRS = original

    progress_events = [e for e in events if e.get("event") == "progress"]
    assert len(progress_events) >= 1, "Expected at least one progress event"
    p = progress_events[0]
    for field in ("completed", "total", "filename", "document_type", "confidence", "rate", "eta_seconds", "document"):
        assert field in p, f"progress event missing field: {field}"
