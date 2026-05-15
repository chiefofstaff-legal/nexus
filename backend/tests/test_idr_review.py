"""
W3 — IDR review endpoint + effective status derivation tests.

V>>'s question during the walkthrough: "how does the state change from
PENDING?" The answer W3 ships is: a human reviewer appends a
falsification_review IDR targeting the sequence number. The original
IDR is never mutated (append-only HMAC chain); the effective status
is derived on read by walking forward for any review IDR targeting
the reviewed entry's sequence.

These tests verify:
- IDRStore.effective_status returns the reviewed verdict when a
  review IDR exists, and pending otherwise.
- find_reviews_for correctly matches review IDRs to targets by
  sequence number.
- Multiple reviews surface the latest by timestamp (human-in-the-
  loop can override a prior review by appending a newer one).
"""

from pathlib import Path

import pytest

from core.idr_store import IDRStore
from core.intent_decision_record import (
    DecisionPoint,
    IntentDecisionRecord,
    SynthesisMethod,
)


def _make_target(input_hash: str) -> IntentDecisionRecord:
    return IntentDecisionRecord(
        decision_point=DecisionPoint.SENSITIVITY_CLASSIFICATION,
        input_hash=input_hash,
        input_summary="test document",
        decision="internal",
        confidence=0.82,
        confidence_rationale="unanimous 2/2",
        reasoning="test reasoning",
        synthesis_method=SynthesisMethod.MAJORITY_VOTE,
        falsification_criterion="anthropic: would be public if...",
        metadata={},
    )


def _make_review(target_seq: int, verdict: str, reviewer_id: str,
                 reviewer_label: str = "", notes: str = "") -> IntentDecisionRecord:
    return IntentDecisionRecord(
        decision_point=DecisionPoint.FALSIFICATION_REVIEW,
        input_hash="sha256:test",
        input_summary=f"Review of sequence {target_seq}",
        decision=verdict,
        confidence=1.0,
        confidence_rationale=f"review by {reviewer_id}",
        reasoning=notes or f"verdict: {verdict}",
        synthesis_method=SynthesisMethod.DETERMINISTIC,
        falsification_criterion="A second reviewer could reach a different verdict",
        metadata={
            "reviews_sequence": target_seq,
            "reviewer_id": reviewer_id,
            "reviewer_label": reviewer_label,
            "notes": notes,
        },
    )


def test_effective_status_is_pending_when_no_review(tmp_path: Path):
    store = IDRStore(tmp_path)
    target = _make_target("sha256:doc1")
    signed = store.append(target, user_id="test-tenant")
    # refetch so the entry carries the sequence
    entry = store.get_by_sequence(signed["sequence"])
    status, latest = store.effective_status(entry)
    assert status == "pending"
    assert latest is None


def test_effective_status_uses_review_verdict(tmp_path: Path):
    store = IDRStore(tmp_path)
    signed_target = store.append(_make_target("sha256:doc2"), user_id="test-tenant")
    target_seq = signed_target["sequence"]

    store.append(
        _make_review(target_seq, "confirmed", "reviewer-1", notes="looks right"),
        user_id="test-tenant",
    )
    entry = store.get_by_sequence(target_seq)
    status, latest = store.effective_status(entry)
    assert status == "confirmed"
    assert latest is not None
    assert latest["metadata"]["reviewer_id"] == "reviewer-1"


def test_effective_status_latest_wins_on_multiple_reviews(tmp_path: Path):
    store = IDRStore(tmp_path)
    signed_target = store.append(_make_target("sha256:doc3"), user_id="test-tenant")
    target_seq = signed_target["sequence"]

    store.append(
        _make_review(target_seq, "confirmed", "reviewer-1", notes="first pass"),
        user_id="test-tenant",
    )
    # Second review appended later overrides the first
    store.append(
        _make_review(
            target_seq,
            "refuted",
            "reviewer-2",
            reviewer_label="confidential",
            notes="missed PII markers",
        ),
        user_id="test-tenant",
    )
    entry = store.get_by_sequence(target_seq)
    status, latest = store.effective_status(entry)
    assert status == "refuted"
    assert latest["metadata"]["reviewer_label"] == "confidential"


def test_find_reviews_for_only_returns_matching_targets(tmp_path: Path):
    store = IDRStore(tmp_path)
    a_seq = store.append(_make_target("sha256:a"), user_id="test-tenant")["sequence"]
    b_seq = store.append(_make_target("sha256:b"), user_id="test-tenant")["sequence"]

    store.append(_make_review(a_seq, "confirmed", "rev-a"), user_id="test-tenant")
    store.append(
        _make_review(b_seq, "refuted", "rev-b", reviewer_label="public"),
        user_id="test-tenant",
    )
    store.append(_make_review(a_seq, "inconclusive", "rev-c"), user_id="test-tenant")

    a_reviews = store.find_reviews_for(a_seq)
    b_reviews = store.find_reviews_for(b_seq)
    assert len(a_reviews) == 2
    assert len(b_reviews) == 1
    assert b_reviews[0]["decision"] == "refuted"


def test_chain_still_verifies_after_reviews(tmp_path: Path):
    store = IDRStore(tmp_path)
    for i in range(3):
        store.append(_make_target(f"sha256:doc{i}"), user_id="test-tenant")
    store.append(_make_review(1, "confirmed", "rev-1"), user_id="test-tenant")
    store.append(
        _make_review(2, "refuted", "rev-2", reviewer_label="public"),
        user_id="test-tenant",
    )

    result = store.verify()
    assert result["valid"] is True
    assert result["total_entries"] == 5


@pytest.mark.asyncio
async def test_process_writes_two_ingestion_idrs(tmp_path: Path):
    """DocumentProcessor.process should emit vision + classification IDRs
    when an IDR store is injected."""
    from services.document_processor import DocumentProcessor

    store = IDRStore(tmp_path)
    processor = DocumentProcessor(
        data_dir=tmp_path, anthropic_client=None, idr_store=store
    )
    # Construct a tiny plain-text document
    sample = tmp_path / "sample.txt"
    sample.write_text(
        "INTERNAL MEMO\n\nFrom: Alex Morgan\nRe: Globex contract terms",
        encoding="utf-8",
    )
    await processor.process(sample, user_id="test-tenant")

    entries = store.list_recent(limit=50)
    decision_points = {e["decision_point"] for e in entries}
    assert "vision_ocr_provider" in decision_points
    assert "document_classification" in decision_points
    # No classifier client -> fallback heuristic, but the IDR still lands
    doc_idrs = [e for e in entries if e["decision_point"] == "document_classification"]
    assert len(doc_idrs) == 1
    assert "sample.txt" in doc_idrs[0]["metadata"]["filename"]
