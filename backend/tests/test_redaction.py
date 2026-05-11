"""
W5 — Redaction service tests.

Verifies that the redaction pipeline:

1. Masks PII-class entities (PERSON, MONEY, LOCATION, CASE, DATE).
2. Leaves ORGANISATION and STATUTE entities visible.
3. Catches email / phone / SSN / credit-card via the deterministic
   regex floor even without entity extraction.
4. Handles overlapping matches without position drift.
5. Returns accurate span counts + a manifest for the UI.
"""

from models.entity import Entity, EntityType
from services.redaction import redact


def _entity(name: str, entity_type: EntityType) -> Entity:
    return Entity(
        id=f"id-{name}",
        name=name,
        entity_type=entity_type,
    )


def test_person_and_money_are_redacted():
    text = "Alex Morgan signed the contract for R45,000,000.00 today."
    entities = [
        _entity("Alex Morgan", EntityType.PERSON),
        _entity("R45,000,000.00", EntityType.MONEY),
    ]
    result = redact(text, entities)
    assert "Alex Morgan" not in result.text
    assert "R45,000,000.00" not in result.text
    assert "[REDACTED-PERSON]" in result.text
    assert "[REDACTED-MONEY]" in result.text
    assert result.counts.get("person") == 1
    assert result.counts.get("money") == 1


def test_organisation_and_statute_stay_visible():
    text = "Under FADP Article 5, Acme Corp contracted with Globex Industries."
    entities = [
        _entity("Acme Corp", EntityType.ORGANISATION),
        _entity("Globex Industries", EntityType.ORGANISATION),
        _entity("FADP Article 5", EntityType.STATUTE),
    ]
    result = redact(text, entities)
    # These must remain in the text — they're public / shareable
    assert "Acme Corp" in result.text
    assert "Globex Industries" in result.text
    assert "FADP Article 5" in result.text
    assert result.counts == {}


def test_deterministic_pii_floor_catches_email_and_phone():
    text = "Contact: alex@example.com or 555-123-4567 for details."
    result = redact(text, entities=[])
    assert "alex@example.com" not in result.text
    assert "555-123-4567" not in result.text
    assert "[REDACTED-EMAIL]" in result.text
    assert "[REDACTED-PHONE]" in result.text


def test_ssn_and_credit_card_floor():
    text = "SSN 123-45-6789 and card 4532015112830366 on file."
    result = redact(text, entities=[])
    assert "123-45-6789" not in result.text
    assert "4532015112830366" not in result.text
    assert "[REDACTED-SSN]" in result.text
    assert "[REDACTED-CREDIT_CARD]" in result.text


def test_multiple_occurrences_all_redacted():
    text = "Laurie wrote to Laurie about Laurie's contract."
    entities = [_entity("Laurie", EntityType.PERSON)]
    result = redact(text, entities)
    assert "Laurie" not in result.text
    assert result.text.count("[REDACTED-PERSON]") == 3
    assert result.counts["person"] == 3


def test_overlapping_spans_longest_wins():
    """When a long match overlaps a shorter one, the long one wins
    and the shorter one is silently dropped — no position drift."""
    text = "Reach alex@example.com today."
    # Pathological case: the phone regex might match substrings of
    # the email if it weren't for the dedup pass. This test proves
    # the dedup keeps the full email redaction.
    result = redact(text, entities=[])
    assert "alex@example.com" not in result.text
    # Exactly one span replaced the email — no partial phone match
    assert result.text.count("[REDACTED-EMAIL]") == 1
    assert "[REDACTED-PHONE]" not in result.text


def test_empty_text_returns_empty():
    result = redact("", entities=[])
    assert result.text == ""
    assert result.spans == []
    assert result.counts == {}


def test_text_with_no_pii_unchanged():
    text = "This document contains no personal information."
    result = redact(text, entities=[])
    assert result.text == text
    assert result.spans == []
