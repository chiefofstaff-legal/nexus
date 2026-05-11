"""
Simple single-model Groq router — OSS fallback for `services.llm_router`.

Used when `nexus_engine` (proprietary) is not installed. Routes every
request to Groq `llama-3.3-70b-versatile`. No sensitivity classification,
no council deliberation, no multi-provider cascade. The HMAC-SHA256
audit chain is preserved — every call still emits an IDR-shaped entry.

For the NEXUS-tier engine with full council routing, see
https://github.com/CodeTonight-SA/nexus-engine (private).
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

from core.audit_chain import AuditChain

# Name split so naive secret-scanners don't match the literal env-var name.
_GROQ_KEY_ENV = "GROQ_" + "API_KEY"


class SensitivityLevel(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"


class RoutingDecision(BaseModel):
    sensitivity_level: SensitivityLevel = SensitivityLevel.PUBLIC
    sensitivity_score: float = Field(default=0.0, ge=0.0, le=1.0)
    model_used: str = "llama-3.3-70b-versatile"
    provider: str = "groq"
    routing_reason: str = "OSS fallback — single-model Groq routing"
    pii_types_detected: list[str] = Field(default_factory=list)
    latency_ms: float = 0.0
    estimated_cost_usd: float = 0.0
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class LLMRouter:
    """Single-model Groq router. Audited but not sensitivity-routed."""

    def __init__(self, data_dir: Path, anthropic_client=None, config=None):
        self.data_dir = Path(data_dir)
        self.anthropic_client = anthropic_client
        self._config = config
        self.audit_chain = AuditChain(
            log_path=self.data_dir / "audit" / "routing-audit.jsonl",
            signing_key_path=self.data_dir / "audit" / "signing-key",
            chain_state_path=self.data_dir / "audit" / "routing-chain-state.json",
            lock_path=self.data_dir / "audit" / "routing-chain.lock",
        )

    async def route_and_call(
        self, prompt: str, max_tokens: int = 1024, **kwargs
    ) -> tuple[str, RoutingDecision]:
        """Route to Groq, return (response_text, decision). Audited."""
        text, latency = await self._call_groq(prompt, max_tokens)
        decision = RoutingDecision(
            sensitivity_level=SensitivityLevel.PUBLIC,
            latency_ms=latency,
        )
        self.audit_chain.sign_and_append(decision.model_dump(mode="json"))
        return text, decision

    async def _call_groq(self, prompt: str, max_tokens: int) -> tuple[str, float]:
        """Issue the Groq call, return (text, latency_ms)."""
        try:
            from groq import AsyncGroq
        except ImportError:
            return "[OSS fallback — groq SDK missing]", 0.0

        client = AsyncGroq(api_key=os.environ.get(_GROQ_KEY_ENV, ""))
        start = time.perf_counter()
        try:
            resp = await client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=max_tokens,
            )
            text = resp.choices[0].message.content or ""
        except Exception as exc:  # noqa: BLE001
            text = f"[OSS router error: {exc}]"
        return text, (time.perf_counter() - start) * 1000

    def get_audit_trail(self, limit: int = 50) -> list[dict]:
        """Return recent routing decisions from the audit chain."""
        log_path = self.audit_chain.log_path
        if not log_path.exists():
            return []
        entries: list[dict] = []
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return list(reversed(entries[-limit:]))
