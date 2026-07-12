"""Day 5: Predictive Recall Engine - Pydantic schemas"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID

from app.db.models import MemoryTypeEnum


class GoalDetectionRequest(BaseModel):
    """Request to infer the user's underlying goal from a query"""
    user_id: UUID
    query: str


class GoalDetectionResult(BaseModel):
    """Inferred goal for a query"""
    goal: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    alternative_goals: List[Dict[str, float]] = Field(default_factory=list)
    matched_signals: List[str] = Field(default_factory=list)


class GoalDetectionResponse(BaseModel):
    """Goal detection response"""
    result: GoalDetectionResult
    detection_latency_ms: float


class IntentClassificationRequest(BaseModel):
    """Request to classify intent(s) behind a query"""
    user_id: UUID
    query: str
    top_k: int = 3


class IntentProbability(BaseModel):
    """A single intent with its predicted probability"""
    intent: str
    probability: float = Field(..., ge=0.0, le=1.0)


class IntentClassificationResponse(BaseModel):
    """Multi-intent classification response"""
    intents: List[IntentProbability]
    primary_intent: str
    classification_latency_ms: float


class UtilityWeights(BaseModel):
    """Configurable weighting for the final utility score. Should sum to ~1.0"""
    goal_alignment: float = 0.30
    identity_alignment: float = 0.20
    concept_relevance: float = 0.20
    importance: float = 0.10
    reinforcement: float = 0.10
    confidence: float = 0.05
    recency: float = 0.05


class MemoryUtilityBreakdown(BaseModel):
    """Per-dimension utility breakdown for a single memory"""
    memory_id: UUID
    memory_type: MemoryTypeEnum
    content_preview: str
    goal_alignment: float
    identity_alignment: float
    concept_relevance: float
    importance: float
    reinforcement: float
    confidence: float
    recency: float
    memory_type_weight: float
    utility_score: float = Field(..., ge=0.0, le=1.0)
    selection_reason: str


class UtilityScoreRequest(BaseModel):
    """Request to score memories for predicted usefulness against a query"""
    user_id: UUID
    query: str
    memory_ids: Optional[List[UUID]] = None
    weights: Optional[UtilityWeights] = None


class UtilityScoreResponse(BaseModel):
    """Utility scoring response"""
    goal: GoalDetectionResult
    scores: List[MemoryUtilityBreakdown]
    scoring_latency_ms: float


class MemoryExplanation(BaseModel):
    """Explains why a specific memory was selected for context"""
    memory_id: UUID
    memory_type: MemoryTypeEnum
    content: str
    reason: str
    utility: float = Field(..., ge=0.0, le=1.0)
    rank: int


class PredictiveRecallRequest(BaseModel):
    """Request to run the full predictive recall pipeline"""
    user_id: UUID
    query: str
    token_budget: Optional[int] = None
    top_k: Optional[int] = None
    memory_types: Optional[List[MemoryTypeEnum]] = None
    weights: Optional[UtilityWeights] = None


class AssembledContext(BaseModel):
    """Final compact context ready for LLM injection"""
    context_text: str
    estimated_tokens: int
    sections: Dict[str, List[str]]


class PredictiveRecallResponse(BaseModel):
    """Full predictive recall pipeline response"""
    recall_id: UUID
    goal: GoalDetectionResult
    intents: List[IntentProbability]
    selected_memories: List[MemoryExplanation]
    assembled_context: AssembledContext
    candidate_count: int
    token_budget: int
    average_utility_score: float
    latency_breakdown_ms: Dict[str, float]
    total_latency_ms: float


class ContextAssembleRequest(BaseModel):
    """Request to assemble a compact context from a specific set of memories"""
    user_id: UUID
    query: str
    memory_ids: List[UUID]
    token_limit: Optional[int] = None


class ContextAssembleResponse(BaseModel):
    """Context assembly response"""
    assembled_context: AssembledContext
    assembly_latency_ms: float


class RetrievalExplanationResponse(BaseModel):
    """Explanation trail for a past predictive recall run"""
    recall_id: UUID
    user_id: UUID
    query: str
    goal: str
    goal_confidence: float
    intents: Dict[str, float]
    explanations: List[MemoryExplanation]
    created_at: datetime
