"""
Memory Decay Engine

Each memory carries a `memory_strength` in [0, 1] that weakens over time —
but not as a simple function of age. Decay depends on age, retrieval
frequency, reinforcement, concept/identity membership, importance, and
emotional significance, on top of an adaptive per-type base rate (identity
memories decay far slower than a throwaway episodic aside).
"""
import logging
import math
from datetime import datetime
from typing import Dict, List, Optional, Set
from uuid import UUID

from sqlalchemy.orm import Session

from neurowave_engine.db.models import Memory, MemoryTypeEnum, ConceptMemory, IdentityNode
from neurowave_engine.core.config import settings

logger = logging.getLogger(__name__)


class AdaptiveDecayStrategy:
    """
    Determines the base decay rate for a memory from its type (and, for
    episodic memories, its importance) — the "different memories decay
    differently" requirement. Rates are configurable via Settings so decay
    curves can be tuned without code changes.
    """

    def base_rate(self, memory: Memory) -> float:
        if memory.memory_type == MemoryTypeEnum.IDENTITY:
            return settings.decay_rate_identity
        if memory.memory_type == MemoryTypeEnum.CONCEPT:
            return settings.decay_rate_concept
        if memory.memory_type == MemoryTypeEnum.PROCEDURAL:
            return settings.decay_rate_procedural
        if memory.memory_type == MemoryTypeEnum.SEMANTIC:
            return settings.decay_rate_semantic
        if memory.memory_type == MemoryTypeEnum.EPISODIC:
            importance = memory.importance_score if memory.importance_score is not None else 0.5
            if importance < settings.low_importance_episodic_threshold:
                return settings.decay_rate_episodic_low_importance  # "random conversation"
            return settings.decay_rate_episodic
        return settings.decay_rate_semantic


class MemoryDecayEngine:
    """Computes and applies multi-factor decay to memory_strength."""

    def __init__(self, session: Session, strategy: Optional[AdaptiveDecayStrategy] = None):
        self.session = session
        self.strategy = strategy or AdaptiveDecayStrategy()
        self._concept_member_ids: Optional[Set[str]] = None
        self._identity_member_ids: Optional[Set[str]] = None
        self._membership_user_id: Optional[UUID] = None

    def _membership_sets(self, user_id: UUID) -> None:
        """Cache which memory ids are referenced by concepts/identity traits
        for this user, so per-memory lookups don't hit the DB N times."""
        if self._membership_user_id != user_id:
            self._concept_member_ids = None
            self._identity_member_ids = None
            self._membership_user_id = user_id

        if self._concept_member_ids is None:
            concept_ids: Set[str] = set()
            for c in self.session.query(ConceptMemory).filter(ConceptMemory.user_id == user_id).all():
                concept_ids.update(str(mid) for mid in (c.supporting_memory_ids or []))
            self._concept_member_ids = concept_ids

        if self._identity_member_ids is None:
            identity_ids: Set[str] = set()
            for node in self.session.query(IdentityNode).filter(IdentityNode.user_id == user_id).all():
                identity_ids.update(str(mid) for mid in (node.supporting_memory_ids or []))
            self._identity_member_ids = identity_ids

    def compute_decay_factor(self, memory: Memory) -> Dict:
        """
        Compute the effective decay rate and its contributing factors for a
        single memory. Pure computation — does not mutate the memory.
        """
        self._membership_sets(memory.user_id)

        base_rate = self.strategy.base_rate(memory)

        anchor = memory.last_accessed or memory.created_at
        age_days = max(0.0, (datetime.utcnow() - anchor).total_seconds() / 86400.0) if anchor else 0.0
        age_factor = min(2.0, 1.0 + age_days / 365.0)  # untouched + old decays faster, capped at 2x

        retrieval_factor = 1.0 / (1.0 + math.log1p(memory.retrieval_count or 0))

        reinforcement = memory.reinforcement_score if memory.reinforcement_score is not None else 0.5
        reinforcement_factor = 1.0 - (reinforcement * 0.6)  # more reinforced => slower decay

        in_concept = str(memory.id) in self._concept_member_ids
        in_identity = str(memory.id) in self._identity_member_ids
        membership_factor = 1.0
        if in_identity:
            membership_factor *= 0.5  # identity-linked memories decay much slower
        if in_concept:
            membership_factor *= 0.7  # concept-linked memories decay slower

        importance = memory.importance_score if memory.importance_score is not None else 0.5
        importance_factor = 1.0 - (importance * 0.5)

        emotional_salience = memory.emotional_salience_score if memory.emotional_salience_score is not None else 0.5
        emotional_factor = 1.0 - (emotional_salience * 0.3)

        effective_rate = max(0.0001, min(1.0, (
            base_rate * age_factor * retrieval_factor * reinforcement_factor *
            membership_factor * importance_factor * emotional_factor
        )))

        return {
            "base_rate": base_rate,
            "age_days": age_days,
            "age_factor": age_factor,
            "retrieval_factor": retrieval_factor,
            "reinforcement_factor": reinforcement_factor,
            "membership_factor": membership_factor,
            "importance_factor": importance_factor,
            "emotional_factor": emotional_factor,
            "effective_decay_rate": effective_rate,
            "in_concept": in_concept,
            "in_identity": in_identity,
        }

    def apply_decay(self, memory: Memory) -> Dict:
        """Apply one decay step to a memory's strength. Does not commit —
        caller controls the transaction (see MemoryEvolutionPipeline)."""
        factors = self.compute_decay_factor(memory)
        previous_strength = memory.memory_strength if memory.memory_strength is not None else 0.5

        new_strength = max(0.0, previous_strength * (1.0 - factors["effective_decay_rate"]))

        memory.memory_strength = new_strength
        memory.decay_rate = factors["effective_decay_rate"]
        memory.last_decay_at = datetime.utcnow()

        return {
            "memory_id": memory.id,
            "previous_strength": previous_strength,
            "new_strength": new_strength,
            **factors,
        }

    def apply_decay_batch(self, memories: List[Memory]) -> List[Dict]:
        """Apply decay to a batch of memories (same user, for cache reuse)."""
        return [self.apply_decay(m) for m in memories]
