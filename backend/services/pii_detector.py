"""
PII detector — OSS stub. The proprietary dual-layer detector (regex +
spaCy NER + sensitivity weighting) lives in `nexus_engine.pii`.

This OSS stub uses the regex floor only. It catches the well-known
patterns (email, phone, SSN, credit card, IBAN) but not entity-level
detection. For full FADP-grade PII coverage, install nexus_engine.
"""

from __future__ import annotations

import re

# Regex floor — well-known, public-domain patterns.
_REGEX_PATTERNS: dict[str, re.Pattern[str]] = {
    "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    "phone": re.compile(r"\b(?:\+?\d{1,3}[\s-]?)?\(?\d{2,4}\)?[\s-]?\d{3,4}[\s-]?\d{3,4}\b"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "credit_card": re.compile(r"\b(?:\d[ -]*?){13,16}\b"),
    "iban": re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{4,30}\b"),
}


class PiiDetector:
    """Regex-only PII detector — OSS fallback for `nexus_engine.pii`."""

    def detect(self, text: str) -> list[str]:
        """Return a list of PII type names found in the text."""
        if not text:
            return []
        found: list[str] = []
        for name, pattern in _REGEX_PATTERNS.items():
            if pattern.search(text):
                found.append(name)
        return found

    def has_pii(self, text: str) -> bool:
        """Fast yes/no check."""
        return bool(self.detect(text))
