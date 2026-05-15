"""
Council-based sensitivity classifier — Swiss FADP aware.

Replaces the density-regex heuristic in LLMRouter with a multi-LLM
council classification that writes an IDR for every decision. The
heuristic is still available as a fast pre-check (density floor) to
short-circuit obviously-clean documents without spending council
calls on them.

The council classifies into three levels matching Swiss legal practice:

- **public** — no PII, no privileged content, safe to route anywhere
- **internal** — some PII or business-sensitive signals, route to
  cloud providers with care
- **confidential** — dense PII, attorney-client privilege markers,
  or regulated data categories (health, financial, minors) — must
  stay on-prem, route through Ollama or a Swiss-hosted provider
"""

import re

from core.intent_decision_record import DecisionPoint, IntentDecisionRecord
from services.council import Council, CouncilQuery, CouncilResult

_SWISS_FADP_SYSTEM_PROMPT = """You are a Swiss legal data-protection classifier. Your job is to label a document's data sensitivity so it can be routed to the appropriate LLM provider under Swiss FADP (Federal Act on Data Protection) compliance.

Classification rubric:

- public: the document contains no personal identifiers, no business-sensitive strategy, no privileged communication. Safe to send to any cloud LLM provider. Examples: market research summaries, published case law citations, public filings.

- internal: the document contains SOME personal identifiers (names, organisations) or business-sensitive signals (client strategies, financial plans) but nothing that would trigger FADP Article 5 "particularly sensitive personal data". Safe to send to cloud providers with standard contractual protections. Examples: client meeting notes without PII, vendor contracts with standard clauses.

- confidential: the document contains DENSE personal identifiers (SSN, ID numbers, account numbers, dates of birth), particularly sensitive data (health records, genetic data, biometric data, religious/political views, information about minors, criminal records), or markers of attorney-client privilege. MUST stay on-prem — route through the local Ollama model, never leave the firm's network. Examples: NDAs with enumerated personal data, health-related contracts, litigation files.

When the document is genuinely ambiguous (e.g. a short sentence that could be strategy discussion or generic advice), classify it as 'internal' with a confidence value below 0.7 to signal to the router that human review is appropriate.

Report your confidence honestly. Low confidence on hard cases is more valuable than confident wrong answers."""


_PII_CHEAP_PATTERNS = {
    "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
    "phone": r"\b(?:\+?1?[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
    "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
    "iban": r"\b[A-Z]{2}\d{2}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{0,4}\b",
    "credit_card": r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13})\b",
}


class SensitivityClassifier:
    """Council-based sensitivity classification with IDR audit trail."""

    def __init__(self, council: Council, truncate_to: int = 4000):
        self._council = council
        self._truncate_to = truncate_to

    @staticmethod
    def pii_fingerprint(text: str) -> list[str]:
        """Cheap regex PII detection — used as a deterministic floor signal."""
        return [
            name
            for name, pattern in _PII_CHEAP_PATTERNS.items()
            if re.search(pattern, text)
        ]

    async def classify(
        self, text: str, doc_summary: str = "", *, user_id: str
    ) -> CouncilResult:
        """Classify via council, return the full CouncilResult with IDR.

        The caller can read ``result.decision`` for the label, ``result.confidence``
        for the honest confidence, and ``result.idr`` for the signed chain entry.

        ``user_id`` (keyword-only, required) is the acting tenant and is
        threaded into the council so the sensitivity IDR is
        tenant-attributed and surfaces on the /idr page.
        """
        truncated = text[: self._truncate_to] if len(text) > self._truncate_to else text
        cheap_pii = self.pii_fingerprint(text)
        hint = (
            f" (deterministic PII fingerprint flagged: {', '.join(cheap_pii)})"
            if cheap_pii
            else " (no deterministic PII markers found by regex)"
        )

        query = CouncilQuery(
            decision_point=DecisionPoint.SENSITIVITY_CLASSIFICATION,
            system_prompt=_SWISS_FADP_SYSTEM_PROMPT,
            user_prompt=(
                f"Classify this document's data sensitivity{hint}:\n\n{truncated}"
            ),
            input_hash=IntentDecisionRecord.hash_input(text),
            input_summary=doc_summary or f"document ({len(text)} chars)",
            allowed_decisions=["public", "internal", "confidential"],
            # Fallback criterion used only when every council member fails
            # to supply a document-specific falsification. Normal operation
            # replaces this with the majority's own refutation statement
            # (see Council._synthesise + CouncilQuery.to_idr).
            falsification_criterion=(
                "(Fallback — council did not supply a document-specific "
                "criterion.) A Swiss-law-trained reviewer would assign a "
                "different label to this document under the FADP rubric."
            ),
            metadata={
                "original_length": len(text),
                "truncated_length": len(truncated),
                "pii_fingerprint": cheap_pii,
            },
        )
        return await self._council.deliberate(query, user_id=user_id)
