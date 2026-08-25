"""
Memory Replay Simulator

Predictive maintenance: for each memory, simulate whether it would
actually help *future* reasoning by scoring it against synthetic future
contexts derived from the user's own identity goals/interests (the best
available proxy for "what will this user ask about next" without a real
query), rather than waiting for a real query to find out. Memories that
simulate poorly get weakened; the actual archive/forget call is left to
Day 7's `ForgettingEngine`, which this feeds strength updates into.
"""
import logging
import re
from typing import Dict, List
from uuid import UUID

from sqlalchemy.orm import Session

from neurowave_engine.db.models import Memory, IdentityNode, CognitiveMemoryStateEnum
from neurowave_engine.core.config import settings
from neurowave_engine.services.context_analyzer import ContextAnalyzer
from neurowave_engine.services.utility_predictor import MemoryUtilityPredictor
from neurowave_engine.services.goal_detector import GOAL_SIGNALS

logger = logging.getLogger(__name__)

SIMULATED_WEAKEN_THRESHOLD = 0.25
SIMULATED_WEAKEN_FACTOR = 0.85


class MemoryReplaySimulator:
    """Predicts whether stored memories will help future reasoning."""

    def __init__(self, session: Session):
        self.session = session
        self.context_analyzer = ContextAnalyzer(session)
        self.predictor = MemoryUtilityPredictor()

    def simulate(self, user_id: UUID, memories: List[Memory] = None) -> List[Dict]:
        """
        Args:
            user_id: User ID
            memories: Memories to simulate (defaults to all active memories)

        Returns:
            List of {memory_id, simulated_future_utility, action} where
            action is "keep", "weaken", or "flag_for_archive".
        """
        memories = memories if memories is not None else self.session.query(Memory).filter(
            Memory.user_id == user_id,
            Memory.cognitive_state.notin_([CognitiveMemoryStateEnum.ARCHIVED, CognitiveMemoryStateEnum.FORGOTTEN]),
        ).all()

        if not memories:
            return []

        synthetic_goals = self._synthetic_future_goals(user_id) or ["general_assistance"]
        contexts = [
            self.context_analyzer.analyze(user_id, goal.replace("_", " "), goal, [])
            for goal in synthetic_goals
        ]

        results = []
        for memory in memories:
            utilities = [self.predictor.predict(memory, ctx)["utility_score"] for ctx in contexts]
            avg_utility = sum(utilities) / len(utilities)

            action = "keep"
            if avg_utility < SIMULATED_WEAKEN_THRESHOLD:
                previous = memory.memory_strength if memory.memory_strength is not None else 0.5
                memory.memory_strength = max(0.0, previous * SIMULATED_WEAKEN_FACTOR)
                action = "weaken"
                if memory.memory_strength < settings.forgetting_archive_threshold:
                    action = "flag_for_archive"

            results.append({
                "memory_id": memory.id,
                "simulated_future_utility": round(avg_utility, 4),
                "action": action,
            })

        self.session.commit()
        return results

    def _synthetic_future_goals(self, user_id: UUID) -> List[str]:
        """Derive plausible future goals from the user's own top identity
        traits/interests."""
        nodes = self.session.query(IdentityNode).filter(
            IdentityNode.user_id == user_id,
            IdentityNode.node_type.in_(["goal", "interest"]),
            IdentityNode.confidence >= 0.4,
        ).order_by(IdentityNode.importance.desc()).limit(5).all()

        if not nodes:
            return []

        text = " ".join((n.node_value or "").replace("_", " ").lower() for n in nodes)

        goals = []
        for goal_name, patterns in GOAL_SIGNALS.items():
            for pattern, _weight in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    goals.append(goal_name)
                    break

        return list(dict.fromkeys(goals))[:3]
