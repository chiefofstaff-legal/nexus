"""
Sensitivity scorer — OSS stub. The proprietary heuristic-weighted
scorer lives in `nexus_engine.scorer`.

This OSS fallback returns a constant 0.5 (medium) sensitivity score so
downstream code that depends on the scorer does not crash. The actual
sensitivity routing decisions are made by the proprietary
nexus_engine.classifier in hosted deployments.
"""

from __future__ import annotations


class SensitivityScorer:
    """Constant-score scorer — OSS fallback."""

    def score(self, text: str, pii_types: list[str] | None = None) -> float:
        """Return a sensitivity score in [0.0, 1.0].

        OSS fallback: returns 0.5 when any PII is detected, 0.0 otherwise.
        The proprietary scorer weighs PII type, document context, and
        sensitivity rubric heuristics.
        """
        if pii_types:
            return 0.5
        return 0.0
