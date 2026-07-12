"""
Replay Engine

Selects the memories most worth "replaying" during a dream session — not a
full re-read of everything, but a prioritized subset chosen the way
sleep-based memory consolidation prioritizes salient, uncertain, or
conflicting experiences: high importance, high uncertainty, memories
linked to recently-shifted identity traits, memories in a conflicting
pair, and heavily reinforced memories worth further consolidating. Replay
*rebuilds* understanding (re-scores each memory from scratch) rather than
simply re-reading stored text.
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Set
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import Memory, IdentityNode, CognitiveMemoryStateEnum
from app.core.config import settings
from app.services.cognitive_scoring import HybridScoringEngine
from app.services.contradiction_resolver import ContradictionResolver, ELIGIBLE_TYPES, find_conflicting_pairs

logger = logging.getLogger(__name__)


class ReplayEngine:
    """Selects and rebuilds understanding for high-value memories."""

    def __init__(self, session: Session):
        self.session = session
        # Heuristic-only: no LLM round trip in the dream hot path (Day 2's
        # scoring engine was already dual-mode; dream mode uses the
        # dependency-free path so this can run unattended at scale).
        self.scoring_engine = HybridScoringEngine(use_llm=False)
        self._contradiction_detector = ContradictionResolver()

    def select_for_replay(self, user_id: UUID, batch_size: int = None) -> List[Memory]:
        """Prioritize memories for replay this dream session."""
        batch_size = batch_size or settings.dream_replay_batch_size

        candidates = self.session.query(Memory).filter(
            Memory.user_id == user_id,
            Memory.cognitive_state.notin_([
                CognitiveMemoryStateEnum.ARCHIVED, CognitiveMemoryStateEnum.FORGOTTEN,
            ]),
        ).all()

        if not candidates:
            return []

        recent_identity_ids = self._recently_updated_identity_memory_ids(user_id)
        conflicting_ids = self._conflicting_memory_ids(candidates)

        scored = [
            (memory, self._priority_score(memory, recent_identity_ids, conflicting_ids))
            for memory in candidates
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [m for m, _ in scored[:batch_size]]

    def _priority_score(self, memory: Memory, recent_identity_ids: Set[str], conflicting_ids: Set) -> float:
        importance = memory.importance_score if memory.importance_score is not None else 0.5
        confidence_signal = memory.prediction_confidence or memory.memory_strength or 0.5
        uncertainty = 1.0 - confidence_signal
        identity_recency = 0.3 if str(memory.id) in recent_identity_ids else 0.0
        conflict_bonus = 0.3 if memory.id in conflicting_ids else 0.0
        reinforcement = min(1.0, (memory.reinforcement_count or 0) / 10.0)

        return (
            importance * 0.35 +
            uncertainty * 0.25 +
            identity_recency +
            conflict_bonus +
            reinforcement * 0.20
        )

    def _recently_updated_identity_memory_ids(self, user_id: UUID) -> Set[str]:
        cutoff = datetime.utcnow() - timedelta(days=7)
        nodes = self.session.query(IdentityNode).filter(
            IdentityNode.user_id == user_id,
            IdentityNode.last_reinforced_at.isnot(None),
            IdentityNode.last_reinforced_at >= cutoff,
        ).all()
        ids: Set[str] = set()
        for node in nodes:
            ids.update(node.supporting_memory_ids or [])
        return ids

    def _conflicting_memory_ids(self, memories: List[Memory]) -> Set:
        eligible = [m for m in memories if m.memory_type in ELIGIBLE_TYPES]
        pairs = find_conflicting_pairs(eligible, self._contradiction_detector._is_contradiction)
        ids: Set = set()
        for a, b in pairs:
            ids.add(a.id)
            ids.add(b.id)
        return ids

    def replay(self, memories: List[Memory]) -> List[Dict]:
        """
        Rebuild understanding: re-score each memory from scratch (heuristic
        re-analysis of its content, not a literal re-read) and update its
        cognitive dimensions in place.
        """
        results = []
        for memory in memories:
            previous_importance = memory.importance_score
            scores = self.scoring_engine.score_memory(memory.content or "", memory.memory_type, use_llm=False)

            memory.future_utility_score = scores.get("future_utility_score", memory.future_utility_score)
            memory.identity_impact_score = scores.get("identity_impact_score", memory.identity_impact_score)
            memory.emotional_salience_score = scores.get("emotional_salience_score", memory.emotional_salience_score)
            memory.temporal_persistence_score = scores.get("temporal_persistence_score", memory.temporal_persistence_score)
            memory.importance_score = scores.get("importance_score", memory.importance_score)

            results.append({
                "memory_id": memory.id,
                "previous_importance": previous_importance,
                "new_importance": memory.importance_score,
                "delta": (memory.importance_score or 0.0) - (previous_importance or 0.0),
            })

        self.session.commit()
        return results
