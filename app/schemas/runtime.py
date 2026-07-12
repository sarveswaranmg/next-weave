"""Day 10: Cognitive Runtime Platform - Pydantic schemas"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID


class ChatRequest(BaseModel):
    """Request for POST /runtime/chat - the CognitiveAgent.chat() surface"""
    user_id: UUID
    message: str
    provider: Optional[str] = None
    model: Optional[str] = None
    memory: bool = True
    world_model: bool = True
    predictive_recall: bool = True
    context_composer: bool = True
    token_budget: Optional[int] = None
    schedule_background: bool = True


class ChatResponse(BaseModel):
    user_id: UUID
    response: str
    provider: str
    model: str
    usage: Dict[str, int]
    memory_stored: Optional[UUID] = None
    world_model: Optional[Dict[str, Any]] = None
    context: Optional[Dict[str, Any]] = None
    background_scheduled: List[str]
    stage_latency_ms: Dict[str, float]
    total_latency_ms: float


class BenchmarkRequest(BaseModel):
    """Request for POST /runtime/benchmark"""
    user_id: UUID
    query: str
    history: List[str] = Field(default_factory=list)
    strategies: Optional[List[str]] = None
    dataset: str = "manual"


class BenchmarkRunSchema(BaseModel):
    id: UUID
    strategy: str
    dataset: str
    latency_ms: float
    token_usage: int
    prompt_token_reduction_percent: float
    personalization_score: float
    reasoning_score: float
    compression_ratio: float
    interaction_count: int
    created_at: datetime

    class Config:
        from_attributes = True


class BenchmarkResponse(BaseModel):
    runs: List[BenchmarkRunSchema]


class EvaluateRequest(BaseModel):
    """Request for POST /runtime/evaluate - runs NeuroBench against a
    freshly generated synthetic dataset (the Continuous Evaluation Pipeline entry point)"""
    dataset_name: str = "synthetic"
    user_count: int = Field(default=3, ge=1, le=50)
    seed: int = 42


class EvaluateResponse(BaseModel):
    dataset_name: str
    users_evaluated: int
    runs: List[BenchmarkRunSchema]
    summary: Dict[str, Dict[str, float]]  # strategy -> {metric: average}


class RuntimeMetricsResponse(BaseModel):
    user_id: Optional[UUID] = None
    memory_count: int
    concept_count: int
    identity_nodes: int
    world_nodes: int
    world_relationships: int
    project_count: int
    compression_ratio: float
    cognitive_health_score: float


class RuntimeHealthResponse(BaseModel):
    status: str
    version: str
    environment: str
    database: str
    timestamp: datetime


class RuntimeVersionResponse(BaseModel):
    version: str
    app_name: str
    day: int
    components: List[str]


class ExplainQuery(BaseModel):
    user_id: UUID
    subject_type: str
    subject_id: Optional[UUID] = None


class PluginActionRequest(BaseModel):
    """Request for POST /runtime/plugins"""
    action: str = Field(..., description="'list', 'register', or 'unregister'")
    plugin_name: Optional[str] = None


class PluginInfo(BaseModel):
    name: str
    version: str
    description: str


class PluginActionResponse(BaseModel):
    action: str
    plugins: List[PluginInfo]
    success: bool = True


class DashboardResponse(BaseModel):
    """GET /runtime/dashboard - bundled summary for observability dashboards"""
    user_id: Optional[UUID] = None
    runtime_metrics: RuntimeMetricsResponse
    recent_benchmark_runs: List[BenchmarkRunSchema]
    version: str


class DeleteUserResponse(BaseModel):
    user_id: UUID
    deleted_counts: Dict[str, int]
