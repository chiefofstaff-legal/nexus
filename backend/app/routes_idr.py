"""
IDR HTTP endpoints — list / lookup / verify / review Intent Decision Records.

Kept in its own module so the existing ``routes.py`` is untouched. Main
application wires this in alongside the other routers.
"""

import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.auth import get_current_user  # noqa: E402
from core.idr_store import IDRStore  # noqa: E402
from core.intent_decision_record import (  # noqa: E402
    DecisionPoint,
    IntentDecisionRecord,
    SynthesisMethod,
)
from models.user import User  # noqa: E402

_DATA_DIR = Path.home() / "nexus-poc" / "data"
_store = IDRStore(_DATA_DIR)

idrs = APIRouter(prefix="/api/idrs", tags=["idrs"])


_REVIEW_VERDICTS = {"confirmed", "refuted", "inconclusive"}


class ReviewRequest(BaseModel):
    status: str = Field(
        ...,
        description="One of: confirmed, refuted, inconclusive",
    )
    reviewer_id: str = Field(..., min_length=1, max_length=120)
    reviewer_label: Optional[str] = Field(
        default=None,
        description=(
            "For refuted reviews, the label the reviewer would have assigned. "
            "Confirms the disagreement concretely and is the Popperian evidence "
            "for the refutation."
        ),
    )
    notes: str = Field(default="", max_length=4000)


def _belongs_to(entry: dict, user_id: str) -> bool:
    """True iff the IDR was written under ``user_id``'s session.

    Legacy IDRs (pre-multi-tenancy) have no ``tenant_id`` and are
    filtered out — they belonged to the shared single-tenant world and
    should not surface to any new account.
    """
    meta = entry.get("metadata") or {}
    return meta.get("tenant_id") == user_id


def _enrich_with_effective_status(entry: dict) -> dict:
    """Overlay ``effective_status`` and the latest review onto the entry.

    The underlying ``falsification_status`` field on the original IDR
    stays ``pending`` forever — the chain is append-only, so we never
    mutate it. Readers see the effective status derived by walking
    forward through review IDRs that target this sequence.
    """
    effective, latest_review = _store.effective_status(entry)
    enriched = dict(entry)
    enriched["effective_falsification_status"] = effective
    if latest_review is not None:
        enriched["latest_review"] = {
            "sequence": latest_review.get("sequence"),
            "timestamp": latest_review.get("timestamp"),
            "reviewer_id": (latest_review.get("metadata") or {}).get("reviewer_id"),
            "reviewer_label": (latest_review.get("metadata") or {}).get("reviewer_label"),
            "notes": (latest_review.get("metadata") or {}).get("notes"),
            "verdict": latest_review.get("decision"),
        }
    return enriched


@idrs.get("/recent")
async def list_recent_idrs(
    limit: int = 20,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Return the caller's most recent IDRs, reverse chronological."""
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="limit must be in [1, 500]")
    # Pull a larger window than ``limit`` so that filtering doesn't
    # under-fill the response when foreign-tenant entries are interleaved.
    raw = _store.list_recent(limit=max(limit * 4, 200))
    own = [e for e in raw if _belongs_to(e, current_user.id)][:limit]
    enriched = [_enrich_with_effective_status(e) for e in own]
    return {"count": len(enriched), "entries": enriched}


@idrs.get("/by-input-hash/{input_hash}")
async def find_idrs_by_input(
    input_hash: str,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Return every IDR whose input_hash matches AND belongs to the caller."""
    raw = _store.find_by_input_hash(input_hash)
    own = [e for e in raw if _belongs_to(e, current_user.id)]
    enriched = [_enrich_with_effective_status(e) for e in own]
    return {"input_hash": input_hash, "count": len(enriched), "entries": enriched}


@idrs.get("/sequence/{sequence}")
async def get_idr_by_sequence(
    sequence: int,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Return the IDR at a specific chain sequence, only if it's the caller's."""
    entry = _store.get_by_sequence(sequence)
    if entry is None or not _belongs_to(entry, current_user.id):
        # 404 (not 403) to avoid leaking that a foreign IDR exists.
        raise HTTPException(status_code=404, detail=f"IDR with sequence {sequence} not found")
    return _enrich_with_effective_status(entry)


@idrs.get("/verify")
async def verify_idr_chain() -> dict:
    """Walk the IDR chain and report HMAC integrity.

    The chain is shared substrate; the verify call surfaces chain
    integrity across all tenants. Tenant-specific verify is a future
    follow-up (per-tenant signing keys, W7).
    """
    return _store.verify()


def _validate_review_body(body: ReviewRequest) -> None:
    """Reject malformed review bodies with a 400."""
    if body.status not in _REVIEW_VERDICTS:
        raise HTTPException(
            status_code=400,
            detail=f"status must be one of {sorted(_REVIEW_VERDICTS)}",
        )
    if body.status == "refuted" and not body.reviewer_label:
        raise HTTPException(
            status_code=400,
            detail=(
                "refuted reviews must supply reviewer_label (the label "
                "the reviewer would have assigned)"
            ),
        )


def _load_review_target(sequence: int) -> dict:
    """Load the IDR being reviewed, raising 404 if absent."""
    target = _store.get_by_sequence(sequence)
    if target is None:
        raise HTTPException(
            status_code=404,
            detail=f"cannot review IDR sequence {sequence}: not found in chain",
        )
    return target


def _build_review_idr(
    sequence: int, target: dict, body: ReviewRequest
) -> IntentDecisionRecord:
    """Construct the append-only REVIEW IDR from a validated body."""
    return IntentDecisionRecord(
        decision_point=DecisionPoint.FALSIFICATION_REVIEW,
        input_hash=target.get("input_hash", "sha256:unknown"),
        input_summary=(
            f"Review of IDR sequence {sequence} — {target.get('decision_point')}"
        ),
        decision=body.status,
        confidence=1.0,  # a human review IS the ground truth for this chain
        confidence_rationale=f"human review by {body.reviewer_id}",
        reasoning=body.notes or f"reviewer marked {body.status}",
        synthesis_method=SynthesisMethod.DETERMINISTIC,
        falsification_criterion=(
            "A second qualified reviewer, given the same document and "
            "rubric, would reach a different verdict. Review chains can "
            "themselves be reviewed — append another review IDR targeting "
            "this sequence to override."
        ),
        metadata={
            "reviews_sequence": sequence,
            "reviewer_id": body.reviewer_id,
            "reviewer_label": body.reviewer_label,
            "notes": body.notes,
            "target_decision_point": target.get("decision_point"),
            "target_decision": target.get("decision"),
        },
    )


@idrs.post("/{sequence}/review")
async def review_idr(sequence: int, body: ReviewRequest) -> dict:
    """Record a human review of an IDR's falsification.

    Writes an append-only REVIEW IDR with
    ``decision_point = falsification_review`` whose
    ``metadata.reviews_sequence`` points at the reviewed entry. The
    original IDR is never mutated — the append-only HMAC chain is
    preserved. Readers derive the effective status from the latest
    review targeting that sequence.

    Three legitimate verdicts:

    - **confirmed**: reviewer agrees with the council's label.
    - **refuted**: reviewer would have assigned a DIFFERENT label.
      The ``reviewer_label`` field carries which label the reviewer
      would have chosen instead — the concrete Popperian evidence
      for the refutation.
    - **inconclusive**: reviewer cannot decide, typically when the
      document is genuinely ambiguous even under the FADP rubric.

    Returns the new review IDR's signed chain entry plus the
    enriched target entry so the caller can re-render with the
    transitioned effective status.
    """
    _validate_review_body(body)
    target = _load_review_target(sequence)
    review = _build_review_idr(sequence, target, body)
    signed = _store.append(review)
    return {
        "review": signed,
        "target": _enrich_with_effective_status(
            _store.get_by_sequence(sequence) or target
        ),
    }
