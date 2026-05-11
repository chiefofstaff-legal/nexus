"""W3 — Ingestion cost meter tests.

Verifies:
1. ``record_call`` appends a JSONL row with all required fields.
2. ``estimate_cost_chf`` computes the right CHF cost for known models.
3. Unknown models record a 0.0 cost rather than failing closed.
4. ``read_all`` round-trips multiple appended rows preserving order.
5. The log path can be overridden via the env var or function arg (test isolation).
6. Goodhart guard: cost > 0 for non-trivial input on a known model
   (catches a regression where price tables get accidentally zeroed).
"""

from __future__ import annotations

import json

import pytest

from core.ingestion_cost import (
    estimate_cost_chf,
    read_all,
    record_call,
)


def test_record_call_appends_jsonl_row(tmp_path):
    log = tmp_path / "costs.jsonl"
    row = record_call(
        model="claude-haiku-4-5-20251001",
        input_tokens=1500,
        output_tokens=400,
        purpose="classify",
        document_id="doc_abc",
        log_path=log,
    )
    assert row["model"] == "claude-haiku-4-5-20251001"
    assert row["input_tokens"] == 1500
    assert row["output_tokens"] == 400
    assert row["purpose"] == "classify"
    assert row["document_id"] == "doc_abc"
    assert row["cost_chf"] > 0.0
    assert "ts" in row

    # The JSONL line on disk matches the returned row.
    lines = log.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1
    on_disk = json.loads(lines[0])
    assert on_disk["model"] == row["model"]
    assert on_disk["cost_chf"] == row["cost_chf"]


def test_estimate_cost_haiku_chf_per_million_tokens():
    # Documented price: $0.90/MTok input, $4.50/MTok output for Haiku 4.5.
    # 1M input tokens + 1M output tokens -> 0.90 + 4.50 = 5.40 CHF.
    cost = estimate_cost_chf(
        "claude-haiku-4-5-20251001",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
    )
    assert cost == pytest.approx(5.40, rel=1e-6)


def test_estimate_cost_unknown_model_returns_zero():
    """Unknown model must NOT raise — record the call, surface the gap."""
    cost = estimate_cost_chf("not-a-real-model", input_tokens=10_000, output_tokens=5_000)
    assert cost == 0.0


def test_record_call_unknown_model_still_logs(tmp_path):
    """Goodhart anchor: cost = 0 must NOT swallow the row — observability matters."""
    log = tmp_path / "costs.jsonl"
    row = record_call(
        model="some-future-model",
        input_tokens=100,
        output_tokens=50,
        purpose="experiment",
        log_path=log,
    )
    assert row["cost_chf"] == 0.0
    assert log.exists()
    assert "some-future-model" in log.read_text(encoding="utf-8")


def test_read_all_round_trip(tmp_path):
    log = tmp_path / "costs.jsonl"
    record_call(
        model="claude-haiku-4-5-20251001",
        input_tokens=100, output_tokens=50,
        purpose="classify", log_path=log,
    )
    record_call(
        model="claude-sonnet-4-6-20250929",
        input_tokens=200, output_tokens=80,
        purpose="summary", log_path=log,
    )
    rows = read_all(log)
    assert len(rows) == 2
    assert rows[0]["purpose"] == "classify"
    assert rows[1]["purpose"] == "summary"


def test_read_all_missing_file_returns_empty_list(tmp_path):
    missing = tmp_path / "never-written.jsonl"
    assert read_all(missing) == []


def test_env_override_for_log_path(tmp_path, monkeypatch):
    """NEXUS_INGESTION_COST_LOG env var redirects the default path."""
    env_log = tmp_path / "env-redirect.jsonl"
    monkeypatch.setenv("NEXUS_INGESTION_COST_LOG", str(env_log))
    record_call(
        model="claude-haiku-4-5-20251001",
        input_tokens=10, output_tokens=5,
        purpose="env_test",
    )
    assert env_log.exists()
    assert "env_test" in env_log.read_text(encoding="utf-8")


def test_record_call_goodhart_cost_above_zero_on_real_model(tmp_path):
    """Anchor: a 1k input call on Haiku must record cost > 0.

    Catches the regression where someone zeroes the price table and tests
    pass because they only check 'a row was written'.
    """
    log = tmp_path / "costs.jsonl"
    row = record_call(
        model="claude-haiku-4-5-20251001",
        input_tokens=1000,
        output_tokens=200,
        purpose="classify",
        log_path=log,
    )
    assert row["cost_chf"] > 0.0
