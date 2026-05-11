"""W6 — Tier vocabulary tests (DEC/RSE/RSG).

Verifies the Swiss legal tier vocabulary extension to DocumentType:
1. New enum values exist with the expected string codes.
2. Pre-existing 8 values remain (no accidental removal).
3. The classify prompt mentions all three new codes so Claude can return them.

Marked TODO — actual semantics await Leandro clarification per
docs/sla.md and the validation matrix.
"""

from __future__ import annotations

import inspect

from models.document import DocumentType
from services.document_processor import DocumentProcessor


def test_tier_enum_values_exist():
    assert DocumentType.DECISION.value == "dec"
    assert DocumentType.REGULATION.value == "rse"
    assert DocumentType.JUDGMENT.value == "rsg"


def test_pre_existing_enum_values_preserved():
    """Regression: adding tier values must NOT remove the original 8."""
    original = {
        "CONTRACT", "BRIEF", "CORRESPONDENCE", "COURT_FILING",
        "INVOICE", "MEMORANDUM", "NDA", "OTHER",
    }
    members = {member.name for member in DocumentType}
    assert original.issubset(members), (
        f"Original DocumentType values missing: {original - members}"
    )


def test_classify_prompt_mentions_tier_codes():
    """Goodhart anchor — the three tier codes must reach the LLM prompt.

    If the prompt template loses 'dec', 'rse', or 'rsg', Claude can never
    return them — the enum value would be unreachable.
    """
    source = inspect.getsource(DocumentProcessor.classify)
    assert "dec" in source
    assert "rse" in source
    assert "rsg" in source


def test_total_enum_member_count():
    """11 = 8 original + 3 tier additions."""
    assert len(list(DocumentType)) == 11
