"""
World Model Pipeline

Orchestrates the full world-model update flow for a piece of text
(typically a conversation or memory content):

    Entity Extraction -> Relationship Detection -> Project Detection ->
    Decision Recording -> World Graph Update -> Context Prediction

Timeline is not a separate write step — `TimelineEngine` reads directly
from the entities/projects/decisions this pipeline produces, so it can
never drift out of sync.
"""
import logging
import time
from typing import Dict, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from neurowave_engine.db.models import WorldEntityTypeEnum
from neurowave_engine.services.entity_extractor import EntityExtractor
from neurowave_engine.services.relationship_builder import RelationshipBuilder
from neurowave_engine.services.project_engine import ProjectMemoryEngine
from neurowave_engine.services.decision_engine import DecisionMemoryEngine
from neurowave_engine.services.world_graph import WorldGraph
from neurowave_engine.services.active_context_engine import ActiveContextEngine
from neurowave_engine.services.predictive_project_intelligence import PredictiveProjectIntelligence

logger = logging.getLogger(__name__)


class WorldModelPipeline:
    """Runs the full world model update pipeline for one piece of text."""

    def __init__(self, session: Session):
        self.session = session
        self.entity_extractor = EntityExtractor(session)
        self.relationship_builder = RelationshipBuilder(session)
        self.project_engine = ProjectMemoryEngine(session)
        self.decision_engine = DecisionMemoryEngine(session)
        self.active_context_engine = ActiveContextEngine(session)
        self.predictive_intelligence = PredictiveProjectIntelligence(session)

    def update(self, user_id: UUID, text: str, source_memory_id: Optional[UUID] = None) -> Dict:
        """Run the full pipeline: extract -> relate -> detect projects ->
        record decisions -> refresh graph -> predict."""
        start = time.time()
        stage_latency: Dict[str, float] = {}

        t0 = time.time()
        entities = self.entity_extractor.extract(user_id, text, source_memory_id)
        stage_latency["entity_extraction"] = (time.time() - t0) * 1000

        t0 = time.time()
        relationships = self.relationship_builder.build(user_id, entities, text, source_memory_id)
        stage_latency["relationship_detection"] = (time.time() - t0) * 1000

        t0 = time.time()
        project_entities = [e for e in entities if e.entity_type == WorldEntityTypeEnum.PROJECT]
        tech_entities = [e for e in entities if e.entity_type == WorldEntityTypeEnum.TECHNOLOGY]
        projects = self.project_engine.update_from_text(user_id, project_entities, text, tech_entities)
        stage_latency["project_detection"] = (time.time() - t0) * 1000

        t0 = time.time()
        primary_project_id = projects[0].id if projects else None
        decisions = self.decision_engine.detect_and_record(user_id, text, primary_project_id, source_memory_id)
        stage_latency["decision_recording"] = (time.time() - t0) * 1000

        t0 = time.time()
        world_graph = WorldGraph()
        world_graph.build_graph_for_user(self.session, user_id)
        graph_stats = world_graph.get_graph_statistics()
        stage_latency["world_graph_update"] = (time.time() - t0) * 1000

        t0 = time.time()
        active_context = self.active_context_engine.get_active_context(user_id)
        prediction = self.predictive_intelligence.predict(user_id, primary_project_id)
        stage_latency["context_prediction"] = (time.time() - t0) * 1000

        total_latency_ms = (time.time() - start) * 1000

        return {
            "entities_extracted": len(entities),
            "relationships_built": len(relationships),
            "projects_touched": len(projects),
            "decisions_recorded": len(decisions),
            "graph_stats": graph_stats,
            "active_context": active_context,
            "prediction": prediction,
            "stage_latency_ms": stage_latency,
            "total_latency_ms": total_latency_ms,
            "entities": entities,
            "relationships": relationships,
            "projects": projects,
            "decisions": decisions,
        }
