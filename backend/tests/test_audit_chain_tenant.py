"""Tests for per-tenant AuditChain partitioning.

Closes the cross-tenant audit leak V>> caught on free.donnaoss.com /idr
(2026-05-12). The chain is now physically partitioned at
``audit_dir/<user_id>/chain.jsonl`` with separate sequence/state files.

Goodhart-proof: each test inspects ON-DISK artefacts and chain HASHES,
not call counts. A test that always passes is worse than no test.
"""

from __future__ import annotations

import pytest

from core.audit_chain import AuditChain


@pytest.fixture()
def chain(tmp_path):
    """Fresh ``AuditChain`` rooted in tmp_path; shared signing key by design."""
    return AuditChain(
        audit_dir=tmp_path / "audit",
        signing_key_path=tmp_path / "audit" / "signing-key",
    )


def test_two_users_separate_chains(chain, tmp_path):
    """Goodhart-proof: counts AND chain hashes are independent per user.

    A bug like ``sequence is global`` or ``chain_hash carries across
    tenants`` would either (a) yield the same hash on both sides, or
    (b) cause the per-user sequence to overshoot. Both are caught.
    """
    for i in range(3):
        chain.sign_and_append({"event": "a", "i": i}, user_id="user_a")
    for i in range(2):
        chain.sign_and_append({"event": "b", "i": i}, user_id="user_b")

    a_entries = list(chain.read_chain("user_a"))
    b_entries = list(chain.read_chain("user_b"))

    assert len(a_entries) == 3, f"user_a should see 3, got {len(a_entries)}"
    assert len(b_entries) == 2, f"user_b should see 2, got {len(b_entries)}"

    # Each user's sequence starts at 1 and is monotonic.
    assert [e["sequence"] for e in a_entries] == [1, 2, 3]
    assert [e["sequence"] for e in b_entries] == [1, 2]

    # Chain HASHES (not just counts) must differ. If they were derived
    # from a shared previous_chain_hash, the first entry of both would
    # collide (empty previous + same entry hash) — that would be the
    # leak shape we're guarding against. Differentiate by event field.
    assert a_entries[-1]["chain_hash"] != b_entries[-1]["chain_hash"]
    # Both chains verify independently (mutation-proof: a corrupted
    # state file would cause verify to report invalid).
    assert chain.verify_chain("user_a")["valid"] is True
    assert chain.verify_chain("user_b")["valid"] is True


def test_empty_user_id_rejected(chain):
    """Goodhart-proof: a chain that accepts empty user_id is the leak.

    The pre-2026-05-12 chain wrote every entry to ONE global log when
    no user_id was threaded through. Empty user_id MUST raise so
    legacy call sites cannot silently regress.
    """
    with pytest.raises(ValueError, match="user_id required"):
        chain.sign_and_append({"event": "x"}, user_id="")

    # Default kwarg also rejected — no implicit fallthrough.
    with pytest.raises(ValueError, match="user_id required"):
        chain.sign_and_append({"event": "x"})


def test_fresh_user_sees_empty_chain(chain):
    """A brand-new user_id reads [] immediately and has state seq=0.

    Goodhart-proof: the test inspects both the iterator AND the
    on-disk state. A bug that "preloads" the global chain into every
    new tenant would show up as either non-empty entries OR a
    non-zero sequence on the very first read.
    """
    entries = list(chain.read_chain("brand-new-user-uid"))
    assert entries == []

    state = chain._load_chain_state("brand-new-user-uid")
    assert state["sequence"] == 0
    assert state["last_chain_hash"] == ""

    # verify_chain on an unused user returns the empty-result shape,
    # not a stale verdict from another user's chain.
    result = chain.verify_chain("brand-new-user-uid")
    assert result == {
        "valid": True,
        "total_entries": 0,
        "signed_entries": 0,
        "unsigned_entries": 0,
        "first_break": None,
        "break_reason": None,
        "last_sequence": 0,
    }


def test_tampering_user_a_does_not_break_user_b(chain, tmp_path):
    """Corrupt user_a's chain; user_b's verify MUST still pass.

    Goodhart-proof: this is the core forensic property — a tenant
    whose log is tampered with cannot poison another tenant's chain.
    The test mutates the on-disk log directly, not via API.
    """
    chain.sign_and_append({"event": "real", "n": 1}, user_id="user_a")
    chain.sign_and_append({"event": "real", "n": 2}, user_id="user_a")
    chain.sign_and_append({"event": "real", "n": 1}, user_id="user_b")
    chain.sign_and_append({"event": "real", "n": 2}, user_id="user_b")

    # Tamper user_a by rewriting one entry's payload (chain_hash now
    # mismatches because the entry_hash changes).
    a_log = chain._log_path("user_a")
    lines = a_log.read_text().splitlines()
    # Corrupt the FIRST line — guarantees the chain breaks immediately.
    lines[0] = lines[0].replace('"real"', '"tampered"')
    a_log.write_text("\n".join(lines) + "\n")

    a_verify = chain.verify_chain("user_a")
    b_verify = chain.verify_chain("user_b")

    assert a_verify["valid"] is False, "tampering user_a must be detectable"
    assert a_verify["first_break"] == 1
    assert "entry_hash mismatch" in (a_verify["break_reason"] or "")

    # user_b's chain is physically untouched — verify must still pass.
    assert b_verify["valid"] is True, (
        f"user_b chain wrongly invalidated by user_a tampering: {b_verify}"
    )
    assert b_verify["total_entries"] == 2
    assert b_verify["signed_entries"] == 2


def test_chain_files_physically_partitioned(chain, tmp_path):
    """The on-disk layout itself is the strongest tenancy guarantee.

    Goodhart-proof: if a future refactor reverts to a single
    ``audit/chain.jsonl``, every tenant's entries would be in that
    one file. This test asserts the per-user directories exist and
    do not cross-contaminate.
    """
    chain.sign_and_append({"event": "only_a", "secret": "alpha"}, user_id="user_a")
    chain.sign_and_append({"event": "only_b", "secret": "bravo"}, user_id="user_b")

    a_log = tmp_path / "audit" / "user_a" / "chain.jsonl"
    b_log = tmp_path / "audit" / "user_b" / "chain.jsonl"

    assert a_log.exists(), f"user_a log missing at {a_log}"
    assert b_log.exists(), f"user_b log missing at {b_log}"

    a_text = a_log.read_text()
    b_text = b_log.read_text()

    # The leak shape we're defending against: B's secret appearing in
    # A's log (or vice versa). On-disk byte-level check.
    assert "alpha" in a_text, "user_a's own entry missing from their log"
    assert "alpha" not in b_text, "user_a's entry leaked into user_b's log"
    assert "bravo" in b_text, "user_b's own entry missing from their log"
    assert "bravo" not in a_text, "user_b's entry leaked into user_a's log"

    # State files are also per-tenant.
    assert (tmp_path / "audit" / "user_a" / "chain-state.json").exists()
    assert (tmp_path / "audit" / "user_b" / "chain-state.json").exists()

    # Shared signing key lives at the top of audit_dir — one per
    # deployment, NOT one per tenant (forensic verification across
    # tenants must remain possible from a single trusted authority).
    assert (tmp_path / "audit" / "signing-key").exists()
