"""Tests for W4 ISP — Protocol interface compatibility.

Mutation criterion: each test must fail if the concrete service is missing a
required method (i.e., if the Protocol contract is not satisfied).
"""
from __future__ import annotations

from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Structural compatibility — concrete classes satisfy their Protocols
# ---------------------------------------------------------------------------

class TestProtocolCompatibility:
    """isinstance checks via @runtime_checkable prove structural compatibility."""

    def test_embedding_service_satisfies_search_protocol(self):
        from services.embedding_service import EmbeddingService
        from services.protocols import SearchProtocol
        svc = EmbeddingService(Path("/tmp/nexus-test-w4"))
        assert isinstance(svc, SearchProtocol), (
            "EmbeddingService must expose index_document, search, get_stats"
        )

    def test_llm_router_satisfies_llm_router_protocol(self):
        from services.llm_router import LLMRouter
        from services.protocols import LLMRouterProtocol
        router = LLMRouter(Path("/tmp/nexus-test-w4"))
        assert isinstance(router, LLMRouterProtocol)

    def test_audit_chain_satisfies_audit_protocol(self):
        from core.audit_chain import AuditChain
        from services.protocols import AuditProtocol
        chain = AuditChain(log_path=Path("/tmp/nexus-test-w4-audit.jsonl"))
        assert isinstance(chain, AuditProtocol)

    def test_mutation_object_missing_method_fails_protocol_check(self):
        """Goodhart: a class missing a required method must NOT satisfy the protocol."""
        from services.protocols import SearchProtocol

        class Incomplete:
            def index_document(self, doc_id, text, metadata=None):
                ...
            # Missing: search, get_stats

        assert not isinstance(Incomplete(), SearchProtocol), (
            "Incomplete class must NOT pass the runtime_checkable check"
        )

    def test_full_mock_satisfies_search_protocol(self):
        """A minimal test double satisfying only the SearchProtocol methods is enough."""
        from services.protocols import SearchProtocol

        class MockSearch:
            def index_document(self, doc_id, text, metadata=None):
                return 0
            def search(self, query, n_results=5, doc_id=None):
                return []
            def get_stats(self):
                return {"total_chunks": 0}

        assert isinstance(MockSearch(), SearchProtocol)


# ---------------------------------------------------------------------------
# ISP narrow-interface: test doubles need only implement Protocol methods
# ---------------------------------------------------------------------------

class TestISPNarrowInterface:
    def test_router_protocol_double_works_for_force_model_path(self):
        """A minimal LLMRouterProtocol double satisfies the force_model endpoint path."""
        from services.protocols import LLMRouterProtocol

        class MinimalRouter:
            async def route_and_call(self, prompt, system="", task_type="general", force_model=None):
                return ("result", object())
            def classify_sensitivity(self, text):
                return ("public", 0.0, [])
            def get_provider_status(self):
                return {"groq": False, "ollama": False, "anthropic": False}

        assert isinstance(MinimalRouter(), LLMRouterProtocol)

    def test_audit_protocol_double_is_sufficient_for_audit_chain_callers(self):
        from services.protocols import AuditProtocol

        class MinimalAudit:
            def sign_and_append(self, entry):
                pass
            def verify(self):
                return {"valid": True, "total_entries": 0}

        assert isinstance(MinimalAudit(), AuditProtocol)
