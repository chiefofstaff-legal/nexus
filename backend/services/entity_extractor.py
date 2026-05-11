"""
Entity Extraction Service
==========================

Extracts legal entities and relationships from document text. Uses spaCy
NER for fast entity detection, Claude Haiku for relationship inference,
and a rule-based correction layer for Swiss / South African legal
content that spaCy's small English model gets wrong (currency formats,
statute citations, case numbers).

Correction layer rationale: ``en_core_web_sm`` is trained on American
news text, so it treats tokens like ``R45,000,000.00`` or ``CHF 250,000``
as ORG (capital-letter + numeric pattern looks like a company code).
V>> flagged this during the MVP walkthrough: a currency figure was
rendering as an ORGANISATION node in the knowledge graph. Rather than
swap spaCy models (``en_core_web_lg`` is 400 MB+ and still mis-types
non-USD currency), we apply deterministic regex overrides AFTER the
NER pass so the base model stays lightweight and the wrong entries
get demoted to the correct type.
"""

import hashlib
import json
import re

from models.entity import (
    Entity,
    EntityType,
    KnowledgeGraph,
    Relationship,
    RelationshipType,
)


# Currency patterns the correction layer recognises. Anchored at the
# SYMBOL so "R45,000,000.00", "R 45 000 000", and "CHF 250'000" all hit.
# Grouped to cover the four currencies the demo audience cares about:
# ZAR (South Africa), CHF (Switzerland), EUR, USD, GBP.
_CURRENCY_RE = re.compile(
    r"""
    (?:
        (?:R|ZAR|USD|\$|EUR|€|CHF|GBP|£)    # symbol or code
        \s?                                  # optional space
        \d[\d\s,.'_]*                        # digits + SA/CH/EU separators
        (?:\.\d{1,2})?                       # optional decimal
    )
    """,
    re.VERBOSE,
)

# Case / statute patterns. Examples the demo will touch:
#   "FADP Article 5"           -> statute
#   "GDPR Art. 6(1)"           -> statute
#   "Case No. 2024-CV-0142"    -> case
#   "Docket 4A_123/2023"       -> case (Swiss Federal Tribunal format)
_STATUTE_RE = re.compile(
    r"""
    (?:FADP|GDPR|HIPAA|CCPA|POPIA|ZGB|OR|StGB)
    \s+
    (?:Art(?:icle|\.)?|§|Section|Sec\.?)
    \s*
    \d+[A-Za-z0-9\(\)\.\-]*
    """,
    re.VERBOSE | re.IGNORECASE,
)

_CASE_RE = re.compile(
    r"""
    (?:
        (?:Case|Docket|Matter|No\.?)\s*(?:No\.?)?\s*
        [A-Z0-9][A-Z0-9_\-/\.]{3,}
        |
        \b\d+[A-Z]_\d+/\d{4}\b                    # Swiss Federal Tribunal
    )
    """,
    re.VERBOSE,
)

# --- False-positive guards for the spaCy NER pass ---

# Version / range strings that en_core_web_sm misidentifies as PERSON.
# Covers: v3, v4.11.1, 3.x, x.x, git range operator ..
_VERSION_TOKEN_RE = re.compile(r"(?:^v\d|\d+\.x|x\.x|\.\.)", re.IGNORECASE)

# Only trust spaCy MONEY when a real currency marker is present.
# en_core_web_sm tags section numbers (5.2, 6.1) and plain decimals as MONEY
# because they resemble financial figures in the news-text training corpus.
# The _currency_pass regex already claimed all legitimate currency tokens
# (those with a symbol prefix) before _spacy_pass runs, so any remaining
# spaCy MONEY entity without a currency marker is a false positive.
_CURRENCY_MARKER_RE = re.compile(
    r"(?:R\s?\d|\$|USD|EUR|CHF|GBP|£|€|ZAR|dollars?|francs?|cents?|million|billion|thousand)",
    re.IGNORECASE,
)

# Common technical nouns that en_core_web_sm tags as PERSON when they appear
# capitalised in documentation, changelogs, or test-suite output.
_TECH_TERM_BLOCKLIST: frozenset[str] = frozenset({
    "hacks", "diff", "patch", "delta", "build", "deploy", "release",
    "rollout", "rollback", "cache", "queue", "stack", "heap", "tree",
    "node", "edge", "leaf", "root", "graph", "hook", "event", "handler",
    "callback", "plugin", "module", "macro", "lambda", "enum",
    "load", "check", "error", "bug", "fix", "test", "stub", "mock",
    "push", "pull", "merge", "commit", "branch", "tag",
})


class EntityExtractor:
    """Extract entities and relationships from legal text."""

    def __init__(self, anthropic_client=None):
        self.anthropic_client = anthropic_client
        self.nlp = None
        self.graph = KnowledgeGraph()

    def _load_spacy(self):
        if self.nlp is None:
            try:
                import spacy
                self.nlp = spacy.load("en_core_web_sm")
            except (ImportError, OSError):
                self.nlp = False

    def _make_id(self, name: str, entity_type: str) -> str:
        return hashlib.sha256(f"{entity_type}:{name.lower()}".encode()).hexdigest()[:12]

    async def extract_entities_spacy(self, text: str, source_doc: str = "") -> list[Entity]:
        """Fast entity extraction using spaCy NER plus a correction layer.

        Runs spaCy first, then applies three corrections:
        1. Any entity whose text matches a currency pattern is re-typed
           to MONEY regardless of the spaCy label (fixes the V>>-flagged
           "R45,000,000.00 as ORGANISATION" bug).
        2. Regex sweep for statute citations the spaCy model misses
           entirely (FADP Article 5, GDPR Art. 6, etc.).
        3. Regex sweep for case/docket numbers (Swiss Federal Tribunal
           format, South African case numbers).
        """
        self._load_spacy()
        entities: list[Entity] = []
        seen: set[str] = set()

        # Regex passes run FIRST so explicit legal patterns (currencies,
        # statutes, Swiss Federal Tribunal case numbers) claim their
        # tokens before spaCy gets a chance to mis-tag them. spaCy's
        # small English model tags "4A_123/2023" as EVENT, which would
        # otherwise block the case-regex correction.
        entities.extend(self._currency_pass(text, source_doc, seen))
        entities.extend(self._statute_pass(text, source_doc, seen))
        entities.extend(self._case_pass(text, source_doc, seen))

        if self.nlp and self.nlp is not False:
            entities.extend(self._spacy_pass(text, source_doc, seen))

        # Post-pass: demote any ORGANISATION whose NAME still matches a
        # currency pattern (happens when spaCy pulled a currency token
        # into a surrounding phrase and the correction pass didn't fire).
        corrected: list[Entity] = []
        for e in entities:
            if (
                e.entity_type == EntityType.ORGANISATION
                and _CURRENCY_RE.fullmatch(e.name.strip())
            ):
                e.entity_type = EntityType.MONEY
                e.properties["corrected_from"] = "organisation"
                e.properties["correction_reason"] = "currency_regex"
                e.id = self._make_id(e.name, e.entity_type.value)
            corrected.append(e)
        return corrected

    def _spacy_pass(
        self, text: str, source_doc: str, seen: set[str]
    ) -> list[Entity]:
        """Run spaCy NER with the base type map + false-positive guards."""
        doc = self.nlp(text[:15000])  # Limit for speed
        type_map = {
            "PERSON": EntityType.PERSON,
            "ORG": EntityType.ORGANISATION,
            "GPE": EntityType.LOCATION,
            "LOC": EntityType.LOCATION,
            "DATE": EntityType.DATE,
            "EVENT": EntityType.EVENT,
            "MONEY": EntityType.MONEY,
            "LAW": EntityType.STATUTE,
        }
        out: list[Entity] = []
        for ent in doc.ents:
            if ent.label_ not in type_map:
                continue
            name = ent.text.strip()
            if len(name) < 2 or name.lower() in seen:
                continue
            entity_type = type_map[ent.label_]

            # Guard MONEY: section numbers (5.2, 6.1) lack currency markers.
            # Legitimate currency was already claimed by _currency_pass.
            if entity_type == EntityType.MONEY and not _CURRENCY_MARKER_RE.search(name):
                continue

            # Guard PERSON: version strings (v3.x.x..v4.11.1) and technical
            # nouns (Hacks, Diff) that appear capitalised in changelogs.
            if entity_type == EntityType.PERSON and (
                _VERSION_TOKEN_RE.search(name) or name.lower() in _TECH_TERM_BLOCKLIST
            ):
                continue

            seen.add(name.lower())
            out.append(
                Entity(
                    id=self._make_id(name, entity_type.value),
                    name=name,
                    entity_type=entity_type,
                    properties={"ner_label": ent.label_},
                    source_document=source_doc,
                )
            )
        return out

    def _currency_pass(
        self, text: str, source_doc: str, seen: set[str]
    ) -> list[Entity]:
        """Regex sweep for currency tokens spaCy missed."""
        return self._regex_sweep(
            text, source_doc, seen,
            pattern=_CURRENCY_RE,
            entity_type=EntityType.MONEY,
            extractor_label="regex_currency",
            min_length=2,
        )

    def _statute_pass(
        self, text: str, source_doc: str, seen: set[str]
    ) -> list[Entity]:
        """Regex sweep for statute / article citations."""
        return self._regex_sweep(
            text, source_doc, seen,
            pattern=_STATUTE_RE,
            entity_type=EntityType.STATUTE,
            extractor_label="regex_statute",
            min_length=2,
        )

    def _case_pass(
        self, text: str, source_doc: str, seen: set[str]
    ) -> list[Entity]:
        """Regex sweep for case / docket numbers."""
        return self._regex_sweep(
            text, source_doc, seen,
            pattern=_CASE_RE,
            entity_type=EntityType.CASE,
            extractor_label="regex_case",
            min_length=5,
        )

    def _regex_sweep(
        self,
        text: str,
        source_doc: str,
        seen: set[str],
        pattern: re.Pattern,
        entity_type: EntityType,
        extractor_label: str,
        min_length: int,
    ) -> list[Entity]:
        """Apply one regex over the text, emit typed entities, dedupe."""
        out: list[Entity] = []
        for match in pattern.finditer(text[:15000]):
            name = re.sub(r"\s+", " ", match.group(0).strip())
            if len(name) < min_length or name.lower() in seen:
                continue
            seen.add(name.lower())
            out.append(
                Entity(
                    id=self._make_id(name, entity_type.value),
                    name=name,
                    entity_type=entity_type,
                    properties={"extractor": extractor_label},
                    source_document=source_doc,
                )
            )
        return out

    async def extract_relationships_llm(
        self, text: str, entities: list[Entity], source_doc: str = ""
    ) -> list[Relationship]:
        """Use Claude Haiku to infer relationships between entities."""
        if not self.anthropic_client or not entities:
            return []

        entity_names = [e.name for e in entities[:20]]  # Limit for prompt size

        prompt = f"""Given these entities extracted from a legal document, identify relationships between them.
Return ONLY a JSON array of relationships:
[
  {{"source": "Entity Name A", "target": "Entity Name B", "type": "party_to|represents|filed_in|referenced_by|authored_by|mentions|occurred_on|associated_with|opposing_counsel"}}
]

Entities: {json.dumps(entity_names)}

Document excerpt (first 2000 chars):
{text[:2000]}"""

        try:
            response = await self.anthropic_client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )

            raw = response.content[0].text
            json_match = re.search(r'\[.*\]', raw, re.DOTALL)
            if not json_match:
                return []

            rel_data = json.loads(json_match.group())
            relationships = []

            entity_lookup = {e.name.lower(): e for e in entities}

            for r in rel_data:
                source_name = r.get("source", "").lower()
                target_name = r.get("target", "").lower()
                rel_type = r.get("type", "associated_with")

                source_entity = entity_lookup.get(source_name)
                target_entity = entity_lookup.get(target_name)

                if source_entity and target_entity:
                    try:
                        relationships.append(Relationship(
                            source_id=source_entity.id,
                            target_id=target_entity.id,
                            relationship_type=RelationshipType(rel_type),
                            source_document=source_doc,
                        ))
                    except ValueError:
                        pass

            return relationships
        except Exception:
            return []

    async def process_document(self, text: str, doc_id: str) -> KnowledgeGraph:
        """Full extraction pipeline for a document."""
        # Add the document as an entity
        doc_entity = Entity(
            id=doc_id,
            name=doc_id,
            entity_type=EntityType.DOCUMENT,
            source_document=doc_id,
        )
        self.graph.add_entity(doc_entity)

        # Extract entities via spaCy
        entities = await self.extract_entities_spacy(text, doc_id)
        for entity in entities:
            added = self.graph.add_entity(entity)
            # Link entity to document
            self.graph.add_relationship(Relationship(
                source_id=added.id,
                target_id=doc_id,
                relationship_type=RelationshipType.MENTIONS,
                source_document=doc_id,
            ))

        # Extract relationships via LLM
        relationships = await self.extract_relationships_llm(text, entities, doc_id)
        for rel in relationships:
            self.graph.add_relationship(rel)

        return self.graph
