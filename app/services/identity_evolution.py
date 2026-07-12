"""
Identity Evolution Engine

Identity should evolve during sleep. If a user's dominant identity trait
was "Interested in React" but recent memories/concepts are now dominated
by Rust, distributed systems, databases, and inference work, the identity
graph should reflect that shift — as a new, reinforced trait alongside
(never replacing) the old one, with the shift logged so evolution stays
inspectable rather than silently overwritten.
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import IdentityNode, IdentityEvolutionEvent
from app.core.config import settings

logger = logging.getLogger(__name__)

IDENTITY_NODE_TYPES = ("interest", "trait", "skill")


class IdentityEvolutionEngine:
    """Detects identity shifts from accumulated recent evidence."""

    def __init__(self, session: Session):
        self.session = session

    def evolve(self, user_id: UUID, dream_session_id: Optional[UUID] = None) -> List[Dict]:
        """
        Compare the user's currently dominant identity trait against recent
        concept/trait evidence; if a different trait now has stronger
        support, log an identity shift and reinforce the new trait without
        touching the old one.

        Returns:
            List of identity shift decisions (usually 0 or 1 per run).
        """
        nodes = self.session.query(IdentityNode).filter(
            IdentityNode.user_id == user_id,
            IdentityNode.node_type.in_(IDENTITY_NODE_TYPES),
        ).all()

        if not nodes:
            return []

        cutoff = datetime.utcnow() - timedelta(days=30)
        recent_nodes = [
            n for n in nodes
            if (n.last_reinforced_at and n.last_reinforced_at >= cutoff)
            or (n.created_at and n.created_at >= cutoff)
        ]

        if len(recent_nodes) < settings.identity_shift_min_supporting_concepts:
            return []

        # "Current dominant" must come from *established* (non-recent)
        # evidence - comparing the whole node set against itself would
        # often pick the same node as both "current" and "recent" (recent
        # evidence tends to score highest), making a real shift undetectable.
        # No established nodes means there's no prior identity to shift away
        # from yet, so no shift is reported.
        recent_ids = {n.id for n in recent_nodes}
        established_nodes = [n for n in nodes if n.id not in recent_ids]
        if not established_nodes:
            return []

        current_dominant = max(established_nodes, key=lambda n: (n.importance or 0) * (n.confidence or 0))
        recent_dominant = max(recent_nodes, key=lambda n: (n.confidence or 0) * (n.evidence_count or 1))

        if recent_dominant.id == current_dominant.id:
            return []  # already the dominant trait - no shift to report

        recent_strength = recent_dominant.confidence or 0.0
        if recent_strength < settings.identity_shift_evidence_threshold:
            return []

        event = IdentityEvolutionEvent(
            user_id=user_id,
            dream_session_id=dream_session_id,
            old_identity=current_dominant.node_value,
            new_identity=recent_dominant.node_value,
            reason=(
                f"Recent evidence ({len(recent_nodes)} reinforced/new traits in the last 30 days) "
                f"now more strongly supports '{recent_dominant.node_value}' than '{current_dominant.node_value}'"
            ),
            evidence_concept_ids=recent_dominant.supporting_concept_ids or [],
            confidence=recent_strength,
        )
        self.session.add(event)

        # Reinforce the new dominant trait - the old trait is left exactly
        # as-is; identity evolution never overwrites history.
        recent_dominant.importance = min(1.0, (recent_dominant.importance or 0.5) + 0.15)
        recent_dominant.last_reinforced_at = datetime.utcnow()

        self.session.commit()

        return [{
            "old_identity": current_dominant.node_value,
            "new_identity": recent_dominant.node_value,
            "reason": event.reason,
            "confidence": round(recent_strength, 3),
        }]
