"""
LLM Orchestration Router
=========================

Multi-provider routing with cost optimisation:
1. Groq (free tier) - Llama 3.3 70B for public queries
2. Ollama (local) - Gemma 4 (gemma4:e4b) for confidential data
3. Anthropic (paid) - Claude for complex reasoning only

Sensitivity detection uses spaCy NER + regex PII patterns.
All routing decisions logged to tamper-evident audit chain.
"""

import asyncio
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from core.audit_chain import AuditChain
from core.config import NexusConfig, get_config
from services.types import SensitivityLevel  # canonical home; re-exported for callers

__all__ = ["SensitivityLevel", "RoutingDecision", "LLMRouter"]

# Provider call timeout (seconds). Each individual provider attempt is wrapped
# in asyncio.wait_for with this budget so a stuck network connection cannot
# block the event loop indefinitely. The cascade in route_and_call still tries
# the next provider on TimeoutError, so user-facing latency is bounded by
# (number of attempts) * _PROVIDER_TIMEOUT_S in the worst case.
_PROVIDER_TIMEOUT_S = 30.0


class RoutingDecision(BaseModel):
    sensitivity_level: SensitivityLevel
    sensitivity_score: float = Field(ge=0.0, le=1.0)
    model_used: str
    provider: str
    routing_reason: str
    pii_types_detected: list[str] = Field(default_factory=list)
    latency_ms: float = 0.0
    estimated_cost_usd: float = 0.0
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class LLMRouter:
    """Multi-provider sensitivity-based LLM routing with audit trail.

    Orchestrates PiiDetector (W3 SRP) and SensitivityScorer (W3 SRP);
    owns only model selection, provider dispatch, and audit.
    """

    MODEL_COSTS = {
        "llama-3.3-70b-versatile": 0.0,
        "llama-3.1-8b-instant": 0.0,
        "llama-3.2-3b-preview": 0.0,
        "mistral:7b": 0.0,
        "llama3.1:8b": 0.0,
        "gemma4:e4b": 0.0,
        "claude-haiku-4-5-20251001": 0.001,
        "claude-sonnet-4-6-20260320": 0.003,
    }

    def __init__(
        self,
        data_dir: Path,
        anthropic_client=None,
        config: Optional[NexusConfig] = None,
    ):
        """Construct an LLMRouter.

        Args:
            data_dir: base directory for audit chain artefacts.
            anthropic_client: optional Anthropic SDK client (sync) for paid
                fallback. ``None`` disables the Anthropic path.
            config: typed application config. When ``None`` (default), falls
                back to the global ``get_config()`` cache so existing call
                sites continue to work unchanged. Inject a fresh
                ``NexusConfig`` (or a test double exposing
                ``ollama_enabled`` / ``ollama_base_url`` /
                ``ollama_confidential_model``) to override probe behaviour
                without monkey-patching module globals — see issue #5.
        """
        from services.pii_detector import PiiDetector
        from services.sensitivity_scorer import SensitivityScorer

        self.audit_chain = AuditChain(
            log_path=data_dir / "audit" / "routing-audit.jsonl",
            signing_key_path=data_dir / "audit" / "signing-key",
            chain_state_path=data_dir / "audit" / "routing-chain-state.json",
            lock_path=data_dir / "audit" / "routing-chain.lock",
        )
        self.anthropic_client = anthropic_client
        self._config = config if config is not None else get_config()
        self._pii_detector = PiiDetector()
        self._scorer = SensitivityScorer()
        self._groq_client = None
        self._ollama_available = None

    def _get_groq(self):
        if self._groq_client is None:
            try:
                from groq import Groq
                self._groq_client = Groq()  # reads GROQ_API_KEY from env
            except (ImportError, Exception):
                self._groq_client = False
        return self._groq_client if self._groq_client else None

    def _check_ollama(self) -> bool:
        # Prod gate: if NEXUS_OLLAMA_ENABLED is False, the confidential path
        # never reaches Ollama even if something is listening on the port.
        config = self._config
        if not config.ollama_enabled:
            self._ollama_available = False
            return False
        if self._ollama_available is None:
            try:
                import urllib.request
                req = urllib.request.Request(
                    f"{config.ollama_base_url}/api/tags", method="GET"
                )
                urllib.request.urlopen(req, timeout=2)
                self._ollama_available = True
            except Exception:
                self._ollama_available = False
        return self._ollama_available

    def classify_sensitivity(self, text: str) -> tuple[SensitivityLevel, float, list[str]]:
        """Delegate to PiiDetector + SensitivityScorer (W3 SRP orchestration)."""
        pii_types, pii_count = self._pii_detector.detect(text)
        level, score = self._scorer.score(pii_count, len(text))
        return level, score, list(set(pii_types))

    def select_model(self, sensitivity: SensitivityLevel, task_type: str = "general") -> tuple[str, str]:
        """Cost-optimised model selection: Groq free > Ollama local > Anthropic paid."""
        if sensitivity == SensitivityLevel.CONFIDENTIAL:
            if self._check_ollama():
                return self._config.ollama_confidential_model, "ollama"
            if self._get_groq():
                return "llama-3.1-8b-instant", "groq"
            return "claude-haiku-4-5-20251001", "anthropic"
        elif sensitivity == SensitivityLevel.INTERNAL:
            if self._get_groq():
                return "llama-3.3-70b-versatile", "groq"
            return "claude-haiku-4-5-20251001", "anthropic"
        else:
            if task_type == "reasoning" and self.anthropic_client:
                return "claude-haiku-4-5-20251001", "anthropic"
            if self._get_groq():
                return "llama-3.3-70b-versatile", "groq"
            return "claude-haiku-4-5-20251001", "anthropic"

    async def route_and_call(
        self,
        prompt: str,
        system: str = "",
        task_type: str = "general",
        force_model: Optional[str] = None,
        force_level: Optional[SensitivityLevel] = None,
        user_id: str = "",
    ) -> tuple[str, RoutingDecision]:
        start = time.time()
        if force_level is not None:
            level = force_level
            score = 1.0
            pii_types = []
        else:
            level, score, pii_types = self.classify_sensitivity(prompt)

        if force_model:
            model_id = force_model
            if ":" in force_model:
                provider = "ollama"
            elif any(k in force_model for k in ("llama", "mixtral", "qwen")):
                provider = "groq"
            else:
                provider = "anthropic"
        else:
            model_id, provider = self.select_model(level, task_type)

        # Try the selected provider first; if it errors, cascade through
        # the remaining configured providers so the user never sees a raw
        # error string in the response box. Order of attempts:
        #   1. the provider select_model() / force_model picked
        #   2. anthropic (the reliable paid path)
        #   3. groq (if not already tried)
        # Every attempt is recorded in the audit chain so the cascade is
        # visible to auditors.
        provider_order: list[tuple[str, str]] = [(provider, model_id)]
        if provider != "anthropic" and self.anthropic_client:
            provider_order.append(("anthropic", "claude-haiku-4-5-20251001"))
        if provider != "groq" and self._get_groq():
            provider_order.append(("groq", "llama-3.3-70b-versatile"))

        response_text = ""
        attempt_errors: list[str] = []
        for attempt_provider, attempt_model in provider_order:
            try:
                # Every provider call is wrapped in asyncio.wait_for so a stuck
                # network connection cannot block the event loop indefinitely.
                # On TimeoutError the cascade continues to the next provider.
                if attempt_provider == "groq":
                    response_text = await asyncio.wait_for(
                        self._call_groq(attempt_model, prompt, system),
                        timeout=_PROVIDER_TIMEOUT_S,
                    )
                elif attempt_provider == "ollama":
                    response_text = await asyncio.wait_for(
                        self._call_ollama(attempt_model, prompt, system),
                        timeout=_PROVIDER_TIMEOUT_S,
                    )
                elif attempt_provider == "anthropic":
                    response_text = await asyncio.wait_for(
                        self._call_anthropic(attempt_model, prompt, system),
                        timeout=_PROVIDER_TIMEOUT_S,
                    )
                else:
                    raise RuntimeError(f"unknown provider {attempt_provider}")
                # Success — update the outward-facing provider/model to
                # reflect the one that actually served the request.
                if (attempt_provider, attempt_model) != (provider, model_id):
                    attempt_errors.append(
                        f"recovered via fallback -> {attempt_provider}/{attempt_model}"
                    )
                provider = attempt_provider
                model_id = attempt_model
                break
            except Exception as e:
                attempt_errors.append(
                    f"{attempt_provider}/{attempt_model}: {str(e)[:200]}"
                )
                response_text = ""
        else:
            # Every provider failed — surface a plain-language message
            # with the full attempt trail in the audit chain.
            response_text = (
                "[All providers failed — see the audit trail for the error "
                "chain. The council IDR for this decision is still valid "
                "and signed.]"
            )

        latency_ms = (time.time() - start) * 1000
        token_estimate = len(prompt.split()) + len(response_text.split())
        cost = self.MODEL_COSTS.get(model_id, 0.0) * (token_estimate / 1000)

        decision = RoutingDecision(
            sensitivity_level=level,
            sensitivity_score=score,
            model_used=model_id,
            provider=provider,
            routing_reason=self._format_reason(level, pii_types, model_id, provider),
            pii_types_detected=pii_types,
            latency_ms=round(latency_ms, 1),
            estimated_cost_usd=round(cost, 6),
        )

        # Per-tenant partitioning (2026-05-12): when a caller threads
        # ``user_id`` through, the routing audit lands in that user's
        # chain. Unauthenticated/internal callers (e.g. fixtures that
        # don't simulate a session) skip the audit write rather than
        # crash with ``ValueError``.
        if user_id:
            try:
                self.audit_chain.sign_and_append(
                    {
                        "event": "llm_routing",
                        "sensitivity_level": level.value,
                        "sensitivity_score": score,
                        "model": model_id,
                        "provider": provider,
                        "pii_types": pii_types,
                        "latency_ms": round(latency_ms, 1),
                        "cost_usd": round(cost, 6),
                        "prompt_length": len(prompt),
                        "response_length": len(response_text),
                        "timestamp": decision.timestamp,
                        "provider_cascade": attempt_errors or None,
                    },
                    user_id=user_id,
                )
            except Exception:
                pass

        return response_text, decision

    @staticmethod
    def _build_messages(prompt: str, system: str = "") -> list[dict]:
        """Build the OpenAI/Groq/Ollama-shaped message list (DRY — issue #6).

        Returns a list with an optional ``system`` role prepended, followed
        by the user ``prompt``. Anthropic does NOT use this helper because
        its SDK takes ``system`` as a top-level kwarg rather than a message
        with role=system; see ``_call_anthropic`` below.
        """
        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return messages

    async def _call_groq(self, model: str, prompt: str, system: str = "") -> str:
        """Call Groq API (free tier) without blocking the event loop.

        The ``groq`` SDK's ``chat.completions.create`` is synchronous, so it
        is dispatched to a worker thread via ``asyncio.to_thread`` to avoid
        stalling the asyncio event loop while the HTTPS round-trip runs
        (issue #7).
        """
        client = self._get_groq()
        if not client:
            raise RuntimeError("Groq client not available (check GROQ_API_KEY)")
        messages = self._build_messages(prompt, system)

        def _blocking_call() -> str:
            response = client.chat.completions.create(
                model=model, messages=messages, max_tokens=1000,
            )
            return response.choices[0].message.content

        return await asyncio.to_thread(_blocking_call)

    async def _call_ollama(self, model: str, prompt: str, system: str = "") -> str:
        """Call Ollama at the URL in config, without blocking the event loop."""
        import json
        import urllib.request

        url = f"{self._config.ollama_base_url}/api/chat"
        payload = json.dumps({
            "model": model,
            "messages": self._build_messages(prompt, system),
            "stream": False,
        }).encode()

        def _blocking_call() -> str:
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
                return data.get("message", {}).get("content", "")

        return await asyncio.to_thread(_blocking_call)

    async def _call_anthropic(self, model: str, prompt: str, system: str = "") -> str:
        """Call Anthropic API (paid) without blocking the event loop.

        The injected ``self.anthropic_client`` is the synchronous SDK
        client (per ``app/dependencies.py::get_anthropic_client``), so we
        dispatch the blocking ``messages.create`` call to a worker thread
        via ``asyncio.to_thread`` (issue #7).
        """
        if not self.anthropic_client:
            raise RuntimeError("Anthropic client not available")
        messages = [{"role": "user", "content": prompt}]
        kwargs = {"model": model, "max_tokens": 1000, "messages": messages}
        if system:
            kwargs["system"] = system

        def _blocking_call() -> str:
            response = self.anthropic_client.messages.create(**kwargs)
            return response.content[0].text

        return await asyncio.to_thread(_blocking_call)

    def _format_reason(self, level: SensitivityLevel, pii_types: list[str], model: str, provider: str) -> str:
        pii_str = ", ".join(pii_types[:3]) if pii_types else "none"
        cost_note = "free" if self.MODEL_COSTS.get(model, 0) == 0 else "paid"
        if level == SensitivityLevel.CONFIDENTIAL:
            return f"High sensitivity (PII: {pii_str}) -> {provider}/{model} ({cost_note})"
        elif level == SensitivityLevel.INTERNAL:
            return f"Moderate sensitivity (PII: {pii_str}) -> {provider}/{model} ({cost_note})"
        else:
            return f"No significant PII -> {provider}/{model} ({cost_note})"

    def get_provider_status(self) -> dict:
        return {
            "groq": bool(self._get_groq()),
            "ollama": self._check_ollama(),
            "anthropic": bool(self.anthropic_client),
        }
