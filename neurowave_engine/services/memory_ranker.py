"""
Predictive Memory Ranker

Orchestrates candidate retrieval, utility prediction, redundancy
elimination, and token-budget optimization into the final memory set for
a predictive recall request. This is the component that actually answers
"what is the smallest set of memories that maximizes predicted usefulness?"
instead of "what are the top-N most similar memories?"
"""
import logging
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import or_

from neurowave_engine.db.models import Memory, MemoryTypeEnum, CognitiveMemoryStateEnum
from neurowave_engine.core.config import settings
from neurowave_engine.services.utility_predictor import MemoryUtilityPredictor, UtilityWeights
from neurowave_engine.services.token_budget_optimizer import TokenBudgetOptimizer

logger = logging.getLogger(__name__)

DEDUP_SIMILARITY_THRESHOLD = 0.80


class PredictiveMemoryRanker:
    """
    Computes utility scores, ranks memories, eliminates redundancy, and
    enforces a token budget to return the optimal memory set.
    """

    def __init__(self, session: Session, weights: Optional[UtilityWeights] = None):
        self.session = session
        self.predictor = MemoryUtilityPredictor(weights)
        self.optimizer = TokenBudgetOptimizer()

    def get_candidates(
        self,
        user_id: UUID,
        memory_types: Optional[List[MemoryTypeEnum]] = None,
        pool_size: Optional[int] = None,
    ) -> List[Memory]:
        """Fetch the candidate pool considered for this query.

        A wide net is cast (bounded by `pool_size` for scale) rather than a
        narrow similarity pre-filter, since utility prediction can surface
        memories that aren't textually similar to the query at all (e.g. a
        procedural preference memory is relevant to almost any task).
        """
        pool_size = pool_size or settings.predictive_recall_candidate_pool_size

        # Day 7: a living memory system retrieves only healthy, current
        # knowledge - archived/forgotten, low-strength, and high-entropy
        # (duplicate/conflicted) memories are excluded before scoring.
        query = self.session.query(Memory).filter(
            Memory.user_id == user_id,
            Memory.cognitive_state.notin_([
                CognitiveMemoryStateEnum.ARCHIVED,
                CognitiveMemoryStateEnum.FORGOTTEN,
            ]),
            or_(Memory.memory_strength.is_(None), Memory.memory_strength >= settings.retrieval_min_strength),
            or_(Memory.entropy_score.is_(None), Memory.entropy_score <= settings.retrieval_max_entropy),
        )
        if memory_types:
            query = query.filter(Memory.memory_type.in_(memory_types))

        return query.order_by(Memory.importance_score.desc()).limit(pool_size).all()

    def rank(
        self,
        user_id: UUID,
        context: Dict,
        token_budget: int,
        memory_types: Optional[List[MemoryTypeEnum]] = None,
        min_utility: Optional[float] = None,
    ) -> Tuple[List[Dict], int, Dict[UUID, Memory]]:
        """
        Run the full ranking pipeline: candidates -> utility -> dedup -> budget.

        Returns:
            (selected_scores, candidate_count, memory_by_id) where
            selected_scores is the utility-optimal, deduplicated, ranked
            list of score dicts, and memory_by_id maps memory_id -> ORM object
            for every scored candidate (selected or not).
        """
        candidates = self.get_candidates(user_id, memory_types)
        memory_by_id = {m.id: m for m in candidates}

        if not candidates:
            return [], 0, memory_by_id

        min_utility = min_utility if min_utility is not None else settings.predictive_recall_min_utility

        scored = self.predictor.predict_batch(candidates, context)
        scored = [s for s in scored if s["utility_score"] >= min_utility]
        scored = self.deduplicate(scored, memory_by_id)

        for s in scored:
            memory = memory_by_id[s["memory_id"]]
            s["content_preview"] = memory.summary or memory.content or ""

        selected = self.optimizer.optimize(scored, token_budget, text_key="content_preview")

        for rank, s in enumerate(selected, start=1):
            s["retrieval_rank"] = rank

        return selected, len(candidates), memory_by_id

    def persist_scores(self, selected: List[Dict], memory_by_id: Dict[UUID, Memory]) -> None:
        """Write utility prediction results back onto Memory rows (Day 5 fields)"""
        now = datetime.utcnow()
        try:
            for s in selected:
                memory = memory_by_id.get(s["memory_id"])
                if not memory:
                    continue
                memory.goal_alignment_score = s["goal_alignment"]
                memory.utility_score = s["utility_score"]
                memory.selection_reason = s["selection_reason"]
                memory.prediction_confidence = s["confidence"]
                memory.retrieval_rank = s["retrieval_rank"]
                memory.last_prediction_time = now
                memory.access_count = (memory.access_count or 0) + 1
                memory.last_accessed = now
            self.session.commit()
        except Exception as e:
            logger.error(f"Failed to persist utility scores: {e}")
            self.session.rollback()

    def deduplicate(self, scored: List[Dict], memory_by_id: Dict[UUID, Memory]) -> List[Dict]:
        """Eliminate near-duplicate memories, keeping the higher-utility one.

        Uses Jaccard similarity over word sets rather than embeddings —
        cheap, dependency-free, and sufficient for catching the common case
        of the same fact captured twice by extraction.
        """
        ranked = sorted(scored, key=lambda s: s["utility_score"], reverse=True)
        kept: List[Dict] = []
        kept_word_sets: List[set] = []

        for s in ranked:
            memory = memory_by_id[s["memory_id"]]
            words = set(re.findall(r"\w+", (memory.content or "").lower()))
            is_duplicate = False
            for existing_words in kept_word_sets:
                if not words or not existing_words:
                    continue
                overlap = len(words & existing_words) / max(1, len(words | existing_words))
                if overlap >= DEDUP_SIMILARITY_THRESHOLD:
                    is_duplicate = True
                    break
            if not is_duplicate:
                kept.append(s)
                kept_word_sets.append(words)

        return kept
