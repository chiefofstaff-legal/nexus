"""Email routes — voice-to-email parsing and send confirmation.

New module: DO NOT modify routes.py or main.py.
Orchestrator wires email_router via include_router.
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.dependencies import get_async_anthropic_client  # noqa: E402
from services.email_service import EmailService, EmailServiceUnavailable  # noqa: E402
from services.voice_to_email import parse_voice_to_email  # noqa: E402


email_router = APIRouter(prefix="/api/email", tags=["Email"])


class VoiceEmailRequest(BaseModel):
    transcript: str


class SendEmailRequest(BaseModel):
    to: list[str]
    subject: str
    body: str
    cc: list[str] = []


@email_router.post("/voice")
async def voice_to_email_draft(req: VoiceEmailRequest):
    """Parse a voice transcript into an email draft for UI confirmation.

    Does NOT send the email — returns {subject, body, recipient_hint} only.
    """
    client = get_async_anthropic_client()
    draft = await parse_voice_to_email(req.transcript, client)
    return draft


@email_router.post("/send")
async def send_email(req: SendEmailRequest):
    """Send an email via MS Graph.

    Returns 503 when MS Graph credentials are not configured.
    """
    try:
        svc = EmailService()
    except EmailServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    try:
        result = svc.send_email(
            to=req.to,
            subject=req.subject,
            body=req.body,
            cc=req.cc,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"MS Graph send failed: {exc}") from exc
    return result
