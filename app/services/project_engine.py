"""
Project Memory Engine

Projects become first-class citizens: goals, architecture, progress,
dependencies, roadmap, decisions, and open questions — not just a memory
mentioning a project name. Links each `Project` row to its `WorldEntity`
node so the graph and the structured project record stay in sync.
"""
import logging
import re
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import Project, ProjectStatusEnum, WorldEntity

logger = logging.getLogger(__name__)

PHASE_PATTERN = re.compile(
    r"\b(?:currently|now)\s+(?:implementing|working on|building|on)\s+"
    r"([A-Za-z][\w\s]{2,40}?)(?:[.!?\n]|$)",
    re.IGNORECASE,
)
NEXT_STEP_PATTERN = re.compile(
    r"\b(?:next(?: step| up| goal)?|then)\s*(?:is|will be|:)?\s+([A-Za-z][^.!?\n]{2,80})",
    re.IGNORECASE,
)
STATUS_PATTERNS = {
    ProjectStatusEnum.PAUSED: [r"\bpaus(?:e|ed|ing)\b", r"\bon hold\b"],
    ProjectStatusEnum.COMPLETED: [r"\b(?:completed|finished|shipped|done)\b"],
    ProjectStatusEnum.ARCHIVED: [r"\barchiv(?:e|ed|ing)\b", r"\babandon(?:ed|ing)?\b"],
}


class ProjectMemoryEngine:
    """Detects and maintains first-class Project records."""

    def __init__(self, session: Session):
        self.session = session

    def update_from_text(
        self, user_id: UUID, project_entities: List[WorldEntity], text: str,
        tech_entities: Optional[List[WorldEntity]] = None,
    ) -> List[Project]:
        """
        Upsert Project rows for detected PROJECT entities, updating
        current_phase/next_step/status/tech_stack from the text.
        """
        if not project_entities:
            return []

        tech_names = [e.entity_name for e in (tech_entities or [])]
        phase_match = PHASE_PATTERN.search(text)
        next_match = NEXT_STEP_PATTERN.search(text)
        detected_status = self._detect_status(text)

        touched = []
        for entity in project_entities:
            project = self.session.query(Project).filter(
                Project.user_id == user_id, Project.project_name.ilike(entity.entity_name),
            ).first()

            if not project:
                project = Project(
                    user_id=user_id, world_entity_id=entity.id,
                    project_name=entity.entity_name, status=ProjectStatusEnum.ACTIVE,
                )
                self.session.add(project)
                self.session.flush()

            if phase_match:
                project.current_phase = phase_match.group(1).strip()
            if next_match:
                project.next_step = next_match.group(1).strip()
            if detected_status:
                project.status = detected_status
            if tech_names:
                project.tech_stack = list(set((project.tech_stack or []) + tech_names))

            project.updated_at = datetime.utcnow()
            touched.append(project)

        self.session.commit()
        return touched

    def _detect_status(self, text: str) -> Optional[ProjectStatusEnum]:
        lowered = text.lower()
        for status, patterns in STATUS_PATTERNS.items():
            if any(re.search(p, lowered) for p in patterns):
                return status
        return None

    def record_progress(
        self, project_id: UUID, progress: float, next_step: Optional[str] = None
    ) -> Optional[Project]:
        """Manually record progress on a project (used by POST /projects updates)."""
        project = self.session.query(Project).filter(Project.id == project_id).first()
        if not project:
            return None
        project.progress = max(0.0, min(1.0, progress))
        if next_step:
            project.next_step = next_step
        project.updated_at = datetime.utcnow()
        self.session.commit()
        return project
