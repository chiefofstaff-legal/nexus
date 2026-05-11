"""
happi/1.1 parity tests — nexus-poc IDR chain ⇄ donna-legal/bin/notarise.

These tests prove that nexus-poc's HappiChain produces records that are
verifiable by the OSS reference implementation at
github.com/chiefofstaff-legal/donna · bin/notarise (and the JS port at
donna-legal/web/lib/idr.js).

Three layers of assertions:

1. **Schema parity** — every signed record contains the exact happi/1.1
   field set (decision_id, timestamp, protocol, intent, signer, confidence,
   previous_hash, metadata, signature) with no extras that would break
   donna-legal/bin/notarise's strict `IDR(**d)` constructor.

2. **Cryptographic parity** — given the same key + same record, nexus-poc's
   HMAC-SHA256 signature byte-matches what donna-legal/bin/notarise would
   compute. Independent of donna-legal being installed locally.

3. **Cross-tool parity** (skipped when ``~/donna-legal/bin/notarise`` is
   absent) — a chain signed by nexus is rendered as a PROBAT-style
   markdown file and verified by the actual donna-legal CLI via
   ``subprocess``. The DEMO key is reused so anyone with both repos can
   reproduce.

Goodhart-proof: these tests check the actual bytes on the wire, not call
counts. A signature is either correct or wrong; there is no middle ground
where the test passes with broken logic.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

# Allow imports from backend/ when pytest is invoked from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.idr_happi import (  # noqa: E402
    GENESIS_PREVIOUS_HASH,
    HappiChain,
    HappiIDR,
    PROTOCOL_VERSION,
    SIGNING_KEY_ENV,
)

# Public demo key — distinct from donna-legal's so the two chains stay
# independent, but stable + documented so PROBAT.md verifies anywhere.
DEMO_KEY = "nexus-public-demo-key-2026-05-11"

# happi/1.1 mandatory field set per donna-legal/bin/notarise.IDR @dataclass.
HAPPI_FIELDS = {
    "decision_id",
    "timestamp",
    "protocol",
    "intent",
    "signer",
    "confidence",
    "previous_hash",
    "metadata",
    "signature",
}


@pytest.fixture
def demo_key_env(monkeypatch):
    """Pin the signing key for reproducibility across tests."""
    monkeypatch.setenv(SIGNING_KEY_ENV, DEMO_KEY)


@pytest.fixture
def chain(tmp_path, demo_key_env):
    """Fresh HappiChain backed by a temp directory."""
    return HappiChain(log_path=tmp_path / "idrs-happi.jsonl", signer="nexus-bot")


def _sign_three(chain: HappiChain) -> list[dict]:
    """Sign three sample IDRs and return the resulting list of signed dicts."""
    samples = [
        ("sensitivity_classification: confidential (input=NDA Acme Corp)", 0.92,
         {"decision_point": "sensitivity_classification", "decision": "confidential"}),
        ("llm_routing: ollama (sensitivity=high)", 0.88,
         {"decision_point": "llm_routing", "decision": "ollama"}),
        ("document_classification: nda (input=draft NDA)", 0.95,
         {"decision_point": "document_classification", "decision": "nda"}),
    ]
    return [
        chain.sign_and_append(intent=intent, confidence=conf, metadata=meta)
        for intent, conf, meta in samples
    ]


# ─── Schema parity ────────────────────────────────────────────────────


def test_signed_record_has_exact_happi_fieldset(chain):
    """No extra top-level keys that would break donna-legal/bin/notarise IDR(**d)."""
    signed = chain.sign_and_append(intent="test", confidence=0.5, metadata={})
    canonical = {k: v for k, v in signed.items() if not k.startswith("_")}
    assert set(canonical.keys()) == HAPPI_FIELDS


def test_protocol_field_is_happi_1_1(chain):
    signed = chain.sign_and_append(intent="t", confidence=0.5, metadata={})
    assert signed["protocol"] == PROTOCOL_VERSION == "happi/1.1"


def test_first_record_links_to_genesis(chain):
    signed = chain.sign_and_append(intent="t", confidence=0.5, metadata={})
    assert signed["previous_hash"] == GENESIS_PREVIOUS_HASH
    assert signed["previous_hash"] == "0" * 64


def test_subsequent_record_links_to_prior_hash(chain):
    first = chain.sign_and_append(intent="a", confidence=0.5, metadata={})
    second = chain.sign_and_append(intent="b", confidence=0.5, metadata={})
    record = HappiIDR(**{k: v for k, v in first.items() if k in HAPPI_FIELDS and k != "signature"},
                      signature=first["signature"])
    assert second["previous_hash"] == record.hash()


def test_confidence_out_of_range_rejected(chain):
    with pytest.raises(ValueError, match="confidence must be"):
        chain.sign_and_append(intent="t", confidence=1.5, metadata={})
    with pytest.raises(ValueError):
        chain.sign_and_append(intent="t", confidence=-0.1, metadata={})


# ─── Cryptographic parity ─────────────────────────────────────────────


def _independent_signature(record_fields: dict, key: bytes) -> str:
    """Re-implement donna-legal/bin/notarise's signing in this test so a
    bug in HappiChain cannot be hidden by a matching bug in HappiChain.verify."""
    payload = json.dumps(record_fields, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def test_signature_matches_independent_hmac(chain):
    """Goodhart-proof: a parallel implementation produces the same HMAC."""
    signed = chain.sign_and_append(intent="parity-test", confidence=0.7,
                                   metadata={"k": "v"})
    payload = {k: v for k, v in signed.items() if k in HAPPI_FIELDS and k != "signature"}
    expected = _independent_signature(payload, DEMO_KEY.encode("utf-8"))
    assert signed["signature"] == expected


def test_verify_succeeds_on_clean_chain(chain):
    _sign_three(chain)
    result = chain.verify()
    assert result["valid"] is True
    assert result["total_entries"] == 3
    assert result["signed_entries"] == 3
    assert result["first_break"] is None


def test_verify_detects_tampered_metadata(chain, tmp_path):
    _sign_three(chain)
    path = chain.log_path
    lines = path.read_text().strip().split("\n")
    record = json.loads(lines[1])
    record["metadata"]["decision"] = "TAMPERED"  # silently change a meta field
    lines[1] = json.dumps(record)
    path.write_text("\n".join(lines) + "\n")

    result = chain.verify()
    assert result["valid"] is False
    assert result["first_break"] == 2
    assert "signature mismatch" in (result["break_reason"] or "")


def test_verify_detects_chain_break(chain):
    _sign_three(chain)
    path = chain.log_path
    lines = path.read_text().strip().split("\n")
    record = json.loads(lines[1])
    record["previous_hash"] = "0" * 64  # claim it links to genesis again
    record["signature"] = _independent_signature(
        {k: v for k, v in record.items() if k in HAPPI_FIELDS and k != "signature"},
        DEMO_KEY.encode("utf-8"),
    )
    lines[1] = json.dumps(record)
    path.write_text("\n".join(lines) + "\n")

    result = chain.verify()
    assert result["valid"] is False
    assert result["first_break"] == 2
    assert "chain break" in (result["break_reason"] or "")


# ─── Cross-tool parity (skipped if donna-legal not present) ───────────


DONNA_NOTARISE = Path.home() / "donna-legal" / "bin" / "notarise"


def _emit_probat(chain_records: list[dict], dest: Path) -> None:
    """Render the signed chain as a PROBAT-style markdown file that
    donna-legal/bin/notarise verify --chain can read."""
    blocks: list[str] = []
    for entry in chain_records:
        payload = {k: v for k, v in entry.items() if k in HAPPI_FIELDS}
        blocks.append("```idr\n" + json.dumps(payload, indent=2, sort_keys=True) + "\n```\n")
    dest.write_text("\n".join(blocks))


@pytest.mark.skipif(not DONNA_NOTARISE.exists(),
                    reason="donna-legal repo not present at ~/donna-legal/")
def test_donna_legal_verifies_nexus_chain(chain, tmp_path):
    """Sign 3 IDRs in nexus, render to PROBAT.md, verify via donna-legal CLI."""
    records = _sign_three(chain)
    probat = tmp_path / "PROBAT.md"
    _emit_probat(records, probat)

    result = subprocess.run(
        [sys.executable, str(DONNA_NOTARISE), "verify", "--chain", str(probat)],
        env={**os.environ, SIGNING_KEY_ENV: DEMO_KEY},
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, (
        f"donna-legal/bin/notarise rejected nexus chain:\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "3 record(s) verified" in result.stderr
