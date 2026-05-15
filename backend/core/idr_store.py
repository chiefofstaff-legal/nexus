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
    signed = store.append(idr, user_id="acme-tenant")  # writes signed dict
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


_IDR_SHARED_TENANT = "_idrs"
"""IDRs go through a single shared HMAC chain regardless of tenant.

The IDR substrate already tags every entry with ``metadata.tenant_id`` and
``routes_idr.py`` filters reads by ``_belongs_to(entry, user_id)``. The
per-user partitioning that ``AuditChain`` newly enforces is for the
*operational* audit log (document_processed, sop_completed, time_entry,
llm_routing, sharepoint_*). The IDR review trail is intentionally a single
HMAC chain so cross-tenant ordering / review references stay verifiable
end-to-end. Using a fixed tenant slot here keeps the chain physically
inside ``data/idr/_idrs/`` and reuses the new partitioned write/read code
path without inventing a second chain.
"""


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

    def append(self, idr: IntentDecisionRecord, user_id: str) -> dict:
        """Sign the IDR and append to the chain. Returns the signed dict.

        ``user_id`` is the acting tenant. It is stamped into
        ``idr.metadata["tenant_id"]`` here — the single DRY injection
        point — so that ``routes_idr._belongs_to`` can filter list reads
        by tenant. Stamping at this one site (rather than at every
        construction site: routes.py, council.py, document_processor.py,
        sensitivity_classifier.py, the review IDR) is what guarantees
        EVERY persisted IDR is tenant-attributed and therefore visible
        on the /idr page. Injection is additive — any caller-supplied
        metadata is preserved.

        Also mirrors to the happi/1.1 chain (non-blocking — mirror failures
        log a warning but do not affect the canonical write).
        """
        if not user_id:
            raise ValueError("user_id required to append an IDR")
        idr.metadata["tenant_id"] = user_id
        signed = self._chain.sign_and_append(
            idr.model_dump(mode="json"), user_id=_IDR_SHARED_TENANT
        )
        try:
            intent, confidence, metadata = _idr_to_happi_fields(idr)
            self._happi_chain.sign_and_append(intent, confidence, metadata)
        except Exception as exc:  # noqa: BLE001 — mirror must never break the canonical write
            logger.warning("happi/1.1 mirror failed for idr %s: %s", idr.idr_id, exc)
        return signed

    def _verify_happi(self) -> dict:
        """Walk the happi/1.1 mirror chain and report HMAC integrity.

        Private (per ISP gate): direct callers should reach for
        ``store._happi_chain.verify()`` if they truly need the mirror
        chain. The public ``verify()`` is the only surfaced verification
        path — Sprint C will cut over to happi-only and rename then.
        """
        return self._happi_chain.verify()

    @staticmethod
    def _read_records(path: Path) -> list[dict]:
        """Parse every JSON record from a flat ``.jsonl`` file."""
        records: list[dict] = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return records

    def _migrate_legacy_flat_log(self) -> None:
        """One-time, concurrency- and crash-safe fold of the legacy flat
        log into the partition.

        Pre-2026-05-12 deployments wrote IDRs to ``idr/idrs.jsonl`` (flat,
        no per-tenant partition). Post-partitioning, ``verify()`` reads
        ``idr/_idrs/chain.jsonl`` while ``_iter_entries`` was still reading
        the flat file and returning early — list and counter diverged
        (the production "2 entries / empty table" contradiction).

        Re-signing every legacy record into the partition preserves all
        history with no loss: ``AuditChain`` strips only the chain-linkage
        fields (entry_hash/chain_hash/sequence) and re-chains, so decision
        content is byte-preserved and ``verify()`` stays valid and counts
        them. The HMAC re-sign is acceptable — the legacy flat log was
        never per-tenant-verifiable; forensic continuity for the
        partition era is what matters going forward.

        Safety (this runs on the read path of a public endpoint over a
        tamper-evident compliance chain, so it must not duplicate records
        or 500 under concurrent first-loads):

        - ``rename(idrs.jsonl -> idrs.jsonl.migrating)`` is a single
          POSIX-atomic claim. Exactly one caller wins; concurrent callers
          get ``FileNotFoundError`` and return — no double-migration, no
          duplicate audit records, no rename-race 500.
        - A crash after the claim leaves no ``idrs.jsonl`` (it is now
          ``.migrating``), so ``_iter_entries`` will not re-enter the
          migration — no duplicates. The records are preserved on disk
          in ``.migrating`` (recoverable), not lost.
        - Accepted transient: a losing concurrent caller proceeds to read
          a partition the winner may still be filling, so that single
          in-flight request can briefly under-count during the one-time
          sub-second migration. It self-corrects on the next read and is
          strictly better than the prior total-empty bug.
        """
        migrating = self._log_path.with_suffix(".jsonl.migrating")
        try:
            self._log_path.rename(migrating)  # atomic single-winner claim
        except (FileNotFoundError, OSError):
            return  # another caller already claimed/completed the migration
        for record in self._read_records(migrating):
            self._chain.sign_and_append(record, user_id=_IDR_SHARED_TENANT)
        migrating.rename(migrating.with_suffix(".migrated"))

    def _iter_entries(self) -> Iterator[dict]:
        """Yield every parsed IDR from the partitioned chain.

        The partitioned ``data/idr/_idrs/chain.jsonl`` (what ``verify()``
        reads) is the single source of truth. If a legacy flat
        ``idr/idrs.jsonl`` still exists, it is migrated into the
        partition once before reading. Invariant guaranteed by this
        design: ``verify().total_entries == len(list(_iter_entries()))``
        for the same data, because both now read the same partition.
        """
        if self._log_path.exists():
            self._migrate_legacy_flat_log()
        yield from self._chain.read_chain(_IDR_SHARED_TENANT)

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
        """Walk the IDR chain and report HMAC integrity.

        Scoped to the shared IDR tenant slot — see ``_IDR_SHARED_TENANT``
        for why IDRs do not use per-user audit partitioning (the IDR
        substrate tags each entry with ``metadata.tenant_id`` instead).
        """
        return self._chain.verify(user_id=_IDR_SHARED_TENANT)
