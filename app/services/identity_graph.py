"""
Identity Graph Service

Builds and manages the user's identity graph.
Enables graph traversal, relationship discovery, and importance analysis.
"""

from typing import List, Dict, Optional, Set, Tuple
import logging
from datetime import datetime
import uuid

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

import networkx as nx
from networkx.algorithms import shortest_path, has_path

from app.db.models import IdentityNode, IdentityRelationship


logger = logging.getLogger(__name__)


class IdentityGraphService:
    """
    Manages the identity graph - a network of identity traits.
    
    Enables:
    - Graph construction from database
    - Relationship discovery
    - Path finding (how traits connect)
    - Importance ranking (PageRank)
    - Goal-interest alignment
    - Influence propagation
    """

    def __init__(self, db: Session):
        """Initialize service with database session."""
        self.db = db
        self.graph_cache = {}  # Cache graphs by user_id

    def build_graph_for_user(self, user_id: str, min_confidence: float = 0.5) -> nx.DiGraph:
        """
        Build identity graph from database nodes and relationships.
        
        Args:
            user_id: User ID
            min_confidence: Minimum confidence for node inclusion
            
        Returns:
            NetworkX directed graph
        """
        graph = nx.DiGraph()

        # Get nodes
        nodes = self.db.query(IdentityNode).filter(
            and_(
                IdentityNode.user_id == user_id,
                IdentityNode.confidence >= min_confidence
            )
        ).all()

        # Add nodes to graph (keyed by string id so lookups from string-typed
        # API params like trait_id match regardless of the DB driver's UUID type)
        for node in nodes:
            graph.add_node(
                str(node.id),
                type=node.node_type,
                value=node.node_value,
                confidence=node.confidence,
                importance=node.importance,
                reinforcement_count=node.reinforcement_count
            )

        # Get relationships
        relationships = self.db.query(IdentityRelationship).filter(
            IdentityRelationship.user_id == user_id
        ).all()

        # Add edges to graph
        for rel in relationships:
            source_id = str(rel.source_node_id)
            target_id = str(rel.target_node_id)

            # Skip edges where nodes don't exist
            if source_id not in graph or target_id not in graph:
                continue

            graph.add_edge(
                source_id,
                target_id,
                type=rel.relationship_type,
                strength=rel.strength,
                reinforcement_count=rel.reinforcement_count
            )

        # Cache the graph
        self.graph_cache[user_id] = graph

        logger.info(
            f"Built identity graph for user {user_id}: "
            f"{len(graph.nodes())} nodes, {len(graph.edges())} edges"
        )

        return graph

    def add_relationship(
        self,
        user_id: str,
        source_node_id: str,
        target_node_id: str,
        relationship_type: str,
        strength: float = 0.5
    ) -> bool:
        """
        Add relationship between two identity traits.
        
        Args:
            user_id: User ID
            source_node_id: Source trait ID
            target_node_id: Target trait ID
            relationship_type: Type of relationship
            strength: Relationship strength (0.0-1.0)
            
        Returns:
            Success
        """
        # Check if nodes exist
        source = self.db.query(IdentityNode).filter_by(
            id=source_node_id,
            user_id=user_id
        ).first()
        target = self.db.query(IdentityNode).filter_by(
            id=target_node_id,
            user_id=user_id
        ).first()

        if not source or not target:
            logger.warning(
                f"Cannot add relationship: source or target node not found "
                f"(source={source_node_id}, target={target_node_id})"
            )
            return False

        # Check if relationship exists
        existing = self.db.query(IdentityRelationship).filter(
            and_(
                IdentityRelationship.user_id == user_id,
                IdentityRelationship.source_node_id == source_node_id,
                IdentityRelationship.target_node_id == target_node_id
            )
        ).first()

        if existing:
            # Strengthen existing
            existing.strength = min(1.0, strength)
            existing.reinforcement_count += 1
            existing.last_reinforced_at = datetime.utcnow()
        else:
            # Create new
            rel = IdentityRelationship(
                id=uuid.uuid4(),
                user_id=user_id,
                source_node_id=source_node_id,
                target_node_id=target_node_id,
                relationship_type=relationship_type,
                strength=strength,
                reinforcement_count=1
            )
            self.db.add(rel)

        self.db.commit()

        # Invalidate cache
        if user_id in self.graph_cache:
            del self.graph_cache[user_id]

        logger.info(
            f"Added relationship for user {user_id}: "
            f"{source.node_value} --[{relationship_type}]--> {target.node_value}"
        )

        return True

    def find_related_traits(
        self,
        user_id: str,
        trait_id: str,
        max_distance: int = 2
    ) -> List[Dict]:
        """
        Find traits related to a given trait.
        
        Args:
            user_id: User ID
            trait_id: Starting trait ID
            max_distance: Maximum path distance
            
        Returns:
            List of related traits with distance and path
        """
        graph = self.build_graph_for_user(user_id)

        if trait_id not in graph:
            logger.warning(f"Trait {trait_id} not found in graph")
            return []

        related = []

        # BFS to find all nodes within max_distance
        visited = set()
        queue = [(trait_id, 0, [trait_id])]

        while queue:
            node_id, distance, path = queue.pop(0)

            if node_id in visited:
                continue
            visited.add(node_id)

            if distance > 0:  # Don't include source node
                node_data = graph.nodes[node_id]
                related.append({
                    "node_id": node_id,
                    "value": node_data.get("value"),
                    "type": node_data.get("type"),
                    "confidence": node_data.get("confidence"),
                    "distance": distance,
                    "path": path
                })

            if distance < max_distance:
                # Explore neighbors
                for neighbor in graph.neighbors(node_id):
                    if neighbor not in visited:
                        edge_data = graph[node_id][neighbor]
                        queue.append((
                            neighbor,
                            distance + 1,
                            path + [neighbor]
                        ))

        # Sort by distance then by confidence
        related.sort(key=lambda x: (x["distance"], -x["confidence"]))

        return related

    def find_shortest_path(
        self,
        user_id: str,
        source_trait_id: str,
        target_trait_id: str
    ) -> Optional[List[Dict]]:
        """
        Find shortest path between two traits.
        
        Args:
            user_id: User ID
            source_trait_id: Source trait ID
            target_trait_id: Target trait ID
            
        Returns:
            Path as list of trait info, or None if no path
        """
        graph = self.build_graph_for_user(user_id)

        if source_trait_id not in graph or target_trait_id not in graph:
            logger.warning("One or both traits not found in graph")
            return None

        try:
            path = shortest_path(graph, source_trait_id, target_trait_id)
            
            # Enrich path with node data
            enriched_path = []
            for node_id in path:
                node_data = graph.nodes[node_id]
                enriched_path.append({
                    "node_id": node_id,
                    "value": node_data.get("value"),
                    "type": node_data.get("type"),
                    "confidence": node_data.get("confidence")
                })

            return enriched_path

        except Exception as e:
            logger.debug(f"No path found between traits: {e}")
            return None

    def compute_importance_scores(
        self,
        user_id: str,
        algorithm: str = "pagerank"
    ) -> Dict[str, float]:
        """
        Compute importance scores for all traits using graph algorithms.
        
        Args:
            user_id: User ID
            algorithm: Algorithm to use (pagerank, betweenness, closeness)
            
        Returns:
            Dict mapping node_id to importance score
        """
        graph = self.build_graph_for_user(user_id)

        if len(graph.nodes()) == 0:
            return {}

        if algorithm == "pagerank":
            scores = nx.pagerank(graph, weight="strength")
        elif algorithm == "betweenness":
            scores = nx.betweenness_centrality(graph, weight="strength")
        elif algorithm == "closeness":
            scores = nx.closeness_centrality(graph)
        else:
            logger.warning(f"Unknown algorithm: {algorithm}, using pagerank")
            scores = nx.pagerank(graph, weight="strength")

        # Normalize scores to 0-1
        if scores:
            max_score = max(scores.values())
            min_score = min(scores.values())
            if max_score > min_score:
                scores = {
                    node_id: (score - min_score) / (max_score - min_score)
                    for node_id, score in scores.items()
                }

        return scores

    def get_goal_interest_alignment(self, user_id: str) -> Dict:
        """
        Analyze how well interests align with goals.
        
        Args:
            user_id: User ID
            
        Returns:
            Alignment metrics
        """
        nodes = self.db.query(IdentityNode).filter(
            IdentityNode.user_id == user_id
        ).all()

        goals = [n for n in nodes if n.node_type == "goal"]
        interests = [n for n in nodes if n.node_type == "interest"]

        alignment = []

        for goal in goals:
            for interest in interests:
                path = self.find_shortest_path(user_id, interest.id, goal.id)
                if path:
                    alignment.append({
                        "goal": goal.node_value,
                        "interest": interest.node_value,
                        "path_length": len(path),
                        "connected": True
                    })

        # Calculate alignment score
        aligned_count = len(alignment)
        total_pairs = len(goals) * len(interests) if goals and interests else 0
        alignment_score = aligned_count / total_pairs if total_pairs > 0 else 0

        return {
            "aligned_pairs": aligned_count,
            "total_goal_interest_pairs": total_pairs,
            "alignment_score": alignment_score,
            "alignments": alignment
        }

    def propagate_importance(
        self,
        user_id: str,
        source_node_id: str,
        propagation_factor: float = 0.7
    ) -> Dict:
        """
        Propagate importance from one trait through its network.
        
        Args:
            user_id: User ID
            source_node_id: Starting trait ID
            propagation_factor: How much importance propagates
            
        Returns:
            Propagation results
        """
        graph = self.build_graph_for_user(user_id)

        if source_node_id not in graph:
            return {}

        source = self.db.query(IdentityNode).filter_by(
            id=source_node_id
        ).first()

        if not source:
            return {}

        propagated = {}
        visited = set()
        queue = [(source_node_id, source.importance, 0)]

        while queue:
            node_id, current_importance, depth = queue.pop(0)

            if node_id in visited:
                continue
            visited.add(node_id)

            # Propagate to neighbors
            for neighbor in graph.neighbors(node_id):
                edge_data = graph[node_id][neighbor]
                strength = edge_data.get("strength", 0.5)

                # Calculate propagated importance
                propagated_importance = current_importance * strength * propagation_factor

                if propagated_importance > 0.01:  # Threshold
                    if neighbor not in propagated:
                        propagated[neighbor] = 0
                    propagated[neighbor] += propagated_importance

                    queue.append((neighbor, propagated_importance, depth + 1))

        return {
            "source_node_id": source_node_id,
            "propagated_nodes": len(propagated),
            "propagation": propagated
        }

    def export_subgraph(
        self,
        user_id: str,
        center_node_id: str,
        radius: int = 2
    ) -> Dict:
        """
        Export subgraph around a center node.
        
        Args:
            user_id: User ID
            center_node_id: Center trait ID
            radius: Radius to include
            
        Returns:
            Subgraph data
        """
        graph = self.build_graph_for_user(user_id)

        if center_node_id not in graph:
            return {}

        # Get nodes within radius
        nodes_in_radius = {center_node_id}
        queue = [(center_node_id, 0)]

        while queue:
            node_id, distance = queue.pop(0)

            if distance < radius:
                for neighbor in graph.neighbors(node_id):
                    if neighbor not in nodes_in_radius:
                        nodes_in_radius.add(neighbor)
                        queue.append((neighbor, distance + 1))

                # Also check predecessors
                for pred in graph.predecessors(node_id):
                    if pred not in nodes_in_radius:
                        nodes_in_radius.add(pred)
                        queue.append((pred, distance + 1))

        # Extract subgraph
        subgraph = graph.subgraph(nodes_in_radius)

        # Convert to export format
        nodes_data = []
        for node_id in subgraph.nodes():
            node_info = graph.nodes[node_id]
            nodes_data.append({
                "id": node_id,
                "value": node_info.get("value"),
                "type": node_info.get("type"),
                "confidence": node_info.get("confidence"),
                "importance": node_info.get("importance")
            })

        edges_data = []
        for source, target in subgraph.edges():
            edge_info = graph[source][target]
            edges_data.append({
                "source": source,
                "target": target,
                "type": edge_info.get("type"),
                "strength": edge_info.get("strength")
            })

        return {
            "center_node_id": center_node_id,
            "radius": radius,
            "nodes": nodes_data,
            "edges": edges_data
        }

    def get_graph_statistics(self, user_id: str) -> Dict:
        """
        Get comprehensive graph statistics.
        
        Args:
            user_id: User ID
            
        Returns:
            Graph metrics
        """
        graph = self.build_graph_for_user(user_id)

        if len(graph.nodes()) == 0:
            return {"nodes": 0, "edges": 0}

        # Basic metrics
        stats = {
            "nodes": len(graph.nodes()),
            "edges": len(graph.edges()),
            "density": nx.density(graph),
        }

        # Connected components
        weakly_connected = nx.number_weakly_connected_components(graph)
        stats["weakly_connected_components"] = weakly_connected

        # Centrality analysis
        degree_centrality = nx.degree_centrality(graph)
        stats["avg_degree_centrality"] = sum(degree_centrality.values()) / len(degree_centrality)

        # Average path length
        if weakly_connected == 1:
            try:
                stats["avg_shortest_path_length"] = nx.average_shortest_path_length(
                    graph.to_undirected()
                )
            except:
                stats["avg_shortest_path_length"] = None
        else:
            stats["avg_shortest_path_length"] = None

        return stats
