"""Day 7: Cognitive Forgetting & Memory Evolution Engine - Pydantic schemas"""
from pydantic import BaseModel, Field, model_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID

from neurowave_engine.db.models import CognitiveMemoryStateEnum


class MergeDecision(BaseModel):
    """A DuplicateResolver merge outcome"""
    concept_id: UUID
    concept_name: str
    support_count: int
    source_memory_ids: List[UUID]


class ObsoleteDecision(BaseModel):
    """An ObsoleteMemoryDetector resolution outcome"""
    memory: str
    decision: str
    reason: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    superseded_memory_id: UUID
    winning_memory_id: UUID


class ForgettingDecision(BaseModel):
    """A ForgettingEngine decision - every evolution decision is explainable"""
    memory: str
    memory_id: UUID
    decision: str  # Remain, Weaken, Archived, Forgotten
    reason: str
    confidence: float = Field(..., ge=0.0, le=1.0)


class EntropyBreakdown(BaseModel):
    """MemoryEntropyCalculator output"""
    redundancy: float = Field(..., ge=0.0, le=1.0)
    conflicts: float = Field(..., ge=0.0, le=1.0)
    fragmentation: float = Field(..., ge=0.0, le=1.0)
    obsolete_concepts: float = Field(..., ge=0.0, le=1.0)
    duplicate_clusters: int
    conflict_count: int
    entropy_score: float = Field(..., ge=0.0, le=1.0)
    total_memories: int


class CognitiveHealthResponse(BaseModel):
    """MemoryHealthService output"""
    user_id: str
    total_memories: int
    active_memories: int
    duplicate_ratio: float
    forgotten_ratio: float
    archive_ratio: float
    average_strength: float
    average_strength_active: float
    average_decay: float
    entropy_score: float
    graph_complexity: float
    storage_growth_ratio: float
    token_efficiency: float
    state_distribution: Dict[str, int]
    cognitive_health_score: float = Field(..., ge=0.0, le=100.0)


class MemoryEvolveRequest(BaseModel):
    """Request to run a full evolution pass for a user"""
    user_id: UUID


class MemoryEvolveResponse(BaseModel):
    """Full evolution pass report"""
    user_id: UUID
    memories_evaluated: int
    decayed_count: int
    merged_clusters: int
    merge_decisions: List[MergeDecision]
    obsolete_resolved: int
    obsolete_decisions: List[ObsoleteDecision]
    forgetting_decisions: List[ForgettingDecision]
    archived_count: int
    forgotten_count: int
    entropy: EntropyBreakdown
    health: CognitiveHealthResponse
    total_latency_ms: float


class MemoryDecayRequest(BaseModel):
    """Request to apply decay evaluation to a user's memories"""
    user_id: UUID
    memory_ids: Optional[List[UUID]] = None  # If omitted, decays all active memories


class DecayResult(BaseModel):
    """Per-memory decay outcome"""
    memory_id: UUID
    previous_strength: float
    new_strength: float
    effective_decay_rate: float
    in_concept: bool
    in_identity: bool


class MemoryDecayResponse(BaseModel):
    """Decay evaluation response"""
    results: List[DecayResult]
    decay_latency_ms: float


class MemoryArchiveRequest(BaseModel):
    """Request to manually archive a memory"""
    user_id: UUID
    memory_id: UUID
    reason: str = Field(..., min_length=1)


class MemoryArchiveResponse(BaseModel):
    """Archive response"""
    memory_id: UUID
    success: bool
    old_state: CognitiveMemoryStateEnum
    new_state: CognitiveMemoryStateEnum
    reason: str


class MemoryReviveRequest(BaseModel):
    """Request to revive memories - either a specific memory, or automatically
    via a query that may make decayed/archived memories relevant again"""
    user_id: UUID
    memory_id: Optional[UUID] = None
    query: Optional[str] = None

    @model_validator(mode="after")
    def _require_target(self):
        if not self.memory_id and not self.query:
            raise ValueError("Either memory_id or query must be provided")
        return self


class RevivalResult(BaseModel):
    """A single memory revival outcome"""
    memory_id: UUID
    content: str
    old_state: CognitiveMemoryStateEnum
    new_state: CognitiveMemoryStateEnum
    old_strength: float
    new_strength: float
    revival_count: int
    reason: str


class MemoryReviveResponse(BaseModel):
    """Revival response"""
    revivals: List[RevivalResult]
    revive_latency_ms: float


class MemoryLifecycleResponse(BaseModel):
    """Lifecycle status for a single memory"""
    memory_id: UUID
    memory_type: str
    cognitive_state: CognitiveMemoryStateEnum
    memory_strength: float
    decay_rate: float
    entropy_score: float
    reinforcement_count: int
    retrieval_count: int
    revival_count: int
    last_accessed: Optional[datetime] = None
    last_reinforced_at: Optional[datetime] = None
    last_decay_at: Optional[datetime] = None
    archive_reason: Optional[str] = None
    forget_reason: Optional[str] = None
    created_at: datetime


class MemoryEventItem(BaseModel):
    """A single memory lifecycle audit event"""
    id: UUID
    memory_id: UUID
    event_type: str
    old_state: Optional[str] = None
    new_state: Optional[str] = None
    old_strength: Optional[float] = None
    new_strength: Optional[float] = None
    reason: Optional[str] = None
    confidence: float
    timestamp: datetime


class MemoryEventsResponse(BaseModel):
    """Memory event history"""
    user_id: UUID
    events: List[MemoryEventItem]


class MemoryEntropyResponse(BaseModel):
    """Store-wide entropy response"""
    user_id: UUID
    entropy: EntropyBreakdown
