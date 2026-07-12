"""
Reinforcement Recovery

Decay is reversible. If an old, weakened memory becomes relevant again —
"User learning React", dormant for a year — and the user then asks "Help me
optimize React rendering", that memory's strength should increase and it
should become retrievable again, the same way a half-forgotten fact
resurfaces once context makes it relevant.
"""
import logging
from datetime import datetime
from typing import Dict, List
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import Memory, MemoryEvent, CognitiveMemoryStateEnum
from app.core.config import settings
from app.services.context_analyzer import ContextAnalyzer
from app.services.utility_predictor import MemoryUtilityPredictor
from app.services.goal_detector import goal_detector
from app.services.intent_classifier import intent_classifier

logger = logging.getLogger(__name__)

REVIVABLE_STATES = {
    CognitiveMemoryStateEnum.DORMANT,
    CognitiveMemoryStateEnum.DECAYING,
    CognitiveMemoryStateEnum.ARCHIVED,
    CognitiveMemoryStateEnum.FORGOTTEN,
}


class ReinforcementRecoveryService:
    """Revives decayed/archived/forgotten memories that become relevant again."""

    def __init__(self, session: Session):
        self.session = session
        self.context_analyzer = ContextAnalyzer(session)
        self.predictor = MemoryUtilityPredictor()

    def check_and_revive(self, user_id: UUID, query: str, threshold: float = None) -> List[Dict]:
        """
        Score a user's decayed/archived/forgotten memories against a new
        query and revive any that clear the relevance threshold.

        Returns:
            List of revival decisions (memory_id, old/new state & strength, reason).
        """
        threshold = threshold if threshold is not None else settings.revival_utility_threshold

        candidates = self.session.query(Memory).filter(
            Memory.user_id == user_id,
            Memory.cognitive_state.in_(REVIVABLE_STATES),
        ).all()

        if not candidates:
            return []

        goal_result = goal_detector.detect(query)
        intent_result = intent_classifier.classify(query)
        context = self.context_analyzer.analyze(
            user_id, query, goal_result["goal"], [i["intent"] for i in intent_result["intents"]]
        )

        scored = self.predictor.predict_batch(candidates, context)
        memory_by_id = {m.id: m for m in candidates}

        revivals = [
            self._revive(user_id, memory_by_id[s["memory_id"]], s)
            for s in scored if s["utility_score"] >= threshold
        ]

        if revivals:
            self.session.commit()

        return revivals

    def revive_memory(self, user_id: UUID, memory: Memory, reason: str = "Manually revived") -> Dict:
        """Directly revive a specific memory (e.g. via POST /memory/revive
        with an explicit memory_id), bypassing utility scoring."""
        result = self._revive(user_id, memory, {"utility_score": 1.0, "selection_reason": reason})
        self.session.commit()
        return result

    def _revive(self, user_id: UUID, memory: Memory, score: Dict) -> Dict:
        old_state = memory.cognitive_state
        old_strength = memory.memory_strength

        new_strength = min(1.0, (memory.memory_strength or 0.3) + settings.revival_strength_boost)
        new_state = (
            CognitiveMemoryStateEnum.ACTIVE if new_strength >= 0.70
            else CognitiveMemoryStateEnum.REINFORCED
        )

        memory.memory_strength = new_strength
        memory.cognitive_state = new_state
        memory.revival_count = (memory.revival_count or 0) + 1
        memory.last_accessed = datetime.utcnow()
        memory.last_reinforced_at = datetime.utcnow()
        memory.archive_reason = None
        memory.forget_reason = None

        reason = f"Revived: utility {score['utility_score']:.2f} for current query ({score['selection_reason']})"

        self.session.add(MemoryEvent(
            memory_id=memory.id,
            user_id=user_id,
            event_type="revive",
            old_state=old_state.value if old_state else None,
            new_state=new_state.value,
            old_strength=old_strength,
            new_strength=new_strength,
            reason=reason,
            confidence=score["utility_score"],
        ))

        return {
            "memory_id": memory.id,
            "content": memory.content,
            "old_state": old_state,
            "new_state": new_state,
            "old_strength": old_strength,
            "new_strength": new_strength,
            "revival_count": memory.revival_count,
            "reason": reason,
        }
