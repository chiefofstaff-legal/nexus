"""
Drafting + Summarisation Routes
===============================

Endpoints for AI template drafting, document summarisation, and
voice-to-draft parsing. Wires the anthropic client from routes.py
(single source) into the pure drafting_service module.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path

from fastapi import APIRouter, HTTPException

# Import resolution matches the sibling routes.py pattern.
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio as _asyncio

from services.drafting_service import (  # noqa: E402
    DraftRequest,
    DraftResponse,
    SummariseRequest,
    VoiceDraftRequest,
    generate_draft,
    list_templates,
    parse_multi_voice_request,
    parse_voice_request,
    summarise_document,
)

from app.dependencies import get_async_anthropic_client  # noqa: E402


drafting = APIRouter(prefix="/api/drafting", tags=["AI Drafting"])


@contextmanager
def _translate_service_errors():
    """Translate drafting_service exceptions into HTTPException.

    ValueError -> 400 (client input fault), RuntimeError -> 502
    (upstream LLM fault). Rule-of-three DRY fix: the same three-line
    block appeared in /generate, /summarise, and /voice-to-draft.
    """
    try:
        yield
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@drafting.get("/templates")
async def get_templates():
    """Return the full template catalogue."""
    return {"templates": list_templates()}


@drafting.post("/generate", response_model=DraftResponse)
async def generate(req: DraftRequest):
    """Generate a draft from the selected template + matter context."""
    client = get_async_anthropic_client()
    with _translate_service_errors():
        return await generate_draft(client, req)


@drafting.post("/summarise")
async def summarise(req: SummariseRequest):
    """Summarise a supplied document text in brief/detailed/action_items."""
    client = get_async_anthropic_client()
    with _translate_service_errors():
        return await summarise_document(client, req.document_text, req.summary_type)


@drafting.post("/voice-to-draft")
async def voice_to_draft(req: VoiceDraftRequest):
    """Parse dictated transcript, then generate a draft in one call.

    Flow: transcript -> CCH parse -> DraftRequest -> CCH draft.
    Returns both the parse plan (for UI feedback) and the draft.
    """
    client = get_async_anthropic_client()
    with _translate_service_errors():
        plan = await parse_voice_request(client, req.transcript)
        draft = await generate_draft(
            client,
            DraftRequest(
                template_id=plan.template_id,
                matter_name=plan.matter_name,
                client_name=plan.client_name,
                key_facts=plan.key_facts,
                additional_instructions=plan.additional_instructions,
            ),
        )
        return {"plan": plan.model_dump(), "draft": draft.model_dump()}


@drafting.post("/voice-to-draft-multi")
async def voice_to_draft_multi(req: VoiceDraftRequest):
    """Parse a transcript containing one or more drafting intents, generate all drafts.

    Flow: transcript -> CCH multi-intent parse -> parallel generate_draft calls.
    Returns a list of {plan, draft} objects — one per detected intent.
    Compound example: "Draft an NDA for Alpine Corp and a billing statement for Müller."
    """
    client = get_async_anthropic_client()
    with _translate_service_errors():
        plans = await parse_multi_voice_request(client, req.transcript)
        drafts = await _asyncio.gather(*[
            generate_draft(
                client,
                DraftRequest(
                    template_id=p.template_id,
                    matter_name=p.matter_name,
                    client_name=p.client_name,
                    key_facts=p.key_facts,
                    additional_instructions=p.additional_instructions,
                ),
            )
            for p in plans
        ])
        return {
            "intent_count": len(plans),
            "results": [
                {"plan": p.model_dump(), "draft": d.model_dump()}
                for p, d in zip(plans, drafts)
            ],
        }
