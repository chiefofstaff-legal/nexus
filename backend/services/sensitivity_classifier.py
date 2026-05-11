"""
Sensitivity classifier — OSS stub. The proprietary Swiss FADP-aware
council classifier lives in `nexus_engine.classifier`.

This OSS fallback returns PUBLIC sensitivity for all inputs and produces
no council vote. Downstream code that depends on the classifier still
runs; the routing just defaults to single-model Groq instead of the
multi-provider FADP council.
"""

from __future__ import annotations

from pydantic import BaseModel

from services.llm_router_simple import SensitivityLevel
from services.pii_detector import PiiDetector
from services.sensitivity_scorer import SensitivityScorer


class ClassificationResult(BaseModel):
    """Result of a sensitivity classification."""

    sensitivity_level: SensitivityLevel = SensitivityLevel.PUBLIC
    sensitivity_score: float = 0.0
    pii_types_detected: list[str] = []
    council_votes: list[dict] = []
    confidence: float = 0.5
    reasoning: str = "OSS fallback — regex-only PII detection, no FADP council"


class SensitivityClassifier:
    """OSS classifier — regex PII + constant scorer, no council.

    Accepts a council positionally for source-compat with the proprietary
    nexus_engine.classifier(council=...) signature, but the OSS fallback
    does not use it (no multi-provider deliberation in this clone).
    """

    def __init__(self, council=None, **kwargs):
        self._council = council  # accepted for compat; unused in OSS fallback
        self._pii = PiiDetector()
        self._scorer = SensitivityScorer()

    async def classify(self, text: str, **kwargs) -> ClassificationResult:
        """Classify sensitivity using regex-only PII detection."""
        pii_types = self._pii.detect(text)
        score = self._scorer.score(text, pii_types)
        if score >= 0.7:
            level = SensitivityLevel.CONFIDENTIAL
        elif score >= 0.3:
            level = SensitivityLevel.INTERNAL
        else:
            level = SensitivityLevel.PUBLIC
        return ClassificationResult(
            sensitivity_level=level,
            sensitivity_score=score,
            pii_types_detected=pii_types,
        )
