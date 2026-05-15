"""PII detection — regex patterns + optional spaCy NER.

Extracted from LLMRouter (W3 SRP fix). Single responsibility: given a text,
return which PII types were found and a weighted occurrence count.
"""
from __future__ import annotations

import re


class PiiDetector:
    """Regex + spaCy PII detection. Returns types found and a weighted count."""

    PII_PATTERNS: dict[str, str] = {
        "email": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        "phone": r'\b(?:\+?1?[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b',
        "ssn": r'\b\d{3}-\d{2}-\d{4}\b',
        "id_number": r'\b(?:ID|passport|license)\s*(?:no\.?|number|#)\s*:?\s*[A-Z0-9-]{5,20}\b',
        "bank_account": r'\b(?:account|IBAN|routing)\s*(?:no\.?|number|#)\s*:?\s*[A-Z0-9-]{8,34}\b',
        "credit_card": r'\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13})\b',
    }

    def __init__(self) -> None:
        self._nlp = None

    def detect(self, text: str) -> tuple[list[str], float]:
        """Return ``(pii_types, pii_count)`` for *text*.

        ``pii_count`` is fractional — spaCy ORG and MONEY entities contribute
        0.5 and 0.3 respectively rather than 1.0.
        """
        pii_types: list[str] = []
        pii_count: float = 0.0

        for pii_type, pattern in self.PII_PATTERNS.items():
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                pii_types.append(pii_type)
                pii_count += len(matches)

        self._load_spacy()
        if self._nlp and self._nlp is not False:
            doc = self._nlp(text[:10000])
            seen_persons: set[str] = set()
            for ent in doc.ents:
                if ent.label_ == "PERSON" and ent.text not in seen_persons:
                    seen_persons.add(ent.text)
                    pii_types.append(f"named_persons:{len(seen_persons)}")
                    pii_count += 1
                elif ent.label_ == "ORG":
                    pii_count += 0.5
                elif ent.label_ == "MONEY":
                    pii_count += 0.3

        return pii_types, pii_count

    def _load_spacy(self) -> None:
        if self._nlp is None:
            try:
                import spacy
                self._nlp = spacy.load("en_core_web_sm")
            except (ImportError, OSError):
                self._nlp = False
