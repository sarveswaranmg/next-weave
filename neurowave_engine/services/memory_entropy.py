"""
Memory Entropy Calculator

Measures disorder inside a user's memory store: redundancy (duplicate
clusters), conflicts (unresolved contradictions), fragmentation (many
low-support, disconnected concepts), and obsolete/decaying memories still
sitting active. The Forgetting Engine and MemoryEvolutionPipeline use this
to decide where cleanup effort matters most; MemoryHealthService surfaces
it as part of the overall Cognitive Health Score. The engine should
continuously reduce entropy over successive evolution runs.
"""
import logging
from typing import Dict, List, Set, Tuple
from uuid import UUID

from sqlalchemy.orm import Session

from neurowave_engine.db.models import Memory, ConceptMemory, CognitiveMemoryStateEnum
from neurowave_engine.services.duplicate_resolver import DuplicateResolver
from neurowave_engine.services.contradiction_resolver import ContradictionResolver, ELIGIBLE_TYPES, find_conflicting_pairs

logger = logging.getLogger(__name__)

ENTROPY_WEIGHTS = {
    "redundancy": 0.30,
    "conflicts": 0.25,
    "fragmentation": 0.20,
    "obsolete": 0.25,
}


class MemoryEntropyCalculator:
    """Computes store-wide and per-memory entropy (disorder) scores."""

    def __init__(self, session: Session):
        self.session = session
        self._contradiction_detector = ContradictionResolver()

    def calculate(self, user_id: UUID, memories: List[Memory] = None) -> Dict:
        """
        Compute the entropy breakdown for a user's memory store.

        Returns:
            Dict with redundancy, conflicts, fragmentation, obsolete_concepts,
            duplicate_clusters, conflict_count, entropy_score (0-1, higher =
            more disorder), total_memories
        """
        memories = memories if memories is not None else self.session.query(Memory).filter(
            Memory.user_id == user_id,
            Memory.cognitive_state != CognitiveMemoryStateEnum.FORGOTTEN,
        ).all()

        if not memories:
            return {
                "redundancy": 0.0, "conflicts": 0.0, "fragmentation": 0.0,
                "obsolete_concepts": 0.0, "duplicate_clusters": 0,
                "conflict_count": 0, "entropy_score": 0.0, "total_memories": 0,
            }

        clusters = DuplicateResolver(self.session).find_clusters(memories)
        duplicate_memory_count = sum(len(c) for c in clusters)
        redundancy = duplicate_memory_count / len(memories)

        conflicting_pairs = self._find_conflicts(memories)
        conflicts = min(1.0, len(conflicting_pairs) / max(1, len(memories) / 4))

        concepts = self.session.query(ConceptMemory).filter(ConceptMemory.user_id == user_id).all()
        fragmentation = (
            sum(1 for c in concepts if (c.support_count or 1) <= 1) / len(concepts)
            if concepts else 0.0
        )

        obsolete_count = sum(
            1 for m in memories
            if m.cognitive_state == CognitiveMemoryStateEnum.DECAYING
            or (m.memory_strength is not None and m.memory_strength < 0.2)
        )
        obsolete_concepts = obsolete_count / len(memories)

        entropy_score = min(1.0, (
            redundancy * ENTROPY_WEIGHTS["redundancy"] +
            conflicts * ENTROPY_WEIGHTS["conflicts"] +
            fragmentation * ENTROPY_WEIGHTS["fragmentation"] +
            obsolete_concepts * ENTROPY_WEIGHTS["obsolete"]
        ))

        return {
            "redundancy": round(redundancy, 4),
            "conflicts": round(conflicts, 4),
            "fragmentation": round(fragmentation, 4),
            "obsolete_concepts": round(obsolete_concepts, 4),
            "duplicate_clusters": len(clusters),
            "conflict_count": len(conflicting_pairs),
            "entropy_score": round(entropy_score, 4),
            "total_memories": len(memories),
        }

    def apply_per_memory_scores(self, memories: List[Memory], aggregate: Dict) -> None:
        """Assign each memory's local contribution to store entropy (the
        `Memory.entropy_score` column): duplicated/conflicted memories carry
        the full store-level score, everything else gets a low baseline."""
        clusters = DuplicateResolver(self.session).find_clusters(memories)
        flagged_ids = {m.id for cluster in clusters for m in cluster}

        conflicting_pairs = self._find_conflicts(memories)
        conflicted_ids: Set = set()
        for a, b in conflicting_pairs:
            conflicted_ids.add(a.id)
            conflicted_ids.add(b.id)

        for memory in memories:
            if memory.id in flagged_ids or memory.id in conflicted_ids:
                memory.entropy_score = aggregate["entropy_score"]
            else:
                memory.entropy_score = min(memory.entropy_score or 0.0, 0.05)

    def _find_conflicts(self, memories: List[Memory]) -> List[Tuple[Memory, Memory]]:
        """Find conflicting memory pairs without resolving them (read-only,
        used for measurement rather than mutation)."""
        candidates = [m for m in memories if m.memory_type in ELIGIBLE_TYPES]
        return find_conflicting_pairs(candidates, self._contradiction_detector._is_contradiction)
