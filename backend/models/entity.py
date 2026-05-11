"""Entity and relationship models for the knowledge graph."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class EntityType(str, Enum):
    PERSON = "person"
    ORGANISATION = "organisation"
    CASE = "case"
    DOCUMENT = "document"
    EVENT = "event"
    LOCATION = "location"
    MONEY = "money"
    DATE = "date"
    STATUTE = "statute"


class RelationshipType(str, Enum):
    PARTY_TO = "party_to"
    REPRESENTS = "represents"
    FILED_IN = "filed_in"
    REFERENCED_BY = "referenced_by"
    AUTHORED_BY = "authored_by"
    MENTIONS = "mentions"
    OCCURRED_ON = "occurred_on"
    ASSOCIATED_WITH = "associated_with"
    OPPOSING_COUNSEL = "opposing_counsel"


class Entity(BaseModel):
    """A node in the knowledge graph."""
    id: str
    name: str
    entity_type: EntityType
    properties: dict = Field(default_factory=dict)
    source_document: Optional[str] = None


class Relationship(BaseModel):
    """An edge in the knowledge graph."""
    source_id: str
    target_id: str
    relationship_type: RelationshipType
    properties: dict = Field(default_factory=dict)
    source_document: Optional[str] = None


class KnowledgeGraph(BaseModel):
    """In-memory knowledge graph."""
    entities: list[Entity] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)

    def add_entity(self, entity: Entity):
        # Deduplicate by name + type
        for existing in self.entities:
            if existing.name.lower() == entity.name.lower() and existing.entity_type == entity.entity_type:
                existing.properties.update(entity.properties)
                return existing
        self.entities.append(entity)
        return entity

    def add_relationship(self, rel: Relationship):
        # Deduplicate
        for existing in self.relationships:
            if (existing.source_id == rel.source_id and
                existing.target_id == rel.target_id and
                existing.relationship_type == rel.relationship_type):
                return existing
        self.relationships.append(rel)
        return rel

    def get_connected(self, entity_id: str, depth: int = 1) -> "KnowledgeGraph":
        """Get subgraph connected to an entity up to given depth."""
        visited = set()
        entities = {}
        rels = []

        def _traverse(eid: str, d: int):
            if d > depth or eid in visited:
                return
            visited.add(eid)
            for e in self.entities:
                if e.id == eid:
                    entities[eid] = e
                    break
            for r in self.relationships:
                if r.source_id == eid:
                    rels.append(r)
                    _traverse(r.target_id, d + 1)
                elif r.target_id == eid:
                    rels.append(r)
                    _traverse(r.source_id, d + 1)

        _traverse(entity_id, 0)
        return KnowledgeGraph(entities=list(entities.values()), relationships=rels)

    def to_cytoscape(self) -> dict:
        """Export as Cytoscape.js-compatible JSON."""
        elements = []
        for e in self.entities:
            elements.append({
                "data": {
                    "id": e.id,
                    "label": e.name,
                    "type": e.entity_type.value,
                    **e.properties,
                },
                "classes": e.entity_type.value,
            })
        for r in self.relationships:
            elements.append({
                "data": {
                    "source": r.source_id,
                    "target": r.target_id,
                    "label": r.relationship_type.value.replace("_", " "),
                    "type": r.relationship_type.value,
                },
            })
        return {"elements": elements}
