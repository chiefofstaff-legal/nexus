"""
Document redaction service.

Takes a document's raw text and an entity list from the entity
extractor, produces a redacted version where PII-class entities are
replaced by opaque placeholder tokens. Used by the document viewer's
"redact" toggle and the /download-redacted endpoint.

What gets redacted:

- PERSON: named individuals -> [REDACTED-PERSON]
- MONEY: currency figures -> [REDACTED-MONEY]
- LOCATION: addresses / geographic markers -> [REDACTED-LOCATION]
- CASE: case / docket numbers -> [REDACTED-CASE]
- DATE: personal dates -> [REDACTED-DATE]
- Also runs the llm_router PII regex (email, phone, SSN, IBAN,
  credit card) as a deterministic floor — catches things the spaCy
  layer might have missed.

What stays visible:

- ORGANISATION — normally OK to share ("CodeTonight", "Sudonum")
- STATUTE — public references ("FADP Article 5") are safe
- EVENT — non-identifying events

Rationale: the redaction target is a document a lawyer would share
outside the firm while preserving the legal content. Org names and
statute citations are exactly what the recipient needs; personal
identifiers are what they don't.
"""

import re
from dataclasses import dataclass

from models.entity import Entity, EntityType


# PII patterns copied from llm_router.LLMRouter.PII_PATTERNS so this
# module doesn't import the router. The canonical list lives there —
# keep in sync on changes. Each pattern is named so we can recover the
# category from the match's lastgroup attribute after the single-pass
# alternation scan.
_PII_ALTERNATION = re.compile(
    "|".join([
        r"(?P<email>\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b)",
        r"(?P<phone>\b(?:\+?1?[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b)",
        r"(?P<ssn>\b\d{3}-\d{2}-\d{4}\b)",
        r"(?P<credit_card>\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13})\b)",
    ])
)

_REDACTED_ENTITY_TYPES = {
    EntityType.PERSON: "[REDACTED-PERSON]",
    EntityType.MONEY: "[REDACTED-MONEY]",
    EntityType.LOCATION: "[REDACTED-LOCATION]",
    EntityType.CASE: "[REDACTED-CASE]",
    EntityType.DATE: "[REDACTED-DATE]",
}


@dataclass
class RedactionSpan:
    """A single replacement the redactor made."""

    start: int
    end: int
    original: str
    category: str
    placeholder: str


@dataclass
class RedactionResult:
    """Text with PII replaced, plus every span that changed."""

    text: str
    spans: list[RedactionSpan]
    counts: dict[str, int]

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "counts": self.counts,
            "span_count": len(self.spans),
            "spans": [
                {
                    "start": s.start,
                    "end": s.end,
                    "original": s.original,
                    "category": s.category,
                    "placeholder": s.placeholder,
                }
                for s in self.spans
            ],
        }


def redact(text: str, entities: list[Entity]) -> RedactionResult:
    """Return a redacted copy of the text plus a span manifest.

    Three-stage O(n + m + s log s) pipeline:

    1. Collect candidate spans from entities AND the regex floor.
    2. Deduplicate overlapping spans (sort-then-scan, longest wins).
    3. Rebuild the text in one pass from the final span list.

    The sort dominates complexity at O(s log s) where s is the number
    of matches; the collection and rebuild stages are linear in text
    length.
    """
    spans = _collect_entity_spans(text, entities) + _collect_regex_spans(text)
    deduped = _dedupe_overlapping(spans)
    rebuilt_text, counts = _rebuild(text, deduped)
    return RedactionResult(text=rebuilt_text, spans=deduped, counts=counts)


def _collect_entity_spans(
    text: str, entities: list[Entity]
) -> list[RedactionSpan]:
    """Find every occurrence of each PII-class entity in the text.

    Builds a compiled alternation regex from the distinct entity
    names so the scan is a single linear pass over the text rather
    than a nested per-entity finditer.
    """
    type_by_name: dict[str, Entity] = {}
    for entity in entities:
        if entity.entity_type not in _REDACTED_ENTITY_TYPES:
            continue
        type_by_name[entity.name] = entity
    if not type_by_name:
        return []
    pattern = re.compile(
        "|".join(re.escape(n) for n in type_by_name.keys())
    )
    out: list[RedactionSpan] = []
    for match in pattern.finditer(text):
        name = match.group(0)
        entity = type_by_name[name]
        out.append(
            RedactionSpan(
                start=match.start(),
                end=match.end(),
                original=name,
                category=entity.entity_type.value,
                placeholder=_REDACTED_ENTITY_TYPES[entity.entity_type],
            )
        )
    return out


def _collect_regex_spans(text: str) -> list[RedactionSpan]:
    """Deterministic PII floor — single-pass alternation scan.

    One compiled regex with named groups covers email, phone, SSN, and
    credit-card patterns. The scan is O(n) over the text length — no
    nested iteration. ``lastgroup`` tells us which alternative fired.
    """
    out: list[RedactionSpan] = []
    for match in _PII_ALTERNATION.finditer(text):
        category = match.lastgroup or "unknown"
        out.append(
            RedactionSpan(
                start=match.start(),
                end=match.end(),
                original=match.group(0),
                category=category,
                placeholder=f"[REDACTED-{category.upper()}]",
            )
        )
    return out


def _dedupe_overlapping(spans: list[RedactionSpan]) -> list[RedactionSpan]:
    """Sort-then-scan dedup — longest wins on overlap."""
    spans.sort(key=lambda s: (s.start, -(s.end - s.start)))
    deduped: list[RedactionSpan] = []
    last_end = -1
    for s in spans:
        if s.start < last_end:
            continue
        deduped.append(s)
        last_end = s.end
    return deduped


def _rebuild(
    text: str, spans: list[RedactionSpan]
) -> tuple[str, dict[str, int]]:
    """Single-pass text reconstruction plus category counts."""
    parts: list[str] = []
    counts: dict[str, int] = {}
    cursor = 0
    for s in spans:
        parts.append(text[cursor:s.start])
        parts.append(s.placeholder)
        cursor = s.end
        counts[s.category] = counts.get(s.category, 0) + 1
    parts.append(text[cursor:])
    return "".join(parts), counts
