"""
Council — OSS stub. The proprietary multi-model council deliberation
pattern lives in `nexus_engine.council` (private).

This stub satisfies imports for callers that reference Council /
CouncilQuery / _parse_vote symbol names, and returns a single-model
result when invoked. It does NOT implement the FADP-aware council
synthesis, devil's advocate, or weighted-vote logic from the NEXUS
tier — see https://github.com/CodeTonight-SA/nexus-engine for the
proprietary implementation.

The OSS fallback returns a single-vote result so downstream code does
not crash; the operator running the OSS clone simply gets the same
quality as a single-model call.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class CouncilQuery(BaseModel):
    """Query envelope for a council deliberation."""

    prompt: str
    context: str = ""
    decision_point: str = "single_model"
    falsification_criterion: str = ""
    metadata: dict = Field(default_factory=dict)


class CouncilVerdict(BaseModel):
    """Synthesised verdict returned by a council deliberation."""

    decision: str
    confidence: float = Field(ge=0.0, le=1.0)
    synthesis_method: str = "single_model"
    votes: list[dict] = Field(default_factory=list)
    reasoning: str = ""
    falsification_criterion: str = ""


def _parse_vote(raw: str) -> dict:
    """Parse a single model's vote from raw text.

    OSS fallback: returns the raw text under `decision` with neutral
    confidence. The proprietary implementation parses structured JSON,
    extracts falsification criterion, normalises labels.
    """
    return {
        "decision": (raw or "").strip(),
        "confidence": 0.5,
        "reasoning": "OSS fallback — single model, no parsing",
        "falsification": "",
    }


class Council:
    """OSS stub of the council deliberation pattern.

    The proprietary nexus_engine.council fans queries to multiple
    providers in parallel and synthesises a unanimous / majority /
    dissenting verdict with mandatory devil's advocate.
    """

    def __init__(self, providers: Optional[list[str]] = None, **kwargs):
        self.providers = providers or ["groq"]

    async def deliberate(self, query: CouncilQuery) -> CouncilVerdict:
        """Single-model deliberation. The NEXUS-tier engine adds the
        multi-provider council + devil's advocate.
        """
        return CouncilVerdict(
            decision="OSS council fallback — install nexus_engine for full deliberation",
            confidence=0.5,
            synthesis_method="single_model",
            votes=[],
            reasoning="OSS fallback: no multi-provider council in the public clone",
        )
