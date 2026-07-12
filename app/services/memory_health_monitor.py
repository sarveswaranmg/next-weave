"""
Cognitive Health Monitor

Aggregates duplicate ratio, forgotten ratio, archive ratio, average
strength, average decay, concept/identity graph complexity, storage
growth, and token efficiency into a single "Cognitive Health Score" — the
dashboard summary metric for whether a user's memory store is becoming
more efficient over time, or just bigger.

Archiving and forgetting are *healthy maintenance*, not failure — so
archive/forgotten ratios are scored against an expected healthy band
rather than simply "lower is better." Remaining duplicates among *active*
memories and overall entropy are penalized directly, since those represent
disorder the evolution pipeline hasn't cleaned up yet.
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.models import Memory, CognitiveMemoryStateEnum
from app.core.config import settings
from app.services.memory_entropy import MemoryEntropyCalculator
from app.services.concept_graph import ConceptGraph
from app.services.identity_graph import IdentityGraphService
from app.services.token_budget_optimizer import TokenBudgetOptimizer

logger = logging.getLogger(__name__)

INACTIVE_STATES = (CognitiveMemoryStateEnum.ARCHIVED, CognitiveMemoryStateEnum.FORGOTTEN)


class MemoryHealthService:
    """Computes the overall Cognitive Health Score for a user's memory store."""

    def __init__(self, session: Session):
        self.session = session
        self.entropy_calculator = MemoryEntropyCalculator(session)

    def compute_health(self, user_id: UUID) -> Dict:
        memories = self.session.query(Memory).filter(Memory.user_id == user_id).all()

        if not memories:
            return self._empty_health(user_id)

        total = len(memories)
        state_counts: Dict[str, int] = {}
        for m in memories:
            key = m.cognitive_state.value if m.cognitive_state else "unknown"
            state_counts[key] = state_counts.get(key, 0) + 1

        forgotten_ratio = state_counts.get(CognitiveMemoryStateEnum.FORGOTTEN.value, 0) / total
        archive_ratio = state_counts.get(CognitiveMemoryStateEnum.ARCHIVED.value, 0) / total

        active_memories = [m for m in memories if m.cognitive_state not in INACTIVE_STATES]
        avg_strength_all = sum((m.memory_strength or 0.0) for m in memories) / total
        avg_strength_active = (
            sum((m.memory_strength or 0.0) for m in active_memories) / len(active_memories)
            if active_memories else 0.0
        )
        avg_decay = sum((m.decay_rate or 0.0) for m in memories) / total

        entropy = self.entropy_calculator.calculate(user_id, memories=active_memories or memories)
        duplicate_ratio = entropy["redundancy"]

        graph_complexity = self._graph_complexity(user_id)
        storage_growth = self._storage_growth(user_id)
        token_efficiency = self._token_efficiency(active_memories)

        health_score = self._score(
            duplicate_ratio=duplicate_ratio,
            archive_ratio=archive_ratio,
            forgotten_ratio=forgotten_ratio,
            avg_strength_active=avg_strength_active,
            entropy_score=entropy["entropy_score"],
            graph_complexity=graph_complexity,
        )

        return {
            "user_id": str(user_id),
            "total_memories": total,
            "active_memories": len(active_memories),
            "duplicate_ratio": round(duplicate_ratio, 4),
            "forgotten_ratio": round(forgotten_ratio, 4),
            "archive_ratio": round(archive_ratio, 4),
            "average_strength": round(avg_strength_all, 4),
            "average_strength_active": round(avg_strength_active, 4),
            "average_decay": round(avg_decay, 4),
            "entropy_score": entropy["entropy_score"],
            "graph_complexity": round(graph_complexity, 4),
            "storage_growth_ratio": round(storage_growth, 4),
            "token_efficiency": round(token_efficiency, 4),
            "state_distribution": state_counts,
            "cognitive_health_score": round(health_score, 2),
        }

    def _graph_complexity(self, user_id: UUID) -> float:
        try:
            concept_graph = ConceptGraph()
            concept_graph.build_graph_for_user(self.session, user_id)
            concept_stats = concept_graph.get_graph_statistics()
            identity_stats = IdentityGraphService(self.session).get_graph_statistics(user_id)

            concept_density = concept_stats.get("density", 0.0)
            identity_density = identity_stats.get("density", 0.0)
            combined = (concept_density + identity_density) / 2
            # Healthy graphs are moderately connected - score distance from an ideal band.
            return self._band_score(combined, 0.05, 0.45)
        except Exception as e:
            logger.warning(f"MemoryHealthService: graph complexity calculation failed: {e}")
            return 0.5

    def _storage_growth(self, user_id: UUID) -> float:
        total = self.session.query(func.count(Memory.id)).filter(Memory.user_id == user_id).scalar() or 0
        if total == 0:
            return 0.0
        cutoff = datetime.utcnow() - timedelta(days=7)
        recent = self.session.query(func.count(Memory.id)).filter(
            Memory.user_id == user_id, Memory.created_at >= cutoff
        ).scalar() or 0
        return recent / total

    def _token_efficiency(self, memories: List[Memory]) -> float:
        if not memories:
            return 1.0
        optimizer = TokenBudgetOptimizer()
        raw_tokens = sum(optimizer.estimate_tokens(m.content or "") for m in memories)
        if raw_tokens == 0:
            return 1.0
        # Strength-weighted tokens vs raw volume: a store dominated by
        # high-strength content is more token-efficient than one carrying
        # a lot of weak, marginal memories.
        weighted_tokens = sum(
            optimizer.estimate_tokens(m.content or "") * (m.memory_strength or 0.5) for m in memories
        )
        return weighted_tokens / raw_tokens

    def _score(
        self,
        duplicate_ratio: float,
        archive_ratio: float,
        forgotten_ratio: float,
        avg_strength_active: float,
        entropy_score: float,
        graph_complexity: float,
    ) -> float:
        w = settings
        raw = (
            (1 - duplicate_ratio) * w.health_weight_duplicate +
            self._band_score(archive_ratio, 0.05, 0.40) * w.health_weight_archive +
            self._band_score(forgotten_ratio, 0.0, 0.15) * w.health_weight_forgotten +
            avg_strength_active * w.health_weight_strength +
            (1 - entropy_score) * w.health_weight_entropy +
            graph_complexity * w.health_weight_graph_complexity
        )
        return max(0.0, min(100.0, raw * 100))

    @staticmethod
    def _band_score(value: float, low: float, high: float) -> float:
        """1.0 inside [low, high], linearly falling off to 0.0 outside it."""
        if low <= value <= high:
            return 1.0
        band_width = max(high - low, 0.05)
        if value < low:
            return max(0.0, 1.0 - (low - value) / band_width)
        return max(0.0, 1.0 - (value - high) / band_width)

    def _empty_health(self, user_id: UUID) -> Dict:
        return {
            "user_id": str(user_id), "total_memories": 0, "active_memories": 0,
            "duplicate_ratio": 0.0, "forgotten_ratio": 0.0, "archive_ratio": 0.0,
            "average_strength": 0.0, "average_strength_active": 0.0, "average_decay": 0.0,
            "entropy_score": 0.0, "graph_complexity": 0.0, "storage_growth_ratio": 0.0,
            "token_efficiency": 1.0, "state_distribution": {}, "cognitive_health_score": 0.0,
        }
