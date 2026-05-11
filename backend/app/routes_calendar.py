"""Calendar routes — voice-to-event parsing and MS Graph event creation.

New module: DO NOT modify routes.py or main.py.
Orchestrator wires calendar_router via include_router.
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.dependencies import get_async_anthropic_client  # noqa: E402
from services.calendar_service import CalendarService, CalendarServiceUnavailable  # noqa: E402
from services.voice_to_event import parse_voice_to_event  # noqa: E402


calendar_router = APIRouter(prefix="/api/calendar", tags=["Calendar"])


class VoiceEventRequest(BaseModel):
    transcript: str


class CreateEventRequest(BaseModel):
    title: str
    start_iso: str
    end_iso: str
    attendees: list[str] = []
    location: str = ""
    body: str = ""


@calendar_router.post("/voice")
async def voice_to_event_draft(req: VoiceEventRequest):
    """Parse a voice transcript into a calendar event draft for UI confirmation.

    Does NOT create the event — returns {title, start_iso, end_iso, attendees, location}.
    """
    client = get_async_anthropic_client()
    draft = await parse_voice_to_event(req.transcript, client)
    return draft


@calendar_router.post("/events")
async def create_event(req: CreateEventRequest):
    """Create a calendar event in MS Graph.

    Returns 503 when MS Graph credentials are not configured.
    """
    try:
        svc = CalendarService()
    except CalendarServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    try:
        result = svc.create_event(
            title=req.title,
            start=req.start_iso,
            end=req.end_iso,
            attendees=req.attendees,
            location=req.location,
            body=req.body,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"MS Graph event creation failed: {exc}") from exc
    return result
