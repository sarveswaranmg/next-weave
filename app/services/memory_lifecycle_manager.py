"""
Memory Lifecycle Manager

Every memory has a lifecycle:

    ACTIVE -> REINFORCED -> SEMANTIC_CANDIDATE ("SEMANTIC") -> DORMANT
    -> ARCHIVED -> FORGOTTEN

(with DECAYING as an intermediate weakening state, and revival possible at
almost every step — see `ReinforcementRecoveryService`). This wraps the
Day 2 `MemoryStateMachine` with database persistence and event logging, so
every transition is both validated and auditable via `MemoryEvent`.
"""
import logging
from datetime import datetime
from typing import Dict, List
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import Memory, MemoryEvent, CognitiveMemoryStateEnum
from app.services.memory_state import MemoryStateMachine

logger = logging.getLogger(__name__)


class MemoryLifecycleManager:
    """Session-aware, event-logging wrapper around the Day 2 state machine."""

    def __init__(self, session: Session):
        self.session = session

    def evaluate_after_decay(self, memory: Memory) -> Dict:
        """
        Evaluate the time-based *state* transition for a memory whose
        `memory_strength` has already been updated by `MemoryDecayEngine`.

        Deliberately does not reuse `MemoryStateMachine.update_state_by_time_decay()`
        wholesale — that method also re-applies its own exponential strength
        decay when the state doesn't change, which would double-decay a
        memory already processed by the richer multi-factor decay engine.
        Only the state-transition-by-idle-time thresholds are reused here;
        strength is treated as already correct.
        """
        old_state = memory.cognitive_state
        old_strength = memory.memory_strength
        anchor = memory.last_accessed or memory.created_at
        days_idle = (datetime.utcnow() - anchor).days if anchor else 0
        thresholds = MemoryStateMachine.TIME_THRESHOLDS

        new_state = old_state
        if old_state in (CognitiveMemoryStateEnum.ACTIVE, CognitiveMemoryStateEnum.REINFORCED):
            if days_idle > thresholds["active_to_dormant"]:
                new_state = CognitiveMemoryStateEnum.DORMANT
        elif old_state == CognitiveMemoryStateEnum.DORMANT:
            if days_idle > thresholds["dormant_to_decay"]:
                new_state = CognitiveMemoryStateEnum.DECAYING
        elif old_state == CognitiveMemoryStateEnum.DECAYING:
            if days_idle > thresholds["decay_to_archive"]:
                new_state = CognitiveMemoryStateEnum.ARCHIVED
                memory.archive_reason = memory.archive_reason or f"No activity for {days_idle} days"

        changed = new_state != old_state
        if changed:
            memory.cognitive_state = new_state

        self._maybe_forget(memory)

        state_label = old_state.value if old_state else "unknown"
        reason = (
            f"Transitioned {state_label} -> {memory.cognitive_state.value} ({days_idle} days idle)"
            if memory.cognitive_state != old_state
            else f"Remained {state_label} ({days_idle} days idle)"
        )

        self._log_event(
            memory, event_type="decay",
            old_state=old_state, new_state=memory.cognitive_state,
            old_strength=old_strength, new_strength=memory.memory_strength,
            reason=reason,
        )

        return {
            "memory_id": memory.id,
            "changed": memory.cognitive_state != old_state,
            "old_state": old_state,
            "new_state": memory.cognitive_state,
            "reason": reason,
        }

    def _maybe_forget(self, memory: Memory) -> None:
        """Beyond what the Day 2 machine handles: ARCHIVED memories that
        stay untouched past `archive_to_forgotten` days become FORGOTTEN —
        soft: retained in the database, excluded from retrieval, still
        revivable (see ReinforcementRecoveryService)."""
        if memory.cognitive_state != CognitiveMemoryStateEnum.ARCHIVED:
            return

        anchor = memory.last_accessed or memory.created_at
        if not anchor:
            return

        days_idle = (datetime.utcnow() - anchor).days
        threshold = MemoryStateMachine.TIME_THRESHOLDS.get("archive_to_forgotten", 180)

        if days_idle > threshold:
            memory.cognitive_state = CognitiveMemoryStateEnum.FORGOTTEN
            memory.forget_reason = f"No activity for {days_idle} days after archival"
            memory.memory_strength = max(0.0, (memory.memory_strength or 0.0) * 0.5)

    def transition(self, memory: Memory, target_state: CognitiveMemoryStateEnum, reason: str) -> Dict:
        """Force a validated transition, logging the outcome."""
        old_state = memory.cognitive_state
        old_strength = memory.memory_strength

        machine = MemoryStateMachine(memory)
        success, message = machine.force_transition(target_state, reason)

        if success:
            if target_state == CognitiveMemoryStateEnum.ARCHIVED:
                memory.archive_reason = reason
            elif target_state == CognitiveMemoryStateEnum.FORGOTTEN:
                memory.forget_reason = reason

            self._log_event(
                memory, event_type="transition",
                old_state=old_state, new_state=memory.cognitive_state,
                old_strength=old_strength, new_strength=memory.memory_strength,
                reason=message,
            )

        return {
            "success": success,
            "message": message,
            "old_state": old_state,
            "new_state": memory.cognitive_state,
        }

    def evaluate_batch(self, memories: List[Memory]) -> List[Dict]:
        """Evaluate post-decay state transitions for a batch and commit once."""
        results = [self.evaluate_after_decay(m) for m in memories]
        self.session.commit()
        return results

    def _log_event(
        self,
        memory: Memory,
        event_type: str,
        old_state: CognitiveMemoryStateEnum,
        new_state: CognitiveMemoryStateEnum,
        old_strength: float,
        new_strength: float,
        reason: str,
        confidence: float = 0.7,
    ) -> None:
        self.session.add(MemoryEvent(
            memory_id=memory.id,
            user_id=memory.user_id,
            event_type=event_type,
            old_state=old_state.value if old_state else None,
            new_state=new_state.value if new_state else None,
            old_strength=old_strength,
            new_strength=new_strength,
            reason=reason,
            confidence=confidence,
        ))
