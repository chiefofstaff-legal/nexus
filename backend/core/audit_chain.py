"""
Tamper-Evident Audit Chain for NEXUS
====================================

HMAC-signed, hash-chained audit entries. Each entry contains:
- entry_hash: SHA256 of entry content (without chain fields)
- chain_hash: HMAC-SHA256(previous_chain_hash + entry_hash)
- sequence: monotonic counter

Tampering with any entry breaks the chain detectably.

Ported from GRIP's production audit_chain.py (standalone, no GRIP dependencies).
"""

import fcntl
import hashlib
import hmac
import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path

# Configurable paths (override via environment or constructor)
DEFAULT_DATA_DIR = Path.home() / "nexus-poc" / "data"
DEFAULT_AUDIT_LOG = DEFAULT_DATA_DIR / "audit" / "audit.jsonl"
DEFAULT_SIGNING_KEY = DEFAULT_DATA_DIR / "audit" / "signing-key"
DEFAULT_CHAIN_STATE = DEFAULT_DATA_DIR / "audit" / "chain-state.json"
DEFAULT_LOCK_FILE = DEFAULT_DATA_DIR / "audit" / "chain.lock"

CHAIN_FIELDS = {"entry_hash", "chain_hash", "sequence"}


@contextmanager
def _file_lock(lock_path: Path, timeout: int = 10):
    """Simple file-based lock using fcntl.flock."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = open(lock_path, "w")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        fd.close()


class AuditChain:
    """Standalone tamper-evident audit chain."""

    def __init__(
        self,
        log_path: Path = None,
        signing_key_path: Path = None,
        chain_state_path: Path = None,
        lock_path: Path = None,
    ):
        self.log_path = log_path or DEFAULT_AUDIT_LOG
        self.signing_key_path = signing_key_path or DEFAULT_SIGNING_KEY
        self.chain_state_path = chain_state_path or DEFAULT_CHAIN_STATE
        self.lock_path = lock_path or DEFAULT_LOCK_FILE

    def _ensure_signing_key(self) -> bytes:
        if self.signing_key_path.exists():
            return self.signing_key_path.read_bytes()
        key = os.urandom(32)
        self.signing_key_path.parent.mkdir(parents=True, exist_ok=True)
        self.signing_key_path.write_bytes(key)
        os.chmod(str(self.signing_key_path), 0o600)
        return key

    def _load_chain_state(self) -> dict:
        if self.chain_state_path.exists():
            try:
                return json.loads(self.chain_state_path.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        return {"last_chain_hash": "", "sequence": 0}

    def _save_chain_state(self, state: dict):
        try:
            self.chain_state_path.parent.mkdir(parents=True, exist_ok=True)
            self.chain_state_path.write_text(json.dumps(state))
            self.chain_state_path.chmod(0o600)
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

    def sign_and_append(self, entry: dict) -> dict:
        """Atomically sign an entry and append to the JSONL audit log."""
        try:
            key = self._ensure_signing_key()
            with _file_lock(self.lock_path):
                state = self._load_chain_state()
                sequence = state["sequence"] + 1
                previous_chain_hash = state["last_chain_hash"]

                clean_entry = {k: v for k, v in entry.items() if k not in CHAIN_FIELDS}
                entry_hash = self.compute_entry_hash(clean_entry)
                chain_hash = self.compute_chain_hash(key, previous_chain_hash, entry_hash)

                signed = dict(clean_entry)
                signed["entry_hash"] = entry_hash
                signed["chain_hash"] = chain_hash
                signed["sequence"] = sequence

                self.log_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.log_path, "a") as f:
                    f.write(json.dumps(signed, default=str) + "\n")

                self._save_chain_state({"last_chain_hash": chain_hash, "sequence": sequence})
            return signed
        except Exception:
            try:
                self.log_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.log_path, "a") as f:
                    f.write(json.dumps(entry, default=str) + "\n")
            except Exception:
                pass
            return entry

    def verify(self, verbose: bool = False) -> dict:
        """Walk the audit chain and verify integrity."""
        if not self.log_path.exists():
            return {
                "valid": True, "total_entries": 0, "signed_entries": 0,
                "unsigned_entries": 0, "first_break": None,
                "break_reason": None, "last_sequence": 0,
            }

        key = self._ensure_signing_key()
        total = signed = unsigned = 0
        previous_chain_hash = ""
        expected_sequence = 1
        first_break = None
        break_reason = None

        with open(self.log_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                total += 1
                if "entry_hash" not in entry or "chain_hash" not in entry:
                    unsigned += 1
                    continue

                signed += 1
                seq = entry.get("sequence", 0)

                expected_entry_hash = self.compute_entry_hash(entry)
                if entry["entry_hash"] != expected_entry_hash:
                    if first_break is None:
                        first_break = seq
                        break_reason = f"entry_hash mismatch at sequence {seq}"
                    continue

                expected_chain_hash = self.compute_chain_hash(key, previous_chain_hash, entry["entry_hash"])
                if entry["chain_hash"] != expected_chain_hash:
                    if first_break is None:
                        first_break = seq
                        break_reason = f"chain_hash mismatch at sequence {seq}"
                    continue

                if seq != expected_sequence and first_break is None:
                    first_break = seq
                    break_reason = f"sequence gap at {seq}, expected {expected_sequence}"

                if verbose:
                    print(f"  Line {line_num}: OK (seq {seq})")

                previous_chain_hash = entry["chain_hash"]
                expected_sequence = seq + 1

        return {
            "valid": first_break is None, "total_entries": total,
            "signed_entries": signed, "unsigned_entries": unsigned,
            "first_break": first_break, "break_reason": break_reason,
            "last_sequence": expected_sequence - 1,
        }


if __name__ == "__main__":
    chain = AuditChain()
    if len(sys.argv) < 2:
        print("Usage: python3 audit_chain.py [verify|status|sign <json>]")
        sys.exit(0)

    cmd = sys.argv[1]
    if cmd == "verify":
        result = chain.verify(verbose="--verbose" in sys.argv or "-v" in sys.argv)
        print(f"Chain: {'VERIFIED' if result['valid'] else 'BROKEN'}")
        print(f"Entries: {result['total_entries']} ({result['signed_entries']} signed)")
        sys.exit(0 if result["valid"] else 1)
    elif cmd == "status":
        state = chain._load_chain_state()
        print(f"Sequence: {state['sequence']}, Key: {'present' if chain.signing_key_path.exists() else 'missing'}")
    elif cmd == "sign":
        entry = json.loads(sys.argv[2] if len(sys.argv) > 2 else sys.stdin.read())
        print(json.dumps(chain.sign_and_append(entry)))
