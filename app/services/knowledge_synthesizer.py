"""
Knowledge Synthesis Engine

Generates entirely new knowledge from multiple concepts — not a summary of
any single memory, but a genuinely new semantic statement synthesized from
a combination (e.g. Distributed Systems + Rust + Backend + Caching +
Scalability -> a new composite concept spanning all five). This is the one
Day 8 component that produces knowledge the user never stated in any
single conversation.

Heuristic, not LLM-based (no round trip in the dream hot path, consistent
with the rest of this engine) — the label is composed from the group's
most distinctive words rather than generated prose. An LLM-optional path
for more fluent labels is a natural, localized future upgrade (see
`DAY8_DREAM_MODE.md`), matching this codebase's existing dual heuristic/
LLM pattern (e.g. `HybridScoringEngine`).
"""
import logging
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import ConceptMemory, KnowledgeSynthesis
from app.core.config import settings

logger = logging.getLogger(__name__)


class KnowledgeSynthesizer:
    """Synthesizes new higher-order concepts from groups of related concepts."""

    def __init__(self, session: Session):
        self.session = session

    def synthesize(self, user_id: UUID, dream_session_id: Optional[UUID] = None) -> List[Dict]:
        """
        Find the user's strongest concepts and synthesize a new concept
        representing their combination.

        Returns:
            List of synthesis records (0 or 1 per run):
            {synthesized_concept, source_concepts, confidence, new_concept_id}
        """
        concepts = self.session.query(ConceptMemory).filter(
            ConceptMemory.user_id == user_id,
            ConceptMemory.confidence >= settings.synthesis_min_confidence,
        ).order_by(ConceptMemory.confidence.desc()).all()
        concepts = [c for c in concepts if not (c.extra_metadata or {}).get("retired")]

        if len(concepts) < settings.synthesis_min_concepts:
            return []

        group = concepts[:settings.synthesis_max_concepts]
        label = self._synthesize_label(group)

        existing = self.session.query(ConceptMemory).filter(
            ConceptMemory.user_id == user_id, ConceptMemory.concept_name == label,
        ).first()
        if existing:
            return []

        confidence = min(1.0, sum(c.confidence or 0.5 for c in group) / len(group))
        if confidence < settings.synthesis_min_confidence:
            return []

        source_ids = [c.id for c in group]
        memory_ids = list(set(sum([(c.supporting_memory_ids or []) for c in group], [])))

        new_concept = ConceptMemory(
            user_id=user_id,
            concept_name=label,
            description=f"Synthesized from: {', '.join(c.concept_name for c in group)}",
            confidence=confidence,
            support_count=sum(c.support_count or 1 for c in group),
            supporting_memory_ids=memory_ids,
            related_concept_ids=[str(i) for i in source_ids],
            is_derived_from=",".join(str(i) for i in source_ids),
        )
        self.session.add(new_concept)
        self.session.flush()

        record = KnowledgeSynthesis(
            user_id=user_id,
            dream_session_id=dream_session_id,
            source_concept_ids=[str(i) for i in source_ids],
            source_concept_names=[c.concept_name for c in group],
            new_concept_id=new_concept.id,
            new_concept=label,
            reasoning=new_concept.description,
            confidence=confidence,
        )
        self.session.add(record)
        self.session.commit()

        return [{
            "synthesized_concept": label,
            "source_concepts": [c.concept_name for c in group],
            "confidence": round(confidence, 3),
            "new_concept_id": new_concept.id,
        }]

    @staticmethod
    def _synthesize_label(group: List[ConceptMemory]) -> str:
        """Compose a new-knowledge label from the group's most distinctive
        words, one per source concept, in confidence order."""
        seen = set()
        words = []
        for concept in group:
            name_words = [
                w for w in (concept.concept_name or "").replace("_", " ").split()
                if w.lower() not in seen
            ]
            if name_words:
                words.append(name_words[0])
                seen.add(name_words[0].lower())
        if not words:
            return f"Synthesized Concept {group[0].id}"
        return " ".join(w.capitalize() for w in words[:5])
