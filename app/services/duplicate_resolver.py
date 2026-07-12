"""
Duplicate Elimination Engine

Repeated near-identical memories ("Likes Rust" / "Enjoys Rust" / "Interested
in Rust" / "Learning Rust") should collapse into one reinforced concept
rather than sit in storage as four separate rows forever. DuplicateResolver
clusters near-duplicates by word overlap, creates (or reinforces) a single
ConceptMemory to represent the cluster, and archives the originals —
preserved, not deleted, with every merge logged as a MemoryEvent.
"""
import logging
import re
from collections import Counter
from datetime import datetime
from typing import Dict, List
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import Memory, MemoryTypeEnum, ConceptMemory, MemoryEvent, CognitiveMemoryStateEnum
from app.core.config import settings
from app.services.context_analyzer import STOPWORDS
from app.services.contradiction_resolver import ContradictionResolver

logger = logging.getLogger(__name__)

MERGEABLE_TYPES = {MemoryTypeEnum.SEMANTIC, MemoryTypeEnum.CONCEPT, MemoryTypeEnum.EPISODIC}
MIN_CLUSTER_SIZE = 2


class DuplicateResolver:
    """Clusters and merges near-duplicate memories into a single concept."""

    def __init__(self, session: Session, similarity_threshold: float = None):
        self.session = session
        self.similarity_threshold = (
            similarity_threshold if similarity_threshold is not None
            else settings.duplicate_similarity_threshold
        )
        self._contradiction_detector = ContradictionResolver()

    def find_clusters(self, memories: List[Memory]) -> List[List[Memory]]:
        """Group near-duplicate memories by word-overlap similarity.

        High word overlap alone isn't sufficient: "prefers Angular for
        frontend work" and "prefers React for frontend work" share 75%+ of
        their words but are contradictory, not duplicate, claims. Merging
        them would blend two conflicting preferences into one nonsensical
        concept, so any candidate that contradicts an existing cluster
        member is excluded from that cluster regardless of overlap.
        """
        eligible = [m for m in memories if m.memory_type in MERGEABLE_TYPES]
        clusters: List[List[Memory]] = []
        cluster_words: List[set] = []

        for memory in eligible:
            words = set(re.findall(r"\w+", (memory.content or "").lower())) - STOPWORDS
            placed = False
            for idx, cwords in enumerate(cluster_words):
                if not words or not cwords:
                    continue
                overlap = len(words & cwords) / max(1, min(len(words), len(cwords)))
                if overlap >= self.similarity_threshold and not self._conflicts_with_any(memory, clusters[idx]):
                    clusters[idx].append(memory)
                    cluster_words[idx] |= words
                    placed = True
                    break
            if not placed:
                clusters.append([memory])
                cluster_words.append(words)

        return [c for c in clusters if len(c) >= MIN_CLUSTER_SIZE]

    def _conflicts_with_any(self, memory: Memory, cluster: List[Memory]) -> bool:
        return any(
            self._contradiction_detector._is_contradiction(memory.content or "", other.content or "")
            for other in cluster
        )

    def resolve(self, user_id: UUID, memories: List[Memory]) -> List[Dict]:
        """
        Find duplicate clusters among the given memories and merge each into
        a ConceptMemory.

        Returns:
            List of merge decisions: {concept_id, concept_name, support_count, source_memory_ids}
        """
        clusters = self.find_clusters(memories)
        return [self._merge_cluster(user_id, cluster) for cluster in clusters]

    def _merge_cluster(self, user_id: UUID, cluster: List[Memory]) -> Dict:
        concept_name = self._derive_concept_name(cluster)
        source_ids = [m.id for m in cluster]

        existing = self.session.query(ConceptMemory).filter(
            ConceptMemory.user_id == user_id,
            ConceptMemory.concept_name == concept_name,
        ).first()

        if existing:
            existing.support_count = (existing.support_count or 0) + len(cluster)
            existing.supporting_memory_ids = list(
                set((existing.supporting_memory_ids or []) + [str(i) for i in source_ids])
            )
            existing.confidence = min(1.0, existing.confidence + 0.05 * len(cluster))
            existing.reinforcement_count = (existing.reinforcement_count or 0) + 1
            existing.last_reinforced_at = datetime.utcnow()
            concept = existing
        else:
            confidence = min(1.0, 0.5 + 0.1 * len(cluster))
            concept = ConceptMemory(
                user_id=user_id,
                concept_name=concept_name,
                description=f"Consolidated from {len(cluster)} related memories",
                confidence=confidence,
                support_count=len(cluster),
                supporting_memory_ids=[str(i) for i in source_ids],
                last_reinforced_at=datetime.utcnow(),
            )
            self.session.add(concept)

        self.session.flush()

        # Archive originals (soft - preserved, not deleted) and log the merge
        for memory in cluster:
            old_state = memory.cognitive_state
            memory.cognitive_state = CognitiveMemoryStateEnum.ARCHIVED
            memory.archive_reason = f"Merged into concept '{concept_name}'"

            self.session.add(MemoryEvent(
                memory_id=memory.id,
                user_id=user_id,
                event_type="merge",
                old_state=old_state.value if old_state else None,
                new_state=CognitiveMemoryStateEnum.ARCHIVED.value,
                old_strength=memory.memory_strength,
                new_strength=memory.memory_strength,
                reason=f"Merged into concept '{concept_name}' ({len(cluster)} duplicates consolidated)",
                confidence=concept.confidence,
            ))

        self.session.commit()

        return {
            "concept_id": concept.id,
            "concept_name": concept_name,
            "support_count": concept.support_count,
            "source_memory_ids": source_ids,
        }

    @staticmethod
    def _derive_concept_name(cluster: List[Memory]) -> str:
        """Derive a short concept label from the cluster's most common
        non-stopword content word (e.g. 4 Rust-preference memories -> 'Rust Interest')."""
        word_counts = Counter()
        for memory in cluster:
            words = [w for w in re.findall(r"\w+", (memory.content or "").lower()) if w not in STOPWORDS]
            word_counts.update(words)

        if not word_counts:
            return f"concept_{cluster[0].id}"

        top_word, _ = word_counts.most_common(1)[0]
        return f"{top_word.capitalize()} Interest"
