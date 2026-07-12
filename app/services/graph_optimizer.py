"""
Graph Optimization Engine

Optimizes the concept graph and identity graph: retires dead nodes (no
supporting evidence, no connections, near-zero confidence) and strengthens
edges between repeatedly-reinforced nodes — the graph-structure
counterpart to Day 7's per-memory forgetting. Retirement is soft (flagged
in metadata, confidence dropped to 0), never a hard delete, so history and
referential integrity are preserved.
"""
import logging
from typing import Dict
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import ConceptMemory, ConceptRelationship, IdentityNode, IdentityRelationship
from app.core.config import settings

logger = logging.getLogger(__name__)


class GraphOptimizationEngine:
    """Prunes dead nodes and strengthens reinforced edges in both graphs."""

    def __init__(self, session: Session):
        self.session = session

    def optimize(self, user_id: UUID) -> Dict:
        concept_result = self._optimize_concept_graph(user_id)
        identity_result = self._optimize_identity_graph(user_id)
        return {
            "concept_graph": concept_result,
            "identity_graph": identity_result,
            "nodes_removed": concept_result["nodes_removed"] + identity_result["nodes_removed"],
            "edges_strengthened": concept_result["edges_strengthened"] + identity_result["edges_strengthened"],
        }

    def _optimize_concept_graph(self, user_id: UUID) -> Dict:
        concepts = self.session.query(ConceptMemory).filter(ConceptMemory.user_id == user_id).all()

        removed = 0
        for concept in concepts:
            if (concept.extra_metadata or {}).get("retired"):
                continue
            is_dead = (
                (concept.confidence or 0) <= settings.graph_dead_node_confidence_threshold
                and (concept.support_count or 0) <= 1
                and not (concept.related_concept_ids or [])
            )
            if is_dead:
                concept.extra_metadata = {
                    **(concept.extra_metadata or {}),
                    "retired": True, "retire_reason": "Dead node - no evidence or connections",
                }
                concept.confidence = 0.0
                removed += 1

        relationships = self.session.query(ConceptRelationship).filter(ConceptRelationship.user_id == user_id).all()
        strengthened = 0
        for rel in relationships:
            if (rel.reinforcement_count or 0) >= 2 and (rel.strength or 0) < 0.95:
                rel.strength = min(1.0, (rel.strength or 0.5) + 0.05)
                strengthened += 1

        self.session.commit()
        return {"nodes_removed": removed, "edges_strengthened": strengthened, "total_concepts": len(concepts)}

    def _optimize_identity_graph(self, user_id: UUID) -> Dict:
        nodes = self.session.query(IdentityNode).filter(IdentityNode.user_id == user_id).all()

        removed = 0
        for node in nodes:
            if (node.extra_metadata or {}).get("retired"):
                continue
            is_dead = (
                (node.confidence or 0) <= settings.graph_dead_node_confidence_threshold
                and (node.evidence_count or 0) <= 1
            )
            if is_dead:
                node.extra_metadata = {
                    **(node.extra_metadata or {}),
                    "retired": True, "retire_reason": "Dead node - no evidence",
                }
                node.confidence = 0.0
                removed += 1

        relationships = self.session.query(IdentityRelationship).filter(IdentityRelationship.user_id == user_id).all()
        strengthened = 0
        for rel in relationships:
            if (rel.reinforcement_count or 0) >= 2 and (rel.strength or 0) < 0.95:
                rel.strength = min(1.0, (rel.strength or 0.5) + 0.05)
                strengthened += 1

        self.session.commit()
        return {"nodes_removed": removed, "edges_strengthened": strengthened, "total_nodes": len(nodes)}
