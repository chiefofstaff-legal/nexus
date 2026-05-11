"""
Task delegation NER tests — falsification criterion.

Hypothesis: the improved name-extraction pipeline correctly resolves
assignee names from voice transcripts under:
  H1 - exact name in transcript
  H2 - phonetic/STT variant (alias map)
  H3 - fuzzy near-miss
  H4 - spaCy PERSON extraction (heuristic path)
  H5 - "Name, please ..." lead pattern
  H6 - actual NEXUS roster names are in KNOWN_ASSIGNEES
  H7 - old generic names (Maria, Stefan, Anna) no longer primed
"""

import pytest
from datetime import date

from services.task_manager import (
    KNOWN_ASSIGNEES,
    _match_known_assignee,
    _heuristic_parse,
    _extract_persons_spacy,
    resolve_deadline,
)


# ---------------------------------------------------------------------------
# H6 — roster contains actual team members
# ---------------------------------------------------------------------------

def test_known_assignees_contains_actual_team():
    team = {n.lower() for n in KNOWN_ASSIGNEES}
    assert "andre" in team
    assert "arnold" in team
    assert "fabio" in team
    assert "mia" in team
    assert "laurie" in team


def test_old_generic_names_removed():
    team = {n.lower() for n in KNOWN_ASSIGNEES}
    assert "maria" not in team
    assert "stefan" not in team
    assert "anna" not in team


# ---------------------------------------------------------------------------
# H1 — exact name
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("Andre", "Andre"),
    ("ANDRE", "Andre"),
    ("Fabio", "Fabio"),
    ("Mia", "Mia"),
    ("Arnold", "Arnold"),
    ("Laurie", "Laurie"),
])
def test_match_exact_name(raw, expected):
    assert _match_known_assignee(raw) == expected


# ---------------------------------------------------------------------------
# H2 — alias / phonetic variants from voice STT
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("Andray", "Andre"),
    ("André", "Andre"),
    ("Andrew", "Andre"),  # common STT mistake for "Andre"
    ("Andrei", "Andre"),
    ("Lori", "Laurie"),
    ("Lourens", "Laurie"),
    ("Maya", "Mia"),
    ("Mya", "Mia"),
    ("Arnould", "Arnold"),
])
def test_match_alias_variants(raw, expected):
    assert _match_known_assignee(raw) == expected


# ---------------------------------------------------------------------------
# H3 — fuzzy near-misses (difflib, not alias map)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("Fabbia", "Fabio"),    # one letter wrong
    ("Fabio.", "Fabio"),    # trailing punctuation absorbed into substring
    ("Arrnold", "Arnold"),  # doubled letter
    ("Andree", "Andre"),    # extra 'e'
])
def test_fuzzy_match(raw, expected):
    result = _match_known_assignee(raw)
    assert result == expected, f"Expected {expected!r} for {raw!r}, got {result!r}"


# ---------------------------------------------------------------------------
# H4 — spaCy PERSON extraction from natural speech
# ---------------------------------------------------------------------------

def test_spacy_extracts_person_from_delegation_sentence():
    persons = _extract_persons_spacy("Andre, please draft the Schneider NDA by Friday.")
    assert len(persons) >= 1
    assert any("Andre" in p for p in persons)


def test_spacy_extracts_person_from_imperative():
    persons = _extract_persons_spacy("Ask Fabio to review the contract for Müller AG.")
    assert any("Fabio" in p for p in persons)


# ---------------------------------------------------------------------------
# H5 — heuristic_parse "Name, please ..." lead pattern
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("transcript,expected_assignee", [
    ("Andre, please draft the Schneider NDA by Friday", "Andre"),
    ("Fabio please review the Müller contract", "Fabio"),
    ("Arnold, schedule a call with the client by Thursday", "Arnold"),
    ("Mia please send the invoice to Richter AG", "Mia"),
])
def test_heuristic_lead_name_pattern(transcript, expected_assignee):
    result = _heuristic_parse(transcript)
    assert result.assignee == expected_assignee, (
        f"Transcript {transcript!r}: expected {expected_assignee!r}, got {result.assignee!r}"
    )


# ---------------------------------------------------------------------------
# H5b — heuristic with spaCy persons injected
# ---------------------------------------------------------------------------

def test_heuristic_uses_spacy_persons():
    result = _heuristic_parse(
        "Write 5000 page essay on law and ethics",
        spacy_persons=["Andre"],
    )
    assert result.assignee == "Andre"


# ---------------------------------------------------------------------------
# Deadline resolution sanity (regression guard)
# ---------------------------------------------------------------------------

def test_resolve_deadline_friday():
    today = date(2026, 4, 21)  # Tuesday
    d = resolve_deadline("friday", today)
    assert d is not None
    assert d.weekday() == 4  # Friday


def test_resolve_deadline_tomorrow():
    today = date(2026, 4, 21)
    d = resolve_deadline("tomorrow", today)
    assert d == date(2026, 4, 22)
