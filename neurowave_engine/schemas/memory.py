"""Pydantic schemas for API requests and responses"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from neurowave_engine.db.models import MemoryTypeEnum, CognitiveMemoryStateEnum
from uuid import UUID


class UserBase(BaseModel):
    """Base user schema"""
    external_id: str
    name: Optional[str] = None
    email: Optional[str] = None


class UserCreate(UserBase):
    """User creation schema"""
    pass


class UserResponse(UserBase):
    """User response schema"""
    id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MemoryBase(BaseModel):
    """Base memory schema"""
    memory_type: MemoryTypeEnum
    content: str
    summary: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MemoryCreate(MemoryBase):
    """Memory creation schema"""
    pass


class MemoryResponse(MemoryBase):
    """Memory response schema"""
    id: UUID
    user_id: UUID
    importance_score: float
    reinforcement_count: int
    access_count: int
    last_accessed: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ExtractedMemory(BaseModel):
    """Extracted memory from conversation"""
    memory_type: MemoryTypeEnum
    content: str
    summary: Optional[str] = None
    importance_score: float = Field(ge=0.0, le=1.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MemoryIngestRequest(BaseModel):
    """Memory ingestion request"""
    user_id: UUID
    conversation: str = Field(..., description="Raw conversation text")
    session_metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


class MemoryIngestResponse(BaseModel):
    """Memory ingestion response"""
    extracted_memories: List[ExtractedMemory]
    total_tokens_saved: int
    ingestion_latency_ms: float


class MemoryRetrievalRequest(BaseModel):
    """Memory retrieval request"""
    user_id: UUID
    query: str
    top_k: Optional[int] = 10
    memory_types: Optional[List[MemoryTypeEnum]] = None
    min_importance: Optional[float] = 0.0


class CompressedContext(BaseModel):
    """Compressed context for LLM injection"""
    user_profile: str
    relevant_memories: List[str]
    context_summary: str
    estimated_tokens: int


class MemoryRetrievalResponse(BaseModel):
    """Memory retrieval response"""
    retrieved_memories: List[MemoryResponse]
    compressed_context: CompressedContext
    retrieval_latency_ms: float
    context_token_reduction_percent: float


class MemoryReconstructRequest(BaseModel):
    """Context reconstruction request"""
    user_id: UUID
    query: str
    include_procedural: bool = True
    context_token_limit: Optional[int] = None


class MemoryReconstructResponse(BaseModel):
    """Context reconstruction response"""
    reconstructed_context: str
    source_memory_count: int
    estimated_tokens: int
    reconstruction_latency_ms: float


class BatchMemoryIngestRequest(BaseModel):
    """Batch memory ingestion"""
    memories: List[MemoryCreate]
    user_id: UUID


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    version: str
    environment: str
    timestamp: datetime


# Day 2: Cognitive Scoring Schemas

class CognitiveScoreDimensions(BaseModel):
    """Individual cognitive scoring dimensions"""
    future_utility: float = Field(..., ge=0.0, le=1.0, description="Likelihood memory matters later")
    identity_impact: float = Field(..., ge=0.0, le=1.0, description="Defines user identity")
    emotional_salience: float = Field(..., ge=0.0, le=1.0, description="Emotional significance")
    reinforcement: float = Field(..., ge=0.0, le=1.0, description="Repetition strength")
    temporal_persistence: float = Field(..., ge=0.0, le=1.0, description="Long-term usefulness")


class CognitiveAnalysisResult(BaseModel):
    """Result of cognitive analysis on a memory"""
    memory_id: UUID
    future_utility_score: float = Field(..., ge=0.0, le=1.0)
    identity_impact_score: float = Field(..., ge=0.0, le=1.0)
    emotional_salience_score: float = Field(..., ge=0.0, le=1.0)
    reinforcement_score: float = Field(..., ge=0.0, le=1.0)
    temporal_persistence_score: float = Field(..., ge=0.0, le=1.0)
    cognitive_importance_score: float = Field(..., ge=0.0, le=1.0, description="Final weighted importance")
    cognitive_state: CognitiveMemoryStateEnum
    memory_strength: float = Field(..., ge=0.0, le=1.0)
    decay_rate: float = Field(default=0.05, description="Exponential decay coefficient")
    analysis_latency_ms: float
    explanation: Optional[str] = None


class MemoryScoreRequest(BaseModel):
    """Request to analyze and score a memory"""
    user_id: UUID
    memory_id: UUID
    use_llm: bool = True  # Use LLM for analysis, fallback to heuristics


class MemoryScoreResponse(BaseModel):
    """Response with cognitive scores"""
    analysis: CognitiveAnalysisResult
    dimensions: CognitiveScoreDimensions
    updated_at: datetime


class MemoryReinforceRequest(BaseModel):
    """Request to reinforce a memory"""
    user_id: UUID
    memory_id: UUID
    reinforcement_context: Optional[str] = None  # Why is this memory being reinforced


class MemoryReinforceResponse(BaseModel):
    """Response after reinforcement"""
    memory_id: UUID
    previous_strength: float
    new_strength: float
    reinforcement_count: int
    cognitive_state: CognitiveMemoryStateEnum
    decay_rate: float
    last_reinforced_at: datetime
    reinforcement_latency_ms: float


class MemoryImportanceResponse(BaseModel):
    """Response with importance details for a specific memory"""
    memory_id: UUID
    memory_type: MemoryTypeEnum
    content_preview: str
    cognitive_state: CognitiveMemoryStateEnum
    memory_strength: float
    importance_score: float
    cognitive_scores: CognitiveScoreDimensions
    reinforcement_count: int
    retrieval_count: int
    last_accessed: Optional[datetime] = None
    last_reinforced_at: Optional[datetime] = None
    created_at: datetime
    decay_rate: float


class MemoryCognitiveStatsResponse(BaseModel):
    """Cognitive memory statistics"""
    total_memories: int
    average_importance_score: float
    average_memory_strength: float
    memory_state_distribution: Dict[str, int]  # State -> count
    memory_type_distribution: Dict[str, int]   # Type -> count
    average_reinforcement_count: float
    average_retrieval_count: float
    total_active_memories: int
    total_dormant_memories: int
    total_decaying_memories: int
    total_archived_memories: int
    importance_distribution: Dict[str, int]  # "high"/"medium"/"low" -> count
    temporal_persistence_average: float
    identity_impact_average: float
    emotional_salience_average: float


class CognitiveMemoryUpdateRequest(BaseModel):
    """Request to update cognitive properties of a memory"""
    user_id: UUID
    memory_id: UUID
    cognitive_state: Optional[CognitiveMemoryStateEnum] = None
    memory_strength: Optional[float] = Field(None, ge=0.0, le=1.0)
    decay_rate: Optional[float] = Field(None, ge=0.0, le=1.0)


class CognitiveMemoryUpdateResponse(BaseModel):
    """Response after cognitive update"""
    memory_id: UUID
    previous_state: CognitiveMemoryStateEnum
    new_state: CognitiveMemoryStateEnum
    previous_strength: float
    new_strength: float
    decay_rate: float
    updated_at: datetime
