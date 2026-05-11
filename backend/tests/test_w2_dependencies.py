"""Tests for W2 DIP — FastAPI dependency injection via Depends().

Mutation criterion: each test must fail when the wrong service instance
is injected (i.e., when dependency_overrides is NOT applied).

These tests prove that:
1. get_* factories return the canonical singleton under normal operation.
2. app.dependency_overrides substitutes a mock — proving the route
   depends on the injected type, not the module-level global.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.dependencies import (
    get_doc_processor,
    get_embedding_service,
    get_entity_extractor,
    get_llm_router,
)


@pytest.fixture()
def client():
    from app.main import app
    return TestClient(app)


# ---------------------------------------------------------------------------
# Factory singleton identity
# ---------------------------------------------------------------------------

class TestFactorySingletonIdentity:
    def test_get_embedding_service_returns_same_instance(self):
        a = get_embedding_service()
        b = get_embedding_service()
        assert a is b, "lru_cache must return the same singleton"

    def test_get_doc_processor_returns_same_instance(self):
        a = get_doc_processor()
        b = get_doc_processor()
        assert a is b

    def test_get_llm_router_returns_same_instance(self):
        a = get_llm_router()
        b = get_llm_router()
        assert a is b

    def test_mutation_different_calls_without_cache_would_differ(self):
        """Goodhart: verify the factories are NOT trivially returning None."""
        instance = get_embedding_service()
        assert instance is not None, "factory must return a real instance"


# ---------------------------------------------------------------------------
# dependency_overrides — DIP proof via TestClient substitution
# ---------------------------------------------------------------------------

class TestDependencyOverrides:
    def test_upload_document_uses_injected_doc_processor(self):
        """Override get_doc_processor → upload must call the mock, not the singleton."""
        import io
        from app.main import app

        mock_dp = AsyncMock()
        mock_dp.extract_text.side_effect = RuntimeError("injected mock")

        app.dependency_overrides[get_doc_processor] = lambda: mock_dp
        try:
            # raise_server_exceptions=False: RuntimeError in handler becomes 500 in response
            tc = TestClient(app, raise_server_exceptions=False)
            response = tc.post(
                "/api/documents/upload",
                files={"file": ("test.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
            )
            assert response.status_code == 500
            mock_dp.extract_text.assert_called_once()
        finally:
            app.dependency_overrides.pop(get_doc_processor, None)

    def test_route_query_uses_injected_llm_router(self, client):
        """Override get_llm_router → force_model path must call the mock."""
        from app.main import app
        from models.entity import KnowledgeGraph
        from services.llm_router import RoutingDecision, SensitivityLevel

        mock_router = AsyncMock()
        fake_decision = MagicMock(spec=RoutingDecision)
        fake_decision.model = "test-model"
        fake_decision.sensitivity_level = SensitivityLevel.PUBLIC
        fake_decision.sensitivity_score = 0.1
        fake_decision.routing_reason = "injected"
        fake_decision.pii_types_detected = []
        fake_decision.cost_estimate_chf = 0.0
        mock_router.route_and_call.return_value = ("mocked response", fake_decision)

        app.dependency_overrides[get_llm_router] = lambda: mock_router
        try:
            response = client.post(
                "/api/routing/query",
                json={"prompt": "hello", "force_model": "test-model"},
            )
            # 200 with mocked response confirms injection was used
            assert response.status_code == 200
            data = response.json()
            assert data["response"] == "mocked response"
            mock_router.route_and_call.assert_called_once()
        finally:
            app.dependency_overrides.pop(get_llm_router, None)

    def test_mutation_override_not_applied_uses_real_service(self):
        """Goodhart: confirm that WITHOUT override, get_doc_processor returns the real singleton."""
        real = get_doc_processor()
        assert real is not None
        assert hasattr(real, "extract_text"), "real DocumentProcessor must have extract_text"
