"""Tests for W3 SRP — LLMRouter decomposition into PiiDetector + SensitivityScorer.

Mutation criterion: patching PiiDetector.detect to return zero counts must
cause SensitivityScorer to return PUBLIC level, proving LLMRouter delegates
rather than running its own detection logic.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# PiiDetector — regex detection (spaCy disabled to keep tests hermetic)
# ---------------------------------------------------------------------------

class TestPiiDetector:
    def _detector(self):
        from services.pii_detector import PiiDetector
        d = PiiDetector()
        d._nlp = False  # disable spaCy for deterministic unit tests
        return d

    def test_detects_email(self):
        d = self._detector()
        types, count = d.detect("Contact me at john.doe@example.com")
        assert "email" in types
        assert count >= 1.0

    def test_detects_ssn(self):
        d = self._detector()
        types, count = d.detect("My SSN is 123-45-6789")
        assert "ssn" in types

    def test_detects_credit_card(self):
        d = self._detector()
        types, count = d.detect("Card number 4111111111111111 on file")
        assert "credit_card" in types

    def test_clean_text_returns_empty(self):
        d = self._detector()
        types, count = d.detect("The quick brown fox jumps over the lazy dog.")
        assert types == []
        assert count == 0.0

    def test_mutation_no_patterns_means_no_detection(self):
        """Goodhart: detector with empty patterns must return zero results."""
        from services.pii_detector import PiiDetector
        d = PiiDetector()
        d._nlp = False
        original = d.PII_PATTERNS.copy()
        d.PII_PATTERNS = {}
        types, count = d.detect("john.doe@example.com 123-45-6789")
        assert types == [] and count == 0.0
        # Restore
        d.PII_PATTERNS = original
        types2, count2 = d.detect("john.doe@example.com")
        assert count2 > 0.0, "real detector must find the email"


# ---------------------------------------------------------------------------
# SensitivityScorer — threshold boundaries
# ---------------------------------------------------------------------------

class TestSensitivityScorer:
    def _scorer(self):
        from services.sensitivity_scorer import SensitivityScorer
        return SensitivityScorer()

    def test_zero_pii_is_public(self):
        s = self._scorer()
        from services.llm_router import SensitivityLevel
        level, score = s.score(0.0, 1000)
        assert level == SensitivityLevel.PUBLIC
        assert score == 0.0

    def test_high_pii_density_is_confidential(self):
        s = self._scorer()
        from services.llm_router import SensitivityLevel
        # 7 hits in 1000 chars → density=7.0, score=0.7 → CONFIDENTIAL
        level, score = s.score(7.0, 1000)
        assert level == SensitivityLevel.CONFIDENTIAL
        assert score >= 0.7

    def test_moderate_pii_density_is_internal(self):
        s = self._scorer()
        from services.llm_router import SensitivityLevel
        # 4 hits in 1000 chars → density=4.0, score=0.4 → INTERNAL
        level, score = s.score(4.0, 1000)
        assert level == SensitivityLevel.INTERNAL

    def test_score_capped_at_one(self):
        s = self._scorer()
        _, score = s.score(1000.0, 100)
        assert score <= 1.0


# ---------------------------------------------------------------------------
# LLMRouter — classify_sensitivity delegates to extracted classes
# ---------------------------------------------------------------------------

class TestLLMRouterDelegation:
    def _router(self):
        from pathlib import Path
        from services.llm_router import LLMRouter
        return LLMRouter(Path("/tmp/nexus-test-w3"))

    def test_classify_sensitivity_delegates_to_pii_detector(self):
        """Patch PiiDetector.detect → LLMRouter.classify_sensitivity must use result."""
        router = self._router()
        with patch.object(router._pii_detector, "detect", return_value=(["email"], 5.0)) as mock_detect:
            with patch.object(router._scorer, "score", return_value=("public", 0.5)) as mock_score:
                router.classify_sensitivity("any text")
                mock_detect.assert_called_once_with("any text")
                mock_score.assert_called_once_with(5.0, len("any text"))

    def test_mutation_detect_returns_zero_yields_public(self):
        """Goodhart: if detection is zeroed, score must be PUBLIC."""
        from services.llm_router import SensitivityLevel
        router = self._router()
        router._pii_detector._nlp = False  # no spaCy
        original_patterns = router._pii_detector.PII_PATTERNS.copy()
        router._pii_detector.PII_PATTERNS = {}  # disable all regex
        level, score, pii_types = router.classify_sensitivity("secret SSN 123-45-6789 email@test.com")
        assert level == SensitivityLevel.PUBLIC
        assert score == 0.0
        # Restore and confirm real detection works
        router._pii_detector.PII_PATTERNS = original_patterns
        level2, score2, _ = router.classify_sensitivity("email@test.com ssn 123-45-6789")
        assert level2 != SensitivityLevel.PUBLIC or score2 > 0.0
