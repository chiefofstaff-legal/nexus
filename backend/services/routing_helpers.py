"""Routing helpers — council result transformation for HTTP responses.

Thin adapter between Council results and LLM routing responses.
Extracted from app/routes.py (W1 SRP): transformation logic between two
service types belongs in the service layer, not the HTTP layer.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.council import CouncilResult
    from services.llm_router import RoutingDecision


def enrich_decision_with_council(
    decision: RoutingDecision,
    council_result: CouncilResult,
) -> None:
    """Overlay council-derived context on the routing decision in place."""
    decision.sensitivity_score = round(council_result.confidence, 3)
    decision.routing_reason = (
        f"Council ({council_result.synthesis_method.value}): "
        f"{council_result.confidence_rationale}"
    )
    fingerprint = council_result.idr.get("metadata", {}).get("pii_fingerprint", [])
    if fingerprint:
        decision.pii_types_detected = fingerprint


def idr_summary(council_result: CouncilResult) -> dict:
    """Build the slim IDR payload returned alongside a routing decision."""
    idr_dict = council_result.idr
    return {
        "idr_id": idr_dict.get("idr_id"),
        "sequence": idr_dict.get("sequence"),
        "decision": council_result.decision,
        "confidence": council_result.confidence,
        "synthesis_method": council_result.synthesis_method.value,
        "chain_hash": idr_dict.get("chain_hash"),
    }
