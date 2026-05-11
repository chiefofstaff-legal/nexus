"""Roster YAML loader.

Externalises the previously-hardcoded ``KNOWN_ASSIGNEES`` tuple and
``_ASSIGNEE_ALIASES`` map from ``services/task_manager.py``. Each tenant
(e.g. Leandro) gets a copy of ``config/roster.yaml`` — onboarding a new
firm requires no backend code change.

Schema (yaml):
    assignees:
      - canonical: <str>
        aliases: [<str>, ...]
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml


DEFAULT_ROSTER_PATH = Path.home() / "nexus-poc" / "config" / "roster.yaml"


class RosterConfigError(ValueError):
    """Raised when the roster YAML is missing, malformed, or empty."""


def _resolve_path(override: Optional[Path]) -> Path:
    return Path(override) if override is not None else DEFAULT_ROSTER_PATH


def _validate(data: object, path: Path) -> list[dict]:
    if not isinstance(data, dict) or "assignees" not in data:
        raise RosterConfigError(
            f"Roster YAML at {path} must have a top-level 'assignees:' key"
        )
    rows = data["assignees"]
    if not isinstance(rows, list) or not rows:
        raise RosterConfigError(
            f"Roster YAML at {path} has no assignees defined"
        )
    return rows


def _row_canonical(row: dict) -> str:
    canonical = str(row.get("canonical", "")).strip()
    if not canonical:
        raise RosterConfigError(f"Roster row missing 'canonical' field: {row!r}")
    return canonical


def _row_alias_pairs(canonical: str, row: dict) -> list[tuple[str, str]]:
    """Return (alias_lower, canonical) pairs for one roster row.

    Single linear pass over a row's aliases — no nesting at module scope.
    """
    pairs = [(canonical.lower(), canonical)]
    pairs.extend(
        (str(alias).strip().lower(), canonical)
        for alias in (row.get("aliases", []) or [])
    )
    return pairs


def load_roster(path: Optional[Path] = None) -> tuple[tuple[str, ...], dict[str, str]]:
    """Read ``config/roster.yaml`` and return (KNOWN_ASSIGNEES, ALIAS_MAP).

    Raises ``RosterConfigError`` if the file is missing or malformed —
    callers must surface this; silent fallback would hide tenant onboarding
    bugs (Rule 19: no issue hierarchy).

    Complexity: O(n) over total alias entries; no nested scanning.
    """
    target = _resolve_path(path)
    if not target.exists():
        raise RosterConfigError(f"Roster YAML not found at {target}")

    with open(target, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    rows = _validate(data, target)
    canonicals = tuple(_row_canonical(r) for r in rows)
    pairs: list[tuple[str, str]] = []
    for canonical, row in zip(canonicals, rows):
        pairs.extend(_row_alias_pairs(canonical, row))
    return canonicals, dict(pairs)
