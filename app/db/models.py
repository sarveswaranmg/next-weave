"""SQLAlchemy models for NeuroWeave"""
from sqlalchemy import Column, String, Float, DateTime, Integer, Text, Index, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
import uuid

from app.db.database import Base


class MemoryTypeEnum(str, enum.Enum):
    """Memory type enumeration"""
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    IDENTITY = "identity"
    PROCEDURAL = "procedural"
    CONCEPT = "concept"  # Day 3: Generalized semantic concepts


class CognitiveMemoryStateEnum(str, enum.Enum):
    """Cognitive memory lifecycle state enumeration"""
    ACTIVE = "active"                          # Highly relevant + frequently accessed
    REINFORCED = "reinforced"                  # Repeated over time
    SEMANTIC_CANDIDATE = "semantic_candidate"  # Ready for abstraction/consolidation
    DORMANT = "dormant"                        # Rarely used but retained
    DECAYING = "decaying"                      # Low-value memory losing strength
    ARCHIVED = "archived"                      # Compressed low-priority memory


class User(Base):
    """User model"""
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
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

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    session_token = Column(String(255), unique=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime)
    metadata = Column(JSON, default={})

    # Relationships
    user = relationship("User", back_populates="sessions")

    __table_args__ = (
        Index("idx_session_user_id", "user_id"),
        Index("idx_session_token", "session_token"),
    )


class Memory(Base):
    """Core memory model with cognitive scoring dimensions"""
    __tablename__ = "memories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
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
    metadata = Column(JSON, default={})
    reinforcement_count = Column(Integer, default=0)
    access_count = Column(Integer, default=0)
    last_accessed = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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
    )


class MemoryEmbedding(Base):
    """Memory embeddings for vector similarity search using pgvector"""
    __tablename__ = "memory_embeddings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    memory_id = Column(UUID(as_uuid=True), ForeignKey("memories.id"), nullable=False)
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

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
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

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    source_memory_ids = Column(JSON)  # List of original memory IDs
    consolidated_memory_id = Column(UUID(as_uuid=True), ForeignKey("memories.id"))
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

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
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
    metadata = Column(JSON, default={})
    
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

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
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
    
    metadata = Column(JSON, default={})
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

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    source_concept_id = Column(UUID(as_uuid=True), ForeignKey("concept_memories.id"), nullable=False)
    target_concept_id = Column(UUID(as_uuid=True), ForeignKey("concept_memories.id"), nullable=False)
    
    # Relationship type
    relationship_type = Column(String(50), nullable=False)  # supports, reinforces, related_to, derived_from
    strength = Column(Float, default=0.5)  # 0.0-1.0: connection strength
    
    # Lifecycle
    reinforcement_count = Column(Integer, default=1)
    last_reinforced_at = Column(DateTime, default=datetime.utcnow)
    
    metadata = Column(JSON, default={})
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

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
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
    
    metadata = Column(JSON, default={})
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

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
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
    metadata = Column(JSON, default={})
    
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

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    source_node_id = Column(UUID(as_uuid=True), ForeignKey("identity_nodes.id"), nullable=False)
    target_node_id = Column(UUID(as_uuid=True), ForeignKey("identity_nodes.id"), nullable=False)
    
    # Relationship properties
    relationship_type = Column(String(50), nullable=False)  # related_to, reinforces, derived_from, influences, conflicts
    strength = Column(Float, default=0.5)  # 0.0-1.0: relationship strength
    
    # Evidence
    reinforcement_count = Column(Integer, default=1)
    last_reinforced_at = Column(DateTime, default=datetime.utcnow)
    
    # Metadata
    metadata = Column(JSON, default={})
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

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    node_id = Column(UUID(as_uuid=True), ForeignKey("identity_nodes.id"), nullable=False)
    
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
    
    metadata = Column(JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_identity_history_user_id", "user_id"),
        Index("idx_identity_history_node_id", "node_id"),
        Index("idx_identity_history_created_at", "created_at"),
        Index("idx_identity_history_event_type", "event_type"),
    )
