"""
Decision Memory Engine

Tracks architectural decisions so later retrieval can explain *why*
something was decided, not just what. Detected from decision-signaling
language ("postponed", "decided to", "X instead of Y", "migrate ...
later") or recorded explicitly via `POST /decision`. Never overwritten —
a changed decision is a new row, preserving the full decision history.
"""
import logging
import re
from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import ArchitecturalDecision

logger = logging.getLogger(__name__)

# (status, regex) - the matched group(s) become the decision text.
DECISION_PATTERNS = [
    ("postponed", r"([A-Za-z][^.!?\n]{3,100}?\s+(?:postponed|deferred|delayed))"),
    ("decided", r"(?:i\s+)?decided\s+to\s+([a-zA-Z][^.!?\n]{3,100})"),
    ("decided", r"(?:we'?ll|i'?ll)\s+(?:migrate|move|switch)\s+"
                 r"([a-zA-Z][^.!?\n]{3,100}?\s+(?:to|for)\s+[a-zA-Z][^.!?\n]{1,60})"),
    ("chosen", r"([A-Za-z][^.!?\n]{2,60}\s+instead of\s+[A-Za-z][^.!?\n]{2,60})"),
]

REASON_PATTERN = re.compile(
    r"\b(?:because|since|reason(?:ing)?(?: is| being)?:?)\s+([a-zA-Z][^.!?\n]{3,150})",
    re.IGNORECASE,
)


class DecisionMemoryEngine:
    """Detects and records architectural decisions."""

    def __init__(self, session: Session):
        self.session = session

    def detect_and_record(
        self, user_id: UUID, text: str, project_id: Optional[UUID] = None,
        source_memory_id: Optional[UUID] = None,
    ) -> List[ArchitecturalDecision]:
        """Detect decision-signaling language in text and record each as an
        ArchitecturalDecision row."""
        decisions = []
        reason_match = REASON_PATTERN.search(text)
        reason = reason_match.group(1).strip() if reason_match else None

        seen_texts = set()
        for status, pattern in DECISION_PATTERNS:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                decision_text = match.group(1).strip().rstrip(".,;:")
                if not decision_text or decision_text.lower() in seen_texts:
                    continue
                seen_texts.add(decision_text.lower())
                decisions.append(self.record(
                    user_id=user_id, decision=decision_text, reason=reason,
                    status=status, project_id=project_id, source_memory_id=source_memory_id,
                ))

        return decisions

    def record(
        self, user_id: UUID, decision: str, reason: Optional[str] = None,
        impact: Optional[str] = None, status: str = "decided",
        project_id: Optional[UUID] = None, confidence: float = 0.7,
        source_memory_id: Optional[UUID] = None,
    ) -> ArchitecturalDecision:
        """Record a single architectural decision (append-only)."""
        record = ArchitecturalDecision(
            user_id=user_id, project_id=project_id, decision=decision,
            reason=reason, impact=impact, status=status, confidence=confidence,
            supporting_memory_ids=[str(source_memory_id)] if source_memory_id else [],
        )
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def history_for_project(self, project_id: UUID, limit: int = 50) -> List[ArchitecturalDecision]:
        """Full decision history for a project, most recent first."""
        return self.session.query(ArchitecturalDecision).filter(
            ArchitecturalDecision.project_id == project_id
        ).order_by(ArchitecturalDecision.timestamp.desc()).limit(limit).all()
