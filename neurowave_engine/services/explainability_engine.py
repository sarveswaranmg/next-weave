"""
Explainability Engine

Every decision NeuroWeave makes should be explainable — why a memory was
selected, why it evolved, why concepts merged, why identity changed, why a
memory was forgotten. This aggregates the `reason`/`selection_reason`/
decision trails already produced by every prior day's engines
(`MemoryUtilityPredictor`'s selection_reason, `MemoryEvent`'s decay/merge/
archive/forget/revive reasons, `PredictiveRecallLog`'s per-memory
explanations, `DreamSession`'s identity shifts and merge decisions,
`IdentityEvolutionEvent`, `ArchitecturalDecision`) into one queryable
surface, rather than inventing a new heuristic — the explanations already
exist, scattered across nine days of tables; this engine is the index
over them.
"""
import logging
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from neurowave_engine.db.models import (
    Memory, MemoryEvent, PredictiveRecallLog, DreamSession,
    IdentityEvolutionEvent, ArchitecturalDecision,
)

logger = logging.getLogger(__name__)

SUBJECT_TYPES = {"memory", "retrieval", "identity", "dream", "decision"}


class ExplainabilityEngine:
    """Aggregates every explainable decision trail into one queryable surface."""

    def __init__(self, session: Session):
        self.session = session

    def explain_memory(self, user_id: UUID, memory_id: UUID) -> Dict:
        """Why was this memory selected/scored the way it is, and what has
        happened to it over its lifecycle?"""
        memory = self.session.query(Memory).filter(
            Memory.id == memory_id, Memory.user_id == user_id
        ).first()
        if not memory:
            return {"found": False}

        events = self.session.query(MemoryEvent).filter(
            MemoryEvent.memory_id == memory_id
        ).order_by(MemoryEvent.timestamp.desc()).all()

        return {
            "found": True,
            "memory_id": memory_id,
            "content": memory.content,
            "cognitive_state": memory.cognitive_state.value if memory.cognitive_state else None,
            "utility_score": memory.utility_score,
            "selection_reason": memory.selection_reason,
            "archive_reason": memory.archive_reason,
            "forget_reason": memory.forget_reason,
            "lifecycle_events": [
                {
                    "event_type": e.event_type, "old_state": e.old_state, "new_state": e.new_state,
                    "reason": e.reason, "confidence": e.confidence, "timestamp": e.timestamp,
                }
                for e in events
            ],
        }

    def explain_retrieval(self, user_id: UUID, recall_id: Optional[UUID] = None) -> Dict:
        """Why were these memories selected for a predictive recall run?"""
        query = self.session.query(PredictiveRecallLog).filter(PredictiveRecallLog.user_id == user_id)
        if recall_id:
            query = query.filter(PredictiveRecallLog.id == recall_id)
        log = query.order_by(PredictiveRecallLog.created_at.desc()).first()
        if not log:
            return {"found": False}

        return {
            "found": True,
            "recall_id": log.id,
            "query": log.query,
            "detected_goal": log.detected_goal,
            "explanations": log.explanations,
            "average_utility_score": log.average_utility_score,
        }

    def explain_identity_shift(self, user_id: UUID, limit: int = 10) -> List[Dict]:
        """Why did the user's identity change?"""
        events = self.session.query(IdentityEvolutionEvent).filter(
            IdentityEvolutionEvent.user_id == user_id
        ).order_by(IdentityEvolutionEvent.created_at.desc()).limit(limit).all()

        return [
            {
                "old_identity": e.old_identity, "new_identity": e.new_identity,
                "reason": e.reason, "confidence": e.confidence, "timestamp": e.created_at,
            }
            for e in events
        ]

    def explain_dream_session(self, user_id: UUID, dream_session_id: Optional[UUID] = None) -> Dict:
        """Why did concepts merge, identity evolve, or memories get
        archived during offline consolidation?"""
        query = self.session.query(DreamSession).filter(DreamSession.user_id == user_id)
        if dream_session_id:
            query = query.filter(DreamSession.id == dream_session_id)
        session_row = query.order_by(DreamSession.started_at.desc()).first()
        if not session_row:
            return {"found": False}

        return {
            "found": True,
            "dream_session_id": session_row.id,
            "status": session_row.status.value,
            "decisions": session_row.extra_metadata,
        }

    def explain_decision(self, user_id: UUID, limit: int = 10) -> List[Dict]:
        """Why were architectural decisions made?"""
        decisions = self.session.query(ArchitecturalDecision).filter(
            ArchitecturalDecision.user_id == user_id
        ).order_by(ArchitecturalDecision.timestamp.desc()).limit(limit).all()

        return [
            {
                "decision": d.decision, "reason": d.reason, "impact": d.impact,
                "status": d.status, "confidence": d.confidence, "timestamp": d.timestamp,
            }
            for d in decisions
        ]

    def explain(self, user_id: UUID, subject_type: str, subject_id: Optional[UUID] = None) -> Dict:
        """Unified entry point for GET /runtime/explain."""
        if subject_type not in SUBJECT_TYPES:
            return {"found": False, "error": f"Unknown subject_type '{subject_type}', expected one of {sorted(SUBJECT_TYPES)}"}

        if subject_type == "memory":
            if not subject_id:
                return {"found": False, "error": "subject_id (memory_id) is required"}
            return self.explain_memory(user_id, subject_id)
        if subject_type == "retrieval":
            return self.explain_retrieval(user_id, subject_id)
        if subject_type == "identity":
            return {"found": True, "events": self.explain_identity_shift(user_id)}
        if subject_type == "dream":
            return self.explain_dream_session(user_id, subject_id)
        return {"found": True, "decisions": self.explain_decision(user_id)}
