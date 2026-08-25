"""
Active Context Engine

The world model should always be able to answer: what's the current
project, current milestone, current blockers, current priorities, current
experiments, current technology stack? Continuously recomputed from the
most recently updated active project and its linked graph entities —
there's no separate cache to keep in sync by hand; it's a live query.
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List
from uuid import UUID

from sqlalchemy.orm import Session

from neurowave_engine.db.models import Project, ProjectStatusEnum, WorldEntity, WorldEntityTypeEnum, WorldRelationship
from neurowave_engine.core.config import settings

logger = logging.getLogger(__name__)


class ActiveContextEngine:
    """Computes the user's current active context on demand."""

    def __init__(self, session: Session):
        self.session = session

    def get_active_context(self, user_id: UUID) -> Dict:
        current_project = self.session.query(Project).filter(
            Project.user_id == user_id, Project.status == ProjectStatusEnum.ACTIVE,
        ).order_by(Project.updated_at.desc()).first()

        cutoff = datetime.utcnow() - timedelta(days=settings.world_active_context_window_days)

        active_tasks = self.session.query(WorldEntity).filter(
            WorldEntity.user_id == user_id, WorldEntity.entity_type == WorldEntityTypeEnum.TASK,
            WorldEntity.last_seen_at >= cutoff,
        ).order_by(WorldEntity.last_seen_at.desc()).limit(10).all()

        active_tech = self.session.query(WorldEntity).filter(
            WorldEntity.user_id == user_id, WorldEntity.entity_type == WorldEntityTypeEnum.TECHNOLOGY,
            WorldEntity.last_seen_at >= cutoff,
        ).order_by(WorldEntity.confidence.desc()).limit(15).all()

        priorities = []
        if current_project:
            if current_project.next_step:
                priorities.append(current_project.next_step)
            priorities.extend(current_project.open_questions or [])

        return {
            "current_project": {
                "id": current_project.id, "name": current_project.project_name,
                "current_phase": current_project.current_phase, "status": current_project.status.value,
                "progress": current_project.progress, "next_step": current_project.next_step,
            } if current_project else None,
            "current_milestone": current_project.current_phase if current_project else None,
            "current_priorities": priorities[:5],
            "current_blockers": self._find_blockers(user_id),
            "current_experiments": [t.entity_name for t in active_tasks],
            "current_technology_stack": [t.entity_name for t in active_tech],
            "window_days": settings.world_active_context_window_days,
        }

    def _find_blockers(self, user_id: UUID) -> List[str]:
        blocking_rels = self.session.query(WorldRelationship).filter(
            WorldRelationship.user_id == user_id, WorldRelationship.relationship_type == "blocks",
        ).order_by(WorldRelationship.strength.desc()).limit(10).all()

        blockers = []
        for rel in blocking_rels:
            source = self.session.query(WorldEntity).filter(WorldEntity.id == rel.source_entity_id).first()
            target = self.session.query(WorldEntity).filter(WorldEntity.id == rel.target_entity_id).first()
            if source and target:
                blockers.append(f"{source.entity_name} blocks {target.entity_name}")
        return blockers
