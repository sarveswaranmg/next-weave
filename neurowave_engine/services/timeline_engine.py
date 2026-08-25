"""
Timeline Engine

Represents past, present, and future for every tracked project: completed
work, the current milestone, and upcoming work — built entirely from
existing timestamped records (`WorldEntity` first/last seen, `Project`
updates, `ArchitecturalDecision` history) rather than a separate timeline
table, so the timeline can never drift out of sync with the underlying
data it summarizes.
"""
import logging
from datetime import datetime
from typing import Dict, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from neurowave_engine.db.models import Project, ArchitecturalDecision, WorldEntity, WorldEntityTypeEnum

logger = logging.getLogger(__name__)


class TimelineEngine:
    """Builds a past/present/future timeline for a user or a specific project."""

    def __init__(self, session: Session):
        self.session = session

    def get_timeline(self, user_id: UUID, project_id: Optional[UUID] = None, limit: int = 50) -> Dict:
        decisions_query = self.session.query(ArchitecturalDecision).filter(
            ArchitecturalDecision.user_id == user_id
        )
        if project_id:
            decisions_query = decisions_query.filter(ArchitecturalDecision.project_id == project_id)
        decisions = decisions_query.order_by(ArchitecturalDecision.timestamp.desc()).limit(limit).all()

        tasks = self.session.query(WorldEntity).filter(
            WorldEntity.user_id == user_id, WorldEntity.entity_type == WorldEntityTypeEnum.TASK,
        ).order_by(WorldEntity.first_seen_at.desc()).limit(limit).all()

        projects_query = self.session.query(Project).filter(Project.user_id == user_id)
        if project_id:
            projects_query = projects_query.filter(Project.id == project_id)
        projects = projects_query.all()

        past = [
            {
                "type": "decision", "label": d.decision, "reason": d.reason,
                "status": d.status, "timestamp": d.timestamp,
            }
            for d in decisions
        ]
        past += [
            {"type": "task_started", "label": t.entity_name, "timestamp": t.first_seen_at}
            for t in tasks
        ]
        past.sort(key=lambda e: e["timestamp"] or datetime.min, reverse=True)

        present = [
            {
                "type": "project", "label": p.project_name, "current_phase": p.current_phase,
                "status": p.status.value, "progress": p.progress, "updated_at": p.updated_at,
            }
            for p in projects if p.status.value == "active"
        ]

        future = [
            {"type": "next_step", "project": p.project_name, "label": p.next_step}
            for p in projects if p.next_step
        ]
        future += [
            {"type": "roadmap_item", "project": p.project_name, "label": item}
            for p in projects for item in (p.roadmap or [])
        ]

        return {
            "user_id": str(user_id),
            "past": past[:limit],
            "present": present,
            "future": future[:limit],
        }
