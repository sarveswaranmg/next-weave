"""Importance scoring engine"""
import logging
from typing import Dict, Any
from neurowave_engine.db.models import MemoryTypeEnum
from neurowave_engine.schemas.memory import ExtractedMemory

logger = logging.getLogger(__name__)


class ImportanceScoringEngine:
    """
    Importance scoring engine for memories.

    Scores memories based on:
    - Future usefulness
    - Repetition potential
    - Identity relevance
    - Emotional relevance
    - Long-term persistence value
    """

    # Weights for different factors
    WEIGHTS = {
        "base_score": 0.5,
        "memory_type": 0.2,
        "content_length": 0.1,
        "specificity": 0.15,
        "actionability": 0.05,
    }

    # Type-specific base scores
    TYPE_BASE_SCORES = {
        MemoryTypeEnum.PROCEDURAL: 0.85,  # How to behave - very important
        MemoryTypeEnum.IDENTITY: 0.80,  # Identity traits - important
        MemoryTypeEnum.SEMANTIC: 0.70,  # Facts/preferences - moderately important
        MemoryTypeEnum.EPISODIC: 0.50,  # Events - less important than others
    }

    # Content heuristics
    HIGH_IMPORTANCE_KEYWORDS = {
        "prefer",
        "like",
        "dislike",
        "hate",
        "love",
        "goal",
        "dream",
        "passionate",
        "interested",
        "building",
        "creating",
        "never",
        "always",
        "important",
        "critical",
    }

    LOW_IMPORTANCE_KEYWORDS = {
        "maybe",
        "could",
        "might",
        "hello",
        "hi",
        "bye",
        "thanks",
        "ok",
        "cool",
        "nice",
    }

    def score(self, memory: ExtractedMemory) -> float:
        """
        Calculate importance score for a memory.

        Args:
            memory: Extracted memory object

        Returns:
            Importance score (0.0 to 1.0)
        """
        if memory.importance_score > 0:
            # Use LLM-provided score as base
            base_score = memory.importance_score
        else:
            base_score = self._heuristic_score(memory)

        return min(max(base_score, 0.0), 1.0)

    def _heuristic_score(self, memory: ExtractedMemory) -> float:
        """Calculate score using heuristics"""
        content = memory.content.lower()
        summary = (memory.summary or "").lower()
        combined_text = f"{content} {summary}"

        # Type-based score
        type_score = self.TYPE_BASE_SCORES.get(memory.memory_type, 0.5)

        # Content length heuristic (too short or too long might be less important)
        length_score = self._score_length(len(memory.content))

        # Keyword analysis
        keyword_score = self._score_keywords(combined_text)

        # Specificity heuristic
        specificity_score = self._score_specificity(memory.content)

        # Weighted combination
        final_score = (
            type_score * 0.4 +
            keyword_score * 0.3 +
            specificity_score * 0.2 +
            length_score * 0.1
        )

        return final_score

    def _score_length(self, length: int) -> float:
        """Score based on content length"""
        if length < 10:
            return 0.2
        elif length < 50:
            return 0.6
        elif length < 500:
            return 0.9
        else:
            return 0.7  # Very long content might be less focused

    def _score_keywords(self, text: str) -> float:
        """Score based on keyword presence"""
        high_importance_count = sum(
            1 for keyword in self.HIGH_IMPORTANCE_KEYWORDS if keyword in text
        )
        low_importance_count = sum(
            1 for keyword in self.LOW_IMPORTANCE_KEYWORDS if keyword in text
        )

        if high_importance_count == 0 and low_importance_count == 0:
            return 0.5

        keyword_score = (high_importance_count * 0.15 - low_importance_count * 0.1)
        return min(max(0.3 + keyword_score, 0.0), 1.0)

    def _score_specificity(self, content: str) -> float:
        """Score based on content specificity"""
        # More specific content (with details) is more valuable
        specific_indicators = [
            ("technology" in content or "tool" in content),
            ("when" in content or "time" in content),
            ("because" in content or "reason" in content),
            (len(content.split()) > 10),
            ("specific" in content or "exactly" in content),
        ]

        specificity_count = sum(specific_indicators)
        return 0.5 + (specificity_count * 0.1)


# Singleton instance
scoring_engine = ImportanceScoringEngine()
