"""
Memory Utility Predictor

The heart of the Predictive Recall Engine. Answers a fundamentally
different question than similarity search:

    "How useful will this memory be for solving THIS task?"

instead of:

    "How similar does this memory look to the query?"

Every memory is scored across independent dimensions (goal alignment,
identity alignment, concept relevance, importance, reinforcement,
confidence, recency), which are combined into a single `utility_score`
via a configurable weighted sum. Memory type acts as a secondary,
bounded priority multiplier (Identity > Concept > Procedural > Semantic >
Episodic) so type priority nudges ranking without ever overriding a
strong task-relevance signal.
"""
import logging
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from app.db.models import Memory, MemoryTypeEnum
from app.core.config import settings

logger = logging.getLogger(__name__)


# Priority weight by memory type. Normalized into a narrow [0.85, 1.0]
# multiplier in `_type_multiplier` so it nudges rather than dominates.
MEMORY_TYPE_PRIORITY: Dict[MemoryTypeEnum, float] = {
    MemoryTypeEnum.IDENTITY: 1.00,
    MemoryTypeEnum.CONCEPT: 0.90,
    MemoryTypeEnum.PROCEDURAL: 0.80,
    MemoryTypeEnum.SEMANTIC: 0.65,
    MemoryTypeEnum.EPISODIC: 0.50,
}

RECENCY_HALF_LIFE_DAYS = 90.0


def compute_recency_score(anchor: Optional[datetime]) -> float:
    """Exponential recency decay shared across utility prediction and
    contradiction resolution (both need "how fresh is this memory")."""
    if not anchor:
        return 0.5
    days_old = max(0.0, (datetime.utcnow() - anchor).total_seconds() / 86400.0)
    return math.exp(-days_old / RECENCY_HALF_LIFE_DAYS)


@dataclass
class UtilityWeights:
    """Configurable weighting for the final utility score. Should sum to ~1.0"""
    goal_alignment: float = settings.utility_weight_goal_alignment
    identity_alignment: float = settings.utility_weight_identity_alignment
    concept_relevance: float = settings.utility_weight_concept_relevance
    importance: float = settings.utility_weight_importance
    reinforcement: float = settings.utility_weight_reinforcement
    confidence: float = settings.utility_weight_confidence
    recency: float = settings.utility_weight_recency

    def as_dict(self) -> Dict[str, float]:
        return {
            "goal_alignment": self.goal_alignment,
            "identity_alignment": self.identity_alignment,
            "concept_relevance": self.concept_relevance,
            "importance": self.importance,
            "reinforcement": self.reinforcement,
            "confidence": self.confidence,
            "recency": self.recency,
        }


class MemoryUtilityPredictor:
    """Predicts per-memory utility for a given task context."""

    def __init__(self, weights: Optional[UtilityWeights] = None):
        self.weights = weights or UtilityWeights()

    def predict(self, memory: Memory, context: Dict) -> Dict:
        """
        Predict the utility of a single memory for the current context.

        Args:
            memory: Candidate Memory ORM object
            context: Structured context from ContextAnalyzer.analyze()

        Returns:
            Dict with per-dimension scores, final utility_score, and a
            human-readable selection_reason.
        """
        content = (memory.content or "").lower()
        content_summary = (memory.summary or memory.content or "").lower()

        goal_alignment = self._score_goal_alignment(memory, content, context)
        identity_alignment = self._score_identity_alignment(memory, content, context)
        concept_relevance = self._score_concept_relevance(memory, content, context)
        importance = self._score_importance(memory)
        reinforcement = self._score_reinforcement(memory)
        confidence = self._score_confidence(memory)
        recency = self._score_recency(memory)

        w = self.weights
        weighted_sum = (
            goal_alignment * w.goal_alignment +
            identity_alignment * w.identity_alignment +
            concept_relevance * w.concept_relevance +
            importance * w.importance +
            reinforcement * w.reinforcement +
            confidence * w.confidence +
            recency * w.recency
        )

        type_multiplier = self._type_multiplier(memory.memory_type)
        utility_score = max(0.0, min(1.0, weighted_sum * type_multiplier))

        dims = {
            "goal_alignment": goal_alignment,
            "identity_alignment": identity_alignment,
            "concept_relevance": concept_relevance,
            "importance": importance,
            "reinforcement": reinforcement,
            "confidence": confidence,
            "recency": recency,
        }
        contributions = {k: v * getattr(w, k) for k, v in dims.items()}
        reason = self._build_selection_reason(memory, dims, contributions)

        return {
            "memory_id": memory.id,
            "memory_type": memory.memory_type,
            "content_preview": (memory.content or "")[:120],
            **dims,
            "memory_type_weight": type_multiplier,
            "utility_score": utility_score,
            "selection_reason": reason,
        }

    def predict_batch(self, memories: List[Memory], context: Dict) -> List[Dict]:
        """Predict utility for a batch of candidate memories"""
        return [self.predict(memory, context) for memory in memories]

    # ------------------------------------------------------------------
    # Dimension scorers
    # ------------------------------------------------------------------

    def _score_goal_alignment(self, memory: Memory, content: str, context: Dict) -> float:
        """Does this memory help achieve the current goal?"""
        keywords = context.get("keywords", [])
        required_knowledge = context.get("required_knowledge", [])

        keyword_hits = sum(1 for kw in keywords if kw in content)
        keyword_score = min(1.0, keyword_hits / max(1, len(keywords))) if keywords else 0.0

        category_hits = 0
        for category in required_knowledge:
            category_terms = category.replace("_", " ")
            if category_terms in content or any(term in content for term in category_terms.split()):
                category_hits += 1
        category_score = min(1.0, category_hits / max(1, len(required_knowledge))) if required_knowledge else 0.0

        # Procedural memories that dictate "how to respond" are always
        # goal-relevant regardless of topical overlap.
        procedural_bonus = 0.15 if memory.memory_type == MemoryTypeEnum.PROCEDURAL else 0.0

        return max(0.0, min(1.0, keyword_score * 0.6 + category_score * 0.4 + procedural_bonus))

    def _score_identity_alignment(self, memory: Memory, content: str, context: Dict) -> float:
        """Does this memory match the user's long-term identity profile?"""
        traits = context.get("identity_traits", [])
        if not traits:
            return 0.5 if memory.memory_type == MemoryTypeEnum.IDENTITY else 0.3

        matched_weight = 0.0
        total_weight = 0.0
        for trait in traits:
            value = str(trait.get("value", "")).lower()
            trait_confidence = trait.get("confidence", 0.5)
            total_weight += trait_confidence
            if value and value in content:
                matched_weight += trait_confidence

        base = (matched_weight / total_weight) if total_weight > 0 else 0.0
        type_bonus = 0.2 if memory.memory_type == MemoryTypeEnum.IDENTITY else 0.0
        return max(0.0, min(1.0, base + type_bonus))

    def _score_concept_relevance(self, memory: Memory, content: str, context: Dict) -> float:
        """Does this concept directly relate to the current task?"""
        concepts = context.get("concepts", [])
        if not concepts:
            return 0.4 if memory.memory_type == MemoryTypeEnum.CONCEPT else 0.2

        matched_weight = 0.0
        total_weight = 0.0
        for concept in concepts:
            name = str(concept.get("name", "")).lower().replace("_", " ")
            confidence = concept.get("confidence", 0.5)
            total_weight += confidence
            if name and (name in content or any(part in content for part in name.split() if len(part) > 3)):
                matched_weight += confidence

        base = (matched_weight / total_weight) if total_weight > 0 else 0.0
        type_bonus = 0.15 if memory.memory_type == MemoryTypeEnum.CONCEPT else 0.0
        return max(0.0, min(1.0, base + type_bonus))

    def _score_importance(self, memory: Memory) -> float:
        """Reuse Day 2 cognitive importance score"""
        return memory.importance_score if memory.importance_score else 0.5

    def _score_reinforcement(self, memory: Memory) -> float:
        """Reuse Day 2 reinforcement signal (score + strength blend)"""
        reinforcement_score = memory.reinforcement_score if memory.reinforcement_score is not None else 0.5
        strength = memory.memory_strength if memory.memory_strength is not None else 0.5
        return max(0.0, min(1.0, (reinforcement_score + strength) / 2))

    def _score_confidence(self, memory: Memory) -> float:
        """Prefer stable, well-reinforced memories over uncertain ones"""
        strength = memory.memory_strength if memory.memory_strength is not None else 0.5
        decay_rate = memory.decay_rate if memory.decay_rate is not None else 0.05
        stability = 1.0 - min(1.0, decay_rate * 5)  # low decay rate => high stability
        return max(0.0, min(1.0, (strength + stability) / 2))

    def _score_recency(self, memory: Memory) -> float:
        """Prefer newer memories when appropriate (exponential decay)"""
        anchor = memory.last_accessed or memory.created_at
        return compute_recency_score(anchor)

    def _type_multiplier(self, memory_type: MemoryTypeEnum) -> float:
        """Bounded [0.85, 1.0] multiplier reflecting type priority:
        Identity > Concept > Procedural > Semantic > Episodic"""
        priority = MEMORY_TYPE_PRIORITY.get(memory_type, 0.6)
        return 0.85 + 0.15 * priority

    def _build_selection_reason(self, memory: Memory, dims: Dict[str, float], contributions: Dict[str, float]) -> str:
        """Generate a short human-readable explanation for debugging/trust"""
        top_dims = sorted(contributions.items(), key=lambda x: x[1], reverse=True)[:2]

        labels = {
            "goal_alignment": "matches the current goal",
            "identity_alignment": "aligns with the user's identity profile",
            "concept_relevance": "relates to a relevant concept",
            "importance": "has high cognitive importance",
            "reinforcement": "has been reinforced through repeated use",
            "confidence": "is a stable, well-established memory",
            "recency": "is recent",
        }

        reasons = [labels[dim] for dim, _ in top_dims if dims[dim] > 0.15]
        if not reasons:
            reasons = ["provides general supporting context"]

        return f"Selected because it {' and '.join(reasons)}."
