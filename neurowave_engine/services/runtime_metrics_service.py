"""
Runtime Metrics Rollup

Computes and persists a point-in-time snapshot of the cognitive runtime's
overall scale and health — memory/concept/identity/world-graph counts,
compression, and health score — the data behind `GET /runtime/metrics`
and `GET /runtime/dashboard`.
"""
import logging
from typing import Dict, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from neurowave_engine.db.models import (
    Memory, ConceptMemory, IdentityNode, WorldEntity, WorldRelationship,
    Project, RuntimeMetrics,
)
from neurowave_engine.services.memory_health_monitor import MemoryHealthService
from neurowave_engine.services.token_budget_optimizer import TokenBudgetOptimizer

logger = logging.getLogger(__name__)


class RuntimeMetricsService:
    """Computes and persists runtime-wide (or per-user) metrics rollups."""

    def __init__(self, session: Session):
        self.session = session

    def compute(self, user_id: Optional[UUID] = None, persist: bool = True) -> Dict:
        """
        Args:
            user_id: Scope to one user, or None for a global rollup
            persist: Whether to write a RuntimeMetrics row (trend history)

        Returns:
            Dict of current counts/ratios/health score.
        """
        memory_query = self.session.query(Memory)
        concept_query = self.session.query(ConceptMemory)
        identity_query = self.session.query(IdentityNode)
        world_entity_query = self.session.query(WorldEntity)
        world_rel_query = self.session.query(WorldRelationship)
        project_query = self.session.query(Project)

        if user_id:
            memory_query = memory_query.filter(Memory.user_id == user_id)
            concept_query = concept_query.filter(ConceptMemory.user_id == user_id)
            identity_query = identity_query.filter(IdentityNode.user_id == user_id)
            world_entity_query = world_entity_query.filter(WorldEntity.user_id == user_id)
            world_rel_query = world_rel_query.filter(WorldRelationship.user_id == user_id)
            project_query = project_query.filter(Project.user_id == user_id)

        memories = memory_query.all()
        memory_count = len(memories)

        optimizer = TokenBudgetOptimizer()
        raw_tokens = sum(optimizer.estimate_tokens(m.content or "") for m in memories)
        weighted_tokens = sum(
            optimizer.estimate_tokens(m.content or "") * (m.memory_strength or 0.5) for m in memories
        )
        compression_ratio = (1 - weighted_tokens / raw_tokens) if raw_tokens > 0 else 0.0

        health_score = 0.0
        if user_id:
            health_score = MemoryHealthService(self.session).compute_health(user_id).get(
                "cognitive_health_score", 0.0
            )

        metrics = {
            "memory_count": memory_count,
            "concept_count": concept_query.count(),
            "identity_nodes": identity_query.count(),
            "world_nodes": world_entity_query.count(),
            "world_relationships": world_rel_query.count(),
            "project_count": project_query.count(),
            "compression_ratio": round(compression_ratio, 4),
            "cognitive_health_score": health_score,
        }

        if persist:
            row = RuntimeMetrics(user_id=user_id, **metrics)
            self.session.add(row)
            self.session.commit()

        return metrics
