"""
Cognitive Forgetting Engine

Continuously evaluates every stored memory: should it remain, weaken,
archive, or disappear? Never deletes immediately — soft forgetting only,
via the FORGOTTEN lifecycle state (memories are retained, just excluded
from retrieval). Every decision is explainable.

Merge and supersession decisions are made upstream by `DuplicateResolver`
and `ObsoleteMemoryDetector`; this engine handles what's left after decay:
plain strength-driven weakening, archival, and soft forgetting.
"""
import logging
from datetime import datetime
from typing import Dict, List

from sqlalchemy.orm import Session

from app.db.models import Memory, CognitiveMemoryStateEnum
from app.core.config import settings
from app.services.memory_lifecycle_manager import MemoryLifecycleManager

logger = logging.getLogger(__name__)


class ForgettingEngine:
    """Decides the fate of each memory after decay has been applied."""

    def __init__(self, session: Session):
        self.session = session
        self.lifecycle_manager = MemoryLifecycleManager(session)

    def evaluate(self, memory: Memory) -> Dict:
        """
        Decide whether an (already decayed) memory should remain, weaken,
        archive, or be soft-forgotten.

        Returns:
            Explainable decision: {memory, memory_id, decision, reason, confidence}
        """
        strength = memory.memory_strength if memory.memory_strength is not None else 0.5
        anchor = memory.last_accessed or memory.created_at
        age_days = (datetime.utcnow() - anchor).days if anchor else 0

        if memory.cognitive_state in (CognitiveMemoryStateEnum.ARCHIVED, CognitiveMemoryStateEnum.FORGOTTEN):
            if (
                memory.cognitive_state == CognitiveMemoryStateEnum.ARCHIVED
                and strength <= settings.forgetting_forget_threshold
                and age_days >= settings.forgetting_min_age_days_for_forget
            ):
                return self._forget(memory, strength, age_days)
            return self._remain(memory, "Already archived/forgotten; no further action needed", strength)

        if strength <= settings.forgetting_archive_threshold:
            return self._archive(memory, strength, age_days)

        if strength <= settings.forgetting_weaken_threshold:
            return self._weaken(memory, strength)

        return self._remain(memory, "Sufficient strength and relevance", strength)

    def evaluate_batch(self, memories: List[Memory]) -> List[Dict]:
        """Evaluate a batch of already-decayed memories and commit once."""
        decisions = [self.evaluate(m) for m in memories]
        self.session.commit()
        return decisions

    def _remain(self, memory: Memory, reason: str, strength: float) -> Dict:
        return {
            "memory": memory.content,
            "memory_id": memory.id,
            "decision": "Remain",
            "reason": reason,
            "confidence": round(1.0 - abs(strength - 0.7), 3) if strength is not None else 0.5,
        }

    def _weaken(self, memory: Memory, strength: float) -> Dict:
        # Decay engine already reduced strength upstream; this records and
        # confirms the trajectory rather than moving the memory to a new state.
        reason = f"Strength {strength:.2f} below comfortable threshold; continuing to weaken"
        self.lifecycle_manager._log_event(
            memory, event_type="weaken",
            old_state=memory.cognitive_state, new_state=memory.cognitive_state,
            old_strength=strength, new_strength=strength,
            reason=reason, confidence=0.6,
        )
        return {
            "memory": memory.content, "memory_id": memory.id,
            "decision": "Weaken", "reason": reason, "confidence": 0.6,
        }

    def _archive(self, memory: Memory, strength: float, age_days: int) -> Dict:
        reason = f"Strength {strength:.2f} fell below archive threshold after {age_days} days"
        result = self.lifecycle_manager.transition(memory, CognitiveMemoryStateEnum.ARCHIVED, reason)
        confidence = round(min(1.0, 1.0 - strength), 3)
        return {
            "memory": memory.content, "memory_id": memory.id,
            "decision": "Archived" if result["success"] else "Remain",
            "reason": reason, "confidence": confidence,
        }

    def _forget(self, memory: Memory, strength: float, age_days: int) -> Dict:
        reason = f"Strength {strength:.2f}, archived and untouched for {age_days} days"
        result = self.lifecycle_manager.transition(memory, CognitiveMemoryStateEnum.FORGOTTEN, reason)
        memory.forget_reason = reason
        confidence = round(min(1.0, (1.0 - strength) + (age_days / 365.0) * 0.1), 3)
        return {
            "memory": memory.content, "memory_id": memory.id,
            "decision": "Forgotten" if result["success"] else "Remain",
            "reason": reason, "confidence": confidence,
        }
