"""Day 9: World Model Engine API endpoints"""
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.database import get_db_session
from app.db.models import Project, WorldEntity, WorldRelationship
from app.schemas.world import (
    WorldUpdateRequest,
    WorldUpdateResponse,
    GraphStatsResponse,
    ActiveContextResponse,
    PredictionResponse,
    WorldModelResponse,
    EnvironmentResponse,
    ProjectResponse,
    ProjectListResponse,
    DecisionRequest,
    DecisionResponse,
    TimelineResponse,
    DependenciesResponse,
    DependencyEntry,
    WorldPredictRequest,
)
from app.services.world_model_pipeline import WorldModelPipeline
from app.services.world_graph import WorldGraph
from app.services.active_context_engine import ActiveContextEngine
from app.services.environmental_context_engine import EnvironmentalContextEngine
from app.services.decision_engine import DecisionMemoryEngine
from app.services.timeline_engine import TimelineEngine
from app.services.world_traversal import WorldTraversalService
from app.services.predictive_project_intelligence import PredictiveProjectIntelligence

logger = logging.getLogger(__name__)

router = APIRouter(tags=["world-model"])


@router.post("/world/update", response_model=WorldUpdateResponse)
async def update_world_model(
    request: WorldUpdateRequest,
    session: Session = Depends(get_db_session),
) -> WorldUpdateResponse:
    """
    Run the full world model pipeline over a piece of text: entity
    extraction, relationship detection, project detection, decision
    recording, world graph update, and context prediction.
    """
    try:
        pipeline = WorldModelPipeline(session)
        result = pipeline.update(request.user_id, request.text, request.source_memory_id)

        return WorldUpdateResponse(
            entities_extracted=result["entities_extracted"],
            relationships_built=result["relationships_built"],
            projects_touched=result["projects_touched"],
            decisions_recorded=result["decisions_recorded"],
            graph_stats=GraphStatsResponse(**result["graph_stats"]),
            active_context=ActiveContextResponse(**result["active_context"]),
            prediction=PredictionResponse(**result["prediction"]),
            stage_latency_ms=result["stage_latency_ms"],
            total_latency_ms=result["total_latency_ms"],
        )
    except Exception as e:
        logger.error(f"World model update error: {e}")
        raise HTTPException(status_code=500, detail=f"World model update failed: {str(e)}")


@router.get("/world/model", response_model=WorldModelResponse)
async def get_world_model(
    user_id: UUID,
    session: Session = Depends(get_db_session),
) -> WorldModelResponse:
    """Get a full snapshot of the user's world model."""
    try:
        entity_count = session.query(WorldEntity).filter(WorldEntity.user_id == user_id).count()
        relationship_count = session.query(WorldRelationship).filter(WorldRelationship.user_id == user_id).count()
        project_count = session.query(Project).filter(Project.user_id == user_id).count()

        world_graph = WorldGraph()
        world_graph.build_graph_for_user(session, user_id)
        graph_stats = world_graph.get_graph_statistics()

        active_context = ActiveContextEngine(session).get_active_context(user_id)
        environment = EnvironmentalContextEngine(session).get_environment(user_id)

        return WorldModelResponse(
            user_id=user_id,
            entity_count=entity_count,
            relationship_count=relationship_count,
            project_count=project_count,
            graph_stats=GraphStatsResponse(**graph_stats),
            active_context=ActiveContextResponse(**active_context),
            environment=EnvironmentResponse(**environment),
        )
    except Exception as e:
        logger.error(f"World model snapshot error: {e}")
        raise HTTPException(status_code=500, detail="Failed to build world model snapshot")


@router.get("/projects", response_model=ProjectListResponse)
async def list_projects(
    user_id: UUID,
    session: Session = Depends(get_db_session),
) -> ProjectListResponse:
    """List all tracked projects for a user."""
    try:
        projects = session.query(Project).filter(Project.user_id == user_id).order_by(
            Project.updated_at.desc()
        ).all()
        return ProjectListResponse(
            user_id=user_id,
            projects=[ProjectResponse.model_validate(p) for p in projects],
        )
    except Exception as e:
        logger.error(f"List projects error: {e}")
        raise HTTPException(status_code=500, detail="Failed to list projects")


@router.get("/projects/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: UUID,
    user_id: UUID,
    session: Session = Depends(get_db_session),
) -> ProjectResponse:
    """Get a single project's full record."""
    try:
        project = session.query(Project).filter(
            Project.id == project_id, Project.user_id == user_id
        ).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        return ProjectResponse.model_validate(project)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get project error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch project")


@router.post("/decision", response_model=DecisionResponse)
async def record_decision(
    request: DecisionRequest,
    session: Session = Depends(get_db_session),
) -> DecisionResponse:
    """Manually record an architectural decision, with reason and impact."""
    try:
        engine = DecisionMemoryEngine(session)
        decision = engine.record(
            user_id=request.user_id, decision=request.decision, reason=request.reason,
            impact=request.impact, status=request.status, project_id=request.project_id,
            confidence=request.confidence,
        )
        return DecisionResponse.model_validate(decision)
    except Exception as e:
        logger.error(f"Record decision error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to record decision: {str(e)}")


@router.get("/timeline", response_model=TimelineResponse)
async def get_timeline(
    user_id: UUID,
    project_id: Optional[UUID] = None,
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_db_session),
) -> TimelineResponse:
    """Get the past/present/future timeline for a user or a specific project."""
    try:
        engine = TimelineEngine(session)
        result = engine.get_timeline(user_id, project_id=project_id, limit=limit)
        return TimelineResponse(**result)
    except Exception as e:
        logger.error(f"Timeline error: {e}")
        raise HTTPException(status_code=500, detail="Failed to build timeline")


@router.get("/dependencies", response_model=DependenciesResponse)
async def get_dependencies(
    user_id: UUID,
    entity_id: UUID,
    max_depth: int = Query(default=3, ge=1, le=6),
    session: Session = Depends(get_db_session),
) -> DependenciesResponse:
    """Find what an entity (typically a project) depends on, transitively."""
    try:
        traversal = WorldTraversalService(session, user_id)
        deps = traversal.find_dependencies(entity_id, max_depth=max_depth)
        return DependenciesResponse(
            entity_id=entity_id,
            dependencies=[DependencyEntry(**d) for d in deps],
        )
    except Exception as e:
        logger.error(f"Dependencies error: {e}")
        raise HTTPException(status_code=500, detail="Failed to compute dependencies")


@router.post("/world/predict", response_model=PredictionResponse)
async def predict_world(
    request: WorldPredictRequest,
    session: Session = Depends(get_db_session),
) -> PredictionResponse:
    """Predict likely next task, blockers, dependencies, and missing knowledge/docs."""
    try:
        intelligence = PredictiveProjectIntelligence(session)
        result = intelligence.predict(request.user_id, request.project_id)
        return PredictionResponse(**result)
    except Exception as e:
        logger.error(f"World predict error: {e}")
        raise HTTPException(status_code=500, detail=f"Prediction failed: {str(e)}")
