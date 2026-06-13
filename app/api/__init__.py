"""API module"""
from app.api.ingest import router as ingest_router
from app.api.retrieval import router as retrieval_router
from app.api.health import router as health_router

__all__ = ["ingest_router", "retrieval_router", "health_router"]
