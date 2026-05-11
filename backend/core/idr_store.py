"""
IDR Store — tamper-evident append-only store for Intent Decision Records.

Composes ``AuditChain`` with a dedicated log path, signing key, and chain
state so IDRs live in their own isolated HMAC chain, separate from the
general routing audit log. Verification walks the chain the same way.

Usage:

    from core.idr_store import IDRStore
    from core.intent_decision_record import (
        IntentDecisionRecord, DecisionPoint, CouncilVote, SynthesisMethod,
    )

    store = IDRStore(data_dir)
    idr = IntentDecisionRecord(
        decision_point=DecisionPoint.SENSITIVITY_CLASSIFICATION,
        input_hash=IntentDecisionRecord.hash_input(doc_text),
        input_summary="NDA draft from Acme Corp",
        decision="confidential",
        confidence=0.87,
        confidence_rationale="2/3 council agreement on confidential",
        reasoning="Dense PII + attorney-client privilege markers",
        council_votes=[...],
        synthesis_method=SynthesisMethod.MAJORITY_VOTE,
        falsification_criterion="Human review confirms no PII or privileged content",
    )
    signed = store.append(idr)                  # writes to disk, returns signed dict
    recent = store.list_recent(limit=20)        # list last 20 IDRs
    matches = store.find_by_input_hash(hash)    # lookup IDRs for a specific input
    result = store.verify()                     # HMAC chain integrity check
"""

import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Optional

from core.audit_chain import AuditChain
from core.idr_happi import HappiChain
from core.intent_decision_record import IntentDecisionRecord

logger = logging.getLogger(__name__)


def _idr_to_happi_fields(idr: IntentDecisionRecord) -> tuple[str, float, dict]:
    """Map a rich nexus IDR to happi/1.1 wire fields.

    Returns ``(intent, confidence, metadata)`` where ``intent`` is the
    human-readable summary and every other nexus field is nested under
    ``metadata`` so the wire stays canonical-payload-compatible with
    donna-legal/bin/notarise.
    """
    intent = (
        f"{idr.decision_point.value}: {idr.decision} "
        f"(input={idr.input_summary[:80]})"
    )
    metadata = {
        "nexus_idr_id": idr.idr_id,
        "decision_point": idr.decision_point.value,
        "input_hash": idr.input_hash,
        "input_summary": idr.input_summary,
        "decision": idr.decision,
        "confidence_rationale": idr.confidence_rationale,
        "reasoning": idr.reasoning,
        "council_votes": [v.model_dump(mode="json") for v in idr.council_votes],
        "synthesis_method": idr.synthesis_method.value,
        "falsification_criterion": idr.falsification_criterion,
        "falsification_status": idr.falsification_status.value,
        "falsification_evidence": idr.falsification_evidence,
        "user_metadata": idr.metadata,
    }
    return intent, idr.confidence, metadata


class IDRStore:
    """Append-only, HMAC-chained store for Intent Decision Records.

    Sprint B alignment (2026-05-11): every append also mirrors to a parallel
    ``HappiChain`` (happi/1.1 wire format, OSS-verifiable via
    chiefofstaff-legal/donna · bin/notarise). Reads keep using the legacy
    NEXUS-schema log; mirror failures log a warning but do not block the
    canonical write. Full cut-over is Sprint C.
    """

    def __init__(self, data_dir: Path):
        idr_dir = data_dir / "idr"
        self._log_path = idr_dir / "idrs.jsonl"
        self._chain = AuditChain(
            log_path=self._log_path,
            signing_key_path=idr_dir / "signing-key",
            chain_state_path=idr_dir / "chain-state.json",
            lock_path=idr_dir / "chain.lock",
        )
        self._happi_chain = HappiChain(
            log_path=idr_dir / "idrs-happi.jsonl",
            signer="nexus-bot",
            chain_state_path=idr_dir / "happi-chain-state.json",
            lock_path=idr_dir / "happi-chain.lock",
            signing_key_path=idr_dir / "happi-signing-key",
        )

    def append(self, idr: IntentDecisionRecord) -> dict:
        """Sign the IDR and append to the chain. Returns the signed dict.

        Also mirrors to the happi/1.1 chain (non-blocking — mirror failures
        log a warning but do not affect the canonical write).
        """
        signed = self._chain.sign_and_append(idr.model_dump(mode="json"))
        try:
            intent, confidence, metadata = _idr_to_happi_fields(idr)
            self._happi_chain.sign_and_append(intent, confidence, metadata)
        except Exception as exc:  # noqa: BLE001 — mirror must never break the canonical write
            logger.warning("happi/1.1 mirror failed for idr %s: %s", idr.idr_id, exc)
        return signed

    def verify_happi(self) -> dict:
        """Walk the happi/1.1 mirror chain and report HMAC integrity.

        Surfaces the OSS-protocol-compatible chain status alongside the
        legacy ``verify()``. Returns the same shape so callers can switch
        when the cut-over completes.
        """
        return self._happi_chain.verify()

    def _iter_entries(self) -> Iterator[dict]:
        """Yield every parsed IDR from the log, skipping blank or malformed lines."""
        if not self._log_path.exists():
            return
        with open(self._log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue

    def list_recent(self, limit: int = 20) -> list[dict]:
        """Return the last ``limit`` IDRs in reverse chronological order."""
        entries = list(self._iter_entries())
        return list(reversed(entries[-limit:]))

    def find_by_input_hash(self, input_hash: str) -> list[dict]:
        """Return all IDRs matching the given input_hash (for dedup + lookup)."""
        return [e for e in self._iter_entries() if e.get("input_hash") == input_hash]

    def get_by_sequence(self, sequence: int) -> Optional[dict]:
        """Return the IDR at a specific chain sequence number, or None."""
        return next((e for e in self._iter_entries() if e.get("sequence") == sequence), None)

    def find_reviews_for(self, sequence: int) -> list[dict]:
        """Return every review IDR that targets the given sequence number.

        Review IDRs are append-only records with
        ``decision_point == 'falsification_review'`` and
        ``metadata.reviews_sequence == <target>``. Multiple reviews for
        the same target are permitted — the latest review by timestamp
        is the effective verdict. Walking forward is O(n) but the IDR
        log is small enough that this is fine for the MVP.
        """
        return [
            e
            for e in self._iter_entries()
            if e.get("decision_point") == "falsification_review"
            and (e.get("metadata") or {}).get("reviews_sequence") == sequence
        ]

    def effective_status(self, entry: dict) -> tuple[str, Optional[dict]]:
        """Derive (status, latest_review) for an entry by walking reviews.

        If no review IDR targets this entry's sequence, returns the
        entry's own ``falsification_status`` (usually ``pending``) and
        None. Otherwise returns the latest review's ``decision`` value
        and the review entry itself so the UI can render the reviewer,
        the notes, and the review timestamp.
        """
        seq = entry.get("sequence")
        if seq is None:
            return entry.get("falsification_status", "pending"), None
        reviews = self.find_reviews_for(seq)
        if not reviews:
            return entry.get("falsification_status", "pending"), None
        latest = max(reviews, key=lambda r: r.get("timestamp", ""))
        return latest.get("decision", "inconclusive"), latest

    def verify(self) -> dict:
        """Walk the IDR chain and report HMAC integrity."""
        return self._chain.verify()
