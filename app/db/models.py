"""SQLAlchemy models for NeuroWeave"""
from sqlalchemy import Column, String, Float, DateTime, Integer, Text, Index, ForeignKey, Enum, JSON
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship
from sqlalchemy.types import CHAR, TypeDecorator
from datetime import datetime
import enum
import uuid

from app.db.database import Base


class GUID(TypeDecorator):
    """Platform-independent UUID type.

    Uses PostgreSQL's native UUID type when available, otherwise stores as a
    stringified hex CHAR(32) (e.g. for SQLite, used in tests/local dev).
    """

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(32))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return str(value)
        if not isinstance(value, uuid.UUID):
            return "%.32x" % uuid.UUID(value).int
        return "%.32x" % value.int

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if not isinstance(value, uuid.UUID):
            value = uuid.UUID(value)
        return value


class MemoryTypeEnum(str, enum.Enum):
    """Memory type enumeration"""
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    IDENTITY = "identity"
    PROCEDURAL = "procedural"
    CONCEPT = "concept"  # Day 3: Generalized semantic concepts


class CognitiveMemoryStateEnum(str, enum.Enum):
    """Cognitive memory lifecycle state enumeration

    Day 7 canonical order: ACTIVE -> REINFORCED -> SEMANTIC_CANDIDATE ("SEMANTIC"
    in the Day 7 spec) -> DORMANT -> ARCHIVED -> FORGOTTEN. DECAYING is an
    additional intermediate weakening state (introduced in Day 2) reachable
    from several states; kept for backwards compatibility with existing
    transitions rather than collapsed into the spec's simpler list.
    """
    ACTIVE = "active"                          # Highly relevant + frequently accessed
    REINFORCED = "reinforced"                  # Repeated over time
    SEMANTIC_CANDIDATE = "semantic_candidate"  # Ready for abstraction/consolidation
    DORMANT = "dormant"                        # Rarely used but retained
    DECAYING = "decaying"                      # Low-value memory losing strength
    ARCHIVED = "archived"                      # Compressed low-priority memory
    FORGOTTEN = "forgotten"                    # Day 7: soft-forgotten - retained but never retrieved


class User(Base):
    """User model"""
    __tablename__ = "users"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    external_id = Column(String(255), unique=True, nullable=False)
    name = Column(String(255))
    email = Column(String(255), unique=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    memories = relationship("Memory", back_populates="user", cascade="all, delete-orphan")
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_user_external_id", "external_id"),
    )


class Session(Base):
    """Session model - tracks user interactions"""
    __tablename__ = "sessions"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID(), ForeignKey("users.id"), nullable=False)
    session_token = Column(String(255), unique=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime)
    extra_metadata = Column("metadata", JSON, default={})

    # Relationships
    user = relationship("User", back_populates="sessions")

    __table_args__ = (
        Index("idx_session_user_id", "user_id"),
        Index("idx_session_token", "session_token"),
    )


class Memory(Base):
    """Core memory model with cognitive scoring dimensions"""
    __tablename__ = "memories"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID(), ForeignKey("users.id"), nullable=False)
    memory_type = Column(Enum(MemoryTypeEnum), nullable=False)
    content = Column(Text, nullable=False)
    summary = Column(Text)
    
    # Original importance score (deprecated - use cognitive scores instead)
    importance_score = Column(Float, default=0.0)  # 0.0 to 1.0
    
    # New cognitive scoring dimensions (Day 2)
    future_utility_score = Column(Float, default=0.5)      # 0.0-1.0: likelihood to matter later
    identity_impact_score = Column(Float, default=0.5)     # 0.0-1.0: defines user identity
    emotional_salience_score = Column(Float, default=0.5)  # 0.0-1.0: emotional significance
    reinforcement_score = Column(Float, default=0.5)       # 0.0-1.0: repetition count
    temporal_persistence_score = Column(Float, default=0.5) # 0.0-1.0: long-term usefulness
    
    # Cognitive memory lifecycle
    cognitive_state = Column(Enum(CognitiveMemoryStateEnum), default=CognitiveMemoryStateEnum.ACTIVE)
    memory_strength = Column(Float, default=0.5)  # 0.0-1.0: current strength/confidence
    decay_rate = Column(Float, default=0.05)      # exponential decay coefficient
    
    # Reinforcement tracking
    retrieval_count = Column(Integer, default=0)
    last_reinforced_at = Column(DateTime)
    
    embedding = Column(String(255))  # Will store pgvector reference
    extra_metadata = Column("metadata", JSON, default={})
    reinforcement_count = Column(Integer, default=0)
    access_count = Column(Integer, default=0)
    last_accessed = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Day 5: Predictive Recall Engine - utility prediction fields
    goal_alignment_score = Column(Float, default=0.0)     # 0.0-1.0: alignment with detected goal
    utility_score = Column(Float, default=0.0)            # 0.0-1.0: final predicted utility for last query
    selection_reason = Column(Text)                       # Human-readable explanation for selection
    prediction_confidence = Column(Float, default=0.0)    # 0.0-1.0: confidence in the utility prediction
    retrieval_rank = Column(Integer)                       # Rank position in most recent predictive recall
    last_prediction_time = Column(DateTime)                # When utility was last predicted

    # Day 7: Cognitive Forgetting & Memory Evolution Engine
    # (kept as columns on Memory rather than a separate `memory_lifecycle`
    # table since these participate in every retrieval's WHERE clause -
    # same convention as the Day 2 cognitive fields above)
    entropy_score = Column(Float, default=0.0)      # 0.0-1.0: local contribution to store disorder
    last_decay_at = Column(DateTime)                 # When decay was last evaluated for this memory
    archive_reason = Column(Text)                     # Why this memory was archived, if applicable
    forget_reason = Column(Text)                       # Why this memory was soft-forgotten, if applicable
    revival_count = Column(Integer, default=0)          # Times this memory was revived after decay

    # Relationships
    user = relationship("User", back_populates="memories")
    embeddings = relationship("MemoryEmbedding", back_populates="memory", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_memory_user_id", "user_id"),
        Index("idx_memory_type", "memory_type"),
        Index("idx_memory_importance", "importance_score"),
        Index("idx_memory_cognitive_state", "cognitive_state"),
        Index("idx_memory_memory_strength", "memory_strength"),
        Index("idx_memory_created_at", "created_at"),
        Index("idx_memory_last_accessed", "last_accessed"),
        Index("idx_memory_last_reinforced", "last_reinforced_at"),
        Index("idx_memory_utility_score", "utility_score"),
        Index("idx_memory_retrieval_rank", "retrieval_rank"),
        Index("idx_memory_entropy_score", "entropy_score"),
        Index("idx_memory_last_decay_at", "last_decay_at"),
    )


class MemoryEmbedding(Base):
    """Memory embeddings for vector similarity search using pgvector"""
    __tablename__ = "memory_embeddings"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    memory_id = Column(GUID(), ForeignKey("memories.id"), nullable=False)
    embedding = Column(String)  # pgvector type - stores as string in JSON
    model = Column(String(100), default="text-embedding-3-small")
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    memory = relationship("Memory", back_populates="embeddings")

    __table_args__ = (
        Index("idx_embedding_memory_id", "memory_id"),
        Index("idx_embedding_model", "model"),
    )


class RetrievalLog(Base):
    """Tracks memory retrieval operations for analytics"""
    __tablename__ = "retrieval_logs"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID(), ForeignKey("users.id"), nullable=False)
    query = Column(Text)
    retrieved_memory_ids = Column(JSON)  # List of memory IDs retrieved
    retrieval_latency_ms = Column(Float)
    context_token_count = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_retrieval_user_id", "user_id"),
        Index("idx_retrieval_created_at", "created_at"),
    )


class MemoryConsolidation(Base):
    """Tracks consolidated memories for future semantic consolidation"""
    __tablename__ = "memory_consolidations"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID(), ForeignKey("users.id"), nullable=False)
    source_memory_ids = Column(JSON)  # List of original memory IDs
    consolidated_memory_id = Column(GUID(), ForeignKey("memories.id"))
    consolidation_score = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_consolidation_user_id", "user_id"),
        Index("idx_consolidation_memory_id", "consolidated_memory_id"),
    )


# ============================================================================
# DAY 3: SEMANTIC CONSOLIDATION ENGINE - NEW MODELS
# ============================================================================

class ConceptMemory(Base):
    """
    Semantic concepts extracted from multiple episodic memories.
    
    Represents generalized knowledge that consolidates multiple experiences.
    Example: "user_prefers_concise_communication" from 4+ related memories.
    """
    __tablename__ = "concept_memories"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID(), ForeignKey("users.id"), nullable=False)
    concept_name = Column(String(255), nullable=False)
    description = Column(Text)
    
    # Semantic properties
    confidence = Column(Float, default=0.0)  # 0.0-1.0: how confident is this concept
    support_count = Column(Integer, default=1)  # Number of supporting memories
    supporting_memory_ids = Column(JSON, default=[])  # List of source memory UUIDs
    
    # Graph properties
    related_concept_ids = Column(JSON, default=[])  # Connected concepts
    is_derived_from = Column(String(255))  # Parent concept if applicable
    
    # Metadata
    last_reinforced_at = Column(DateTime)
    reinforcement_count = Column(Integer, default=0)
    embedding = Column(String(255))  # Vector representation of concept
    extra_metadata = Column("metadata", JSON, default={})
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_concept_user_id", "user_id"),
        Index("idx_concept_name", "concept_name"),
        Index("idx_concept_confidence", "confidence"),
        Index("idx_concept_created_at", "created_at"),
    )


class MemoryCluster(Base):
    """
    Temporary groupings of similar memories for clustering analysis.
    
    Represents intermediate stage in consolidation pipeline.
    Used for pattern detection before concept extraction.
    """
    __tablename__ = "memory_clusters"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID(), ForeignKey("users.id"), nullable=False)
    cluster_id = Column(String(255), nullable=False)  # Unique cluster identifier
    theme = Column(String(255))  # Inferred theme/topic of cluster
    
    # Cluster composition
    memory_ids = Column(JSON, default=[])  # Member memory UUIDs
    member_count = Column(Integer, default=0)
    
    # Cluster metrics
    avg_similarity = Column(Float, default=0.0)  # Average pairwise similarity
    confidence = Column(Float, default=0.0)  # Cluster quality metric
    centroid_embedding = Column(String(255))  # Vector representation
    
    # Lifecycle
    consolidation_status = Column(String(50), default="pending")  # pending, processing, completed
    concept_generated = Column(String(255))  # Reference to generated concept, if any
    
    extra_metadata = Column("metadata", JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_cluster_user_id", "user_id"),
        Index("idx_cluster_theme", "theme"),
        Index("idx_cluster_status", "consolidation_status"),
        Index("idx_cluster_created_at", "created_at"),
    )


class ConceptRelationship(Base):
    """
    Semantic knowledge graph edges connecting concepts.
    
    Represents relationships between concepts in the semantic cortex.
    Enables concept propagation and reinforcement through the graph.
    """
    __tablename__ = "concept_relationships"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID(), ForeignKey("users.id"), nullable=False)
    
    source_concept_id = Column(GUID(), ForeignKey("concept_memories.id"), nullable=False)
    target_concept_id = Column(GUID(), ForeignKey("concept_memories.id"), nullable=False)
    
    # Relationship type
    relationship_type = Column(String(50), nullable=False)  # supports, reinforces, related_to, derived_from
    strength = Column(Float, default=0.5)  # 0.0-1.0: connection strength
    
    # Lifecycle
    reinforcement_count = Column(Integer, default=1)
    last_reinforced_at = Column(DateTime, default=datetime.utcnow)
    
    extra_metadata = Column("metadata", JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_relationship_user_id", "user_id"),
        Index("idx_relationship_source", "source_concept_id"),
        Index("idx_relationship_target", "target_concept_id"),
        Index("idx_relationship_type", "relationship_type"),
        Index("idx_relationship_strength", "strength"),
    )


class ConsolidationMetrics(Base):
    """
    Observability metrics for the consolidation pipeline.
    
    Tracks performance and effectiveness of semantic consolidation.
    """
    __tablename__ = "consolidation_metrics"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID(), ForeignKey("users.id"), nullable=False)
    
    # Consolidation run metadata
    consolidation_run_id = Column(String(255))  # Identifier for this consolidation run
    consolidation_timestamp = Column(DateTime, default=datetime.utcnow)
    
    # Memory metrics
    total_memories = Column(Integer, default=0)  # Total memories processed
    episodic_memories = Column(Integer, default=0)  # Count by type
    semantic_memories = Column(Integer, default=0)
    identity_memories = Column(Integer, default=0)
    procedural_memories = Column(Integer, default=0)
    
    # Clustering metrics
    cluster_count = Column(Integer, default=0)  # Number of clusters created
    avg_cluster_size = Column(Float, default=0.0)
    
    # Concept metrics
    concept_count = Column(Integer, default=0)  # Total concepts created
    new_concepts_created = Column(Integer, default=0)  # New in this run
    concepts_reinforced = Column(Integer, default=0)  # Updated/reinforced
    
    # Graph metrics
    total_relationships = Column(Integer, default=0)
    avg_concept_degree = Column(Float, default=0.0)  # Average connections per concept
    
    # Compression metrics
    memory_reduction_percentage = Column(Float, default=0.0)  # (concepts/memories)*100 inverted
    compression_ratio = Column(Float, default=0.0)  # memories/concepts
    token_reduction = Column(Integer, default=0)  # Estimated tokens saved
    
    # Performance metrics
    processing_time_ms = Column(Float, default=0.0)
    
    # Quality metrics
    avg_concept_confidence = Column(Float, default=0.0)
    min_cluster_similarity = Column(Float, default=0.0)
    max_cluster_similarity = Column(Float, default=0.0)
    
    extra_metadata = Column("metadata", JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_metrics_user_id", "user_id"),
        Index("idx_metrics_timestamp", "consolidation_timestamp"),
        Index("idx_metrics_run_id", "consolidation_run_id"),
    )


# ============================================================================
# DAY 4: IDENTITY GRAPH ENGINE - NEW MODELS
# ============================================================================

class IdentityNode(Base):
    """
    Identity trait nodes in the user's cognitive profile.
    
    Represents individual traits, goals, interests, values, behaviors, skills.
    Each node has confidence score that evolves as evidence accumulates.
    
    Node types:
    - goal: Career/personal goals (e.g., "Become Staff Engineer")
    - interest: Areas of interest (e.g., "Distributed Systems")
    - communication: Communication style (e.g., "concise", "technical")
    - behavior: Behavioral traits (e.g., "high_curiosity", "ambitious")
    - value: Core values (e.g., "continuous_learning")
    - skill: Technical skills (e.g., "backend_engineering")
    """
    __tablename__ = "identity_nodes"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID(), ForeignKey("users.id"), nullable=False)
    
    # Node identity
    node_type = Column(String(50), nullable=False)  # goal, interest, communication, behavior, value, skill
    node_value = Column(String(255), nullable=False)  # The trait itself (e.g., "ambitious")
    
    # Confidence and evidence
    confidence = Column(Float, default=0.0)  # 0.0-1.0: how confident is this trait
    evidence_count = Column(Integer, default=1)  # Number of times reinforced
    supporting_memory_ids = Column(JSON, default=[])  # Source memories
    supporting_concept_ids = Column(JSON, default=[])  # Source concepts
    
    # Progression tracking (for skills)
    progression_level = Column(String(50))  # novice, intermediate, advanced, expert
    progression_score = Column(Float, default=0.0)  # 0.0-1.0: skill level
    
    # Lifecycle
    last_reinforced_at = Column(DateTime)
    reinforcement_count = Column(Integer, default=0)  # How many times reinforced
    decay_rate = Column(Float, default=0.02)  # Confidence decay per day
    
    # Graph properties
    related_node_ids = Column(JSON, default=[])  # Connected identity traits
    importance = Column(Float, default=0.5)  # 0.0-1.0: importance in overall identity
    
    # Metadata
    embedding = Column(String(255))  # Vector representation
    extra_metadata = Column("metadata", JSON, default={})
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_identity_node_user_id", "user_id"),
        Index("idx_identity_node_type", "node_type"),
        Index("idx_identity_node_value", "node_value"),
        Index("idx_identity_node_confidence", "confidence"),
        Index("idx_identity_node_importance", "importance"),
        Index("idx_identity_node_created_at", "created_at"),
    )


class IdentityRelationship(Base):
    """
    Edges in the identity graph connecting related traits.
    
    Represents relationships between identity traits (e.g., goals, interests).
    Enables:
    - Goal propagation (achieving goal A supports goal B)
    - Interest reinforcement (interest in X reinforces interest in Y)
    - Value alignment checking (values support/conflict with traits)
    
    Relationship types:
    - related_to: Traits that often co-occur
    - reinforces: Trait A strengthens trait B
    - derived_from: Trait B is derived from trait A
    - influences: Trait A influences trait B
    - conflicts: Trait A conflicts with trait B
    """
    __tablename__ = "identity_relationships"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID(), ForeignKey("users.id"), nullable=False)
    
    source_node_id = Column(GUID(), ForeignKey("identity_nodes.id"), nullable=False)
    target_node_id = Column(GUID(), ForeignKey("identity_nodes.id"), nullable=False)
    
    # Relationship properties
    relationship_type = Column(String(50), nullable=False)  # related_to, reinforces, derived_from, influences, conflicts
    strength = Column(Float, default=0.5)  # 0.0-1.0: relationship strength
    
    # Evidence
    reinforcement_count = Column(Integer, default=1)
    last_reinforced_at = Column(DateTime, default=datetime.utcnow)
    
    # Metadata
    extra_metadata = Column("metadata", JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_identity_rel_user_id", "user_id"),
        Index("idx_identity_rel_source", "source_node_id"),
        Index("idx_identity_rel_target", "target_node_id"),
        Index("idx_identity_rel_type", "relationship_type"),
        Index("idx_identity_rel_strength", "strength"),
    )


class IdentityHistory(Base):
    """
    Historical tracking of identity trait evolution.
    
    Records how user identity changes over time:
    - Traits that increase in confidence
    - Traits that disappear
    - New traits that emerge
    - Skills that progress
    
    Enables:
    - Observing identity trajectory
    - Detecting pivots in interests/goals
    - Understanding user evolution
    """
    __tablename__ = "identity_history"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID(), ForeignKey("users.id"), nullable=False)
    
    node_id = Column(GUID(), ForeignKey("identity_nodes.id"), nullable=False)
    
    # Trait information
    node_type = Column(String(50), nullable=False)  # goal, interest, etc.
    node_value = Column(String(255), nullable=False)  # The trait value
    
    # Change tracking
    old_confidence = Column(Float)  # Previous confidence value
    new_confidence = Column(Float)  # New confidence value
    confidence_delta = Column(Float)  # Change amount
    
    # Change context
    change_reason = Column(String(255))  # Why it changed (e.g., "reinforced", "decay", "concept_update")
    triggering_memory_ids = Column(JSON, default=[])  # Memories that caused change
    triggering_concept_ids = Column(JSON, default=[])  # Concepts that caused change
    
    # Event metadata
    event_type = Column(String(50))  # created, reinforced, declined, resolved, emerged
    
    extra_metadata = Column("metadata", JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_identity_history_user_id", "user_id"),
        Index("idx_identity_history_node_id", "node_id"),
        Index("idx_identity_history_created_at", "created_at"),
        Index("idx_identity_history_event_type", "event_type"),
    )


# ============================================================================
# DAY 5: PREDICTIVE RECALL ENGINE - NEW MODELS
# ============================================================================

class PredictiveRecallLog(Base):
    """
    Records a single predictive recall pipeline run.

    Captures the full decision trail (goal, intents, selected memories with
    per-memory utility explanations) so retrieval decisions can be audited
    via GET /retrieval/explanation, and aggregated for observability.
    """
    __tablename__ = "predictive_recall_logs"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID(), ForeignKey("users.id"), nullable=False)

    query = Column(Text, nullable=False)

    # Goal / intent detection results
    detected_goal = Column(String(100))
    goal_confidence = Column(Float, default=0.0)
    intents = Column(JSON, default={})  # {intent: probability}

    # Selection results
    candidate_count = Column(Integer, default=0)      # Memories considered
    selected_memory_ids = Column(JSON, default=[])    # Final selected memory UUIDs (as strings)
    explanations = Column(JSON, default=[])           # [{memory_id, reason, utility, rank}, ...]

    token_budget = Column(Integer)
    estimated_tokens = Column(Integer)
    average_utility_score = Column(Float, default=0.0)

    # Per-stage latency breakdown (ms)
    goal_detection_latency_ms = Column(Float, default=0.0)
    intent_classification_latency_ms = Column(Float, default=0.0)
    candidate_retrieval_latency_ms = Column(Float, default=0.0)
    utility_prediction_latency_ms = Column(Float, default=0.0)
    ranking_latency_ms = Column(Float, default=0.0)
    token_optimization_latency_ms = Column(Float, default=0.0)
    context_assembly_latency_ms = Column(Float, default=0.0)
    total_latency_ms = Column(Float, default=0.0)

    extra_metadata = Column("metadata", JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_recall_log_user_id", "user_id"),
        Index("idx_recall_log_created_at", "created_at"),
        Index("idx_recall_log_goal", "detected_goal"),
    )


# ============================================================================
# DAY 6: COGNITIVE CONTEXT COMPOSER - NEW MODELS
# ============================================================================

class ContextSnapshot(Base):
    """
    Records a single Cognitive Context Composer run: the final reconstructed
    cognitive state sent in place of raw memories, plus its quality and
    compression stats. This is the audit trail behind GET /context/history.
    """
    __tablename__ = "context_snapshots"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID(), ForeignKey("users.id"), nullable=False)

    query = Column(Text, nullable=False)
    detected_goal = Column(String(100))
    generated_context = Column(Text, nullable=False)   # Final composed narrative + state text
    narrative = Column(Text)                            # Narrative section alone

    context_quality = Column(Float, default=0.0)        # 0.0-1.0 overall quality_score
    token_count = Column(Integer, default=0)
    original_token_count = Column(Integer, default=0)   # Pre-compression token estimate
    compression_ratio = Column(Float, default=0.0)       # 1 - (token_count / original_token_count)

    contradiction_count = Column(Integer, default=0)
    missing_topics = Column(JSON, default=[])            # Knowledge gaps detected
    source_memory_ids = Column(JSON, default=[])         # Memories that fed the composition

    total_latency_ms = Column(Float, default=0.0)
    extra_metadata = Column("metadata", JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_context_snapshot_user_id", "user_id"),
        Index("idx_context_snapshot_created_at", "created_at"),
        Index("idx_context_snapshot_goal", "detected_goal"),
        Index("idx_context_snapshot_quality", "context_quality"),
    )


class ContextMetrics(Base):
    """
    Quality metrics for a single ContextSnapshot.

    Kept as a separate table (rather than columns on ContextSnapshot) so the
    scoring rubric can evolve independently of the snapshot record itself.
    """
    __tablename__ = "context_metrics"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    snapshot_id = Column(GUID(), ForeignKey("context_snapshots.id"), nullable=False)

    coverage = Column(Float, default=0.0)              # Fraction of required knowledge represented
    redundancy = Column(Float, default=0.0)            # Duplicate/near-duplicate ratio pre-compression
    identity_alignment = Column(Float, default=0.0)
    goal_alignment = Column(Float, default=0.0)
    quality_score = Column(Float, default=0.0)          # Composite of the above

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_context_metrics_snapshot_id", "snapshot_id"),
    )


# ============================================================================
# DAY 7: COGNITIVE FORGETTING & MEMORY EVOLUTION ENGINE - NEW MODELS
# ============================================================================

class MemoryEvent(Base):
    """
    Audit trail for every memory lifecycle transition.

    Every decay, reinforcement, merge, archive, forget, or revival decision
    is logged here so evolution decisions stay explainable and reversible
    in principle (soft forgetting, never hard deletion). Mirrors the
    Day 4 IdentityHistory pattern applied to raw memories.
    """
    __tablename__ = "memory_events"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    memory_id = Column(GUID(), ForeignKey("memories.id"), nullable=False)
    user_id = Column(GUID(), ForeignKey("users.id"), nullable=False)

    event_type = Column(String(50), nullable=False)  # decay, reinforce, revive, merge, archive, forget
    old_state = Column(String(50))
    new_state = Column(String(50))
    old_strength = Column(Float)
    new_strength = Column(Float)
    reason = Column(Text)
    confidence = Column(Float, default=0.0)  # Confidence in this evolution decision

    extra_metadata = Column("metadata", JSON, default={})
    timestamp = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_memory_event_memory_id", "memory_id"),
        Index("idx_memory_event_user_id", "user_id"),
        Index("idx_memory_event_type", "event_type"),
        Index("idx_memory_event_timestamp", "timestamp"),
    )


# ============================================================================
# DAY 8: OFFLINE COGNITIVE CONSOLIDATION ENGINE ("DREAM MODE") - NEW MODELS
# ============================================================================

class DreamSessionStatusEnum(str, enum.Enum):
    """Lifecycle of a single dream (offline consolidation) session"""
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class DreamSession(Base):
    """
    A single offline consolidation pass for a user: replay, pattern
    discovery, concept refinement, identity evolution, graph optimization,
    knowledge synthesis, compression, and health evaluation. The audit
    record behind GET /dream/status and GET /dream/history.
    """
    __tablename__ = "dream_sessions"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID(), ForeignKey("users.id"), nullable=False)

    status = Column(Enum(DreamSessionStatusEnum), default=DreamSessionStatusEnum.RUNNING)
    trigger = Column(String(50), default="manual")  # manual, hourly, daily, weekly, idle

    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime)

    memories_replayed = Column(Integer, default=0)
    memories_processed = Column(Integer, default=0)
    patterns_discovered = Column(Integer, default=0)
    concepts_created = Column(Integer, default=0)
    concepts_refined = Column(Integer, default=0)
    identity_updates = Column(Integer, default=0)
    contradictions_resolved = Column(Integer, default=0)
    graph_nodes_removed = Column(Integer, default=0)
    graph_edges_strengthened = Column(Integer, default=0)
    knowledge_synthesized = Column(Integer, default=0)

    compression_ratio = Column(Float, default=0.0)
    health_score_before = Column(Float)
    health_score_after = Column(Float)

    stage_latency_ms = Column(JSON, default={})  # {"replay": 12.3, "pattern_discovery": 4.1, ...}
    total_latency_ms = Column(Float, default=0.0)

    error = Column(Text)
    extra_metadata = Column("metadata", JSON, default={})

    __table_args__ = (
        Index("idx_dream_session_user_id", "user_id"),
        Index("idx_dream_session_status", "status"),
        Index("idx_dream_session_started_at", "started_at"),
    )


class KnowledgeSynthesis(Base):
    """
    A new higher-order concept synthesized from several existing concepts
    during a dream session — knowledge NeuroWeave generated on its own,
    without direct user input (e.g. "Distributed Systems" + "Rust" +
    "Backend" + "Caching" + "Scalability" -> "High Performance Distributed
    Backend Engineering").
    """
    __tablename__ = "knowledge_synthesis"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID(), ForeignKey("users.id"), nullable=False)
    dream_session_id = Column(GUID(), ForeignKey("dream_sessions.id"), nullable=True)

    source_concept_ids = Column(JSON, default=[])  # List of ConceptMemory UUIDs (as strings)
    source_concept_names = Column(JSON, default=[])
    new_concept_id = Column(GUID(), ForeignKey("concept_memories.id"), nullable=True)
    new_concept = Column(String(255), nullable=False)
    reasoning = Column(Text)

    confidence = Column(Float, default=0.0)
    generated_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_knowledge_synthesis_user_id", "user_id"),
        Index("idx_knowledge_synthesis_session_id", "dream_session_id"),
        Index("idx_knowledge_synthesis_generated_at", "generated_at"),
    )


class IdentityEvolutionEvent(Base):
    """
    Records a shift in the user's inferred identity discovered during
    offline consolidation (e.g. "Interested in React" -> "Systems
    Engineer" once Rust/distributed-systems/databases evidence
    accumulates). History is always preserved — this is an append-only
    log, never an overwrite of the prior IdentityNode.
    """
    __tablename__ = "identity_evolution_events"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID(), ForeignKey("users.id"), nullable=False)
    dream_session_id = Column(GUID(), ForeignKey("dream_sessions.id"), nullable=True)

    old_identity = Column(String(255))
    new_identity = Column(String(255), nullable=False)
    reason = Column(Text)
    evidence_concept_ids = Column(JSON, default=[])
    confidence = Column(Float, default=0.0)

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_identity_evolution_user_id", "user_id"),
        Index("idx_identity_evolution_session_id", "dream_session_id"),
        Index("idx_identity_evolution_created_at", "created_at"),
    )


# ============================================================================
# DAY 9: WORLD MODEL ENGINE - NEW MODELS
# ============================================================================

class WorldEntityTypeEnum(str, enum.Enum):
    """Kinds of real-world entities the world model can represent"""
    PERSON = "person"
    PROJECT = "project"
    COMPANY = "company"
    GOAL = "goal"
    TECHNOLOGY = "technology"
    FILE = "file"
    REPOSITORY = "repository"
    TASK = "task"
    MEETING = "meeting"
    IDEA = "idea"
    DOCUMENT = "document"
    API = "api"
    LOCATION = "location"
    DEVICE = "device"
    SERVICE = "service"


class ProjectStatusEnum(str, enum.Enum):
    """Lifecycle status of a tracked project"""
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class WorldEntity(Base):
    """
    A node in the World Model Graph: a person, project, company, goal,
    technology, file, repository, task, meeting, idea, document, API,
    location, device, or service that exists in the user's world -
    understanding, not just recollection.
    """
    __tablename__ = "world_entities"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID(), ForeignKey("users.id"), nullable=False)

    entity_type = Column(Enum(WorldEntityTypeEnum), nullable=False)
    entity_name = Column(String(255), nullable=False)
    description = Column(Text)

    confidence = Column(Float, default=0.5)      # 0.0-1.0: confidence this entity genuinely exists/matters
    mention_count = Column(Integer, default=1)
    attributes = Column(JSON, default={})         # Type-specific structured attributes
    supporting_memory_ids = Column(JSON, default=[])

    first_seen_at = Column(DateTime, default=datetime.utcnow)
    last_seen_at = Column(DateTime, default=datetime.utcnow)

    extra_metadata = Column("metadata", JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_world_entity_user_id", "user_id"),
        Index("idx_world_entity_type", "entity_type"),
        Index("idx_world_entity_name", "entity_name"),
        Index("idx_world_entity_confidence", "confidence"),
        Index("idx_world_entity_last_seen", "last_seen_at"),
    )


class WorldRelationship(Base):
    """
    A weighted, typed edge in the World Model Graph between two entities
    (e.g. NeuroWeave -[uses]-> PostgreSQL -[stores]-> Memory Objects).
    Relationship confidence/strength grows with repeated evidence.
    """
    __tablename__ = "world_relationships"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID(), ForeignKey("users.id"), nullable=False)

    source_entity_id = Column(GUID(), ForeignKey("world_entities.id"), nullable=False)
    target_entity_id = Column(GUID(), ForeignKey("world_entities.id"), nullable=False)

    relationship_type = Column(String(50), nullable=False)  # uses, stores, depends_on, migrates_to, works_on, deployed_to, part_of, blocks, related_to
    strength = Column(Float, default=0.5)   # 0.0-1.0: weighted edge confidence
    evidence_count = Column(Integer, default=1)
    supporting_memory_ids = Column(JSON, default=[])

    extra_metadata = Column("metadata", JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_world_rel_user_id", "user_id"),
        Index("idx_world_rel_source", "source_entity_id"),
        Index("idx_world_rel_target", "target_entity_id"),
        Index("idx_world_rel_type", "relationship_type"),
        Index("idx_world_rel_strength", "strength"),
    )


class Project(Base):
    """
    A first-class project: goals, architecture, progress, dependencies,
    roadmap, decisions, and open questions - not just a memory mentioning
    a project name.
    """
    __tablename__ = "projects"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID(), ForeignKey("users.id"), nullable=False)
    world_entity_id = Column(GUID(), ForeignKey("world_entities.id"), nullable=True)

    project_name = Column(String(255), nullable=False)
    status = Column(Enum(ProjectStatusEnum), default=ProjectStatusEnum.ACTIVE)
    current_phase = Column(String(255))
    progress = Column(Float, default=0.0)   # 0.0-1.0 estimated completion
    next_step = Column(Text)

    goals = Column(JSON, default=[])
    architecture_notes = Column(Text)
    tech_stack = Column(JSON, default=[])          # List of world_entity ids/names
    dependencies = Column(JSON, default=[])
    roadmap = Column(JSON, default=[])
    open_questions = Column(JSON, default=[])

    extra_metadata = Column("metadata", JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_project_user_id", "user_id"),
        Index("idx_project_name", "project_name"),
        Index("idx_project_status", "status"),
        Index("idx_project_updated_at", "updated_at"),
    )


class ArchitecturalDecision(Base):
    """
    A tracked architectural decision: what was decided, why, and its
    impact - so later retrieval can explain *why* something was decided,
    not just what. Never overwritten; superseding decisions are new rows.
    """
    __tablename__ = "architectural_decisions"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID(), ForeignKey("users.id"), nullable=False)
    project_id = Column(GUID(), ForeignKey("projects.id"), nullable=True)

    decision = Column(Text, nullable=False)
    reason = Column(Text)
    impact = Column(Text)
    status = Column(String(50), default="decided")  # decided, postponed, reversed, superseded
    confidence = Column(Float, default=0.7)

    supporting_memory_ids = Column(JSON, default=[])
    extra_metadata = Column("metadata", JSON, default={})
    timestamp = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_decision_user_id", "user_id"),
        Index("idx_decision_project_id", "project_id"),
        Index("idx_decision_timestamp", "timestamp"),
        Index("idx_decision_status", "status"),
    )


# ============================================================================
# DAY 10: COGNITIVE RUNTIME PLATFORM, SDK & BENCHMARK SUITE - NEW MODELS
# ============================================================================

class BenchmarkRun(Base):
    """
    One run of one strategy (no_memory / raw_history / neuroweave / ...)
    against one benchmark dataset - the record NeuroBench compares across
    strategies and over time to catch regressions.
    """
    __tablename__ = "benchmark_runs"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID(), ForeignKey("users.id"), nullable=True)

    strategy = Column(String(100), nullable=False)   # no_memory, raw_history, neuroweave, mem0, zep, ...
    model = Column(String(100))
    dataset = Column(String(255), nullable=False)     # Dataset name/identifier

    latency_ms = Column(Float, default=0.0)
    token_usage = Column(Integer, default=0)
    prompt_token_reduction_percent = Column(Float, default=0.0)
    memory_precision = Column(Float, default=0.0)
    memory_recall = Column(Float, default=0.0)
    task_completion_score = Column(Float, default=0.0)
    personalization_score = Column(Float, default=0.0)
    reasoning_score = Column(Float, default=0.0)
    hallucination_rate = Column(Float, default=0.0)
    long_term_consistency_score = Column(Float, default=0.0)
    identity_continuity_score = Column(Float, default=0.0)
    world_model_accuracy = Column(Float, default=0.0)
    storage_growth_bytes = Column(Integer, default=0)
    compression_ratio = Column(Float, default=0.0)
    cost_usd = Column(Float, default=0.0)
    interaction_count = Column(Integer, default=0)   # Performance after N interactions

    extra_metadata = Column("metadata", JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_benchmark_run_user_id", "user_id"),
        Index("idx_benchmark_run_strategy", "strategy"),
        Index("idx_benchmark_run_dataset", "dataset"),
        Index("idx_benchmark_run_created_at", "created_at"),
    )


class RuntimeMetrics(Base):
    """
    A point-in-time rollup of the cognitive runtime's overall scale and
    health - memory/concept/identity/world-graph counts, compression, and
    latency - the data backing GET /runtime/metrics and GET /runtime/dashboard.
    """
    __tablename__ = "runtime_metrics"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID(), ForeignKey("users.id"), nullable=True)  # null = global rollup

    memory_count = Column(Integer, default=0)
    concept_count = Column(Integer, default=0)
    identity_nodes = Column(Integer, default=0)
    world_nodes = Column(Integer, default=0)
    world_relationships = Column(Integer, default=0)
    project_count = Column(Integer, default=0)
    compression_ratio = Column(Float, default=0.0)
    cognitive_health_score = Column(Float, default=0.0)
    latency_ms = Column(Float, default=0.0)

    extra_metadata = Column("metadata", JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_runtime_metrics_user_id", "user_id"),
        Index("idx_runtime_metrics_created_at", "created_at"),
    )
