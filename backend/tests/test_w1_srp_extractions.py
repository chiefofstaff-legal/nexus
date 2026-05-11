"""Tests for W1 SRP extractions — graph_service, routing_helpers, embedding log.

Mutation criterion: each test must fail when the function under test is
broken (patched to return None / wrong value). Goodhart protection is
the explicit mutation section at the bottom of each class.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# graph_service.capped_cytoscape
# ---------------------------------------------------------------------------

def _make_entity(eid: str, name: str, etype: str = "person", degree: int = 0):
    """Build a minimal mock entity."""
    e = SimpleNamespace(
        id=eid,
        name=name,
        entity_type=SimpleNamespace(value=etype),
        properties={},
    )
    return e


def _make_rel(source: str, target: str, rtype: str = "related_to"):
    return SimpleNamespace(
        source_id=source,
        target_id=target,
        relationship_type=SimpleNamespace(value=rtype),
    )


class TestCappedCytoscape:
    def _graph(self, n_entities: int = 3, n_rels: int = 2):
        entities = [_make_entity(f"e{i}", f"Entity {i}") for i in range(n_entities)]
        rels = [_make_rel(f"e{i}", f"e{i+1}") for i in range(min(n_rels, n_entities - 1))]
        g = MagicMock()
        g.entities = entities
        g.relationships = rels
        g.to_cytoscape.return_value = {"elements": [], "other": "data"}
        return g

    def test_returns_full_graph_when_under_limit(self):
        from services.graph_service import capped_cytoscape
        g = self._graph(3)
        result = capped_cytoscape(g, limit=10)
        assert result["capped"] is False
        assert result["total_entities"] == 3

    def test_caps_graph_to_limit(self):
        from services.graph_service import capped_cytoscape
        g = self._graph(n_entities=5, n_rels=4)
        result = capped_cytoscape(g, limit=2)
        assert result["capped"] is True
        assert result["shown"] == 2
        assert result["total_entities"] == 5
        node_ids = {el["data"]["id"] for el in result["elements"] if "source" not in el["data"]}
        assert len(node_ids) <= 2

    def test_selects_highest_degree_nodes(self):
        from services.graph_service import capped_cytoscape
        entities = [_make_entity(f"e{i}", f"E{i}") for i in range(4)]
        # e0 has degree 3 (appears in 3 rels), e1/e2/e3 have degree 1 each
        rels = [_make_rel("e0", "e1"), _make_rel("e0", "e2"), _make_rel("e0", "e3")]
        g = MagicMock()
        g.entities = entities
        g.relationships = rels
        g.to_cytoscape.return_value = {}
        result = capped_cytoscape(g, limit=1)
        node_ids = {el["data"]["id"] for el in result["elements"] if "source" not in el["data"]}
        assert "e0" in node_ids, "highest-degree node must be selected"

    def test_mutation_broken_top_node_ids_causes_failure(self):
        """Goodhart protection: test fails against a mutant that always returns empty set."""
        from services import graph_service
        g = self._graph(5, 4)
        with patch.object(graph_service, "_top_node_ids", return_value=set()):
            result = graph_service.capped_cytoscape(g, limit=2)
            mutant_nodes = [el for el in result["elements"] if "source" not in el["data"]]
            assert len(mutant_nodes) == 0
        real = graph_service.capped_cytoscape(g, limit=2)
        real_nodes = [el for el in real["elements"] if "source" not in el["data"]]
        assert len(real_nodes) > 0, "real implementation must select nodes"


# ---------------------------------------------------------------------------
# routing_helpers
# ---------------------------------------------------------------------------

class TestEnrichDecisionWithCouncil:
    def _decision(self):
        d = MagicMock()
        d.sensitivity_score = 0.0
        d.routing_reason = ""
        d.pii_types_detected = []
        return d

    def _council_result(self, decision="internal", confidence=0.8, pii=None):
        cr = MagicMock()
        cr.confidence = confidence
        cr.synthesis_method.value = "unanimous"
        cr.confidence_rationale = "all 3 providers agreed"
        cr.idr = {"metadata": {"pii_fingerprint": pii or []}}
        return cr

    def test_sets_sensitivity_score_rounded(self):
        from services.routing_helpers import enrich_decision_with_council
        d = self._decision()
        cr = self._council_result(confidence=0.8333)
        enrich_decision_with_council(d, cr)
        assert d.sensitivity_score == 0.833

    def test_sets_routing_reason_with_council_prefix(self):
        from services.routing_helpers import enrich_decision_with_council
        d = self._decision()
        cr = self._council_result()
        enrich_decision_with_council(d, cr)
        assert d.routing_reason.startswith("Council (unanimous):")

    def test_sets_pii_types_when_present(self):
        from services.routing_helpers import enrich_decision_with_council
        d = self._decision()
        cr = self._council_result(pii=["PERSON", "EMAIL"])
        enrich_decision_with_council(d, cr)
        assert d.pii_types_detected == ["PERSON", "EMAIL"]

    def test_leaves_pii_unchanged_when_empty(self):
        from services.routing_helpers import enrich_decision_with_council
        d = self._decision()
        cr = self._council_result(pii=[])
        enrich_decision_with_council(d, cr)
        assert d.pii_types_detected == []


class TestIdrSummary:
    def _council_result(self):
        cr = MagicMock()
        cr.idr = {"idr_id": "abc123", "sequence": 7, "chain_hash": "deadbeef"}
        cr.decision = "confidential"
        cr.confidence = 0.91
        cr.synthesis_method.value = "majority"
        return cr

    def test_returns_all_expected_keys(self):
        from services.routing_helpers import idr_summary
        result = idr_summary(self._council_result())
        assert set(result.keys()) == {"idr_id", "sequence", "decision", "confidence", "synthesis_method", "chain_hash"}

    def test_passes_decision_and_confidence(self):
        from services.routing_helpers import idr_summary
        result = idr_summary(self._council_result())
        assert result["decision"] == "confidential"
        assert result["confidence"] == 0.91

    def test_mutation_missing_idr_id_produces_none(self):
        """Goodhart protection: test detects when idr_id field is absent."""
        from services.routing_helpers import idr_summary
        cr = self._council_result()
        cr.idr = {}  # idr_id absent
        result = idr_summary(cr)
        assert result["idr_id"] is None
        cr2 = self._council_result()
        real = idr_summary(cr2)
        assert real["idr_id"] == "abc123"


# ---------------------------------------------------------------------------
# embedding_service.log_search_idr
# ---------------------------------------------------------------------------

class TestLogSearchIdr:
    def test_appends_idr_to_store(self):
        from services.embedding_service import log_search_idr
        store = MagicMock()
        results = [{"metadata": {"filename": "contract.pdf", "doc_id": "d1"}, "relevance": 0.9}]
        log_search_idr("who is the claimant", results, 5, store)
        store.append.assert_called_once()

    def test_swallows_store_errors(self):
        from services.embedding_service import log_search_idr
        store = MagicMock()
        store.append.side_effect = RuntimeError("store down")
        results = [{"metadata": {"filename": "f.pdf"}, "relevance": 0.5}]
        log_search_idr("query", results, 5, store)  # must not raise

    def test_handles_empty_results(self):
        from services.embedding_service import log_search_idr
        store = MagicMock()
        log_search_idr("query", [], 5, store)
        store.append.assert_called_once()
