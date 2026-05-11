"""Graph service — Cytoscape.js output helpers.

Domain algorithm for capping and serialising the knowledge graph.
Extracted from app/routes.py (W1 SRP): a ranking algorithm has no business
living in the HTTP layer.
"""
from __future__ import annotations

from models.entity import KnowledgeGraph


def _top_node_ids(graph: KnowledgeGraph, limit: int) -> set[str]:
    """Return IDs of the *limit* most-connected entities by degree."""
    degree: dict[str, int] = {}
    for r in graph.relationships:
        degree[r.source_id] = degree.get(r.source_id, 0) + 1
        degree[r.target_id] = degree.get(r.target_id, 0) + 1
    return {
        e.id for e in sorted(
            graph.entities, key=lambda e: degree.get(e.id, 0), reverse=True
        )[:limit]
    }


def _build_elements(graph: KnowledgeGraph, top_ids: set[str]) -> list[dict]:
    """Build Cytoscape node + edge elements restricted to *top_ids*."""
    elements: list[dict] = []
    for e in graph.entities:
        if e.id in top_ids:
            elements.append({
                "data": {"id": e.id, "label": e.name, "type": e.entity_type.value, **e.properties},
                "classes": e.entity_type.value,
            })
    for r in graph.relationships:
        if r.source_id in top_ids and r.target_id in top_ids:
            elements.append({
                "data": {
                    "source": r.source_id,
                    "target": r.target_id,
                    "label": r.relationship_type.value.replace("_", " "),
                    "type": r.relationship_type.value,
                },
            })
    return elements


def capped_cytoscape(graph: KnowledgeGraph, limit: int) -> dict:
    """Return Cytoscape JSON capped at *limit* most-connected nodes."""
    total = len(graph.entities)
    if total <= limit:
        result = graph.to_cytoscape()
        result.update({"total_entities": total, "capped": False})
        return result
    top_ids = _top_node_ids(graph, limit)
    return {
        "elements": _build_elements(graph, top_ids),
        "total_entities": total,
        "capped": True,
        "shown": limit,
    }
