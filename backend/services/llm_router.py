"""
LLMRouter dispatcher — imports the proprietary nexus_engine router when
available, otherwise falls back to the OSS single-model router below.

Hosted deployments at free.donnaoss.com use the full NEXUS-tier engine
(sensitivity classification, council deliberation, multi-provider routing).
Self-hosters running the OSS clone get a single-model Groq router with no
sensitivity classification. The audit chain is preserved in both modes.

See nexus_engine.router (private) for the proprietary implementation:
  https://github.com/CodeTonight-SA/nexus-engine
"""

from __future__ import annotations

try:
    from nexus_engine.router import LLMRouter, RoutingDecision  # type: ignore
    from nexus_engine.types import SensitivityLevel  # type: ignore
    _ENGINE = "nexus_engine"
except ImportError:
    from services.llm_router_simple import (  # noqa: F401
        LLMRouter,
        RoutingDecision,
        SensitivityLevel,
    )
    _ENGINE = "simple"

__all__ = ["LLMRouter", "RoutingDecision", "SensitivityLevel"]
