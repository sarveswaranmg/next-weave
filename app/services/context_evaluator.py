"""
Context Quality Evaluator

Scores an assembled cognitive context across the dimensions that determine
whether it will actually help an LLM reason well: coverage of required
knowledge, redundancy, contradictions resolved, identity/goal alignment,
and token efficiency. Every composed context receives a quality score.
"""
import logging
from typing import Dict, List
from uuid import UUID

from app.core.config import settings
from app.services.context_compression import CompressedMemory

logger = logging.getLogger(__name__)


class ContextEvaluator:
    """Computes a multi-dimensional quality score for a composed context."""

    def evaluate(
        self,
        required_knowledge: List[str],
        compressed_memories: List[CompressedMemory],
        scored_by_id: Dict[UUID, Dict],
        duplicate_count: int,
        original_candidate_count: int,
        contradiction_count: int,
        missing_topics: List[str],
        token_count: int,
    ) -> Dict:
        """
        Args:
            required_knowledge: Goal-implied knowledge categories (from ContextAnalyzer)
            compressed_memories: Final CompressedMemory list sent as context
            scored_by_id: memory_id -> Day 5 utility score dict (for alignment dims)
            duplicate_count: Duplicates removed during compression
            original_candidate_count: Candidate pool size before compression
            contradiction_count: Conflicts resolved by ContradictionResolver
            missing_topics: Knowledge gaps from KnowledgeGapDetector
            token_count: Final token count of the composed context

        Returns:
            Dict with coverage, redundancy, identity_alignment, goal_alignment,
            estimated_reasoning_quality, contradictions, token_count, quality_score
        """
        coverage = self._coverage(required_knowledge, compressed_memories)
        redundancy = duplicate_count / max(1, original_candidate_count)
        identity_alignment, goal_alignment = self._alignment(compressed_memories, scored_by_id)
        reasoning_quality = self._reasoning_quality(coverage, redundancy, contradiction_count, missing_topics)
        non_contradiction = 1.0 if contradiction_count == 0 else max(0.0, 1.0 - contradiction_count * 0.15)

        quality_score = max(0.0, min(1.0, (
            coverage * settings.ccc_quality_weight_coverage +
            (1 - redundancy) * settings.ccc_quality_weight_non_redundancy +
            identity_alignment * settings.ccc_quality_weight_identity_alignment +
            goal_alignment * settings.ccc_quality_weight_goal_alignment +
            reasoning_quality * settings.ccc_quality_weight_reasoning +
            non_contradiction * settings.ccc_quality_weight_non_contradiction
        )))

        return {
            "coverage": coverage,
            "redundancy": redundancy,
            "identity_alignment": identity_alignment,
            "goal_alignment": goal_alignment,
            "estimated_reasoning_quality": reasoning_quality,
            "contradictions": contradiction_count,
            "token_count": token_count,
            "quality_score": quality_score,
        }

    def _coverage(self, required_knowledge: List[str], compressed_memories: List[CompressedMemory]) -> float:
        if not required_knowledge:
            return 1.0
        combined = " ".join(m.content.lower() for m in compressed_memories)
        hits = sum(
            1 for category in required_knowledge
            if category.replace("_", " ") in combined or any(w in combined for w in category.split("_"))
        )
        return min(1.0, hits / len(required_knowledge))

    def _alignment(self, compressed_memories: List[CompressedMemory], scored_by_id: Dict[UUID, Dict]):
        identity_scores, goal_scores = [], []
        for m in compressed_memories:
            for source_id in m.source_ids:
                s = scored_by_id.get(source_id)
                if s:
                    identity_scores.append(s.get("identity_alignment", 0.0))
                    goal_scores.append(s.get("goal_alignment", 0.0))
        identity_alignment = sum(identity_scores) / len(identity_scores) if identity_scores else 0.0
        goal_alignment = sum(goal_scores) / len(goal_scores) if goal_scores else 0.0
        return identity_alignment, goal_alignment

    def _reasoning_quality(
        self,
        coverage: float,
        redundancy: float,
        contradiction_count: int,
        missing_topics: List[str],
    ) -> float:
        gap_penalty = min(0.5, len(missing_topics) * 0.1)
        contradiction_penalty = min(0.5, contradiction_count * 0.1)
        score = coverage * 0.6 + (1 - redundancy) * 0.4 - gap_penalty - contradiction_penalty
        return max(0.0, min(1.0, score))


# Singleton instance
context_evaluator = ContextEvaluator()
