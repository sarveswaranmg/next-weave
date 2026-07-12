"""
Predictive Project Intelligence

Given the world model, proactively predicts: the likely next task, likely
blockers, likely missing dependencies, likely missing knowledge, and
likely documentation needs — so NeuroWeave can anticipate rather than
just respond.
"""
import logging
from typing import Dict, List, Optional, Set, Tuple
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import Project, ArchitecturalDecision
from app.services.world_traversal import WorldTraversalService

logger = logging.getLogger(__name__)

# Companion technologies/practices a healthy project stack "should" have -
# same data-driven pattern as Day 6's KnowledgeGapDetector, applied to
# project tech stacks instead of query topics.
STACK_EXPECTATIONS: List[Tuple[Set[str], List[str]]] = [
    ({"fastapi", "flask", "django"}, ["testing", "ci/cd", "api documentation", "monitoring"]),
    ({"postgresql", "mysql", "mongodb"}, ["migrations", "backup strategy", "connection pooling"]),
    ({"redis"}, ["cache invalidation strategy", "eviction policy"]),
    ({"docker", "kubernetes"}, ["deployment pipeline", "health checks", "logging"]),
    ({"react", "vue", "angular"}, ["state management", "testing", "accessibility"]),
]


class PredictiveProjectIntelligence:
    """Predicts likely next steps, blockers, and gaps from the world model."""

    def __init__(self, session: Session):
        self.session = session

    def predict(self, user_id: UUID, project_id: Optional[UUID] = None) -> Dict:
        project = None
        if project_id:
            project = self.session.query(Project).filter(Project.id == project_id).first()
        if not project:
            project = self.session.query(Project).filter(
                Project.user_id == user_id
            ).order_by(Project.updated_at.desc()).first()

        if not project:
            return {
                "project_id": None, "project_name": None,
                "likely_next_task": None, "likely_blockers": [], "likely_dependencies": [],
                "likely_missing_knowledge": [], "likely_documentation_needed": [], "confidence": 0.0,
            }

        likely_next_task = self._predict_next_task(project)
        missing_knowledge = self._predict_missing_knowledge(project)
        dependencies = self._predict_dependencies(user_id, project)
        blockers = self._predict_blockers(project)

        confidence = 0.5
        if likely_next_task:
            confidence += 0.2
        if missing_knowledge:
            confidence += 0.15
        confidence = min(1.0, confidence)

        return {
            "project_id": project.id,
            "project_name": project.project_name,
            "likely_next_task": likely_next_task,
            "likely_blockers": blockers,
            "likely_dependencies": dependencies,
            "likely_missing_knowledge": missing_knowledge,
            "likely_documentation_needed": [
                topic if "documentation" in topic else f"{topic} documentation"
                for topic in missing_knowledge[:3]
            ],
            "confidence": round(confidence, 3),
        }

    def _predict_next_task(self, project: Project) -> Optional[str]:
        if project.next_step:
            return project.next_step
        if project.roadmap:
            return project.roadmap[0]

        postponed = self.session.query(ArchitecturalDecision).filter(
            ArchitecturalDecision.project_id == project.id, ArchitecturalDecision.status == "postponed",
        ).order_by(ArchitecturalDecision.timestamp.desc()).first()
        if postponed:
            return postponed.decision

        return None

    def _predict_missing_knowledge(self, project: Project) -> List[str]:
        stack_lower = {t.lower() for t in (project.tech_stack or [])}
        missing = []
        for trigger_set, expectations in STACK_EXPECTATIONS:
            if trigger_set & stack_lower:
                for topic in expectations:
                    if topic not in missing and not any(topic in t for t in stack_lower):
                        missing.append(topic)
        return missing[:5]

    def _predict_dependencies(self, user_id: UUID, project: Project) -> List[str]:
        if not project.world_entity_id:
            return []
        traversal = WorldTraversalService(self.session, user_id)
        deps = traversal.find_dependencies(project.world_entity_id)
        return [d["name"] for d in deps if d.get("name")]

    def _predict_blockers(self, project: Project) -> List[str]:
        return list(project.open_questions or [])[:3]
