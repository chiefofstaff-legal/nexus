"""Tests for issues #5 / #6 / #7 — LLMRouter config injection, DRY message
helper, and async-safety.

Each test is shaped as a Goodhart-proof assertion: it must fail if the
implementation regresses. The mutation-style checks (a deliberately broken
state must surface in the assertion) are documented inline.
"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# #5 — NexusConfig is injected, not pulled from a global cache
# ---------------------------------------------------------------------------

class TestConfigInjection:
    """Issue #5 — LLMRouter.__init__ accepts a NexusConfig override.

    Mutation criterion: an injected config with ``ollama_enabled=True`` must
    cause a different ``select_model`` decision than the default
    ``ollama_enabled=False`` config — proving the injected value is the one
    actually being read at runtime, not the global ``get_config()`` cache.
    """

    @staticmethod
    def _fake_config(*, ollama_enabled: bool, base_url: str = "http://nope:1") -> SimpleNamespace:
        return SimpleNamespace(
            ollama_enabled=ollama_enabled,
            ollama_base_url=base_url,
            ollama_confidential_model="gemma4:e4b",
        )

    def test_config_kwarg_is_stored_on_instance(self, tmp_path: Path) -> None:
        from services.llm_router import LLMRouter
        cfg = self._fake_config(ollama_enabled=True)
        router = LLMRouter(tmp_path, anthropic_client=None, config=cfg)
        assert router._config is cfg, "injected config must be stored verbatim on the instance"

    def test_default_falls_back_to_get_config(self, tmp_path: Path) -> None:
        """Backward compatibility: existing call sites pass no config kwarg."""
        from services.llm_router import LLMRouter
        from core.config import NexusConfig
        router = LLMRouter(tmp_path, anthropic_client=None)
        assert isinstance(router._config, NexusConfig), (
            "absent config kwarg must fall back to get_config()"
        )

    def test_injected_disabled_config_blocks_ollama_path(self, tmp_path: Path) -> None:
        """Mutation: ollama_enabled=False ⇒ _check_ollama returns False without probing."""
        from services.llm_router import LLMRouter
        cfg = self._fake_config(ollama_enabled=False)
        router = LLMRouter(tmp_path, anthropic_client=None, config=cfg)
        assert router._check_ollama() is False
        # And the result was NOT obtained by network probe — _ollama_available
        # must be set to False directly, not None (which would mean "not yet probed")
        assert router._ollama_available is False

    def test_injected_config_drives_select_model_confidential_path(self, tmp_path: Path) -> None:
        """Goodhart: the model name in select_model() must come from injected config.

        If the implementation regressed to ``get_config().ollama_confidential_model``
        the test would still pass with the default value — so we override the
        injected config's model to a sentinel string and assert it appears in
        the returned tuple. This proves the injected config is the source.
        """
        from services.llm_router import LLMRouter, SensitivityLevel
        cfg = SimpleNamespace(
            ollama_enabled=True,
            ollama_base_url="http://localhost:11434",
            ollama_confidential_model="sentinel-model:99b",
        )
        router = LLMRouter(tmp_path, anthropic_client=None, config=cfg)
        # Force the ollama probe to "succeed" without network access.
        router._ollama_available = True
        model_id, provider = router.select_model(SensitivityLevel.CONFIDENTIAL)
        assert model_id == "sentinel-model:99b"
        assert provider == "ollama"


# ---------------------------------------------------------------------------
# #6 — DRY: _build_messages helper used by groq and ollama paths
# ---------------------------------------------------------------------------

class TestBuildMessagesHelper:
    """Issue #6 — message-list construction is centralised, no duplication."""

    def test_helper_with_system_prompt(self) -> None:
        from services.llm_router import LLMRouter
        msgs = LLMRouter._build_messages("hello", system="be terse")
        assert msgs == [
            {"role": "system", "content": "be terse"},
            {"role": "user", "content": "hello"},
        ]

    def test_helper_without_system_prompt_omits_system_role(self) -> None:
        """Goodhart: empty system string must NOT produce a {role:system,content:''} entry."""
        from services.llm_router import LLMRouter
        msgs = LLMRouter._build_messages("hello", system="")
        assert msgs == [{"role": "user", "content": "hello"}]
        assert all(m["role"] != "system" for m in msgs)

    def test_helper_default_system_is_empty(self) -> None:
        from services.llm_router import LLMRouter
        msgs = LLMRouter._build_messages("hello")
        assert msgs == [{"role": "user", "content": "hello"}]

    def test_helper_returns_a_fresh_list_each_call(self) -> None:
        """Mutation: a cached/shared list would let callers leak state across calls."""
        from services.llm_router import LLMRouter
        a = LLMRouter._build_messages("one", system="sys")
        b = LLMRouter._build_messages("two", system="sys")
        assert a is not b
        a.append({"role": "user", "content": "mutation"})
        assert len(b) == 2, "second call's list must be independent"


# ---------------------------------------------------------------------------
# #7 — async-safety: provider calls do not block the asyncio event loop
# ---------------------------------------------------------------------------

class TestAsyncSafety:
    """Issue #7 — every provider call uses asyncio.to_thread + asyncio.wait_for."""

    @staticmethod
    def _router_with_anthropic_stub(tmp_path: Path, *, sleep_s: float):
        """Build a router whose Anthropic client blocks for ``sleep_s`` seconds."""
        from services.llm_router import LLMRouter

        class _SlowResponse:
            def __init__(self) -> None:
                self.content = [SimpleNamespace(text="slow but ok")]

        class _SlowAnthropic:
            class messages:
                @staticmethod
                def create(**kwargs):
                    time.sleep(sleep_s)  # synchronous block — this is the SDK shape
                    return _SlowResponse()

        cfg = SimpleNamespace(
            ollama_enabled=False,
            ollama_base_url="http://nope:1",
            ollama_confidential_model="gemma4:e4b",
        )
        return LLMRouter(tmp_path, anthropic_client=_SlowAnthropic(), config=cfg)

    def test_call_anthropic_is_awaitable_coroutine(self, tmp_path: Path) -> None:
        """Mutation: a synchronous _call_anthropic would crash the cascade's await."""
        import inspect
        from services.llm_router import LLMRouter
        assert inspect.iscoroutinefunction(LLMRouter._call_anthropic), (
            "_call_anthropic must be an async coroutine for asyncio.wait_for compatibility"
        )

    def test_call_groq_is_awaitable_coroutine(self, tmp_path: Path) -> None:
        import inspect
        from services.llm_router import LLMRouter
        assert inspect.iscoroutinefunction(LLMRouter._call_groq)

    def test_anthropic_call_does_not_block_event_loop(self, tmp_path: Path) -> None:
        """Goodhart: while one anthropic call sleeps for 0.3s, a parallel
        coroutine must still get CPU time. If the event loop were blocked
        the parallel timer would lag by ~0.3s; with to_thread, lag is <0.1s.
        """
        router = self._router_with_anthropic_stub(tmp_path, sleep_s=0.3)

        async def _exercise() -> tuple[str, float]:
            ticks: list[float] = []
            stop = asyncio.Event()

            async def _ticker() -> None:
                while not stop.is_set():
                    ticks.append(time.monotonic())
                    await asyncio.sleep(0.02)

            ticker_task = asyncio.create_task(_ticker())
            try:
                result = await router._call_anthropic("claude-haiku-4-5-20251001", "hi")
            finally:
                stop.set()
                await ticker_task

            # Compute the max gap between consecutive ticks. If the event loop
            # was blocked, this gap would be ~0.3s. With to_thread, gaps stay
            # below ~0.1s.
            assert len(ticks) >= 2
            max_gap = max(b - a for a, b in zip(ticks, ticks[1:]))
            return result, max_gap

        result, max_gap = asyncio.run(_exercise())
        assert result == "slow but ok"
        assert max_gap < 0.15, (
            f"event loop was blocked: max tick gap {max_gap*1000:.0f}ms "
            f"(should be <150ms even under a 300ms sync SDK call)"
        )

    def test_route_and_call_wraps_provider_in_wait_for_timeout(self, tmp_path: Path) -> None:
        """Goodhart: a provider that hangs forever must surface as a TimeoutError
        to the cascade so the next provider gets a chance.

        We verify by patching ``asyncio.wait_for`` itself — if route_and_call
        fails to wrap the call, this stub never fires and the assertion fails.
        """
        from services.llm_router import LLMRouter, SensitivityLevel

        cfg = SimpleNamespace(
            ollama_enabled=False,
            ollama_base_url="http://nope:1",
            ollama_confidential_model="gemma4:e4b",
        )

        class _OkAnthropic:
            class messages:
                @staticmethod
                def create(**kwargs):
                    return SimpleNamespace(content=[SimpleNamespace(text="ok")])

        router = LLMRouter(tmp_path, anthropic_client=_OkAnthropic(), config=cfg)

        wait_for_calls: list[float] = []
        original_wait_for = asyncio.wait_for

        async def _spy_wait_for(coro, timeout):
            wait_for_calls.append(timeout)
            return await original_wait_for(coro, timeout)

        async def _exercise() -> None:
            import services.llm_router as mod
            mod.asyncio.wait_for = _spy_wait_for  # type: ignore[assignment]
            try:
                # Force_level avoids spaCy/PII detection in the unit test.
                text, decision = await router.route_and_call(
                    "test prompt",
                    force_level=SensitivityLevel.PUBLIC,
                    force_model="claude-haiku-4-5-20251001",
                )
            finally:
                mod.asyncio.wait_for = original_wait_for  # type: ignore[assignment]
            assert text == "ok"
            assert decision.provider == "anthropic"

        asyncio.run(_exercise())

        assert wait_for_calls, (
            "route_and_call must wrap every provider attempt in asyncio.wait_for"
        )
        assert all(t > 0 for t in wait_for_calls), (
            "wait_for timeouts must be positive numbers"
        )
