"""Summary routes — versioned matter summaries.

Deliberately NOT wired into main.py here; the orchestrator adds
``app.include_router(summary_router)`` in a single integration commit.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.dependencies import get_async_anthropic_client
from services.matter_service import MatterStore
from services.summary_service import SummaryStore
from services.summary_generator import regenerate

summary_router = APIRouter(prefix="/api/matters", tags=["Summary"])

_matter_store = MatterStore()
_summary_store = SummaryStore()


def _require_matter(matter_id: str) -> None:
    """Raise 404 if the matter does not exist."""
    if _matter_store.get(matter_id) is None:
        raise HTTPException(status_code=404, detail=f"Matter {matter_id!r} not found")


@summary_router.get("/{matter_id}/summary")
async def get_or_generate_summary(matter_id: str):
    """Return the latest snapshot, or trigger generation if none exists."""
    _require_matter(matter_id)
    snapshot = _summary_store.get_latest(matter_id)
    if snapshot is not None:
        return snapshot
    # No snapshot yet — generate one (soft-fail: returns placeholder on LLM error).
    client = get_async_anthropic_client()
    return await regenerate(matter_id, client, _matter_store, _summary_store)


@summary_router.get("/{matter_id}/summary/{version_id}")
async def get_summary_version(matter_id: str, version_id: int):
    """Return a specific snapshot version."""
    _require_matter(matter_id)
    snapshot = _summary_store.get_version(matter_id, version_id)
    if snapshot is None:
        raise HTTPException(
            status_code=404,
            detail=f"Version {version_id} not found for matter {matter_id!r}",
        )
    return snapshot


@summary_router.post("/{matter_id}/summary/regenerate")
async def force_regenerate_summary(matter_id: str):
    """Force a new summary generation regardless of existing snapshots."""
    _require_matter(matter_id)
    client = get_async_anthropic_client()
    return await regenerate(matter_id, client, _matter_store, _summary_store)
