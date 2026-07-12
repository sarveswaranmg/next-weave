"""Day 6: Cognitive Context Composer - Pydantic schemas"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID

from app.db.models import MemoryTypeEnum
from app.schemas.predictive_recall import GoalDetectionResult, IntentProbability, UtilityWeights


class CognitiveStateSchema(BaseModel):
    """The synthesized 'Current User State' block"""
    primary_goal: str
    relevant_expertise: List[str]
    preferred_communication: List[str]
    reasoning_strategy: str
    text: str


class CompressedMemorySchema(BaseModel):
    """A single post-compression memory entry (may represent several merged memories)"""
    id: str
    memory_type: MemoryTypeEnum
    content: str
    utility_score: float
    merged: bool
    source_ids: List[str]


class ContradictionSchema(BaseModel):
    """A resolved conflict between two memories"""
    verb_bucket: str
    kept_memory_id: UUID
    superseded_memory_id: UUID
    kept_content: str
    superseded_content: str
    reason: str


class KnowledgeGapsSchema(BaseModel):
    """Knowledge gaps detected for the current query"""
    missing_topics: List[str]
    triggered_topics: List[str]
    covered_topics: List[str]


class CompressionStatsSchema(BaseModel):
    """Compression Engine output stats"""
    original_tokens: int
    compressed_tokens: int
    compression_ratio: float = Field(..., ge=0.0, le=1.0)
    duplicate_count: int
    merged_count: int


class ContextEvaluationSchema(BaseModel):
    """Context Quality Evaluator output"""
    coverage: float = Field(..., ge=0.0, le=1.0)
    redundancy: float = Field(..., ge=0.0, le=1.0)
    identity_alignment: float = Field(..., ge=0.0, le=1.0)
    goal_alignment: float = Field(..., ge=0.0, le=1.0)
    estimated_reasoning_quality: float = Field(..., ge=0.0, le=1.0)
    contradictions: int
    token_count: int
    quality_score: float = Field(..., ge=0.0, le=1.0)


class ContextComposeRequest(BaseModel):
    """Request to run the full Cognitive Context Composer pipeline"""
    user_id: UUID
    query: str
    token_budget: Optional[int] = None
    memory_types: Optional[List[MemoryTypeEnum]] = None
    weights: Optional[UtilityWeights] = None


class ContextComposeResponse(BaseModel):
    """Full CCC pipeline response"""
    snapshot_id: UUID
    goal: GoalDetectionResult
    intents: List[IntentProbability]
    state: CognitiveStateSchema
    narrative: str
    final_context: str
    compressed_memories: List[CompressedMemorySchema]
    contradictions: List[ContradictionSchema]
    knowledge_gaps: KnowledgeGapsSchema
    compression: CompressionStatsSchema
    evaluation: ContextEvaluationSchema
    candidate_count: int
    token_budget: int
    total_latency_ms: float


class ContextEvaluateRequest(BaseModel):
    """Request to evaluate the quality of a specific memory set as context"""
    user_id: UUID
    query: str
    memory_ids: List[UUID]


class ContextEvaluateResponse(BaseModel):
    """Evaluation-only response"""
    evaluation: ContextEvaluationSchema
    evaluation_latency_ms: float


class ContextCompressRequest(BaseModel):
    """Request to compress a specific memory set"""
    user_id: UUID
    query: str
    memory_ids: List[UUID]
    token_budget: Optional[int] = None


class ContextCompressResponse(BaseModel):
    """Compression-only response"""
    compressed_memories: List[CompressedMemorySchema]
    compression: CompressionStatsSchema
    compression_latency_ms: float


class ContextNarrativeRequest(BaseModel):
    """Request to generate a narrative from a specific memory set"""
    user_id: UUID
    query: str
    memory_ids: List[UUID]


class ContextNarrativeResponse(BaseModel):
    """Narrative-only response"""
    narrative: str
    state: CognitiveStateSchema
    narrative_latency_ms: float


class ContextGapsRequest(BaseModel):
    """Request to detect knowledge gaps for a query"""
    user_id: UUID
    query: str
    memory_ids: Optional[List[UUID]] = None


class ContextGapsResponse(BaseModel):
    """Knowledge gap detection response"""
    gaps: KnowledgeGapsSchema
    gap_detection_latency_ms: float


class ContextHistoryItem(BaseModel):
    """A single past ContextSnapshot"""
    snapshot_id: UUID
    query: str
    detected_goal: Optional[str] = None
    context_quality: float
    token_count: int
    compression_ratio: float
    contradiction_count: int
    missing_topics: List[str]
    created_at: datetime


class ContextHistoryResponse(BaseModel):
    """History of past context compositions for a user"""
    user_id: UUID
    snapshots: List[ContextHistoryItem]


class ContextMetricsAggregateResponse(BaseModel):
    """Aggregated CCC observability metrics for a user"""
    user_id: UUID
    snapshot_count: int
    average_quality_score: float
    average_coverage: float
    average_redundancy: float
    average_identity_alignment: float
    average_goal_alignment: float
    average_compression_ratio: float
    average_token_count: float
    average_contradiction_count: float
    average_missing_topics: float
    average_latency_ms: float
