"""Ingestion filters — pure functions deciding which files to skip.

No I/O, no side effects. All rules documented inline.
"""

from __future__ import annotations

import re
from pathlib import Path


# Media formats that cannot be meaningfully indexed as text.
_MEDIA_EXTENSIONS = {".mp4", ".mov", ".avi", ".mp3", ".wav"}

# Filename fragment patterns that signal a draft or superseded document.
_DRAFT_PATTERNS = [
    re.compile(r"_draft", re.IGNORECASE),           # explicit draft suffix
    re.compile(r"_v\d+_old", re.IGNORECASE),        # versioned old copy
    re.compile(r"_superseded", re.IGNORECASE),       # explicitly superseded
    re.compile(r"_OLD", re.IGNORECASE),              # legacy capitalised marker
    re.compile(r"~\$"),                              # Office temporary file prefix
]


def should_skip_file(filename: str) -> tuple[bool, str]:
    """Return (skip, reason) for a single filename.

    Args:
        filename: bare filename or path — only the final component is evaluated.

    Returns:
        A tuple where the first element is True when the file should be
        excluded from ingestion, and the second element is a short human-readable
        reason (empty string when skip is False).
    """
    name = Path(filename).name

    # Dotfiles — system or hidden files have no legal content.
    if name.startswith("."):
        return True, "dotfile"

    # Media extensions — not indexable as text.
    suffix = Path(name).suffix.lower()
    if suffix in _MEDIA_EXTENSIONS:
        return True, f"media extension {suffix}"

    # Draft / superseded / temporary patterns.
    for pattern in _DRAFT_PATTERNS:
        if pattern.search(name):
            return True, f"draft/superseded pattern ({pattern.pattern!r})"

    return False, ""


def find_superseded_versions(filenames: list[str]) -> set[str]:
    """Return the set of filenames that have a higher-version sibling.

    Detects the ``*_v1.pdf`` / ``*_v2.pdf`` … ``*_vN.pdf`` family.
    Any filename whose version number is less than the maximum observed
    version for that base name is considered superseded.

    The highest-versioned file is NOT included — it is the surviving copy.

    Example:
        ['contract_v1.pdf', 'contract_v2.pdf', 'contract_v3.pdf']
        → {'contract_v1.pdf', 'contract_v2.pdf'}

    Returns an empty set when no versioned families are found or when
    a family has only one member (nothing to supersede).
    """
    # Pattern: <base>_v<N><ext>  — anchored at the version marker.
    _VERSION_RE = re.compile(r"^(.+?)_v(\d+)(\.[^.]+)?$", re.IGNORECASE)

    # Group filenames by (base, ext) key.
    families: dict[tuple[str, str], dict[int, str]] = {}
    for name in filenames:
        stem = Path(name).name
        m = _VERSION_RE.match(stem)
        if not m:
            continue
        base, version_str, ext = m.group(1), m.group(2), (m.group(3) or "")
        key = (base.lower(), ext.lower())
        families.setdefault(key, {})[int(version_str)] = stem

    # Hash-based O(n): per family, find max_v then collect non-winners via
    # set difference — one pass each, no nested loops.
    superseded: set[str] = set()
    for versions in families.values():
        if len(versions) < 2:
            continue
        max_v = max(versions)  # O(k) over family size k
        all_names = set(versions.values())
        winner = {versions[max_v]}
        superseded.update(all_names - winner)
    return superseded
