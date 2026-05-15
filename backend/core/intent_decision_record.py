"""
Intent Decision Record (IDR) — typed schema for auditable AI decisions.

An IDR captures what the AI decided, why, how confident it was, which council
members voted how, and what would falsify the decision. IDRs are appended to
a tamper-evident HMAC chain (see ``idr_store.IDRStore``) so Swiss FADP
audit requirements can be satisfied with legal-grade evidence.

Popperian falsification is built in: every IDR carries an explicit
``falsification_criterion`` stating what observation would prove the decision
wrong, and a ``falsification_status`` that starts ``pending`` and resolves to
``confirmed`` or ``falsified`` when ground truth becomes available.
"""

import hashlib
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class DecisionPoint(str, Enum):
    """The decision surface the IDR belongs to.

    ``FALSIFICATION_REVIEW`` is a special self-referential decision
    point: a review IDR's ``metadata.reviews_sequence`` points at the
    IDR being reviewed, and its ``decision`` carries the reviewer's
    verdict (confirmed | refuted | inconclusive). The chain remains
    append-only — the reviewed IDR is never mutated; its effective
    status is derived by walking forward for any review IDRs that
    target it.
    """

    SENSITIVITY_CLASSIFICATION = "sensitivity_classification"
    LLM_ROUTING = "llm_routing"
    DOCUMENT_INGESTION = "document_ingestion"
    DOCUMENT_CLASSIFICATION = "document_classification"
    VISION_EXTRACTION = "vision_extraction"
    VISION_OCR_PROVIDER = "vision_ocr_provider"
    ENTITY_EXTRACTION = "entity_extraction"
    SEMANTIC_LABELLING = "semantic_labelling"
    SEMANTIC_SEARCH = "semantic_search"
    REDACTION_POLICY = "redaction_policy"
    TIME_ENTRY_PARSE = "time_entry_parse"
    TASK_DELEGATION_PARSE = "task_delegation_parse"
    FALSIFICATION_REVIEW = "falsification_review"


class FalsificationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    FALSIFIED = "falsified"
    INCONCLUSIVE = "inconclusive"


class SynthesisMethod(str, Enum):
    SINGLE_MODEL = "single_model"
    MAJORITY_VOTE = "majority_vote"
    WEIGHTED_VOTE = "weighted_vote"
    DEVILS_ADVOCATE = "devils_advocate"
    DETERMINISTIC = "deterministic"


class CouncilVote(BaseModel):
    """A single LLM's vote in a multi-model council."""

    model: str = Field(..., description="Model identifier, e.g. claude-haiku-4-5-20251001")
    provider: str = Field(..., description="anthropic | groq | ollama")
    decision: str = Field(..., description="The raw decision/label this model produced")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Self-reported or derived 0..1 confidence")
    reasoning: str = Field(default="", description="Short natural-language reasoning from the model")
    falsification: str = Field(
        default="",
        description=(
            "Document-specific observation this model says would refute its "
            "own decision. When present, the council synthesis prefers a "
            "majority-vote falsification over the query's static default."
        ),
    )
    latency_ms: float = Field(default=0.0, ge=0.0)
    error: Optional[str] = Field(default=None, description="If the call failed, why")


class IntentDecisionRecord(BaseModel):
    """One append-only record of an AI decision with full auditable context."""

    idr_id: str = Field(default_factory=lambda: f"idr-{uuid.uuid4().hex[:12]}")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    decision_point: DecisionPoint

    input_hash: str = Field(..., description="sha256 of the input (doc, prompt, etc.) for lookup + dedup")
    input_summary: str = Field(..., max_length=500, description="Short human-readable description of input")

    decision: str = Field(..., description="The final decision string (e.g. 'confidential')")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Synthesised confidence, honest")
    confidence_rationale: str = Field(
        default="",
        description="Why this confidence level, e.g. '2/3 council agreement on label'",
    )
    reasoning: str = Field(default="", description="Synthesised reasoning summary")

    council_votes: list[CouncilVote] = Field(default_factory=list)
    synthesis_method: SynthesisMethod = Field(default=SynthesisMethod.SINGLE_MODEL)

    falsification_criterion: str = Field(
        ...,
        description="Popper criterion: what observation would prove this decision wrong",
    )
    falsification_status: FalsificationStatus = Field(default=FalsificationStatus.PENDING)
    falsification_evidence: Optional[str] = Field(default=None)

    metadata: dict = Field(default_factory=dict, description="Per-decision-point flexible fields")

    @staticmethod
    def hash_input(content: str | bytes) -> str:
        """Compute the canonical input_hash for a given string or bytes payload."""
        if isinstance(content, str):
            content = content.encode("utf-8")
        return "sha256:" + hashlib.sha256(content).hexdigest()
