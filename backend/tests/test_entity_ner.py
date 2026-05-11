"""
Entity NER false-positive falsification tests.

Hypothesis: the false-positive guards in _spacy_pass prevent version strings,
section numbers, and technical nouns from being mis-tagged as PII, while
leaving genuine currency and person entities intact.

H-NER-1: Section numbers (5.2, 6.1) are NOT tagged as MONEY.
H-NER-2: Version strings (v3.x.x..v4.11.1) are NOT tagged as PERSON.
H-NER-3: Technical nouns (Hacks, Diff) are NOT tagged as PERSON.
H-NER-4: Real currency (CHF 250,000 / R45,000) IS still tagged as MONEY.
H-NER-5: Real person names (full name) ARE still tagged as PERSON.

Each test would FAIL if the corresponding guard were removed.
"""

import asyncio

import pytest

from models.entity import EntityType
from services.entity_extractor import EntityExtractor


@pytest.fixture
def extractor():
    return EntityExtractor(anthropic_client=None)


def _entities(extractor: EntityExtractor, text: str):
    return asyncio.run(extractor.extract_entities_spacy(text, "test_doc"))


def _names_of_type(entities, entity_type: EntityType) -> list[str]:
    return [e.name for e in entities if e.entity_type == entity_type]


# ---------------------------------------------------------------------------
# H-NER-1: section numbers not tagged MONEY
# ---------------------------------------------------------------------------

def test_section_number_5_2_not_money(extractor):
    entities = _entities(extractor, "5.2 Verify test case passes.")
    money = _names_of_type(entities, EntityType.MONEY)
    assert "5.2" not in money, f"5.2 should not be MONEY; got {money}"


def test_section_number_6_1_not_money(extractor):
    entities = _entities(extractor, "6.1 System health check.")
    money = _names_of_type(entities, EntityType.MONEY)
    assert "6.1" not in money, f"6.1 should not be MONEY; got {money}"


def test_section_number_5_3_not_money(extractor):
    entities = _entities(extractor, "5.3 Hacks Diff Check")
    money = _names_of_type(entities, EntityType.MONEY)
    assert "5.3" not in money, f"5.3 should not be MONEY; got {money}"


@pytest.mark.parametrize("section", ["3.1", "4.2", "10.5", "1.0"])
def test_decimal_section_numbers_not_money(extractor, section):
    entities = _entities(extractor, f"{section} Some section heading.")
    money = _names_of_type(entities, EntityType.MONEY)
    assert section not in money, f"Section {section!r} should not be MONEY; got {money}"


# ---------------------------------------------------------------------------
# H-NER-2: version strings not tagged PERSON
# ---------------------------------------------------------------------------

def test_git_range_not_person(extractor):
    entities = _entities(extractor, "git diff v3.x.x..v4.11.1")
    persons = _names_of_type(entities, EntityType.PERSON)
    assert not any("v3" in n or "v4" in n or ".." in n for n in persons), (
        f"Version range should not be PERSON; got {persons}"
    )


def test_version_prefix_not_person(extractor):
    entities = _entities(extractor, "Upgrade from v3.2.1 to v4.0.0.")
    persons = _names_of_type(entities, EntityType.PERSON)
    assert not any(n.startswith("v") and n[1:2].isdigit() for n in persons), (
        f"Version prefix should not be PERSON; got {persons}"
    )


def test_wildcard_version_not_person(extractor):
    entities = _entities(extractor, "Supported versions: 3.x and 4.x.x")
    persons = _names_of_type(entities, EntityType.PERSON)
    assert not any(".x" in n for n in persons), (
        f"Wildcard version should not be PERSON; got {persons}"
    )


# ---------------------------------------------------------------------------
# H-NER-3: technical nouns not tagged PERSON
# ---------------------------------------------------------------------------

def test_hacks_not_person(extractor):
    entities = _entities(extractor, "5.2 Verify Hacks Load Without Error")
    persons = _names_of_type(entities, EntityType.PERSON)
    assert "Hacks" not in persons, f"'Hacks' should not be PERSON; got {persons}"


def test_diff_not_person(extractor):
    entities = _entities(extractor, "Run the Diff check on all files.")
    persons = _names_of_type(entities, EntityType.PERSON)
    assert "Diff" not in persons, f"'Diff' should not be PERSON; got {persons}"


def test_combined_changelog_false_positives_absent(extractor):
    """Full changelog line must not produce any false-positive PERSON or MONEY."""
    text = "5.3 Hacks Diff Check (Caswell Method)"
    entities = _entities(extractor, text)
    money = _names_of_type(entities, EntityType.MONEY)
    persons = _names_of_type(entities, EntityType.PERSON)

    assert "5.3" not in money, f"5.3 should not be MONEY"
    assert "Hacks" not in persons, f"'Hacks' should not be PERSON"
    assert "Diff" not in persons, f"'Diff' should not be PERSON"


def test_version_range_line_no_false_positives(extractor):
    """git diff line must not produce any PERSON entities."""
    entities = _entities(extractor, "git diff v3.x.x..v4.11.1")
    persons = _names_of_type(entities, EntityType.PERSON)
    assert persons == [], f"git diff line should have no PERSON entities; got {persons}"


# ---------------------------------------------------------------------------
# H-NER-4: real currency still tagged MONEY (no regression)
# ---------------------------------------------------------------------------

def test_chf_currency_is_money(extractor):
    entities = _entities(extractor, "The fee is CHF 250,000 per annum.")
    money = _names_of_type(entities, EntityType.MONEY)
    assert any("CHF" in n for n in money), (
        f"CHF currency should be MONEY; got {money}"
    )


def test_zar_currency_is_money(extractor):
    entities = _entities(extractor, "Total settlement: R45,000,000.00")
    money = _names_of_type(entities, EntityType.MONEY)
    assert any("R" in n and any(c.isdigit() for c in n) for n in money), (
        f"ZAR currency should be MONEY; got {money}"
    )


def test_usd_currency_is_money(extractor):
    entities = _entities(extractor, "Payment of $1,500 is due.")
    money = _names_of_type(entities, EntityType.MONEY)
    assert any("$" in n or "1,500" in n for n in money), (
        f"USD currency should be MONEY; got {money}"
    )


# ---------------------------------------------------------------------------
# H-NER-5: real person names still tagged PERSON (no regression)
# ---------------------------------------------------------------------------

def test_full_name_is_person(extractor):
    entities = _entities(extractor, "Andre Schneider signed the agreement.")
    persons = _names_of_type(entities, EntityType.PERSON)
    assert len(persons) >= 1, (
        f"Real full name should produce at least one PERSON; got {persons}"
    )


def test_two_person_names_extracted(extractor):
    entities = _entities(
        extractor,
        "Maria Keller and Thomas Richter appeared before the court.",
    )
    persons = _names_of_type(entities, EntityType.PERSON)
    assert len(persons) >= 2, (
        f"Two distinct names should produce at least 2 PERSON entities; got {persons}"
    )
