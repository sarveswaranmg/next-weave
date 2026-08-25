"""
Pattern Discovery Engine

Finds hidden relationships that were never explicitly stored. A user who
"studies distributed systems," "likes Rust," "researches operating
systems," and "builds backend services" never said "I'm a systems
engineer" — but the pattern is there across their memories and concepts.
This engine looks for that kind of higher-order signal and, when the
evidence is strong enough, writes it as a new IdentityNode.
"""
import logging
from datetime import datetime
from typing import Dict, List
from uuid import UUID

from sqlalchemy.orm import Session

from neurowave_engine.db.models import Memory, ConceptMemory, IdentityNode, CognitiveMemoryStateEnum
from neurowave_engine.core.config import settings

logger = logging.getLogger(__name__)

# Higher-order trait patterns: data, not logic, so new domains don't
# require pipeline changes. `min_matches` is the number of distinct
# keywords that must appear across a user's memories/concepts before the
# trait is even considered.
HIGHER_ORDER_PATTERNS: List[Dict] = [
    {
        "trait": "systems_engineering_interest",
        "keywords": ["distributed systems", "operating systems", "systems programming",
                     "concurrency", "kernel", "rust", "backend", "low-level", "memory management"],
        "min_matches": 3,
    },
    {
        "trait": "ai_infrastructure_interest",
        "keywords": ["machine learning", "inference", "llm", "model serving", "gpu",
                     "training", "neural network", "ai infrastructure"],
        "min_matches": 3,
    },
    {
        "trait": "product_builder_mindset",
        "keywords": ["startup", "product", "mvp", "shipping", "launch", "customer", "founder"],
        "min_matches": 2,
    },
    {
        "trait": "data_engineering_interest",
        "keywords": ["data pipeline", "etl", "data warehouse", "sql", "database", "analytics", "big data"],
        "min_matches": 3,
    },
    {
        "trait": "frontend_engineering_interest",
        "keywords": ["react", "frontend", "ui", "css", "javascript", "typescript", "component"],
        "min_matches": 3,
    },
    {
        "trait": "security_engineering_interest",
        "keywords": ["security", "encryption", "authentication", "vulnerability",
                     "penetration testing", "threat model"],
        "min_matches": 2,
    },
]


class PatternDiscoveryEngine:
    """Discovers higher-order traits from accumulated memory/concept evidence."""

    def __init__(self, session: Session):
        self.session = session

    def discover(self, user_id: UUID, patterns: List[Dict] = None) -> List[Dict]:
        """
        Args:
            user_id: User ID
            patterns: Override the default HIGHER_ORDER_PATTERNS (for testing/config)

        Returns:
            List of newly discovered patterns: {new_trait, confidence, matched_keywords, supporting_concept_ids}
        """
        patterns = patterns if patterns is not None else HIGHER_ORDER_PATTERNS

        memories = self.session.query(Memory).filter(
            Memory.user_id == user_id,
            Memory.cognitive_state.notin_([CognitiveMemoryStateEnum.ARCHIVED, CognitiveMemoryStateEnum.FORGOTTEN]),
        ).all()
        concepts = self.session.query(ConceptMemory).filter(ConceptMemory.user_id == user_id).all()

        if not memories and not concepts:
            return []

        combined_text = " ".join((m.content or "") for m in memories).lower()
        combined_text += " " + " ".join(
            (c.concept_name or "").replace("_", " ") + " " + (c.description or "") for c in concepts
        ).lower()

        existing_traits = {
            n.node_value for n in
            self.session.query(IdentityNode).filter(IdentityNode.user_id == user_id).all()
        }

        discovered = []
        for pattern in patterns:
            if pattern["trait"] in existing_traits:
                continue  # already known - not a *new* discovery

            matched = [kw for kw in pattern["keywords"] if kw in combined_text]
            if len(matched) < pattern["min_matches"]:
                continue

            evidence_score = min(1.0, len(matched) / len(pattern["keywords"]) + 0.2)
            if evidence_score < settings.pattern_discovery_min_evidence:
                continue

            supporting_concepts = [
                c.id for c in concepts
                if any(kw in (c.concept_name or "").lower() or kw in (c.description or "").lower() for kw in matched)
            ]

            node = IdentityNode(
                user_id=user_id,
                node_type="trait",
                node_value=pattern["trait"],
                confidence=evidence_score,
                evidence_count=len(matched),
                supporting_concept_ids=[str(i) for i in supporting_concepts],
                importance=0.6,
                last_reinforced_at=datetime.utcnow(),
                reinforcement_count=1,
            )
            self.session.add(node)

            discovered.append({
                "new_trait": pattern["trait"],
                "confidence": round(evidence_score, 3),
                "matched_keywords": matched,
                "supporting_concept_ids": [str(i) for i in supporting_concepts],
            })

        if discovered:
            self.session.commit()

        return discovered
