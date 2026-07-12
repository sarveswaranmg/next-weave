"""Day 9: World Model Engine - Pydantic schemas"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID

from app.db.models import WorldEntityTypeEnum, ProjectStatusEnum


class WorldUpdateRequest(BaseModel):
    """Request to run the full world model pipeline over a piece of text"""
    user_id: UUID
    text: str
    source_memory_id: Optional[UUID] = None


class EntitySummary(BaseModel):
    id: UUID
    entity_type: WorldEntityTypeEnum
    entity_name: str
    confidence: float
    mention_count: int


class RelationshipSummary(BaseModel):
    id: UUID
    source_entity_id: UUID
    target_entity_id: UUID
    relationship_type: str
    strength: float


class ProjectSummary(BaseModel):
    id: UUID
    project_name: str
    status: ProjectStatusEnum
    current_phase: Optional[str] = None
    progress: float
    next_step: Optional[str] = None


class DecisionSummary(BaseModel):
    id: UUID
    decision: str
    reason: Optional[str] = None
    status: str
    confidence: float


class ActiveContextResponse(BaseModel):
    current_project: Optional[Dict[str, Any]] = None
    current_milestone: Optional[str] = None
    current_priorities: List[str]
    current_blockers: List[str]
    current_experiments: List[str]
    current_technology_stack: List[str]
    window_days: int


class GraphStatsResponse(BaseModel):
    node_count: int
    edge_count: int
    density: float
    entity_type_distribution: Dict[str, int]


class PredictionResponse(BaseModel):
    project_id: Optional[UUID] = None
    project_name: Optional[str] = None
    likely_next_task: Optional[str] = None
    likely_blockers: List[str]
    likely_dependencies: List[str]
    likely_missing_knowledge: List[str]
    likely_documentation_needed: List[str]
    confidence: float = Field(..., ge=0.0, le=1.0)


class WorldUpdateResponse(BaseModel):
    """Full world model pipeline response"""
    entities_extracted: int
    relationships_built: int
    projects_touched: int
    decisions_recorded: int
    graph_stats: GraphStatsResponse
    active_context: ActiveContextResponse
    prediction: PredictionResponse
    stage_latency_ms: Dict[str, float]
    total_latency_ms: float


class EnvironmentResponse(BaseModel):
    operating_system: List[str]
    ide: List[str]
    cloud_providers: List[str]
    integrations: List[str]
    databases: List[str]
    repositories: List[str]
    deployment_targets: List[str]


class WorldModelResponse(BaseModel):
    """GET /world/model - full world model snapshot"""
    user_id: UUID
    entity_count: int
    relationship_count: int
    project_count: int
    graph_stats: GraphStatsResponse
    active_context: ActiveContextResponse
    environment: EnvironmentResponse


class ProjectResponse(BaseModel):
    id: UUID
    project_name: str
    status: ProjectStatusEnum
    current_phase: Optional[str] = None
    progress: float
    next_step: Optional[str] = None
    goals: List[str]
    architecture_notes: Optional[str] = None
    tech_stack: List[str]
    dependencies: List[str]
    roadmap: List[str]
    open_questions: List[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProjectListResponse(BaseModel):
    user_id: UUID
    projects: List[ProjectResponse]


class DecisionRequest(BaseModel):
    """Request to manually record an architectural decision"""
    user_id: UUID
    decision: str
    reason: Optional[str] = None
    impact: Optional[str] = None
    status: str = "decided"
    project_id: Optional[UUID] = None
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)


class DecisionResponse(BaseModel):
    id: UUID
    project_id: Optional[UUID] = None
    decision: str
    reason: Optional[str] = None
    impact: Optional[str] = None
    status: str
    confidence: float
    timestamp: datetime

    class Config:
        from_attributes = True


class TimelineEntry(BaseModel):
    type: str
    label: Optional[str] = None
    reason: Optional[str] = None
    status: Optional[str] = None
    project: Optional[str] = None
    current_phase: Optional[str] = None
    progress: Optional[float] = None
    timestamp: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class TimelineResponse(BaseModel):
    user_id: UUID
    past: List[TimelineEntry]
    present: List[TimelineEntry]
    future: List[TimelineEntry]


class DependencyEntry(BaseModel):
    entity_id: UUID
    name: Optional[str] = None
    entity_type: Optional[str] = None
    depth: int


class DependenciesResponse(BaseModel):
    entity_id: UUID
    dependencies: List[DependencyEntry]


class WorldPredictRequest(BaseModel):
    user_id: UUID
    project_id: Optional[UUID] = None
