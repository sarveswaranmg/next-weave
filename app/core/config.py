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

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
