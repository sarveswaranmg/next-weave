"""
Context Compression Engine

Compresses a set of memories into the smallest representation that still
carries the same understanding: duplicates removed, near-identical
concepts merged into single statements, low-confidence noise dropped, and
the remainder fit to a token budget via the Day 5 knapsack optimizer.
Target: 80-95% reduction versus sending raw memory text.
"""
import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from neurowave_engine.db.models import Memory, MemoryTypeEnum
from neurowave_engine.core.config import settings
from neurowave_engine.services.token_budget_optimizer import TokenBudgetOptimizer

logger = logging.getLogger(__name__)

MERGEABLE_TYPES = {MemoryTypeEnum.CONCEPT, MemoryTypeEnum.SEMANTIC}
MAX_MERGED_FRAGMENTS = 4  # Bounds merged-entry size so one cluster can't blow the token budget alone


@dataclass
class CompressedMemory:
    """Uniform post-compression representation. May be backed by a single
    original memory or synthesized from several merged ones — downstream
    consumers (StateGenerator, NarrativeGenerator, ContextEvaluator) only
    need this shape, not the ORM model."""
    id: str
    memory_type: MemoryTypeEnum
    content: str
    importance_score: float
    utility_score: float
    source_ids: List[UUID] = field(default_factory=list)
    merged: bool = False


class ContextCompressionEngine:
    """Compresses ranked memories into the smallest useful representation."""

    def __init__(
        self,
        dedup_threshold: float = None,
        merge_threshold: float = None,
    ):
        self.dedup_threshold = dedup_threshold if dedup_threshold is not None else settings.ccc_dedup_similarity_threshold
        self.merge_threshold = merge_threshold if merge_threshold is not None else settings.ccc_concept_merge_similarity_threshold
        self.optimizer = TokenBudgetOptimizer()

    def compress(
        self,
        scored: List[Dict],
        memory_by_id: Dict[UUID, Memory],
        token_budget: int,
    ) -> Dict:
        """
        Args:
            scored: utility-scored candidates (post contradiction resolution)
            memory_by_id: memory_id -> Memory ORM object
            token_budget: final token budget for the compressed set

        Returns:
            Dict with `memories` (List[CompressedMemory]), `original_tokens`,
            `compressed_tokens`, `compression_ratio`, `duplicate_count`,
            `merged_count`
        """
        original_tokens = sum(
            self.optimizer.estimate_tokens(memory_by_id[s["memory_id"]].content or "")
            for s in scored
        )

        deduped, duplicate_count = self._deduplicate(scored, memory_by_id)
        merged, merged_count = self._merge_concepts(deduped, memory_by_id)

        # Prioritize high-confidence knowledge: sort by utility before budgeting
        merged.sort(key=lambda cm: cm.utility_score, reverse=True)

        budget_candidates = [
            {
                "ref": cm,
                "utility_score": cm.utility_score,
                "content_preview": cm.content,
            }
            for cm in merged
        ]
        selected = self.optimizer.optimize(budget_candidates, token_budget, text_key="content_preview")
        final_memories = [c["ref"] for c in selected]

        if not final_memories and merged:
            # Every candidate individually exceeded the budget (e.g. a large
            # merged cluster) — degrade gracefully to a truncated single
            # entry rather than silently returning an empty context.
            final_memories = [self._fallback_single(merged[0], token_budget)]

        final_memories.sort(key=lambda cm: cm.utility_score, reverse=True)

        compressed_tokens = sum(self.optimizer.estimate_tokens(cm.content) for cm in final_memories)
        compression_ratio = (
            max(0.0, (original_tokens - compressed_tokens) / original_tokens)
            if original_tokens > 0 else 0.0
        )

        return {
            "memories": final_memories,
            "original_tokens": original_tokens,
            "compressed_tokens": compressed_tokens,
            "compression_ratio": compression_ratio,
            "duplicate_count": duplicate_count,
            "merged_count": merged_count,
        }

    def _fallback_single(self, best: CompressedMemory, token_budget: int) -> CompressedMemory:
        """Truncate the single highest-utility candidate to fit the budget,
        used only when nothing fits whole (e.g. an oversized merged cluster)."""
        char_limit = max(0, token_budget * 4)
        content = best.content
        if len(content) > char_limit:
            truncated = content[:char_limit].rsplit(" ", 1)[0]
            content = (truncated + "...") if truncated else content[:char_limit]
        return CompressedMemory(
            id=best.id,
            memory_type=best.memory_type,
            content=content,
            importance_score=best.importance_score,
            utility_score=best.utility_score,
            source_ids=best.source_ids,
            merged=best.merged,
        )

    def _deduplicate(self, scored: List[Dict], memory_by_id: Dict[UUID, Memory]) -> Tuple[List[Dict], int]:
        """Remove near-duplicate memories, keeping the higher-utility one."""
        ranked = sorted(scored, key=lambda s: s["utility_score"], reverse=True)
        kept: List[Dict] = []
        kept_word_sets: List[set] = []
        duplicate_count = 0

        for s in ranked:
            memory = memory_by_id[s["memory_id"]]
            words = set(re.findall(r"\w+", (memory.content or "").lower()))
            is_duplicate = False
            for existing_words in kept_word_sets:
                if not words or not existing_words:
                    continue
                overlap = len(words & existing_words) / max(1, len(words | existing_words))
                if overlap >= self.dedup_threshold:
                    is_duplicate = True
                    break
            if is_duplicate:
                duplicate_count += 1
            else:
                kept.append(s)
                kept_word_sets.append(words)

        return kept, duplicate_count

    def _merge_concepts(
        self,
        scored: List[Dict],
        memory_by_id: Dict[UUID, Memory],
    ) -> Tuple[List[CompressedMemory], int]:
        """Merge overlapping concept/semantic memories into single statements
        so five related facts collapse into one line instead of five."""
        mergeable = [s for s in scored if memory_by_id[s["memory_id"]].memory_type in MERGEABLE_TYPES]
        rest = [s for s in scored if memory_by_id[s["memory_id"]].memory_type not in MERGEABLE_TYPES]

        clusters: List[List[Dict]] = []
        cluster_words: List[set] = []

        for s in mergeable:
            memory = memory_by_id[s["memory_id"]]
            words = set(re.findall(r"\w+", (memory.content or "").lower()))
            placed = False
            for idx, cword in enumerate(cluster_words):
                if not words or not cword:
                    continue
                overlap = len(words & cword) / max(1, min(len(words), len(cword)))
                if overlap >= self.merge_threshold:
                    clusters[idx].append(s)
                    cluster_words[idx] |= words
                    placed = True
                    break
            if not placed:
                clusters.append([s])
                cluster_words.append(words)

        merged_count = 0
        result: List[CompressedMemory] = [
            CompressedMemory(
                id=str(s["memory_id"]),
                memory_type=memory_by_id[s["memory_id"]].memory_type,
                content=memory_by_id[s["memory_id"]].content or "",
                importance_score=memory_by_id[s["memory_id"]].importance_score or 0.5,
                utility_score=s["utility_score"],
                source_ids=[s["memory_id"]],
            )
            for s in rest
        ]

        for cluster in clusters:
            if len(cluster) == 1:
                s = cluster[0]
                memory = memory_by_id[s["memory_id"]]
                result.append(CompressedMemory(
                    id=str(s["memory_id"]),
                    memory_type=memory.memory_type,
                    content=memory.content or "",
                    importance_score=memory.importance_score or 0.5,
                    utility_score=s["utility_score"],
                    source_ids=[s["memory_id"]],
                ))
                continue

            merged_count += len(cluster) - 1
            top_members = sorted(cluster, key=lambda s: s["utility_score"], reverse=True)[:MAX_MERGED_FRAGMENTS]
            fragments = []
            for s in top_members:
                memory = memory_by_id[s["memory_id"]]
                text = (memory.summary or memory.content or "").strip().rstrip(".")
                if text and text not in fragments:
                    fragments.append(text)

            result.append(CompressedMemory(
                id=str(cluster[0]["memory_id"]),
                memory_type=memory_by_id[cluster[0]["memory_id"]].memory_type,
                content="; ".join(fragments),
                importance_score=max(memory_by_id[s["memory_id"]].importance_score or 0.5 for s in cluster),
                utility_score=max(s["utility_score"] for s in cluster),
                source_ids=[s["memory_id"] for s in cluster],
                merged=True,
            ))

        return result, merged_count


# Singleton instance
context_compression_engine = ContextCompressionEngine()
