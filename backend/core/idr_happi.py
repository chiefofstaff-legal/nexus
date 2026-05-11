"""
happi/1.1 IDR chain — nexus-poc reference implementation.

Sprint B alignment: nexus-poc emits IDR records in the OSS happi/1.1 wire
format (per chiefofstaff-legal/donna ·  bin/notarise). The proprietary
NEXUS IDR semantics — council votes, synthesis method, falsification
status — are nested under `metadata` so the wire-level chain remains
verifiable by ANY happi/1.1 verifier (donna-legal/bin/notarise,
donna-legal/web/lib/idr.js) while preserving nexus's rich audit shape.

Protocol reference:
- happi.md v1.1 spec: https://gist.github.com/architext1/808548dd25cfac5cc47fb6e910b79292
- OSS reference impl: github.com/chiefofstaff-legal/donna · bin/notarise

Cross-verification: a chain produced by HappiChain.sign_and_append can be
verified by donna-legal/bin/notarise verify --chain PROBAT.md (and the
JS port at donna-legal/web/lib/idr.js). See tests/test_idr_happi_parity.py.

Stdlib-only, no external dependencies. Mirrors the canonical payload rules
of donna-legal/bin/notarise byte-for-byte (sort_keys=True, separators=(',',':'),
UTF-8 encoding). The same DONNA_NOTARISE_KEY env var is read so a firm's
single signing secret covers both OSS demos and NEXUS production records.
"""

from __future__ import annotations

import fcntl
import hashlib
import hmac
import json
import os
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Optional

# ─── happi/1.1 protocol constants (must match donna-legal/bin/notarise) ──
GENESIS_PREVIOUS_HASH = "0" * 64
PROTOCOL_VERSION = "happi/1.1"
SIGNATURE_ALGORITHM = "HMAC-SHA256"
SIGNING_KEY_ENV = "DONNA_NOTARISE_KEY"  # OSS-compatible env var name
FALLBACK_KEY_FILENAME = "happi-signing-key"  # used when env var unset


@dataclass
class HappiIDR:
    """happi/1.1 IDR — wire-level structure.

    Field order is fixed; canonical_payload uses sort_keys so callers do
    not need to preserve insertion order, but the dataclass shape matches
    donna-legal/bin/notarise so a JSON dump round-trips byte-identically.
    """

    decision_id: str
    timestamp: str
    protocol: str
    intent: str
    signer: str
    confidence: float
    previous_hash: str
    metadata: dict
    signature: str = ""

    def canonical_payload(self) -> bytes:
        """Stable JSON serialisation of every field except `signature`.

        Mirrors donna-legal/bin/notarise.IDR.canonical_payload byte-for-byte.
        The signature signs this payload; any verifier reproducing the same
        canonical form will get the same HMAC.
        """
        d = asdict(self)
        d.pop("signature", None)
        return json.dumps(d, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def hash(self) -> str:
        """SHA-256 of the canonical payload (used as `previous_hash` for the next IDR)."""
        return hashlib.sha256(self.canonical_payload()).hexdigest()


@contextmanager
def _file_lock(lock_path: Path):
    """fcntl-based exclusive lock (process-level)."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = open(lock_path, "w")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        fd.close()


def _resolve_signing_key(fallback_path: Optional[Path] = None) -> bytes:
    """Resolve the happi/1.1 signing key.

    Resolution order:
    1. `DONNA_NOTARISE_KEY` env var (OSS-compatible — same secret signs
       donna-legal demos AND nexus production records).
    2. `fallback_path` if provided AND exists: read bytes from disk.
    3. `fallback_path` if provided AND missing: generate `os.urandom(32)`,
       persist it with mode 0o600, return it.
    4. No fallback: raise RuntimeError.
    """
    raw = os.environ.get(SIGNING_KEY_ENV)
    if raw:
        return raw.encode("utf-8")
    if fallback_path is None:
        raise RuntimeError(
            f"{SIGNING_KEY_ENV} env var not set and no fallback key path provided. "
            f"For a one-time per-firm secret: "
            f"export {SIGNING_KEY_ENV}=$(openssl rand -hex 32)"
        )
    if fallback_path.exists():
        return fallback_path.read_bytes()
    key = os.urandom(32)
    fallback_path.parent.mkdir(parents=True, exist_ok=True)
    fallback_path.write_bytes(key)
    os.chmod(str(fallback_path), 0o600)
    return key


class HappiChain:
    """Append-only HMAC-chained IDR log emitting happi/1.1 wire records.

    Cross-verifies with donna-legal/bin/notarise (Python) and
    donna-legal/web/lib/idr.js (Node). The chain state is stored in a
    sidecar JSON file so concurrent processes can append safely under
    fcntl.flock.

    The signer string is configurable so different surfaces (nexus-poc,
    donna-bot, mcp-server, etc.) can be distinguished on the same chain.
    """

    def __init__(
        self,
        log_path: Path,
        signer: str = "nexus-bot",
        chain_state_path: Optional[Path] = None,
        lock_path: Optional[Path] = None,
        signing_key_path: Optional[Path] = None,
    ):
        self.log_path = log_path
        self.signer = signer
        base = log_path.parent
        self.chain_state_path = chain_state_path or (base / "happi-chain-state.json")
        self.lock_path = lock_path or (base / "happi-chain.lock")
        self.signing_key_path = signing_key_path or (base / FALLBACK_KEY_FILENAME)

    def _load_state(self) -> dict:
        if self.chain_state_path.exists():
            try:
                return json.loads(self.chain_state_path.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        return {"last_hash": GENESIS_PREVIOUS_HASH, "sequence": 0}

    def _save_state(self, state: dict) -> None:
        self.chain_state_path.parent.mkdir(parents=True, exist_ok=True)
        self.chain_state_path.write_text(json.dumps(state))
        try:
            os.chmod(str(self.chain_state_path), 0o600)
        except OSError:
            pass

    def sign_and_append(
        self,
        intent: str,
        confidence: float,
        metadata: Optional[dict] = None,
        decision_id: Optional[str] = None,
        signer: Optional[str] = None,
    ) -> dict:
        """Sign one happi/1.1 IDR, append to the chain, return signed dict.

        `intent` is the human-readable summary of what's being decided.
        Rich nexus fields (decision_point, council_votes, falsification_*,
        etc.) belong in `metadata` so the wire format stays canonical.
        """
        if not (0.0 <= confidence <= 1.0):
            raise ValueError(f"confidence must be in [0.0, 1.0]; got {confidence}")

        key = _resolve_signing_key(self.signing_key_path)
        with _file_lock(self.lock_path):
            state = self._load_state()
            sequence = state["sequence"] + 1
            previous_hash = state["last_hash"]

            record = HappiIDR(
                decision_id=decision_id or f"idr_{int(time.time() * 1e9)}_{uuid.uuid4().hex[:8]}",
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                protocol=PROTOCOL_VERSION,
                intent=intent,
                signer=signer or self.signer,
                confidence=float(confidence),
                previous_hash=previous_hash,
                metadata=dict(metadata or {}),
            )
            sig = hmac.new(key, record.canonical_payload(), hashlib.sha256).hexdigest()
            record.signature = sig

            signed = asdict(record)
            # Optional convenience field for downstream UIs that want a chain
            # position without re-walking. NOT part of canonical_payload, so
            # it does not affect the signature.
            signed["_chain_sequence"] = sequence

            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_path, "a") as f:
                f.write(json.dumps(signed) + "\n")

            self._save_state({"last_hash": record.hash(), "sequence": sequence})
            return signed

    def iter_records(self) -> Iterable[dict]:
        """Yield every parsed IDR from the log; skips blank/malformed lines."""
        if not self.log_path.exists():
            return
        with open(self.log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue

    def _check_entry(
        self, idx: int, entry: dict, key: bytes, previous_hash: str
    ) -> tuple[bool, Optional[str], str]:
        """Validate one entry against the running chain state.

        Returns ``(is_valid, break_reason, next_previous_hash)``. When
        ``is_valid`` is False, ``break_reason`` carries the diagnostic
        and ``next_previous_hash`` is unchanged so the caller can decide
        how to proceed.
        """
        payload_fields = {
            k: v for k, v in entry.items() if k not in ("signature", "_chain_sequence")
        }
        try:
            record = HappiIDR(**payload_fields)
        except TypeError as exc:
            return False, f"entry {idx}: schema mismatch ({exc})", previous_hash

        expected_sig = hmac.new(key, record.canonical_payload(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected_sig, entry["signature"]):
            return False, f"entry {idx}: signature mismatch", previous_hash

        if record.previous_hash != previous_hash:
            return (
                False,
                f"entry {idx}: chain break — previous_hash expected "
                f"{previous_hash[:8]}…, got {record.previous_hash[:8]}…",
                previous_hash,
            )

        if record.protocol != PROTOCOL_VERSION:
            return (
                False,
                f"entry {idx}: unexpected protocol {record.protocol!r}",
                previous_hash,
            )

        return True, None, record.hash()

    def verify(self) -> dict:
        """Walk the chain, verify every signature + previous_hash link.

        Returns the same shape as the legacy AuditChain.verify so existing
        callers keep working: valid / total_entries / signed_entries /
        unsigned_entries / first_break / break_reason / last_sequence.

        Skips entries without a `signature` field (treats them as
        legacy NEXUS-schema records — counted but not verified).
        """
        empty = {
            "valid": True, "total_entries": 0, "signed_entries": 0,
            "unsigned_entries": 0, "first_break": None,
            "break_reason": None, "last_sequence": 0,
        }
        if not self.log_path.exists():
            return empty

        try:
            key = _resolve_signing_key(self.signing_key_path)
        except RuntimeError as exc:
            return {**empty, "valid": False, "first_break": 0, "break_reason": str(exc)}

        total = signed_count = unsigned = 0
        previous_hash = GENESIS_PREVIOUS_HASH
        first_break: Optional[int] = None
        break_reason: Optional[str] = None

        for idx, entry in enumerate(self.iter_records(), start=1):
            total += 1
            if "signature" not in entry or "previous_hash" not in entry:
                unsigned += 1
                continue
            signed_count += 1
            ok, reason, previous_hash = self._check_entry(idx, entry, key, previous_hash)
            if not ok and first_break is None:
                first_break, break_reason = idx, reason

        return {
            "valid": first_break is None,
            "total_entries": total,
            "signed_entries": signed_count,
            "unsigned_entries": unsigned,
            "first_break": first_break,
            "break_reason": break_reason,
            "last_sequence": total,
        }
