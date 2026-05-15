"""
Regression: free.donnaoss.com /idr showed an EMPTY records table while the
header counted entries. Three compounding root causes:

BUG A — every IDR construction site stamped metadata WITHOUT tenant_id, so
        routes_idr._belongs_to filtered every entry out for every user.
BUG B — IDRStore._iter_entries read the legacy flat idrs.jsonl and returned
        early, never reading the partitioned _idrs/chain.jsonl that verify()
        counts — list and counter read different files.
BUG C — voice time-entry + voice delegation emitted NO IntentDecisionRecord,
        so those AI decisions were invisible on the IDR page.

These tests are written FIRST and fail pre-fix (TDD). They assert real
values, not call counts (Goodhart-proof).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.idr_store import IDRStore
from core.intent_decision_record import (
    DecisionPoint,
    IntentDecisionRecord,
    SynthesisMethod,
)


def _make_idr(input_hash: str = "sha256:doc") -> IntentDecisionRecord:
    return IntentDecisionRecord(
        decision_point=DecisionPoint.SENSITIVITY_CLASSIFICATION,
        input_hash=input_hash,
        input_summary="visibility regression doc",
        decision="internal",
        confidence=0.8,
        confidence_rationale="2/2 agreement",
        reasoning="test reasoning",
        synthesis_method=SynthesisMethod.MAJORITY_VOTE,
        falsification_criterion="a reviewer would assign a different label",
        metadata={},
    )


# --- BUG A -------------------------------------------------------------------

def test_appended_idr_is_returned_by_tenant_filtered_list(tmp_path: Path):
    """An IDR appended with user_id='u1' MUST carry metadata.tenant_id='u1'
    so routes_idr._belongs_to(entry, 'u1') matches it.

    Pre-fix: append() did not inject tenant_id, _belongs_to returned False
    for every entry, the list path returned []. This test fails pre-fix.
    """
    from app.routes_idr import _belongs_to

    store = IDRStore(tmp_path)
    store.append(_make_idr("sha256:u1doc"), user_id="u1")

    entries = store.list_recent(limit=10)
    assert entries, "the IDR must be retrievable from the store"
    assert entries[0]["metadata"]["tenant_id"] == "u1"
    assert _belongs_to(entries[0], "u1") is True
    assert _belongs_to(entries[0], "u2") is False


def test_append_does_not_clobber_other_metadata(tmp_path: Path):
    """tenant_id injection is additive — pre-existing metadata survives."""
    store = IDRStore(tmp_path)
    idr = _make_idr("sha256:meta")
    idr.metadata["query"] = "liability clause"
    store.append(idr, user_id="alice")

    entry = store.list_recent(limit=1)[0]
    assert entry["metadata"]["tenant_id"] == "alice"
    assert entry["metadata"]["query"] == "liability clause"


# --- BUG B -------------------------------------------------------------------

def test_verify_total_equals_iter_entries_count_fresh(tmp_path: Path):
    """verify().total_entries MUST equal len(list(_iter_entries())) on a
    fresh (partitioned-only) store."""
    store = IDRStore(tmp_path)
    for i in range(4):
        store.append(_make_idr(f"sha256:fresh{i}"), user_id="u1")

    iter_count = len(list(store._iter_entries()))
    verify_total = store.verify()["total_entries"]
    assert iter_count == 4
    assert verify_total == iter_count, (
        f"verify counts {verify_total} but list yields {iter_count}"
    )


def test_verify_total_equals_iter_entries_with_legacy_flat_log(tmp_path: Path):
    """The exact production bug: a legacy flat data/idr/idrs.jsonl exists
    AND new entries went to the partitioned _idrs chain. verify() counted
    the partition; _iter_entries read only the legacy file. They diverged.

    Post-fix: legacy lines are migrated into the partition, _iter_entries
    reads the partition, and the invariant holds. Fails pre-fix.
    """
    store = IDRStore(tmp_path)
    # Seed the partitioned chain (what verify() reads) with 2 entries.
    store.append(_make_idr("sha256:part1"), user_id="u1")
    store.append(_make_idr("sha256:part2"), user_id="u1")

    # Simulate a legacy flat log left over from a pre-partitioning deploy.
    legacy = tmp_path / "idr" / "idrs.jsonl"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    import json as _json
    with open(legacy, "a", encoding="utf-8") as fh:
        for i in range(3):
            rec = _make_idr(f"sha256:legacy{i}").model_dump(mode="json")
            rec["metadata"]["tenant_id"] = "u1"
            fh.write(_json.dumps(rec) + "\n")

    iter_entries = list(store._iter_entries())
    verify_total = store.verify()["total_entries"]
    # 2 partition + 3 migrated legacy = 5, on BOTH counters.
    assert verify_total == len(iter_entries), (
        f"verify={verify_total} iter={len(iter_entries)} — counters diverge"
    )
    assert verify_total == 5
    # History preserved — no entry lost in migration.
    hashes = {e["input_hash"] for e in iter_entries}
    assert "sha256:part1" in hashes
    assert "sha256:legacy0" in hashes
    assert "sha256:legacy2" in hashes


# --- BUG C -------------------------------------------------------------------

@pytest.fixture()
def client_and_store(tmp_path, monkeypatch):
    """TestClient wired to an isolated IDR store + isolated user store."""
    monkeypatch.setenv("NEXUS_SESSION_SECRET", "test-secret-only-for-pytest")
    monkeypatch.setenv("NEXUS_SESSION_SECURE", "false")
    import app.auth as auth_module

    # app.auth caches the HMAC signing key at module scope. Save, reset,
    # and (in the finally block) restore it so this fixture is a good
    # test-isolation citizen — a stale cached key leaking out of here
    # would 401 whatever TestClient-using test pytest schedules next.
    _saved_signing_key = auth_module._SIGNING_KEY
    auth_module._SIGNING_KEY = None

    isolated_store = IDRStore(tmp_path)

    from fastapi.testclient import TestClient

    from app import routes as routes_module
    from app import routes_idr
    from app.auth import get_data_dir, get_user_store
    from app.main import app
    from services.user_store import UserStore

    monkeypatch.setattr(routes_idr, "_store", isolated_store)
    monkeypatch.setattr(routes_module, "idr_store", isolated_store)

    users = UserStore(tmp_path)
    app.dependency_overrides[get_user_store] = lambda: users
    app.dependency_overrides[get_data_dir] = lambda: tmp_path
    # The FastAPI lifespan sets app.state.user_store ONCE and reuses it
    # across every subsequent TestClient(app) (the app object is a
    # module-level singleton). Without overriding app.state directly,
    # the second test in a run would sign/verify sessions against a
    # stale prior-test UserStore and 401. Save + restore so we are a
    # good test-isolation citizen.
    _saved_user_store = getattr(app.state, "user_store", None)
    _saved_data_dir = getattr(app.state, "data_dir", None)
    app.state.user_store = users
    app.state.data_dir = tmp_path
    try:
        with TestClient(app) as client:
            # Lifespan re-inits app.state.user_store on startup from
            # app.state.data_dir; re-pin to our isolated store so every
            # code path (override AND direct app.state reads) agrees.
            app.state.user_store = users
            yield client, isolated_store
    finally:
        app.dependency_overrides.clear()
        auth_module._SIGNING_KEY = _saved_signing_key
        app.state.user_store = _saved_user_store
        app.state.data_dir = _saved_data_dir


def test_time_capture_emits_retrievable_idr(client_and_store, monkeypatch):
    """POST /api/time/capture MUST produce an IDR retrievable by the acting
    user via /api/idrs/recent. Fails pre-fix (time path wrote only a
    generic operational audit entry, never an IDR)."""
    client, _store = client_and_store

    # Deterministic parse — no network. Patch the transcript parser.
    from services.time_capture import TimeEntry

    def _fake_build(transcript, anthropic_client=None, hourly_rate_chf=400.0):
        return TimeEntry(
            matter="Acme Corp",
            description="drafted NDA",
            duration_minutes=30,
            hourly_rate_chf=hourly_rate_chf,
        )

    monkeypatch.setattr("app.routes.build_entry_from_transcript", _fake_build)

    signup = client.post(
        "/api/auth/signup",
        json={"email": "tina@test.com", "password": "longenough"},
    )
    assert signup.status_code == 200
    uid = signup.json()["id"]

    resp = client.post(
        "/api/time/capture",
        json={"transcript": "30 minutes on the Acme NDA", "hourly_rate_chf": 400.0},
    )
    assert resp.status_code == 200, resp.text

    recent = client.get("/api/idrs/recent?limit=20")
    assert recent.status_code == 200
    entries = recent.json()["entries"]
    assert entries, "time capture must leave an IDR the user can see"
    time_idrs = [
        e for e in entries
        if e["decision_point"] == DecisionPoint.TIME_ENTRY_PARSE.value
    ]
    assert len(time_idrs) == 1
    assert time_idrs[0]["metadata"]["tenant_id"] == uid
    # Real-value assertion (Goodhart-proof): the parsed matter is captured.
    assert "Acme" in time_idrs[0]["input_summary"] or (
        "Acme" in str(time_idrs[0]["metadata"])
    )


def test_delegate_emits_retrievable_idr(client_and_store, monkeypatch):
    """POST /api/tasks/delegate MUST produce an IDR retrievable by the
    acting user. Fails pre-fix (delegate persisted/audited nothing)."""
    client, _store = client_and_store

    from services.task_manager import ParsedDelegation, Priority

    async def _fake_parse(transcript, anthropic_client=None):
        return ParsedDelegation(
            title="Review Globex lease",
            description="check renewal clause",
            assignee="Dana",
            matter="Globex",
            deadline=None,
            priority=Priority.HIGH,
        )

    monkeypatch.setattr("services.task_manager.parse_delegation", _fake_parse)

    signup = client.post(
        "/api/auth/signup",
        json={"email": "dave@test.com", "password": "longenough"},
    )
    assert signup.status_code == 200
    uid = signup.json()["id"]

    resp = client.post(
        "/api/tasks/delegate",
        json={"transcript": "ask Dana to review the Globex lease, high priority"},
    )
    assert resp.status_code == 200, resp.text
    # Preview flow still works — the parsed task comes back unpersisted.
    assert resp.json()["title"] == "Review Globex lease"
    assert resp.json()["assignee"] == "Dana"

    recent = client.get("/api/idrs/recent?limit=20")
    assert recent.status_code == 200
    entries = recent.json()["entries"]
    delegation_idrs = [
        e for e in entries
        if e["decision_point"] == DecisionPoint.TASK_DELEGATION_PARSE.value
    ]
    assert len(delegation_idrs) == 1
    assert delegation_idrs[0]["metadata"]["tenant_id"] == uid
    assert "Globex" in str(delegation_idrs[0]["metadata"]) or (
        "Globex" in delegation_idrs[0]["input_summary"]
    )


# --- BUG B HARDENING: migration must be concurrency- + crash-safe ----------
# This runs on the read path of a public endpoint over a tamper-evident
# compliance chain. The unsafe version (re-migrate whenever idrs.jsonl
# exists, non-atomic) DUPLICATES audit records under repeated/concurrent
# reads and 500s on the rename race. These assert real values (exact
# counts, unique idr_id sets, file state) — Goodhart-proof — and fail
# against the unhardened migration.

import json as _json
import threading


def _seed_legacy(tmp_path: Path, n: int, prefix: str) -> Path:
    legacy = tmp_path / "idr" / "idrs.jsonl"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    with open(legacy, "a", encoding="utf-8") as fh:
        for i in range(n):
            rec = _make_idr(f"sha256:{prefix}{i}").model_dump(mode="json")
            rec["metadata"]["tenant_id"] = "u1"
            fh.write(_json.dumps(rec) + "\n")
    return legacy


def test_migration_idempotent_across_repeated_reads(tmp_path: Path):
    store = IDRStore(tmp_path)
    store.append(_make_idr("sha256:p1"), user_id="u1")
    legacy = _seed_legacy(tmp_path, 3, "lg")

    counts = [len(list(store._iter_entries())) for _ in range(5)]
    assert counts == [4, 4, 4, 4, 4], counts  # migrate exactly once, never grow
    ids = [e.get("idr_id") for e in store._iter_entries()]
    assert len(ids) == len(set(ids)), "duplicate idr_id after repeated reads"
    assert store.verify()["total_entries"] == 4
    assert not legacy.exists()
    assert (tmp_path / "idr" / "idrs.jsonl.migrated").exists()


def test_concurrent_migration_no_duplicate_no_500(tmp_path: Path):
    store = IDRStore(tmp_path)
    store.append(_make_idr("sha256:seed"), user_id="u1")
    _seed_legacy(tmp_path, 5, "c")

    errors: list[str] = []

    def worker() -> None:
        try:
            list(store._iter_entries())
        except Exception as e:  # noqa: BLE001
            errors.append(repr(e))

    ts = [threading.Thread(target=worker) for _ in range(8)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()

    assert errors == [], f"migration raised under concurrency: {errors}"
    final = list(store._iter_entries())
    assert len(final) == 6, [r.get("input_hash") for r in final]
    ids = [e.get("idr_id") for e in final]
    assert len(ids) == len(set(ids)), "duplicate idr_id under concurrent migration"
    assert store.verify()["total_entries"] == 6


def test_crash_after_claim_does_not_duplicate(tmp_path: Path, monkeypatch):
    store = IDRStore(tmp_path)
    store.append(_make_idr("sha256:s"), user_id="u1")
    legacy = _seed_legacy(tmp_path, 3, "k")

    orig = store._chain.sign_and_append
    n = {"i": 0}

    def boom(*a, **k):
        n["i"] += 1
        if n["i"] == 2:
            raise RuntimeError("simulated crash mid-migration")
        return orig(*a, **k)

    monkeypatch.setattr(store._chain, "sign_and_append", boom)
    with pytest.raises(RuntimeError):
        list(store._iter_entries())

    # Atomic claim already renamed idrs.jsonl away → no re-migration path,
    # records preserved on disk in .migrating (recoverable, not lost).
    assert not legacy.exists()
    assert (tmp_path / "idr" / "idrs.jsonl.migrating").exists()

    monkeypatch.setattr(store._chain, "sign_and_append", orig)
    entries = list(store._iter_entries())
    ids = [e.get("idr_id") for e in entries]
    assert len(ids) == len(set(ids)), "crash caused duplicate audit records"
