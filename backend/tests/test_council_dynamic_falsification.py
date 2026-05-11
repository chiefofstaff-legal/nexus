"""
W1.5 — Dynamic falsification criterion synthesis tests.

The council now expects each model to supply a document-specific
`falsification` string in its JSON response. The orchestrator must:

1. Parse the falsification field out of each vote.
2. Synthesise a per-document criterion that prefers supporting votes.
3. Thread that synthesised criterion into the IDR, overriding the
   query's static fallback.
4. Fall back to the static query.falsification_criterion iff every
   supporting vote supplied an empty string (e.g. all models errored
   or a malformed response omitted the field).

These tests verify the wiring without hitting real providers.
"""

from unittest.mock import AsyncMock

import pytest

from core.intent_decision_record import (
    CouncilVote,
    DecisionPoint,
    IntentDecisionRecord,
    SynthesisMethod,
)
from services.council import Council, CouncilQuery, _parse_vote


_STATIC_FALLBACK = "STATIC-FALLBACK-CRITERION"


def _query() -> CouncilQuery:
    return CouncilQuery(
        decision_point=DecisionPoint.SENSITIVITY_CLASSIFICATION,
        system_prompt="classify",
        user_prompt="document body",
        input_hash=IntentDecisionRecord.hash_input("document body"),
        input_summary="test doc",
        allowed_decisions=["public", "internal", "confidential"],
        falsification_criterion=_STATIC_FALLBACK,
        metadata={},
    )


class _FakeStore:
    """In-memory stand-in for IDRStore.append."""

    def __init__(self):
        self.entries: list = []

    def append(self, idr: IntentDecisionRecord) -> dict:
        self.entries.append(idr)
        d = idr.model_dump()
        d["sequence"] = len(self.entries)
        return d


def test_parse_vote_extracts_falsification_field():
    """Strict JSON parser pulls the new field without breaking old callers."""
    raw = (
        '{"decision": "internal", "confidence": 0.82, '
        '"reasoning": "document mentions named individuals X, Y, Z", '
        '"falsification": "A reviewer who finds X, Y, Z are public '
        'figures would assign public"}'
    )
    decision, confidence, reasoning, falsification = _parse_vote(
        raw, ["public", "internal", "confidential"]
    )
    assert decision == "internal"
    assert confidence == 0.82
    assert "named individuals" in reasoning
    assert "public figures" in falsification


def test_parse_vote_missing_falsification_returns_empty_string():
    """Legacy responses without the field degrade gracefully."""
    raw = '{"decision": "public", "confidence": 0.9, "reasoning": "generic"}'
    decision, confidence, reasoning, falsification = _parse_vote(
        raw, ["public", "internal", "confidential"]
    )
    assert decision == "public"
    assert falsification == ""


@pytest.mark.asyncio
async def test_council_threads_dynamic_criterion_into_idr():
    """When supporting votes supply falsifications, the IDR carries
    the synthesised criterion rather than the static fallback."""
    store = _FakeStore()
    council = Council(idr_store=store, async_anthropic_client=object())

    # Skip real network — inject votes directly.
    council._ask_anthropic = AsyncMock(
        return_value=CouncilVote(
            model="claude-haiku-4-5-20251001",
            provider="anthropic",
            decision="internal",
            confidence=0.85,
            reasoning="Named individuals L, D, R cited; no SSN or health data",
            falsification=(
                "A reviewer finds that L, D, R are publicly listed directors "
                "OR finds FADP Article 5 particularly-sensitive categories"
            ),
            latency_ms=150.0,
        )
    )
    council._ask_groq = AsyncMock(
        return_value=CouncilVote(
            model="llama-3.3-70b-versatile",
            provider="groq",
            decision="internal",
            confidence=0.75,
            reasoning="Contains proper nouns and an organisation name",
            falsification=(
                "A reviewer identifies the org as a public sector body, "
                "making this public record"
            ),
            latency_ms=300.0,
        )
    )

    result = await council.deliberate(_query())

    assert result.decision == "internal"
    # The stored IDR's criterion MUST come from the synthesised council
    # falsification, not the static fallback.
    stored = store.entries[0]
    assert _STATIC_FALLBACK not in stored.falsification_criterion
    assert "publicly listed directors" in stored.falsification_criterion
    assert "public sector body" in stored.falsification_criterion
    # Both provider prefixes should appear for per-vote attribution
    assert "anthropic:" in stored.falsification_criterion
    assert "groq:" in stored.falsification_criterion


@pytest.mark.asyncio
async def test_council_falls_back_when_no_vote_supplies_falsification():
    """If every model omits the field, the IDR uses the static fallback."""
    store = _FakeStore()
    council = Council(idr_store=store, async_anthropic_client=object())

    council._ask_anthropic = AsyncMock(
        return_value=CouncilVote(
            model="m", provider="anthropic", decision="public",
            confidence=0.9, reasoning="looks clean",
            falsification="",  # model didn't supply
            latency_ms=100.0,
        )
    )
    council._ask_groq = AsyncMock(
        return_value=CouncilVote(
            model="g", provider="groq", decision="public",
            confidence=0.85, reasoning="no PII detected",
            falsification="",
            latency_ms=200.0,
        )
    )

    await council.deliberate(_query())

    stored = store.entries[0]
    assert stored.falsification_criterion == _STATIC_FALLBACK


@pytest.mark.asyncio
async def test_council_uses_dissent_criteria_when_supporting_votes_silent():
    """Dissent criteria are still useful context — if nobody else spoke."""
    store = _FakeStore()
    council = Council(idr_store=store, async_anthropic_client=object())

    # Anthropic (supporting majority) supplies no criterion
    council._ask_anthropic = AsyncMock(
        return_value=CouncilVote(
            model="m", provider="anthropic", decision="internal",
            confidence=0.8, reasoning="internal-ish",
            falsification="",
            latency_ms=100.0,
        )
    )
    # Groq dissents AND supplies a criterion
    council._ask_groq = AsyncMock(
        return_value=CouncilVote(
            model="g", provider="groq", decision="confidential",
            confidence=0.7, reasoning="I see enumerated PII",
            falsification="A reviewer confirms the IDs are test fixtures",
            latency_ms=200.0,
        )
    )

    await council.deliberate(_query())

    stored = store.entries[0]
    assert stored.decision == "internal"  # majority wins
    # Synthesis should surface the dissent criterion since majority was silent
    assert "test fixtures" in stored.falsification_criterion
    assert "dissent" in stored.falsification_criterion.lower()
    assert stored.synthesis_method == SynthesisMethod.DEVILS_ADVOCATE
