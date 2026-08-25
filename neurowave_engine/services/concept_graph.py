"""Semantic knowledge graph management"""
import logging
from typing import List, Dict, Optional, Set, Tuple
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

import networkx as nx

from neurowave_engine.db.models import ConceptMemory, ConceptRelationship

logger = logging.getLogger(__name__)


class ConceptGraph:
    """
    Manages semantic knowledge graph of concepts.
    
    Provides:
    - Concept relationship tracking
    - Graph traversal and analysis
    - Concept reinforcement propagation
    - Similarity-based link discovery
    """

    def __init__(self):
        self.graph = nx.DiGraph()
        self.relationship_types = [
            'supports',
            'reinforces',
            'related_to',
            'derived_from',
            'specializes',
            'generalizes',
        ]

    def build_graph_for_user(
        self,
        session: Session,
        user_id: UUID,
    ) -> nx.DiGraph:
        """
        Build semantic graph for a user from database.
        
        Args:
            session: Database session
            user_id: User ID
            
        Returns:
            NetworkX directed graph
        """
        try:
            # Clear existing graph
            self.graph.clear()

            # Get all concepts for user
            concepts = session.query(ConceptMemory).filter(
                ConceptMemory.user_id == user_id
            ).all()

            # Add concept nodes
            for concept in concepts:
                self.graph.add_node(
                    concept.id,
                    name=concept.concept_name,
                    confidence=concept.confidence,
                    support_count=concept.support_count,
                    description=concept.description,
                )

            # Get all relationships for user
            relationships = session.query(ConceptRelationship).filter(
                ConceptRelationship.user_id == user_id
            ).all()

            # Add edges
            for rel in relationships:
                self.graph.add_edge(
                    rel.source_concept_id,
                    rel.target_concept_id,
                    weight=rel.strength,
                    type=rel.relationship_type,
                    reinforcement_count=rel.reinforcement_count,
                )

            logger.info(f"Built graph: {len(concepts)} concepts, {len(relationships)} relationships")
            return self.graph

        except Exception as e:
            logger.error(f"Error building concept graph: {e}")
            return self.graph

    def add_relationship(
        self,
        session: Session,
        user_id: UUID,
        source_concept_id: UUID,
        target_concept_id: UUID,
        relationship_type: str,
        strength: float = 0.75,
    ) -> Optional[ConceptRelationship]:
        """
        Add or update relationship between concepts.
        
        Args:
            session: Database session
            user_id: User ID
            source_concept_id: Source concept UUID
            target_concept_id: Target concept UUID
            relationship_type: Type of relationship
            strength: Relationship strength (0.0-1.0)
            
        Returns:
            ConceptRelationship object
        """
        try:
            if relationship_type not in self.relationship_types:
                logger.warning(f"Unknown relationship type: {relationship_type}")
                return None

            # Check if relationship exists
            existing = session.query(ConceptRelationship).filter(
                and_(
                    ConceptRelationship.source_concept_id == source_concept_id,
                    ConceptRelationship.target_concept_id == target_concept_id,
                )
            ).first()

            if existing:
                # Strengthen existing relationship
                existing.strength = min(1.0, existing.strength + 0.1)
                existing.reinforcement_count += 1
                relationship = existing
                logger.info(f"Reinforced relationship: {existing.reinforcement_count} times")
            else:
                # Create new relationship
                relationship = ConceptRelationship(
                    user_id=user_id,
                    source_concept_id=source_concept_id,
                    target_concept_id=target_concept_id,
                    relationship_type=relationship_type,
                    strength=min(1.0, max(0.0, strength)),
                )
                session.add(relationship)
                logger.info(f"Created new relationship: {relationship_type}")

            session.commit()
            return relationship

        except Exception as e:
            logger.error(f"Error adding relationship: {e}")
            session.rollback()
            return None

    def find_related_concepts(
        self,
        concept_id: UUID,
        depth: int = 2,
        max_results: int = 10,
    ) -> List[Tuple[UUID, str, float]]:
        """
        Find related concepts in the graph.
        
        Args:
            concept_id: Starting concept UUID
            depth: Maximum depth to traverse
            max_results: Maximum results to return
            
        Returns:
            List of (concept_id, relationship_type, strength) tuples
        """
        try:
            if concept_id not in self.graph:
                logger.warning(f"Concept not in graph: {concept_id}")
                return []

            related = []
            visited = {concept_id}
            queue = [(concept_id, 0)]

            while queue and len(related) < max_results:
                current, current_depth = queue.pop(0)

                if current_depth >= depth:
                    continue

                # Get neighbors
                for neighbor in self.graph.successors(current):
                    if neighbor not in visited:
                        edge_data = self.graph.edges[current, neighbor]
                        related.append((
                            neighbor,
                            edge_data.get('type', 'unknown'),
                            edge_data.get('weight', 0.0),
                        ))
                        visited.add(neighbor)
                        queue.append((neighbor, current_depth + 1))

            # Sort by strength
            related.sort(key=lambda x: x[2], reverse=True)
            return related[:max_results]

        except Exception as e:
            logger.error(f"Error finding related concepts: {e}")
            return []

    def get_concept_paths(
        self,
        source_id: UUID,
        target_id: UUID,
    ) -> List[List[UUID]]:
        """
        Find all paths between two concepts.
        
        Useful for understanding concept connections.
        """
        try:
            if source_id not in self.graph or target_id not in self.graph:
                return []

            paths = list(nx.all_simple_paths(
                self.graph,
                source_id,
                target_id,
                cutoff=3,  # Limit to 3 hops
            ))

            return paths

        except nx.NetworkXNoPath:
            return []
        except Exception as e:
            logger.error(f"Error finding paths: {e}")
            return []

    def compute_concept_importance(
        self,
        session: Session,
        user_id: UUID,
    ) -> Dict[UUID, float]:
        """
        Compute importance score for each concept based on graph structure.
        
        Uses PageRank-like algorithm weighted by:
        - Node confidence
        - Edge strength
        - Reinforcement count
        """
        try:
            if len(self.graph) == 0:
                return {}

            # Add weights from database
            relationships = session.query(ConceptRelationship).filter(
                ConceptRelationship.user_id == user_id
            ).all()

            weights = {}
            for rel in relationships:
                weights[(rel.source_concept_id, rel.target_concept_id)] = rel.strength

            # Compute PageRank
            importance = nx.pagerank(
                self.graph,
                weight='weight',
                max_iter=100,
            )

            # Scale by concept confidence
            concepts = session.query(ConceptMemory).filter(
                ConceptMemory.user_id == user_id
            ).all()

            concept_confidence = {c.id: c.confidence for c in concepts}

            for concept_id in importance:
                confidence = concept_confidence.get(concept_id, 0.5)
                importance[concept_id] *= confidence

            return importance

        except Exception as e:
            logger.error(f"Error computing importance: {e}")
            return {}

    def propagate_reinforcement(
        self,
        session: Session,
        concept_id: UUID,
        propagation_strength: float = 0.8,
    ) -> int:
        """
        Propagate reinforcement through concept graph.
        
        When a concept is reinforced, strengthen related concepts.
        
        Returns: Number of concepts updated
        """
        try:
            updated_count = 0

            # Get neighbors
            if concept_id not in self.graph:
                return 0

            for neighbor in self.graph.successors(concept_id):
                edge_data = self.graph.edges[concept_id, neighbor]

                # Calculate propagated strength
                base_strength = edge_data.get('weight', 0.5)
                new_strength = base_strength * propagation_strength

                # Update concept confidence
                concept = session.query(ConceptMemory).filter(
                    ConceptMemory.id == neighbor
                ).first()

                if concept:
                    concept.confidence = min(1.0, concept.confidence * (1 + (new_strength - base_strength)))
                    concept.reinforcement_count += 1
                    updated_count += 1

            session.commit()
            logger.info(f"Propagated reinforcement to {updated_count} concepts")
            return updated_count

        except Exception as e:
            logger.error(f"Error propagating reinforcement: {e}")
            session.rollback()
            return 0

    def get_graph_statistics(self) -> Dict:
        """Get basic statistics about the concept graph"""
        return {
            'node_count': len(self.graph.nodes()),
            'edge_count': len(self.graph.edges()),
            'density': nx.density(self.graph) if len(self.graph) > 0 else 0.0,
            'avg_clustering': nx.average_clustering(self.graph.to_undirected()) if len(self.graph) > 1 else 0.0,
        }

    def export_subgraph(
        self,
        concept_id: UUID,
        depth: int = 2,
    ) -> Dict:
        """Export subgraph around a concept"""
        try:
            if concept_id not in self.graph:
                return {}

            # Get ego graph
            ego = nx.ego_graph(self.graph, concept_id, radius=depth)

            # Convert to serializable format
            nodes = [
                {
                    'id': str(node),
                    'name': ego.nodes[node].get('name', ''),
                    'confidence': ego.nodes[node].get('confidence', 0.0),
                }
                for node in ego.nodes()
            ]

            edges = [
                {
                    'source': str(edge[0]),
                    'target': str(edge[1]),
                    'type': ego.edges[edge].get('type', ''),
                    'strength': ego.edges[edge].get('weight', 0.0),
                }
                for edge in ego.edges()
            ]

            return {
                'center_id': str(concept_id),
                'nodes': nodes,
                'edges': edges,
            }

        except Exception as e:
            logger.error(f"Error exporting subgraph: {e}")
            return {}
