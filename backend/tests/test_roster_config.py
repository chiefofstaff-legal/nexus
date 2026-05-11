"""W3 — Roster YAML loader tests.

Verifies:
1. A valid YAML file loads canonical names + aliases.
2. Missing top-level ``assignees:`` key surfaces as RosterConfigError.
3. The alias map normalises voice-STT phonetic variants back to canonical.
4. Reset cache + load from override path lets tests inject custom rosters.
5. Goodhart guard: ``_match_known_assignee`` still resolves "Andray" → "Andre"
   after externalisation (regression anchor for the in-place refactor).
"""

from __future__ import annotations

import pytest

from core.roster_config import (
    RosterConfigError,
    load_roster,
)
from services.task_manager import (
    KNOWN_ASSIGNEES,
    _match_known_assignee,
    reset_roster_cache,
)


@pytest.fixture(autouse=True)
def _reset_cache_around_each_test():
    """Drop the roster cache before AND after each test so monkeypatched
    paths can never leak into other test modules. Without this teardown,
    test_task_ner.py runs after this file with the last tmp-roster cached
    and 10 alias-resolution tests fail.
    """
    reset_roster_cache()
    yield
    reset_roster_cache()


def _write_yaml(tmp_path, body: str):
    path = tmp_path / "roster.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def test_roster_loads_canonicals_and_aliases(tmp_path):
    path = _write_yaml(
        tmp_path,
        """
assignees:
  - canonical: "Andre"
    aliases: [andray, andre]
  - canonical: "Mia"
    aliases: [maya, mya]
""",
    )
    canonicals, alias_map = load_roster(path)
    assert canonicals == ("Andre", "Mia")
    assert alias_map["andray"] == "Andre"
    assert alias_map["maya"] == "Mia"
    assert alias_map["andre"] == "Andre"


def test_roster_missing_top_level_key_raises(tmp_path):
    path = _write_yaml(tmp_path, "team:\n  - name: Andre\n")
    with pytest.raises(RosterConfigError, match="top-level 'assignees:'"):
        load_roster(path)


def test_roster_empty_assignees_raises(tmp_path):
    path = _write_yaml(tmp_path, "assignees: []\n")
    with pytest.raises(RosterConfigError, match="no assignees defined"):
        load_roster(path)


def test_roster_missing_canonical_raises(tmp_path):
    path = _write_yaml(
        tmp_path,
        "assignees:\n  - aliases: [foo, bar]\n",
    )
    with pytest.raises(RosterConfigError, match="missing 'canonical'"):
        load_roster(path)


def test_roster_file_not_found_raises(tmp_path):
    missing = tmp_path / "no-such-file.yaml"
    with pytest.raises(RosterConfigError, match="not found"):
        load_roster(missing)


def test_match_known_assignee_resolves_alias_after_externalisation(monkeypatch, tmp_path):
    """Goodhart anchor — phonetic STT variants must still normalise.

    This is the regression test for the in-place YAML refactor: if the alias
    lookup in ``_match_known_assignee`` ever loses the call to ``_alias_map``,
    "Andray" stops resolving to "Andre" and silently passes through as raw.
    """
    path = _write_yaml(
        tmp_path,
        """
assignees:
  - canonical: "Andre"
    aliases: [andray, andre, andrew]
  - canonical: "Fabio"
    aliases: [fabia]
""",
    )
    monkeypatch.setattr(
        "core.roster_config.DEFAULT_ROSTER_PATH", path,
    )
    reset_roster_cache()

    assert _match_known_assignee("Andray") == "Andre"
    assert _match_known_assignee("ANDREW") == "Andre"
    assert _match_known_assignee("Fabia") == "Fabio"
    # Whole-list iteration via the proxy must hit the new YAML, not the fallback.
    assert "Andre" in KNOWN_ASSIGNEES
    assert "Fabio" in KNOWN_ASSIGNEES


def test_match_known_assignee_unknown_passes_through(monkeypatch, tmp_path):
    """An unfamiliar name should NOT be hallucinated into a roster member."""
    path = _write_yaml(
        tmp_path,
        """
assignees:
  - canonical: "Andre"
    aliases: [andray]
""",
    )
    monkeypatch.setattr(
        "core.roster_config.DEFAULT_ROSTER_PATH", path,
    )
    reset_roster_cache()
    # "Zachary" is far from "Andre" by difflib similarity (cutoff=0.72).
    assert _match_known_assignee("Zachary") == "Zachary"
