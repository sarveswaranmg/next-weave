"""
Graph Traversal Engine (WorldTraversalService)

Answers questions over the World Model Graph: what projects are related to
this entity, what systems would be affected by a change here, what does
this depend on (transitively), and why — an explained shortest-path
reasoning trail between any two entities.
"""
import logging
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session
import networkx as nx

from app.db.models import WorldEntityTypeEnum
from app.services.world_graph import WorldGraph

logger = logging.getLogger(__name__)

DEPENDENCY_RELATIONSHIP_TYPES = {"uses", "depends_on", "stores", "deployed_to"}


class WorldTraversalService:
    """Traversal queries over the World Model Graph."""

    def __init__(self, session: Session, user_id: UUID):
        self.session = session
        self.user_id = user_id
        self.world_graph = WorldGraph()
        self.graph = self.world_graph.build_graph_for_user(session, user_id)

    def find_related_projects(self, entity_id: UUID, max_depth: int = 2) -> List[Dict]:
        """Find PROJECT-type entities reachable from a given entity within max_depth hops."""
        if entity_id not in self.graph:
            return []

        undirected = self.graph.to_undirected()
        related = []
        for node, depth in nx.single_source_shortest_path_length(undirected, entity_id, cutoff=max_depth).items():
            if node == entity_id or depth == 0:
                continue
            data = self.graph.nodes[node]
            if data.get("entity_type") == WorldEntityTypeEnum.PROJECT.value:
                related.append({"entity_id": node, "name": data.get("name"), "depth": depth})

        related.sort(key=lambda r: r["depth"])
        return related

    def find_affected_systems(self, entity_id: UUID, max_depth: int = 2) -> List[Dict]:
        """Find entities downstream of (dependent on) a given entity — what
        would be affected if this entity changed."""
        if entity_id not in self.graph:
            return []

        affected = []
        reversed_graph = self.graph.reverse()
        for node, depth in nx.single_source_shortest_path_length(reversed_graph, entity_id, cutoff=max_depth).items():
            if node == entity_id or depth == 0:
                continue
            data = self.graph.nodes[node]
            affected.append({
                "entity_id": node, "name": data.get("name"),
                "entity_type": data.get("entity_type"), "depth": depth,
            })

        affected.sort(key=lambda r: r["depth"])
        return affected

    def find_dependencies(self, entity_id: UUID, max_depth: int = 3) -> List[Dict]:
        """Find what an entity depends on/uses, transitively — following
        only dependency-flavored edges (uses/depends_on/stores/deployed_to),
        not every relationship type."""
        if entity_id not in self.graph:
            return []

        dep_edges = [
            (u, v) for u, v, data in self.graph.edges(data=True)
            if data.get("relationship_type") in DEPENDENCY_RELATIONSHIP_TYPES
        ]
        if not dep_edges:
            return []

        dep_subgraph = self.graph.edge_subgraph(dep_edges)
        if entity_id not in dep_subgraph:
            return []

        deps = []
        for node, depth in nx.single_source_shortest_path_length(dep_subgraph, entity_id, cutoff=max_depth).items():
            if node == entity_id or depth == 0:
                continue
            data = self.graph.nodes[node]
            deps.append({
                "entity_id": node, "name": data.get("name"),
                "entity_type": data.get("entity_type"), "depth": depth,
            })

        deps.sort(key=lambda r: r["depth"])
        return deps

    def explain_path(self, source_entity_id: UUID, target_entity_id: UUID) -> Optional[Dict]:
        """Explain the shortest reasoning path between two entities, with
        each hop's relationship type and direction."""
        if source_entity_id not in self.graph or target_entity_id not in self.graph:
            return None

        try:
            path = nx.shortest_path(self.graph.to_undirected(), source_entity_id, target_entity_id)
        except nx.NetworkXNoPath:
            return None

        hops = []
        for i in range(len(path) - 1):
            a, b = path[i], path[i + 1]
            if self.graph.has_edge(a, b):
                edge, direction = self.graph[a][b], "forward"
            else:
                edge, direction = self.graph[b][a], "backward"
            hops.append({
                "from": self.graph.nodes[a].get("name"),
                "to": self.graph.nodes[b].get("name"),
                "relationship": edge.get("relationship_type"),
                "direction": direction,
                "strength": edge.get("weight"),
            })

        return {
            "path": [self.graph.nodes[n].get("name") for n in path],
            "hops": hops,
            "length": len(path) - 1,
        }
