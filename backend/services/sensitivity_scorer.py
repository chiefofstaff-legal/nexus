"""Sensitivity scoring — converts PII density into a 0–1 score and level.

Extracted from LLMRouter (W3 SRP fix). Single responsibility: given a PII
occurrence count and text length, return the sensitivity level and score.
"""
from __future__ import annotations

from services.types import SensitivityLevel


class SensitivityScorer:
    """Converts PII density into a 0–1 sensitivity score and routing level."""

    THRESHOLD_INTERNAL: float = 0.3
    THRESHOLD_CONFIDENTIAL: float = 0.7

    def score(self, pii_count: float, text_len: int) -> tuple[SensitivityLevel, float]:
        """Return ``(level, score)`` where score is in [0.0, 1.0].

        ``pii_count`` may be fractional (spaCy ORG/MONEY partial weights).
        ``text_len`` must be > 0; callers pass ``len(text)`` directly.
        """
        density = pii_count / (max(text_len, 1) / 1000)
        raw = min(density / 10.0, 1.0)

        if raw >= self.THRESHOLD_CONFIDENTIAL:
            level = SensitivityLevel.CONFIDENTIAL
        elif raw >= self.THRESHOLD_INTERNAL:
            level = SensitivityLevel.INTERNAL
        else:
            level = SensitivityLevel.PUBLIC

        return level, round(raw, 3)
