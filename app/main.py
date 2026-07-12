"""Main FastAPI application"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import logger as app_logger
from app.api import ingest_router, retrieval_router, health_router
from app.api.cognitive import router as cognitive_router
from app.api.consolidation import router as consolidation_router
from app.api.identity import router as identity_router
from app.api.predictive_recall import router as predictive_recall_router
from app.api.context_composer import router as context_composer_router
from app.api.memory_evolution import router as memory_evolution_router
from app.api.dream import router as dream_router
from app.api.world import router as world_router
from app.api.runtime import router as runtime_router, metrics_router
from app.db.database import async_engine
from app.db.models import Base


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management"""
    # Startup
    app_logger.info("Starting NeuroWeave application")
    
    # Create tables (in production, use Alembic migrations)
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield
    
    # Shutdown
    app_logger.info("Shutting down NeuroWeave application")


# Create FastAPI application
app = FastAPI(
    title="NeuroWeave",
    description="Cognitive Memory Engine for AI",
    version=settings.app_version,
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health_router)
app.include_router(ingest_router)
app.include_router(retrieval_router)
app.include_router(cognitive_router)
app.include_router(consolidation_router)
app.include_router(identity_router)
app.include_router(predictive_recall_router)
app.include_router(context_composer_router)
app.include_router(memory_evolution_router)
app.include_router(dream_router)
app.include_router(world_router)
app.include_router(runtime_router)
app.include_router(metrics_router)

# Root endpoint
@app.get("/")
def root():
    """Root endpoint"""
    return {
        "name": "NeuroWeave",
        "version": settings.app_version,
        "description": "Cognitive Memory Engine for AI",
        "docs_url": "/docs",
        "health_url": "/health",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level=settings.log_level.lower(),
    )
