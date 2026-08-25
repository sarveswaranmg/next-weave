"""Core configuration settings"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings"""

    # Database
    database_url: str = "postgresql://neuroweave:neuroweave@localhost:5432/neuroweave"
    database_pool_size: int = 20
    database_max_overflow: int = 40

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # OpenAI
    openai_api_key: str = ""
    openai_embedding_model: str = "text-embedding-3-small"
    openai_embedding_dimension: int = 1536

    # Anthropic (optional - only used if provider="anthropic")
    anthropic_api_key: str = ""

    # Google Gemini (optional - only used if provider="google"; free tier
    # key from https://aistudio.google.com/apikey)
    google_api_key: str = ""

    # Application
    debug: bool = False
    log_level: str = "INFO"
    environment: str = "development"
    app_name: str = "NeuroWeave"
    app_version: str = "0.1.0"

    # Memory Settings
    memory_importance_threshold: float = 0.3
    memory_retrieval_top_k: int = 10
    memory_context_token_limit: int = 2000
    memory_embedding_batch_size: int = 32
    memory_decay_rate: float = 0.01

    # Performance
    cache_ttl_seconds: int = 3600
    async_workers: int = 4

    # Day 5: Predictive Recall Engine - utility scoring weights (must sum to 1.0)
    utility_weight_goal_alignment: float = 0.30
    utility_weight_identity_alignment: float = 0.20
    utility_weight_concept_relevance: float = 0.20
    utility_weight_importance: float = 0.10
    utility_weight_reinforcement: float = 0.10
    utility_weight_confidence: float = 0.05
    utility_weight_recency: float = 0.05

    # Day 5: Predictive Recall Engine - retrieval tuning
    predictive_recall_default_token_budget: int = 1000
    predictive_recall_candidate_pool_size: int = 200  # Max candidates considered per query
    predictive_recall_min_utility: float = 0.15       # Floor below which memories are discarded
    predictive_recall_knapsack_max_candidates: int = 60  # DP optimizer switches to greedy above this

    # Day 6: Cognitive Context Composer - target compression & quality weights
    ccc_default_token_budget: int = 600
    ccc_compression_target_ratio: float = 0.85  # 85% reduction target vs raw memory text
    ccc_dedup_similarity_threshold: float = 0.80
    ccc_concept_merge_similarity_threshold: float = 0.40
    ccc_contradiction_similarity_threshold: float = 0.5

    # Quality score weights (should sum to ~1.0)
    ccc_quality_weight_coverage: float = 0.25
    ccc_quality_weight_non_redundancy: float = 0.15
    ccc_quality_weight_identity_alignment: float = 0.20
    ccc_quality_weight_goal_alignment: float = 0.20
    ccc_quality_weight_reasoning: float = 0.10
    ccc_quality_weight_non_contradiction: float = 0.10

    # Day 7: Cognitive Forgetting & Memory Evolution Engine
    # Adaptive per-type base daily decay rates (fraction of strength lost per day
    # of inactivity, before reinforcement/importance/emotional-salience adjustment)
    decay_rate_identity: float = 0.002      # Very slow - identity persists
    decay_rate_concept: float = 0.006       # Slow - abstracted knowledge persists
    decay_rate_procedural: float = 0.012    # Medium - behavioral rules
    decay_rate_semantic: float = 0.02       # Medium-fast - facts can go stale
    decay_rate_episodic: float = 0.05       # Fast - individual events fade
    decay_rate_episodic_low_importance: float = 0.12  # Very fast - "random conversation"
    low_importance_episodic_threshold: float = 0.25   # Below this, episodic = "random conversation"

    # Forgetting thresholds
    forgetting_weaken_threshold: float = 0.55    # Below this utility-adjacent score -> weaken
    forgetting_archive_threshold: float = 0.30   # Below this -> archive
    forgetting_forget_threshold: float = 0.10    # Below this + old + unused -> soft-forget
    forgetting_min_age_days_for_forget: int = 180

    # Reinforcement recovery (revival)
    revival_utility_threshold: float = 0.55      # Utility score above which a decayed memory revives
    revival_strength_boost: float = 0.25

    # Duplicate / obsolete detection. Short paraphrased memories ("Likes
    # Rust" / "Enjoys Rust") often share only their topic word once
    # boilerplate is stripped, so this is deliberately lower than a
    # "these sentences are 75% identical" threshold would suggest.
    duplicate_similarity_threshold: float = 0.40
    obsolete_confidence_penalty: float = 0.5     # Multiplier applied to superseded memory's strength

    # Cognitive health score weights (should sum to ~1.0)
    health_weight_duplicate: float = 0.15
    health_weight_forgotten: float = 0.10
    health_weight_archive: float = 0.10
    health_weight_strength: float = 0.25
    health_weight_entropy: float = 0.25
    health_weight_graph_complexity: float = 0.15

    # Day 7: Retrieval-time filtering - ignore low-strength/high-entropy memories
    retrieval_min_strength: float = 0.15
    retrieval_max_entropy: float = 0.85

    # Day 8: Offline Cognitive Consolidation Engine ("Dream Mode")
    dream_replay_batch_size: int = 100            # Max memories replayed per session
    dream_min_hours_between_sessions: float = 1.0  # Cooldown per user
    dream_idle_minutes_threshold: int = 15         # No activity for this long => eligible for idle-triggered dream
    dream_max_users_per_scheduler_tick: int = 20

    # Pattern discovery: how much combined evidence (0-1, weighted by
    # concept confidence) is needed before inferring a higher-order trait
    pattern_discovery_min_evidence: float = 0.55

    # Concept refinement
    concept_merge_similarity_threshold: float = 0.40
    concept_retire_confidence_threshold: float = 0.15
    concept_retire_min_age_days: int = 90
    concept_generalize_min_group_size: int = 3   # >= this many related concepts -> generalize into one

    # Identity evolution
    identity_shift_evidence_threshold: float = 0.6  # New-trait evidence strength needed to log a shift
    identity_shift_min_supporting_concepts: int = 3

    # Knowledge synthesis
    synthesis_min_concepts: int = 3
    synthesis_max_concepts: int = 6
    synthesis_min_confidence: float = 0.5

    # Graph optimization
    graph_dead_node_confidence_threshold: float = 0.1
    graph_weak_node_merge_similarity: float = 0.5

    # Day 9: World Model Engine
    world_entity_merge_similarity_threshold: float = 0.7  # Same-name-ish entities collapse into one node
    world_relationship_min_strength: float = 0.2
    world_active_context_window_days: int = 14   # "Currently active" = touched within this window
    world_project_stale_days: int = 30           # No updates for this long -> no longer "active" by default
    world_prediction_min_confidence: float = 0.4

    # Day 10: Cognitive Runtime Platform
    # Defaults to Google Gemini's free tier (no billing required) rather
    # than a paid provider - see google_api_key above.
    runtime_default_provider: str = "google"
    runtime_default_model: str = "gemini-2.0-flash"
    runtime_default_token_budget: int = 800
    runtime_api_key: str = ""              # Optional seed value: scripts/bootstrap_tenant.py hashes this into
                                            # the first ApiKey row for a zero-downtime upgrade path from the old
                                            # single-shared-secret model. Not checked at request time anymore -
                                            # auth is now per-tenant via the api_keys table (neurowave_engine.core.security).
    credential_encryption_key: str = ""    # Fernet key (Fernet.generate_key()) encrypting stored BYOK provider
                                            # credentials at rest. Required once any ProviderCredential is stored.
    runtime_version: str = "1.0.0-day10"

    class Config:
        env_file = ".env"
        case_sensitive = False
        # pydantic-settings defaults to extra="forbid" - any env var in
        # .env (or the process environment) that isn't a declared field
        # above crashes Settings() at import time, before the app even
        # starts. That's too brittle for a real .env file, which
        # routinely picks up ops-only vars that have nothing to do with
        # application config (e.g. docker-compose host port overrides
        # like POSTGRES_PORT, or a stray ANTHROPIC_API_KEY before it was
        # wired up as a field here) - ignore unrecognized keys instead.
        extra = "ignore"


settings = Settings()
