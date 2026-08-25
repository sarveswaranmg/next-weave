"""
Obsolete Memory Detector

When a new memory supersedes an older one ("User prefers Vue." -> "User
builds everything in React."), the old preference shouldn't linger at full
confidence forever, nor should it be silently overwritten. This detector
finds such conflicts among a user's stored memories, reduces confidence in
and archives the obsolete one, strengthens the current one, and preserves
full history via a MemoryEvent.

This is the durable, store-mutating counterpart to Day 6's
`ContradictionResolver`, which only excludes conflicts from a single
composed context without ever touching the database. Detection logic
(verb-bucket grouping, word-overlap conflict test, recency/reinforcement/
confidence winner-scoring) is reused from there rather than duplicated.
"""
import logging
from datetime import datetime
from typing import Dict, List
from uuid import UUID

from sqlalchemy.orm import Session

from neurowave_engine.db.models import Memory, MemoryEvent, CognitiveMemoryStateEnum
from neurowave_engine.core.config import settings
from neurowave_engine.services.contradiction_resolver import ContradictionResolver, ELIGIBLE_TYPES, find_conflicting_pairs

logger = logging.getLogger(__name__)


class ObsoleteMemoryDetector:
    """Detects superseded memories and durably archives them, preserving history."""

    def __init__(self, session: Session, confidence_penalty: float = None):
        self.session = session
        self.confidence_penalty = (
            confidence_penalty if confidence_penalty is not None
            else settings.obsolete_confidence_penalty
        )
        self._detector = ContradictionResolver()

    def detect_and_resolve(self, user_id: UUID, memories: List[Memory]) -> List[Dict]:
        """
        Args:
            user_id: User ID
            memories: Candidate memories to check for supersession (typically
                a user's active IDENTITY/SEMANTIC/PROCEDURAL memories)

        Returns:
            List of explainable resolution decisions:
            {memory, decision, reason, confidence, superseded_memory_id, winning_memory_id}
        """
        candidates = [
            m for m in memories
            if m.memory_type in ELIGIBLE_TYPES and m.cognitive_state != CognitiveMemoryStateEnum.ARCHIVED
        ]

        pairs = find_conflicting_pairs(candidates, self._detector._is_contradiction)

        resolved_ids = set()
        decisions: List[Dict] = []

        for mem_a, mem_b in pairs:
            if mem_a.id in resolved_ids or mem_b.id in resolved_ids:
                continue

            score_a = self._detector._resolution_score(mem_a)
            score_b = self._detector._resolution_score(mem_b)
            winner, loser = (mem_a, mem_b) if score_a >= score_b else (mem_b, mem_a)
            confidence = min(1.0, 0.5 + abs(score_a - score_b))
            bucket = self._detector._bucket_label(loser)

            decisions.append(self._resolve_pair(user_id, winner, loser, bucket, confidence))
            resolved_ids.add(loser.id)

        if decisions:
            self.session.commit()

        return decisions

    def _resolve_pair(self, user_id: UUID, winner: Memory, loser: Memory, bucket: str, confidence: float) -> Dict:
        old_state = loser.cognitive_state
        old_strength = loser.memory_strength

        # Reduce confidence and archive the obsolete memory (never overwrite blindly)
        loser.memory_strength = max(0.0, (loser.memory_strength or 0.5) * self.confidence_penalty)
        loser.cognitive_state = CognitiveMemoryStateEnum.ARCHIVED
        loser.archive_reason = f"Superseded by: \"{winner.content}\""

        # Strengthen the current preference
        winner.memory_strength = min(1.0, (winner.memory_strength or 0.5) + 0.1)
        winner.reinforcement_count = (winner.reinforcement_count or 0) + 1
        winner.last_reinforced_at = datetime.utcnow()

        self.session.add(MemoryEvent(
            memory_id=loser.id,
            user_id=user_id,
            event_type="archive",
            old_state=old_state.value if old_state else None,
            new_state=CognitiveMemoryStateEnum.ARCHIVED.value,
            old_strength=old_strength,
            new_strength=loser.memory_strength,
            reason=loser.archive_reason,
            confidence=confidence,
        ))

        return {
            "memory": loser.content,
            "decision": "Archived",
            "reason": f"Superseded by '{bucket}' statement: \"{winner.content}\"",
            "confidence": round(confidence, 3),
            "superseded_memory_id": loser.id,
            "winning_memory_id": winner.id,
        }
