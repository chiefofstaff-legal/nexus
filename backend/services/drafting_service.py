"""
Drafting Service
================

Template-based legal drafting + document summarisation for
ChiefOfStaff.pro. "Call up the most appropriate template and apply
matter-specific changes."

Design notes
------------
- Templates are a dispatch dict keyed by ``template_id`` (no if/elif chains).
- All LLM calls use ``claude-haiku-4-5-20251001`` (CCH) — fast, cost-effective,
  and sufficient for template-based legal drafting in a POC context.
- Summaries use the same model; Haiku handles short deterministic outputs well.
- All callers go through ``_call_anthropic`` so the wiring matches the
  existing ``llm_router._call_anthropic`` pattern.
- British English throughout user-facing strings and LLM prompts.
"""

from __future__ import annotations

import json
import re
from typing import Literal, Optional

from pydantic import BaseModel, Field


# --- Models -----------------------------------------------------------------

CCH = "claude-haiku-4-5-20251001"
DRAFTING_MODEL = CCH
SUMMARY_MODEL = CCH

SUMMARY_TYPES = ("brief", "detailed", "action_items")


class DraftTemplate(BaseModel):
    id: str
    name: str
    description: str
    template_type: str
    base_prompt: str


class DraftRequest(BaseModel):
    template_id: str
    matter_name: str = ""
    client_name: str = ""
    key_facts: list[str] = Field(default_factory=list)
    additional_instructions: str = ""


class DraftResponse(BaseModel):
    template_id: str
    template_name: str
    matter_name: str
    client_name: str
    draft_text: str
    word_count: int
    estimated_reading_minutes: float
    model_used: str


class SummariseRequest(BaseModel):
    document_text: str
    summary_type: Literal["brief", "detailed", "action_items"] = "brief"


# --- Template catalogue -----------------------------------------------------

# British English, Swiss-law aware. Each base_prompt instructs the model on
# structural expectations; matter-specific context is appended at call time.
_TEMPLATES: dict[str, DraftTemplate] = {
    "contract": DraftTemplate(
        id="contract",
        name="Service Agreement",
        description="Standard service agreement for a Swiss law firm.",
        template_type="contract",
        base_prompt=(
            "Draft a standard professional services agreement governed by "
            "Swiss law. Use clear, plain British English. Include: parties, "
            "recitals, scope of services, fees and payment terms, "
            "confidentiality, data protection under the Swiss FADP, "
            "liability cap, termination, governing law (Switzerland) and "
            "jurisdiction (competent courts of the canton). Use numbered "
            "clauses and short paragraphs."
        ),
    ),
    "brief": DraftTemplate(
        id="brief",
        name="Legal Brief",
        description="Legal brief in Swiss court format.",
        template_type="brief",
        base_prompt=(
            "Draft a legal brief in the structure expected by Swiss courts. "
            "Sections: Heading (court, parties, case reference), Statement "
            "of Facts, Legal Question, Applicable Law (with citations to "
            "the Swiss Civil Code / CO / CPC / relevant cantonal statute), "
            "Argument, Prayer for Relief. British English, formal register."
        ),
    ),
    "nda": DraftTemplate(
        id="nda",
        name="Non-Disclosure Agreement",
        description="Bilateral NDA under Swiss law.",
        template_type="nda",
        base_prompt=(
            "Draft a bilateral (mutual) non-disclosure agreement governed "
            "by Swiss law. Include: definition of confidential information, "
            "obligations of the receiving party, permitted disclosures, "
            "term (typically 3-5 years), return/destruction, injunctive "
            "relief, governing law and jurisdiction. Keep it under two "
            "pages where possible. British English."
        ),
    ),
    "motion": DraftTemplate(
        id="motion",
        name="Court Motion",
        description="Motion to court with standard Swiss procedural headers.",
        template_type="motion",
        base_prompt=(
            "Draft a formal motion to a Swiss court. Include: court "
            "heading, case reference, parties, motion caption, grounds "
            "(factual and legal, with statute citations), relief sought, "
            "evidence list, signature block. British English, formal."
        ),
    ),
    "letter": DraftTemplate(
        id="letter",
        name="Professional Letter",
        description="Professional correspondence from a law firm.",
        template_type="letter",
        base_prompt=(
            "Draft a professional letter on behalf of a Swiss law firm. "
            "Include: sender block, recipient block, date, subject line, "
            "salutation, body paragraphs (concise, one idea per paragraph), "
            "closing, signature block. British English, courteous and firm."
        ),
    ),
    "summary": DraftTemplate(
        id="summary",
        name="Case Summary",
        description="Case summary for client update.",
        template_type="summary",
        base_prompt=(
            "Draft a client-facing case summary. Sections: Where we are "
            "today, What happened since last update, Next steps, Key "
            "risks, What we need from the client. British English, plain "
            "language suitable for a non-lawyer reader."
        ),
    ),
    "invoice_letter": DraftTemplate(
        id="invoice_letter",
        name="Billing Statement",
        description="Billing statement with itemised time entries.",
        template_type="invoice_letter",
        base_prompt=(
            "Draft a billing statement cover letter accompanying an "
            "itemised invoice. Include: matter reference, period covered, "
            "summary of work done, total hours, hourly rate, total fees "
            "(CHF), expenses, VAT note, payment terms (30 days), payment "
            "details placeholder. British English, professional."
        ),
    ),
    "custody_petition": DraftTemplate(
        id="custody_petition",
        name="Custody Petition",
        description="Family law custody petition framework.",
        template_type="custody_petition",
        base_prompt=(
            "Draft a custody petition under Swiss family law. Sections: "
            "Court heading, parties (petitioner, respondent, child(ren) "
            "with date of birth), factual background, current custody "
            "arrangement, proposed arrangement, best-interests analysis "
            "(Art. 298 CC), prayer for relief. British English, formal."
        ),
    ),
}


# --- Public template API ----------------------------------------------------

def list_templates() -> list[dict]:
    """Return the full template catalogue as plain dicts."""
    return [t.model_dump() for t in _TEMPLATES.values()]


def get_template(template_id: str) -> Optional[DraftTemplate]:
    return _TEMPLATES.get(template_id)


# --- Prompt composition -----------------------------------------------------

def _compose_matter_block(req: DraftRequest) -> str:
    """Render the matter-specific instruction block appended to every draft.

    Pure function — no side effects, no I/O. Keeps ``generate_draft`` short.
    """
    parts: list[str] = []
    if req.matter_name:
        parts.append(f"Matter: {req.matter_name}")
    if req.client_name:
        parts.append(f"Client: {req.client_name}")
    if req.key_facts:
        facts = "\n".join(f"- {f}" for f in req.key_facts if f.strip())
        if facts:
            parts.append(f"Key facts to incorporate:\n{facts}")
    if req.additional_instructions.strip():
        parts.append(
            f"Additional instructions:\n{req.additional_instructions.strip()}"
        )
    if not parts:
        return ""
    return "\n\n---\n\nMatter context\n" + "\n\n".join(parts)


def _reading_minutes(text: str) -> float:
    """200 wpm is the Swiss legal reading benchmark used in the spec."""
    words = len(text.split())
    return round(words / 200.0, 1) if words else 0.0


# --- LLM call wrappers ------------------------------------------------------

async def _call_anthropic(
    client,
    model: str,
    system: str,
    prompt: str,
    max_tokens: int = 2500,
) -> str:
    """Async Anthropic call — uses AsyncAnthropic so the FastAPI event loop
    is not blocked during the network round-trip.

    Raised exceptions propagate to the route handler which converts them
    to HTTP 502s. No retry, no cascade — drafting is operator-initiated
    and a clean error message is better than silent degraded output.
    """
    if client is None:
        raise RuntimeError(
            "Anthropic client unavailable. Set ANTHROPIC_API_KEY."
        )
    try:
        response = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text
    except Exception as exc:
        raise RuntimeError(f"Anthropic API error: {exc}") from exc


# --- Public generation API --------------------------------------------------

async def generate_draft(client, req: DraftRequest) -> DraftResponse:
    """Generate a draft from the selected template + matter context.

    ``client`` is an ``anthropic.AsyncAnthropic()`` instance injected by
    the route handler to keep this module pure and testable.
    """
    template = get_template(req.template_id)
    if template is None:
        raise ValueError(f"unknown template_id: {req.template_id}")

    system = (
        "You are a senior Swiss legal drafting assistant working for a "
        "boutique law firm. Produce ready-to-review drafts in British "
        "English. Be precise, avoid hedging, use numbered clauses where "
        "appropriate, and keep Swiss-law conventions."
    )
    prompt = template.base_prompt + _compose_matter_block(req)

    draft_text = await _call_anthropic(
        client, DRAFTING_MODEL, system, prompt, max_tokens=2500
    )

    return DraftResponse(
        template_id=template.id,
        template_name=template.name,
        matter_name=req.matter_name,
        client_name=req.client_name,
        draft_text=draft_text,
        word_count=len(draft_text.split()),
        estimated_reading_minutes=_reading_minutes(draft_text),
        model_used=DRAFTING_MODEL,
    )


# --- Summarisation ----------------------------------------------------------

_SUMMARY_INSTRUCTIONS: dict[str, str] = {
    "brief": (
        "Produce a brief summary in 3-4 sentences. British English. "
        "Capture the document's purpose, parties and key outcome only."
    ),
    "detailed": (
        "Produce a detailed structured summary. Sections: Purpose, "
        "Parties, Key Terms, Obligations, Dates, Risks. British English, "
        "bullet points where natural."
    ),
    "action_items": (
        "Extract action items only. Return a numbered list; each item "
        "starts with a verb, specifies the responsible party if known, "
        "and the deadline if stated. British English. If no actions are "
        "present, return 'No explicit action items identified.'"
    ),
}


async def summarise_document(
    client, document_text: str, summary_type: str = "brief"
) -> dict:
    """Summarise a supplied document text in one of three modes.

    Returns a dict (not a Pydantic model) so the FastAPI route can pass
    it through directly without another conversion layer.
    """
    if summary_type not in _SUMMARY_INSTRUCTIONS:
        raise ValueError(
            f"summary_type must be one of {SUMMARY_TYPES}, got {summary_type!r}"
        )
    text = (document_text or "").strip()
    if not text:
        raise ValueError("document_text is empty")

    system = (
        "You are a Swiss legal document summariser. Accurate, concise, "
        "British English. Never fabricate facts beyond the supplied text."
    )
    prompt = (
        f"{_SUMMARY_INSTRUCTIONS[summary_type]}\n\n"
        f"Document text (truncated if long):\n\n{text[:18000]}"
    )

    summary = await _call_anthropic(
        client, SUMMARY_MODEL, system, prompt, max_tokens=800
    )
    return {
        "summary_type": summary_type,
        "summary": summary,
        "word_count": len(summary.split()),
        "source_chars": len(text),
        "model_used": SUMMARY_MODEL,
    }


# --- Voice-to-draft parsing -------------------------------------------------

class VoiceDraftRequest(BaseModel):
    transcript: str


class VoiceDraftPlan(BaseModel):
    template_id: str
    matter_name: str = ""
    client_name: str = ""
    key_facts: list[str] = Field(default_factory=list)
    additional_instructions: str = ""
    rationale: str = ""


_VOICE_PARSE_SYSTEM = (
    "You parse short dictated instructions from a Swiss lawyer into a "
    "structured drafting plan. Always respond with valid JSON matching "
    "the schema supplied. British English."
)


def _voice_parse_prompt(transcript: str, template_ids: list[str]) -> str:
    """Build the parse prompt — separated so it's unit-testable."""
    return (
        "Parse this dictated request into a drafting plan.\n\n"
        f"Available template_id values: {template_ids}\n\n"
        "Return ONLY JSON with keys: template_id (str, required), "
        "matter_name (str), client_name (str), key_facts (list of str), "
        "additional_instructions (str), rationale (str, one sentence "
        "explaining the template choice).\n\n"
        f"Transcript:\n{transcript.strip()}"
    )


async def parse_voice_request(client, transcript: str) -> VoiceDraftPlan:
    """Use Haiku to auto-pick a template and extract matter metadata.

    Kept <30 lines: delegates JSON parsing to a helper so the happy
    path stays readable.
    """
    if not transcript or not transcript.strip():
        raise ValueError("transcript is empty")

    template_ids = list(_TEMPLATES.keys())
    raw = await _call_anthropic(
        client,
        SUMMARY_MODEL,
        _VOICE_PARSE_SYSTEM,
        _voice_parse_prompt(transcript, template_ids),
        max_tokens=600,
    )
    return _parse_voice_json(raw, template_ids)


def _parse_voice_json(raw: str, template_ids: list[str]) -> VoiceDraftPlan:
    """Extract the JSON blob from the model output and validate it."""
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError(f"no JSON found in voice-parse output: {raw[:200]}")

    data = json.loads(match.group(0))
    tid = data.get("template_id", "")
    if tid not in template_ids:
        # Fallback: LLM returned something off-catalogue — default to letter
        # (a safe, non-destructive choice) and surface the issue in rationale.
        data["template_id"] = "letter"
        data["rationale"] = (
            f"Requested template '{tid}' is not in catalogue; "
            "defaulted to 'letter'."
        )
    return VoiceDraftPlan(**data)


# --- Multi-intent voice parsing ---------------------------------------------

_MULTI_INTENT_SYSTEM = (
    "You detect and parse multiple distinct drafting intents from a single "
    "dictated instruction from a Swiss lawyer. Always respond with a JSON "
    "array even if there is only one intent. British English."
)


def _multi_intent_prompt(transcript: str, template_ids: list[str]) -> str:
    """Build the multi-intent parse prompt — separated so it is unit-testable."""
    return (
        "Parse this dictated request into one or more drafting plans.\n\n"
        f"Available template_id values: {template_ids}\n\n"
        "Return ONLY a JSON array where each element has keys: "
        "template_id (str, required), matter_name (str), client_name (str), "
        "key_facts (list of str), additional_instructions (str), "
        "rationale (str, one sentence explaining the template choice).\n\n"
        "If a single document is requested, return a one-element array.\n"
        f"Transcript:\n{transcript.strip()}"
    )


def _parse_multi_intent_json(raw: str, template_ids: list[str]) -> list[VoiceDraftPlan]:
    """Extract the JSON array from the model output and validate each plan.

    Uses json.loads on the stripped raw string first (handles LLM output that
    starts directly with `[`). Falls back to object-level search when the model
    wraps the array in prose, then wraps a bare object as a single-element list.
    Never uses a greedy bracket regex — that falsely matches inner `[]` arrays.
    """
    stripped = raw.strip()

    # Fast path: the model returned a clean JSON array
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, list):
            data_list = parsed
        else:
            # Single object returned — wrap it
            return [_parse_voice_json(raw, template_ids)]
    except (json.JSONDecodeError, ValueError):
        # Fallback: find the first `[` ... last `]` block in prose output
        start = stripped.find("[")
        end = stripped.rfind("]")
        if start == -1 or end == -1 or end <= start:
            return [_parse_voice_json(raw, template_ids)]
        try:
            data_list = json.loads(stripped[start:end + 1])
            if not isinstance(data_list, list):
                return [_parse_voice_json(raw, template_ids)]
        except (json.JSONDecodeError, ValueError):
            return [_parse_voice_json(raw, template_ids)]

    plans: list[VoiceDraftPlan] = []
    for item in data_list:
        tid = item.get("template_id", "")
        if tid not in template_ids:
            item["template_id"] = "letter"
            item["rationale"] = (
                f"Requested template '{tid}' not in catalogue; defaulted to 'letter'."
            )
        plans.append(VoiceDraftPlan(**item))
    return plans or [VoiceDraftPlan(template_id="letter", rationale="No intents parsed; defaulted to letter.")]


async def parse_multi_voice_request(client, transcript: str) -> list[VoiceDraftPlan]:
    """Parse one transcript into ≥1 VoiceDraftPlans using CCH.

    Returns a list so the caller can fan out generate_draft calls in parallel.
    """
    if not transcript or not transcript.strip():
        raise ValueError("transcript is empty")

    template_ids = list(_TEMPLATES.keys())
    raw = await _call_anthropic(
        client,
        CCH,
        _MULTI_INTENT_SYSTEM,
        _multi_intent_prompt(transcript, template_ids),
        max_tokens=800,
    )
    return _parse_multi_intent_json(raw, template_ids)
