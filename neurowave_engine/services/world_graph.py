"""
World Model Graph

The graph representation of everything surrounding the user: people,
projects, companies, goals, technologies, files, repositories, tasks,
meetings, ideas, documents, APIs, locations, devices, and services. Every
entity is a node; every `WorldRelationship` is a weighted, typed edge.
Mirrors the Day 3 `ConceptGraph` / Day 4 `IdentityGraphService` convention
of a thin networkx wrapper over the underlying DB tables.
"""
import logging
from typing import Dict
from uuid import UUID

from sqlalchemy.orm import Session
import networkx as nx

from neurowave_engine.db.models import WorldEntity, WorldRelationship

logger = logging.getLogger(__name__)


class WorldGraph:
    """Builds and exposes the user's world model as a networkx graph."""

    def __init__(self):
        self.graph = nx.DiGraph()

    def build_graph_for_user(self, session: Session, user_id: UUID) -> nx.DiGraph:
        """Rebuild the graph from `world_entities`/`world_relationships`."""
        self.graph.clear()

        entities = session.query(WorldEntity).filter(WorldEntity.user_id == user_id).all()
        for entity in entities:
            self.graph.add_node(
                entity.id,
                name=entity.entity_name,
                entity_type=entity.entity_type.value,
                confidence=entity.confidence,
                mention_count=entity.mention_count,
            )

        relationships = session.query(WorldRelationship).filter(WorldRelationship.user_id == user_id).all()
        for rel in relationships:
            if rel.source_entity_id in self.graph and rel.target_entity_id in self.graph:
                self.graph.add_edge(
                    rel.source_entity_id, rel.target_entity_id,
                    relationship_type=rel.relationship_type, weight=rel.strength,
                    evidence_count=rel.evidence_count,
                )

        logger.info(
            f"Built world graph for user {user_id}: {len(entities)} entities, {len(relationships)} relationships"
        )
        return self.graph

    def get_graph_statistics(self) -> Dict:
        """Basic graph-health stats, mirroring ConceptGraph/IdentityGraphService."""
        if len(self.graph) == 0:
            return {"node_count": 0, "edge_count": 0, "density": 0.0, "entity_type_distribution": {}}

        type_dist: Dict[str, int] = {}
        for _, data in self.graph.nodes(data=True):
            entity_type = data.get("entity_type", "unknown")
            type_dist[entity_type] = type_dist.get(entity_type, 0) + 1

        return {
            "node_count": self.graph.number_of_nodes(),
            "edge_count": self.graph.number_of_edges(),
            "density": nx.density(self.graph),
            "entity_type_distribution": type_dist,
        }
