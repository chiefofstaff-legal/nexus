"""W4 — Ingestion filter tests.

Verifies the pure functions that decide which files reach the indexer:
- ``should_skip_file`` for media, drafts, dotfiles, Office temp files.
- ``find_superseded_versions`` for the ``*_v1`` / ``*_v2`` family.

No I/O — all inputs are bare filename strings.
"""

from __future__ import annotations

import pytest

from services.ingestion_filters import (
    find_superseded_versions,
    should_skip_file,
)


@pytest.mark.parametrize(
    "filename,reason_substring",
    [
        ("video.mp4", "media"),
        ("recording.mov", "media"),
        ("voicemail.mp3", "media"),
        ("audio.wav", "media"),
        ("contract_draft.pdf", "draft"),
        ("report_v1_old.docx", "draft"),
        ("nda_superseded.pdf", "draft"),
        ("important_OLD.pdf", "draft"),
        ("~$word_temp.docx", "draft"),
        (".DS_Store", "dotfile"),
        (".gitignore", "dotfile"),
    ],
)
def test_should_skip_returns_true_with_reason(filename, reason_substring):
    skip, reason = should_skip_file(filename)
    assert skip is True
    assert reason_substring in reason.lower()


@pytest.mark.parametrize(
    "filename",
    [
        "contract.pdf",
        "nda.pdf",
        "report.docx",
        "client_brief.txt",
        "invoice_2026.pdf",
        "matter_helvetica.pdf",
    ],
)
def test_should_skip_returns_false_for_normal_files(filename):
    skip, reason = should_skip_file(filename)
    assert skip is False
    assert reason == ""


def test_should_skip_handles_full_paths():
    """Only the final filename component matters — leading directories ignored."""
    skip, _ = should_skip_file("/tmp/uploads/contract.pdf")
    assert skip is False
    skip, _ = should_skip_file("/tmp/uploads/contract_draft.pdf")
    assert skip is True


def test_find_superseded_returns_lower_versions():
    """v3 is the survivor; v1 and v2 superseded."""
    files = ["contract_v1.pdf", "contract_v2.pdf", "contract_v3.pdf"]
    superseded = find_superseded_versions(files)
    assert superseded == {"contract_v1.pdf", "contract_v2.pdf"}


def test_find_superseded_empty_when_one_version():
    """Goodhart anchor: a single-version 'family' has nothing to supersede."""
    files = ["contract_v1.pdf"]
    assert find_superseded_versions(files) == set()


def test_find_superseded_ignores_non_versioned_files():
    files = ["contract.pdf", "nda.pdf", "report_v1.pdf", "report_v2.pdf"]
    superseded = find_superseded_versions(files)
    assert superseded == {"report_v1.pdf"}


def test_find_superseded_handles_multiple_families():
    files = [
        "contract_v1.pdf", "contract_v2.pdf",
        "nda_v1.docx", "nda_v2.docx", "nda_v3.docx",
    ]
    superseded = find_superseded_versions(files)
    assert superseded == {
        "contract_v1.pdf",
        "nda_v1.docx",
        "nda_v2.docx",
    }


def test_find_superseded_empty_input_returns_empty_set():
    assert find_superseded_versions([]) == set()
