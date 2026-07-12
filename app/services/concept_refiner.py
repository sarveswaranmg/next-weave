"""
Concept Refinement Engine

Improves existing concepts over time rather than letting them accumulate
unchanged: merges near-duplicate concepts, generalizes a cluster of
related-but-distinct concepts into one broader concept (e.g. "Backend" +
"Distributed Systems" + "Infrastructure" -> "Backend Distributed
Infrastructure"), strengthens concepts that keep gaining supporting
evidence, and retires concepts that have gone stale. Nothing is deleted —
retirement and merges are soft (confidence dropped, `retired` flagged in
metadata), preserving history.
"""
import logging
import re
from collections import Counter
from datetime import datetime, timedelta
from typing import Dict, List
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import ConceptMemory
from app.core.config import settings
from app.services.context_analyzer import STOPWORDS

logger = logging.getLogger(__name__)

# Looser than the merge threshold (0.40) on purpose: "related domain" should
# catch more than "basically the same concept" does.
GENERALIZE_SIMILARITY_THRESHOLD = 0.25


class ConceptRefiner:
    """Merges, generalizes, strengthens, and retires concepts."""

    def __init__(self, session: Session):
        self.session = session

    def refine(self, user_id: UUID) -> Dict:
        """Run one full refinement pass: merge -> generalize -> strengthen -> retire."""
        merged = self._merge_duplicates(user_id)
        generalized = self._generalize(user_id)
        strengthened = self._strengthen(user_id)
        retired = self._retire_obsolete(user_id)

        return {
            "merged": merged,
            "generalized": generalized,
            "strengthened": strengthened,
            "retired": retired,
        }

    def _merge_duplicates(self, user_id: UUID) -> List[Dict]:
        """Merge concepts whose names/descriptions overlap heavily — the
        concept-level counterpart to Day 7's memory-level DuplicateResolver."""
        concepts = self._active_concepts(user_id)
        clusters: List[List[ConceptMemory]] = []
        cluster_words: List[set] = []

        for concept in concepts:
            words = self._words(concept)
            placed = False
            for idx, cwords in enumerate(cluster_words):
                if not words or not cwords:
                    continue
                overlap = len(words & cwords) / max(1, min(len(words), len(cwords)))
                if overlap >= settings.concept_merge_similarity_threshold:
                    clusters[idx].append(concept)
                    cluster_words[idx] |= words
                    placed = True
                    break
            if not placed:
                clusters.append([concept])
                cluster_words.append(words)

        decisions = []
        for cluster in clusters:
            if len(cluster) < 2:
                continue
            primary = max(cluster, key=lambda c: c.confidence or 0.0)
            others = [c for c in cluster if c.id != primary.id]

            primary.support_count = sum(c.support_count or 1 for c in cluster)
            primary.supporting_memory_ids = list(set(sum(
                [(c.supporting_memory_ids or []) for c in cluster], []
            )))
            primary.confidence = min(1.0, max(c.confidence or 0.0 for c in cluster) + 0.05 * len(others))
            primary.related_concept_ids = list(set(
                (primary.related_concept_ids or []) + [str(o.id) for o in others]
            ))

            for other in others:
                other.extra_metadata = {**(other.extra_metadata or {}), "merged_into": str(primary.id), "retired": True}
                other.confidence = 0.0

            decisions.append({
                "action": "merge",
                "primary_concept_id": primary.id,
                "primary_name": primary.concept_name,
                "merged_concept_ids": [o.id for o in others],
                "merged_names": [o.concept_name for o in others],
            })

        if decisions:
            self.session.commit()
        return decisions

    def _generalize(self, user_id: UUID) -> List[Dict]:
        """Roll up a group of related-but-distinct concepts into one
        broader concept."""
        concepts = self._active_concepts(user_id)
        if len(concepts) < settings.concept_generalize_min_group_size:
            return []

        # Overlap-coefficient (shared / smaller set), same style as
        # _merge_duplicates, not Jaccard-over-union: a growing cluster's
        # word union dilutes a union-based ratio every time a new member
        # joins, making later, still-genuinely-related members fail to
        # match (the same effect Day 7's DuplicateResolver hit).
        clusters: List[List[ConceptMemory]] = []
        cluster_words: List[set] = []
        for concept in concepts:
            words = self._words(concept)
            placed = False
            for idx, cwords in enumerate(cluster_words):
                if not words or not cwords:
                    continue
                overlap = len(words & cwords) / max(1, min(len(words), len(cwords)))
                if overlap >= GENERALIZE_SIMILARITY_THRESHOLD:
                    clusters[idx].append(concept)
                    cluster_words[idx] |= words
                    placed = True
                    break
            if not placed:
                clusters.append([concept])
                cluster_words.append(words)

        decisions = []
        for cluster in clusters:
            if len(cluster) < settings.concept_generalize_min_group_size:
                continue

            label = self._generalized_label(cluster)
            existing = self.session.query(ConceptMemory).filter(
                ConceptMemory.user_id == user_id, ConceptMemory.concept_name == label,
            ).first()
            if existing:
                continue

            member_ids = [str(c.id) for c in cluster]
            memory_ids = list(set(sum([(c.supporting_memory_ids or []) for c in cluster], [])))

            generalized = ConceptMemory(
                user_id=user_id,
                concept_name=label,
                description=f"Generalized from: {', '.join(c.concept_name for c in cluster)}",
                confidence=min(1.0, sum(c.confidence or 0.5 for c in cluster) / len(cluster) + 0.1),
                support_count=sum(c.support_count or 1 for c in cluster),
                supporting_memory_ids=memory_ids,
                related_concept_ids=member_ids,
                is_derived_from=",".join(member_ids),
            )
            self.session.add(generalized)
            decisions.append({
                "action": "generalize",
                "new_concept_name": label,
                "source_concept_ids": [c.id for c in cluster],
                "source_names": [c.concept_name for c in cluster],
            })

        if decisions:
            self.session.commit()
        return decisions

    def _strengthen(self, user_id: UUID) -> List[Dict]:
        """Concepts with growing support get a confidence boost."""
        concepts = self._active_concepts(user_id)
        decisions = []
        for concept in concepts:
            if (concept.support_count or 0) >= 3 and (concept.confidence or 0) < 0.95:
                previous = concept.confidence or 0.5
                concept.confidence = min(1.0, previous + 0.03)
                concept.reinforcement_count = (concept.reinforcement_count or 0) + 1
                concept.last_reinforced_at = datetime.utcnow()
                decisions.append({
                    "action": "strengthen", "concept_id": concept.id,
                    "previous_confidence": previous, "new_confidence": concept.confidence,
                })
        if decisions:
            self.session.commit()
        return decisions

    def _retire_obsolete(self, user_id: UUID) -> List[Dict]:
        """Low-confidence, stale concepts are retired (soft - not deleted)."""
        cutoff = datetime.utcnow() - timedelta(days=settings.concept_retire_min_age_days)
        concepts = self._active_concepts(user_id)
        decisions = []
        for concept in concepts:
            anchor = concept.last_reinforced_at or concept.created_at
            if (
                (concept.confidence or 0) <= settings.concept_retire_confidence_threshold
                and anchor and anchor <= cutoff
            ):
                concept.extra_metadata = {
                    **(concept.extra_metadata or {}),
                    "retired": True, "retire_reason": "Low confidence and stale",
                }
                concept.confidence = 0.0
                decisions.append({"action": "retire", "concept_id": concept.id, "concept_name": concept.concept_name})
        if decisions:
            self.session.commit()
        return decisions

    def _active_concepts(self, user_id: UUID) -> List[ConceptMemory]:
        concepts = self.session.query(ConceptMemory).filter(ConceptMemory.user_id == user_id).all()
        return [c for c in concepts if not (c.extra_metadata or {}).get("retired")]

    @staticmethod
    def _words(concept: ConceptMemory) -> set:
        text = (concept.concept_name or "").replace("_", " ") + " " + (concept.description or "")
        return set(re.findall(r"\w+", text.lower())) - STOPWORDS

    @staticmethod
    def _generalized_label(cluster: List[ConceptMemory]) -> str:
        word_counts = Counter()
        for concept in cluster:
            words = [
                w for w in re.findall(r"\w+", (concept.concept_name or "").replace("_", " ").lower())
                if w not in STOPWORDS
            ]
            word_counts.update(words)
        top_words = [w for w, _ in word_counts.most_common(3)]
        if not top_words:
            return f"Generalized Concept {cluster[0].id}"
        return " ".join(w.capitalize() for w in top_words)
