"""
Tamper-Evident Audit Chain for NEXUS (per-tenant partitioning)
==============================================================

HMAC-signed, hash-chained audit entries. Each entry contains:
- entry_hash: SHA256 of entry content (without chain fields)
- chain_hash: HMAC-SHA256(previous_chain_hash + entry_hash)
- sequence: monotonic counter per user

Tampering with any entry breaks that user's chain detectably.

Per-tenant partitioning (2026-05-12, V>>-caught leak on free.donnaoss.com /idr):
the chain is now physically partitioned at ``audit_dir/<user_id>/chain.jsonl``
with separate sequence/state files. The SIGNING KEY stays SHARED across
tenants (one key per deployment) so forensic verification across all
tenants remains possible from a single trusted authority.

Empty user_id is rejected on write (raises ValueError) and yields an
empty iterator on read - there is no longer a "global" chain.
"""

import fcntl
import hashlib
import hmac
import json
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

DEFAULT_DATA_DIR = Path.home() / "nexus-poc" / "data"
DEFAULT_AUDIT_DIR = DEFAULT_DATA_DIR / "audit"
DEFAULT_SIGNING_KEY = DEFAULT_AUDIT_DIR / "signing-key"

CHAIN_FIELDS = {"entry_hash", "chain_hash", "sequence"}


@contextmanager
def _file_lock(lock_path: Path):
    """Simple file-based lock using fcntl.flock."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = open(lock_path, "w")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        fd.close()


def _require_user_id(user_id: str) -> str:
    """Reject empty user_id loudly - there is no global chain anymore."""
    if not user_id:
        raise ValueError("user_id required for audit chain")
    return user_id


class AuditChain:
    """Tamper-evident audit chain, physically partitioned per tenant.

    All on-disk artefacts for a given ``user_id`` live under
    ``audit_dir/<user_id>/``: the JSONL log, the chain-state file, and
    the lock file. The signing key is shared at ``signing_key_path`` so
    a single deployment-wide authority can verify any tenant's chain.
    """

    def __init__(
        self,
        audit_dir: Path = None,
        signing_key_path: Path = None,
        log_path: Path = None,
        chain_state_path: Path = None,
        lock_path: Path = None,
    ):
        if log_path is not None and audit_dir is None:
            audit_dir = Path(log_path).parent
        self.audit_dir = Path(audit_dir) if audit_dir else DEFAULT_AUDIT_DIR
        self.signing_key_path = signing_key_path or DEFAULT_SIGNING_KEY
        self.log_path = log_path
        self.chain_state_path = chain_state_path
        self.lock_path = lock_path

    def _tenant_dir(self, user_id: str) -> Path:
        _require_user_id(user_id)
        return self.audit_dir / user_id

    def _log_path(self, user_id: str) -> Path:
        return self._tenant_dir(user_id) / "chain.jsonl"

    def _state_path(self, user_id: str) -> Path:
        return self._tenant_dir(user_id) / "chain-state.json"

    def _lock_path_for(self, user_id: str) -> Path:
        return self._tenant_dir(user_id) / "chain.lock"

    def _ensure_signing_key(self) -> bytes:
        if self.signing_key_path.exists():
            return self.signing_key_path.read_bytes()
        key = os.urandom(32)
        self.signing_key_path.parent.mkdir(parents=True, exist_ok=True)
        self.signing_key_path.write_bytes(key)
        os.chmod(str(self.signing_key_path), 0o600)
        return key

    def _load_chain_state(self, user_id: str) -> dict:
        path = self._state_path(user_id)
        if path.exists():
            try:
                return json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        return {"last_chain_hash": "", "sequence": 0}

    def _save_chain_state(self, user_id: str, state: dict) -> None:
        path = self._state_path(user_id)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(state))
            path.chmod(0o600)
        except OSError:
            pass

    @staticmethod
    def compute_entry_hash(entry: dict) -> str:
        clean = {k: v for k, v in sorted(entry.items()) if k not in CHAIN_FIELDS}
        content = json.dumps(clean, sort_keys=True, separators=(",", ":"))
        return "sha256:" + hashlib.sha256(content.encode()).hexdigest()

    @staticmethod
    def compute_chain_hash(key: bytes, previous_chain_hash: str, entry_hash: str) -> str:
        message = (previous_chain_hash + entry_hash).encode()
        h = hmac.new(key, message, hashlib.sha256)
        return "sha256:" + h.hexdigest()

    def _build_signed_entry(
        self, entry: dict, key: bytes, state: dict
    ) -> tuple[dict, dict]:
        """Pure: take a cleaned entry + state, return signed + new state."""
        sequence = state["sequence"] + 1
        previous_chain_hash = state["last_chain_hash"]
        clean_entry = {k: v for k, v in entry.items() if k not in CHAIN_FIELDS}
        entry_hash = self.compute_entry_hash(clean_entry)
        chain_hash = self.compute_chain_hash(key, previous_chain_hash, entry_hash)
        signed = dict(clean_entry)
        signed["entry_hash"] = entry_hash
        signed["chain_hash"] = chain_hash
        signed["sequence"] = sequence
        new_state = {"last_chain_hash": chain_hash, "sequence": sequence}
        return signed, new_state

    def _append_signed(self, user_id: str, signed: dict) -> None:
        log_path = self._log_path(user_id)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a") as f:
            f.write(json.dumps(signed, default=str) + "\n")

    def _append_unsigned_fallback(self, user_id: str, entry: dict) -> None:
        """Last-resort write so an entry is never silently dropped."""
        try:
            log_path = self._log_path(user_id)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a") as f:
                f.write(json.dumps(entry, default=str) + "\n")
        except Exception:
            pass

    def sign_and_append(
        self, entry: dict, user_id: str = "", payload: dict | None = None
    ) -> dict:
        """Atomically sign ``entry`` into ``user_id``'s tenant chain."""
        _require_user_id(user_id)
        if payload:
            entry = {**entry, **payload}
        try:
            key = self._ensure_signing_key()
            with _file_lock(self._lock_path_for(user_id)):
                state = self._load_chain_state(user_id)
                signed, new_state = self._build_signed_entry(entry, key, state)
                self._append_signed(user_id, signed)
                self._save_chain_state(user_id, new_state)
            return signed
        except ValueError:
            raise
        except Exception:
            self._append_unsigned_fallback(user_id, entry)
            return entry

    def read_chain(self, user_id: str) -> Iterator[dict]:
        """Yield every parsed entry from ``user_id``'s chain. Empty if none."""
        if not user_id:
            return
        log_path = self._log_path(user_id)
        if not log_path.exists():
            return
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue

    @staticmethod
    def _empty_verify_result() -> dict:
        return {
            "valid": True, "total_entries": 0, "signed_entries": 0,
            "unsigned_entries": 0, "first_break": None,
            "break_reason": None, "last_sequence": 0,
        }

    def _check_entry(
        self, entry: dict, key: bytes, previous_chain_hash: str, expected_sequence: int
    ) -> tuple[bool, str | None]:
        """Pure per-entry validation. Returns (ok, break_reason)."""
        seq = entry.get("sequence", 0)
        expected_entry_hash = self.compute_entry_hash(entry)
        if entry["entry_hash"] != expected_entry_hash:
            return False, f"entry_hash mismatch at sequence {seq}"
        expected_chain_hash = self.compute_chain_hash(
            key, previous_chain_hash, entry["entry_hash"]
        )
        if entry["chain_hash"] != expected_chain_hash:
            return False, f"chain_hash mismatch at sequence {seq}"
        if seq != expected_sequence:
            return False, f"sequence gap at {seq}, expected {expected_sequence}"
        return True, None

    def verify_chain(self, user_id: str) -> dict:
        """Walk ``user_id``'s chain and report HMAC integrity."""
        _require_user_id(user_id)
        log_path = self._log_path(user_id)
        if not log_path.exists():
            return self._empty_verify_result()
        key = self._ensure_signing_key()
        total = signed = unsigned = 0
        previous_chain_hash = ""
        expected_sequence = 1
        first_break: int | None = None
        break_reason: str | None = None
        for entry in self.read_chain(user_id):
            total += 1
            if "entry_hash" not in entry or "chain_hash" not in entry:
                unsigned += 1
                continue
            signed += 1
            ok, reason = self._check_entry(
                entry, key, previous_chain_hash, expected_sequence
            )
            if not ok:
                if first_break is None:
                    first_break = entry.get("sequence", 0)
                    break_reason = reason
                continue
            previous_chain_hash = entry["chain_hash"]
            expected_sequence = entry["sequence"] + 1
        return {
            "valid": first_break is None, "total_entries": total,
            "signed_entries": signed, "unsigned_entries": unsigned,
            "first_break": first_break, "break_reason": break_reason,
            "last_sequence": expected_sequence - 1,
        }

    def verify(self, user_id: str = "", verbose: bool = False) -> dict:
        """Back-compat: per-tenant verify when user_id supplied; empty otherwise."""
        if not user_id:
            return self._empty_verify_result()
        return self.verify_chain(user_id)


def _cli_main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python3 audit_chain.py [verify <user_id>|status <user_id>]")
        return 0
    cmd = sys.argv[1]
    chain = AuditChain()
    if cmd == "verify":
        user_id = sys.argv[2] if len(sys.argv) > 2 else ""
        result = chain.verify(user_id=user_id)
        label = user_id or "EMPTY"
        print(f"Chain ({label}): {'VERIFIED' if result['valid'] else 'BROKEN'}")
        print(f"Entries: {result['total_entries']} ({result['signed_entries']} signed)")
        return 0 if result["valid"] else 1
    if cmd == "status":
        user_id = sys.argv[2] if len(sys.argv) > 2 else ""
        state = chain._load_chain_state(user_id) if user_id else {"sequence": 0}
        present = "present" if chain.signing_key_path.exists() else "missing"
        print(f"Sequence: {state['sequence']}, Key: {present}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(_cli_main())
