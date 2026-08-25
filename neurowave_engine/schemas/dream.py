"""Day 8: Offline Cognitive Consolidation Engine ("Dream Mode") - Pydantic schemas"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID

from neurowave_engine.db.models import DreamSessionStatusEnum


class DreamStartRequest(BaseModel):
    """Request to manually start a dream session for a user"""
    user_id: UUID
    trigger: str = "manual"


class DreamSessionResponse(BaseModel):
    """Full dream session record"""
    id: UUID
    user_id: UUID
    status: DreamSessionStatusEnum
    trigger: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    memories_replayed: int
    memories_processed: int
    patterns_discovered: int
    concepts_created: int
    concepts_refined: int
    identity_updates: int
    contradictions_resolved: int
    graph_nodes_removed: int
    graph_edges_strengthened: int
    knowledge_synthesized: int
    compression_ratio: float
    health_score_before: Optional[float] = None
    health_score_after: Optional[float] = None
    stage_latency_ms: Dict[str, float]
    total_latency_ms: float
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        from_attributes = True


class DreamStopRequest(BaseModel):
    """Request to cancel a running dream session"""
    dream_session_id: UUID


class DreamStopResponse(BaseModel):
    """Stop response"""
    dream_session_id: UUID
    success: bool
    status: str


class DreamHistoryResponse(BaseModel):
    """Past dream sessions for a user"""
    user_id: UUID
    sessions: List[DreamSessionResponse]


class DreamReplayRequest(BaseModel):
    """Request to run a standalone replay pass"""
    user_id: UUID
    batch_size: Optional[int] = None


class ReplayResult(BaseModel):
    memory_id: UUID
    previous_importance: Optional[float] = None
    new_importance: Optional[float] = None
    delta: float


class DreamReplayResponse(BaseModel):
    """Replay response"""
    replayed: List[ReplayResult]
    replay_latency_ms: float


class DreamRefineRequest(BaseModel):
    """Request to run a standalone concept refinement pass"""
    user_id: UUID


class DreamRefineResponse(BaseModel):
    """Refinement response"""
    merged: List[Dict[str, Any]]
    generalized: List[Dict[str, Any]]
    strengthened: List[Dict[str, Any]]
    retired: List[Dict[str, Any]]
    refine_latency_ms: float


class DreamSynthesizeRequest(BaseModel):
    """Request to run a standalone knowledge synthesis pass"""
    user_id: UUID


class SynthesisResult(BaseModel):
    synthesized_concept: str
    source_concepts: List[str]
    confidence: float = Field(..., ge=0.0, le=1.0)
    new_concept_id: UUID


class DreamSynthesizeResponse(BaseModel):
    """Synthesis response"""
    synthesized: List[SynthesisResult]
    synthesize_latency_ms: float


class DreamStatisticsResponse(BaseModel):
    """Aggregated Dream Mode observability metrics for a user"""
    user_id: UUID
    total_sessions: int
    completed_sessions: int
    cancelled_sessions: int
    failed_sessions: int
    average_dream_duration_ms: float
    average_memories_replayed: float
    average_patterns_discovered: float
    average_concepts_created: float
    average_identity_updates: float
    average_graph_nodes_removed: float
    average_graph_edges_strengthened: float
    average_compression_ratio: float
    average_health_improvement: float
    total_knowledge_synthesized: int
    total_patterns_discovered: int
