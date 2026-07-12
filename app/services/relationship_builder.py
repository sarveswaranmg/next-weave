"""
Relationship Builder

Automatically infers typed, weighted relationships between world entities
that co-occur in the same text (e.g. "NeuroWeave uses PostgreSQL" ->
NeuroWeave -[uses]-> PostgreSQL). Relationship confidence grows with
repeated evidence; a generic `related_to` edge is recorded when entities
co-occur in the same sentence without a specific relationship verb.
"""
import logging
import re
from datetime import datetime
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import WorldEntity, WorldRelationship

logger = logging.getLogger(__name__)

# Verb patterns that imply a specific relationship type between whatever
# entity precedes and follows them in the same sentence. Data, not logic.
RELATIONSHIP_VERBS: List[Tuple[str, List[str]]] = [
    ("uses", [r"\buses?\b", r"\busing\b", r"\bbuilt with\b", r"\bpowered by\b"]),
    ("stores", [r"\bstores?\b", r"\bstoring\b", r"\bpersists?\b"]),
    ("depends_on", [r"\bdepends? on\b", r"\brequires?\b", r"\bneeds?\b"]),
    ("migrates_to", [r"\bmigrat\w* to\b", r"\bmoving to\b", r"\bswitch\w* to\b"]),
    ("deployed_to", [r"\bdeploy\w* (?:to|on)\b", r"\bhosted on\b", r"\brunning on\b"]),
    ("works_on", [r"\bwork\w* on\b", r"\bbuilding\b", r"\bdeveloping\b"]),
    ("blocks", [r"\bblocks?\b", r"\bblocked by\b", r"\bblocking\b"]),
    ("part_of", [r"\bpart of\b", r"\bwithin\b", r"\bbelongs to\b"]),
]


class RelationshipBuilder:
    """Infers and persists weighted relationships between world entities."""

    def __init__(self, session: Session):
        self.session = session

    def build(
        self, user_id: UUID, entities: List[WorldEntity], text: str,
        source_memory_id: Optional[UUID] = None,
    ) -> List[WorldRelationship]:
        """
        Infer relationships among entities that co-occur in `text`.

        Args:
            user_id: User ID
            entities: WorldEntity nodes detected in this text (from EntityExtractor)
            text: The source text (used to find verb patterns between mentions)
            source_memory_id: Originating memory, if any

        Returns:
            List of WorldRelationship rows touched.
        """
        if len(entities) < 2:
            return []

        touched = []
        lowered = text.lower()

        for i in range(len(entities)):
            for j in range(len(entities)):
                if i == j:
                    continue
                source, target = entities[i], entities[j]
                inferred = self._infer_relationship(source, target, lowered)
                if inferred is None:
                    continue
                rel_type, confidence = inferred
                touched.append(self._upsert(user_id, source, target, rel_type, confidence, source_memory_id))

        if touched:
            self.session.commit()
        return touched

    def _infer_relationship(self, source: WorldEntity, target: WorldEntity, lowered_text: str):
        """Look for a relationship verb pattern positioned between the two
        entity mentions in the text; fall back to generic co-occurrence."""
        source_pos = lowered_text.find(source.entity_name.lower())
        target_pos = lowered_text.find(target.entity_name.lower())

        if source_pos == -1 or target_pos == -1 or source_pos >= target_pos:
            return None  # only build source->target in mention order

        between = lowered_text[source_pos:target_pos]

        for rel_type, patterns in RELATIONSHIP_VERBS:
            if any(re.search(p, between) for p in patterns):
                return rel_type, 0.7

        if self._same_sentence(source_pos, target_pos, lowered_text):
            return "related_to", 0.4

        return None

    @staticmethod
    def _same_sentence(pos_a: int, pos_b: int, text: str) -> bool:
        segment = text[pos_a:pos_b]
        return "." not in segment and "\n" not in segment

    def _upsert(
        self, user_id: UUID, source: WorldEntity, target: WorldEntity,
        rel_type: str, confidence: float, source_memory_id: Optional[UUID],
    ) -> WorldRelationship:
        existing = self.session.query(WorldRelationship).filter(
            WorldRelationship.user_id == user_id,
            WorldRelationship.source_entity_id == source.id,
            WorldRelationship.target_entity_id == target.id,
            WorldRelationship.relationship_type == rel_type,
        ).first()

        if existing:
            existing.evidence_count = (existing.evidence_count or 1) + 1
            existing.strength = min(1.0, (existing.strength or 0.5) + 0.05)
            existing.updated_at = datetime.utcnow()
            if source_memory_id and str(source_memory_id) not in (existing.supporting_memory_ids or []):
                existing.supporting_memory_ids = (existing.supporting_memory_ids or []) + [str(source_memory_id)]
            return existing

        relationship = WorldRelationship(
            user_id=user_id, source_entity_id=source.id, target_entity_id=target.id,
            relationship_type=rel_type, strength=confidence, evidence_count=1,
            supporting_memory_ids=[str(source_memory_id)] if source_memory_id else [],
        )
        self.session.add(relationship)
        self.session.flush()
        return relationship
