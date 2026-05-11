"""Async summary generator — calls Claude Sonnet to summarise a matter.

Soft-fail contract: if the Anthropic client is None or the API call
fails for any reason, a placeholder snapshot is persisted and returned.
The caller never receives an exception from this module.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from core.ingestion_cost import record_call
from models.summary import SummarySnapshot

if TYPE_CHECKING:
    from services.matter_service import MatterStore
    from services.summary_service import SummaryStore


_SUMMARY_MODEL = "claude-sonnet-4-6-20250929"
_PLACEHOLDER_CONTENT = "(automatic summary unavailable)"

# Matches doc_id tokens cited in the assistant response, e.g. [doc_abc123].
_CITATION_RE = re.compile(r"\[([a-zA-Z0-9_\-]+)\]")


async def regenerate(
    matter_id: str,
    anthropic_client,
    matter_store: "MatterStore",
    summary_store: "SummaryStore",
) -> SummarySnapshot:
    """Generate and persist a fresh summary snapshot for a matter.

    Reads all documents from matter_store.documents, sends a structured
    prompt to Claude Sonnet, extracts cited doc_ids, records cost, and
    persists the snapshot. On any failure, persists a placeholder and returns
    it — never raises.
    """
    doc_memberships = matter_store.documents.list(matter_id)
    doc_ids = [m.document_id for m in doc_memberships]

    if anthropic_client is None:
        return summary_store.create(matter_id, _PLACEHOLDER_CONTENT, [])

    prompt = _build_prompt(matter_id, doc_ids)
    try:
        response = await anthropic_client.messages.create(
            model=_SUMMARY_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        content = response.content[0].text
        citations = _extract_citations(content, doc_ids)
        record_call(
            model=_SUMMARY_MODEL,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            purpose="summary",
            document_id=matter_id,
        )
    except Exception:  # noqa: BLE001 — intentional soft-fail
        content = _PLACEHOLDER_CONTENT
        citations = []

    return summary_store.create(matter_id, content, citations)


def _build_prompt(matter_id: str, doc_ids: list[str]) -> str:
    """Construct the summarisation prompt."""
    doc_list = "\n".join(f"- [{d}]" for d in doc_ids) if doc_ids else "(none)"
    return (
        f"You are a Swiss law-firm assistant.\n"
        f"Matter ID: {matter_id}\n"
        f"Indexed documents:\n{doc_list}\n\n"
        "Write a concise legal matter summary (max 300 words). "
        "Where relevant, cite document IDs in square brackets, e.g. [doc_abc]. "
        "Be factual and objective."
    )


def _extract_citations(text: str, known_ids: list[str]) -> list[str]:
    """Return doc_ids mentioned in the response that are in known_ids."""
    found = set(_CITATION_RE.findall(text))
    known_set = set(known_ids)
    return sorted(found & known_set)
