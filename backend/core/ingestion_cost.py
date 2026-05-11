"""Ingestion cost meter — tokens per Claude call, persisted as JSONL.

Audit-ready append-only log. Each call appends one JSON line with timestamp,
model, token counts (input + output), and computed CHF cost. Used by the
ingestion pipeline (``document_processor.classify``) and any other
LLM-call wrapper that wants to surface cost.

The log lives in ``data/ingestion-costs.jsonl`` (gitignored — same rule
as ChromaDB and audit logs).

Concurrency: opens the file with ``"a"`` and writes one line atomically
per call. Multiple processes appending interleaved single lines is safe
on POSIX (atomic for writes < PIPE_BUF). For the POC this is sufficient;
production would use a queue.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# CHF per 1M tokens — published Anthropic prices as of 2026-04. Update
# alongside upstream price changes. Approximation only; surface as an
# operator hint, not as a billing line item.
_MODEL_COSTS_CHF_PER_MTOK: dict[str, dict[str, float]] = {
    "claude-haiku-4-5-20251001": {"input": 0.90, "output": 4.50},
    "claude-sonnet-4-6-20250929": {"input": 3.00, "output": 15.00},
}


DEFAULT_LOG_PATH = Path.home() / "nexus-poc" / "data" / "ingestion-costs.jsonl"


def _resolve_log_path(override: Optional[Path]) -> Path:
    if override is not None:
        return Path(override)
    env_value = os.environ.get("NEXUS_INGESTION_COST_LOG")
    if env_value:
        return Path(env_value)
    return DEFAULT_LOG_PATH


def estimate_cost_chf(
    model: str, input_tokens: int, output_tokens: int
) -> float:
    """Return CHF cost for a single Claude call.

    Returns 0.0 for unknown models (don't fail closed — surfacing the call
    in the log is more valuable than blocking on a missing price).
    """
    rates = _MODEL_COSTS_CHF_PER_MTOK.get(model)
    if not rates:
        return 0.0
    return (
        input_tokens * rates["input"] / 1_000_000
        + output_tokens * rates["output"] / 1_000_000
    )


def record_call(
    *,
    model: str,
    input_tokens: int,
    output_tokens: int,
    purpose: str = "",
    document_id: str = "",
    log_path: Optional[Path] = None,
) -> dict:
    """Append one JSONL row describing a Claude call. Returns the row dict.

    Args:
        model: model id (e.g. ``claude-haiku-4-5-20251001``).
        input_tokens: prompt tokens consumed.
        output_tokens: completion tokens produced.
        purpose: short tag (``classify``, ``summary``, ``parse_delegation``).
        document_id: optional document identifier when applicable.
        log_path: override for tests; defaults to the env or built-in path.
    """
    cost_chf = estimate_cost_chf(model, input_tokens, output_tokens)
    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "input_tokens": int(input_tokens),
        "output_tokens": int(output_tokens),
        "cost_chf": round(cost_chf, 6),
        "purpose": purpose,
        "document_id": document_id,
    }
    target = _resolve_log_path(log_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
    return row


def read_all(log_path: Optional[Path] = None) -> list[dict]:
    """Read all rows from the cost log. Empty list if file is absent."""
    target = _resolve_log_path(log_path)
    if not target.exists():
        return []
    rows: list[dict] = []
    with open(target, "r", encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if stripped:
                rows.append(json.loads(stripped))
    return rows
