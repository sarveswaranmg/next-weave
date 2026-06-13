"""Workers module"""
from app.workers.celery_app import celery_app
from app.workers.tasks import (
    generate_embeddings_for_memory,
    consolidate_similar_memories,
    enforce_memory_retention_policy,
)

__all__ = [
    "celery_app",
    "generate_embeddings_for_memory",
    "consolidate_similar_memories",
    "enforce_memory_retention_policy",
]
