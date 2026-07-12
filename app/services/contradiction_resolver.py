"""
Contradiction Resolver

Humans don't reason over two conflicting beliefs at once — memory
reconsolidation keeps the stronger, more current claim and lets the older
one fade. NeuroWeave's memory store can accumulate genuinely conflicting
preference/fact memories over time (e.g. "User prefers React." followed
later by "User now prefers Rust."). Sending both to an LLM produces
incoherent, self-contradicting context.

This resolver detects same-topic conflicting claims, picks a winner based
on recency + reinforcement + confidence, and records the resolution (never
silently deletes) so historical evolution stays inspectable.
"""
import re
import logging
from typing import Dict, List, Tuple
from uuid import UUID

from app.db.models import Memory, MemoryTypeEnum
from app.core.config import settings
from app.services.context_analyzer import STOPWORDS
from app.services.utility_predictor import compute_recency_score

logger = logging.getLogger(__name__)

# Verbs/phrases that signal a stance-bearing statement (preference, current
# usage, choice, ...). Bucket labels are kept for human-readable "reason"
# text only — they do NOT gate which pairs get compared. An earlier version
# required both memories to share the same bucket, which meant "prefers
# Vue" could never be compared against "builds everything in React" (a
# different verb entirely) even though that is exactly the kind of
# supersession this module exists to catch. The stricter word-overlap test
# in `_is_contradiction` is what actually guards against false positives,
# so any two stance-bearing memories are eligible for pairwise comparison.
PREFERENCE_VERB_BUCKETS: Dict[str, List[str]] = {
    "preference": ["prefers", "prefer", "preferred"],
    "liking": ["likes", "like", "liked"],
    "want": ["wants", "want", "wanted"],
    "usage": ["uses", "use", "using", "used", "builds everything in", "builds with", "codes in", "develops in", "works primarily in"],
    "choice": ["chooses", "choose", "chose", "switched to", "moved to", "adopted"],
    "favor": ["favors", "favor", "favours", "favour"],
}
VERB_TO_BUCKET = {
    variant: bucket for bucket, variants in PREFERENCE_VERB_BUCKETS.items() for variant in variants
}
# Sort longest-first so multi-word phrases (e.g. "builds everything in")
# match before shorter substrings that might otherwise shadow them.
_VERB_VARIANTS_BY_LENGTH = sorted(VERB_TO_BUCKET, key=len, reverse=True)
VERB_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(v) for v in _VERB_VARIANTS_BY_LENGTH) + r")\b", re.IGNORECASE
)

# Types that can meaningfully "contradict" — episodic events don't conflict
# the way stated preferences/facts do.
ELIGIBLE_TYPES = {MemoryTypeEnum.IDENTITY, MemoryTypeEnum.SEMANTIC, MemoryTypeEnum.PROCEDURAL}


def find_stance_memories(memories: List[Memory]) -> List[Memory]:
    """Filter to memories that make a stance-bearing claim (matches a verb
    in VERB_PATTERN) — the shared candidate pool for conflict detection."""
    return [m for m in memories if VERB_PATTERN.search(m.content or "")]


def find_conflicting_pairs(memories: List[Memory], is_contradiction_fn) -> List[Tuple[Memory, Memory]]:
    """
    Find all pairs of stance-bearing memories whose content conflicts, per
    `is_contradiction_fn`. Shared by `ContradictionResolver`,
    `ObsoleteMemoryDetector`, and `MemoryEntropyCalculator` so the detection
    logic lives in exactly one place.
    """
    stance_memories = find_stance_memories(memories)
    pairs = []
    for i in range(len(stance_memories)):
        for j in range(i + 1, len(stance_memories)):
            if is_contradiction_fn(stance_memories[i].content or "", stance_memories[j].content or ""):
                pairs.append((stance_memories[i], stance_memories[j]))
    return pairs


class ContradictionResolver:
    """Detects and resolves conflicting preference/fact memories."""

    def __init__(self, similarity_threshold: float = None):
        self.similarity_threshold = (
            similarity_threshold
            if similarity_threshold is not None
            else settings.ccc_contradiction_similarity_threshold
        )

    def resolve(
        self,
        scored: List[Dict],
        memory_by_id: Dict[UUID, Memory],
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        Args:
            scored: utility-scored candidates (Day 5 shape: dicts with
                `memory_id`, `utility_score`, etc.)
            memory_by_id: memory_id -> Memory ORM object

        Returns:
            (kept, contradictions) — `kept` excludes superseded memories;
            `contradictions` is the resolution trail (winner/loser/reason).
        """
        candidates = [
            s for s in scored
            if memory_by_id[s["memory_id"]].memory_type in ELIGIBLE_TYPES
        ]
        candidate_memories = [memory_by_id[s["memory_id"]] for s in candidates]

        pairs = find_conflicting_pairs(candidate_memories, self._is_contradiction)

        superseded_ids = set()
        contradictions: List[Dict] = []

        for mem_a, mem_b in pairs:
            if mem_a.id in superseded_ids or mem_b.id in superseded_ids:
                continue

            score_a, score_b = self._resolution_score(mem_a), self._resolution_score(mem_b)
            winner_mem, loser_mem = (mem_a, mem_b) if score_a >= score_b else (mem_b, mem_a)

            superseded_ids.add(loser_mem.id)
            contradictions.append({
                "verb_bucket": self._bucket_label(loser_mem),
                "kept_memory_id": winner_mem.id,
                "superseded_memory_id": loser_mem.id,
                "kept_content": winner_mem.content,
                "superseded_content": loser_mem.content,
                "reason": (
                    f"Superseded by a more recent/reinforced statement: \"{winner_mem.content}\""
                ),
            })

        kept = [s for s in scored if s["memory_id"] not in superseded_ids]
        return kept, contradictions

    @staticmethod
    def _bucket_label(memory: Memory) -> str:
        match = VERB_PATTERN.search(memory.content or "")
        return VERB_TO_BUCKET[match.group(1).lower()] if match else "stance"

    def _is_contradiction(self, content_a: str, content_b: str) -> bool:
        """Same claim template (high shared-word overlap) but genuinely
        different objects (non-overlapping differing tokens) => conflict."""
        words_a = set(re.findall(r"\w+", content_a.lower())) - STOPWORDS
        words_b = set(re.findall(r"\w+", content_b.lower())) - STOPWORDS
        if not words_a or not words_b:
            return False

        shared = words_a & words_b
        diff_a = words_a - words_b
        diff_b = words_b - words_a

        if len(shared) < 2 or not diff_a or not diff_b:
            return False
        if diff_a & diff_b:
            # Shouldn't happen given set difference, but guards against
            # near-identical claims being flagged as conflicting.
            return False

        overlap_ratio = len(shared) / min(len(words_a), len(words_b))
        return overlap_ratio >= self.similarity_threshold

    def _resolution_score(self, memory: Memory) -> float:
        """Winner-picking score: recency + reinforcement + stability."""
        recency = compute_recency_score(memory.last_accessed or memory.created_at)
        reinforcement = memory.reinforcement_score if memory.reinforcement_score is not None else 0.5
        strength = memory.memory_strength if memory.memory_strength is not None else 0.5
        return recency * 0.40 + reinforcement * 0.35 + strength * 0.25


# Singleton instance
contradiction_resolver = ContradictionResolver()
