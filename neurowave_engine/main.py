"""Main FastAPI application"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from neurowave_engine.core.config import settings
from neurowave_engine.core.logging import logger as app_logger
from neurowave_engine.api import ingest_router, retrieval_router, health_router
from neurowave_engine.api.cognitive import router as cognitive_router
from neurowave_engine.api.consolidation import router as consolidation_router
from neurowave_engine.api.identity import router as identity_router
from neurowave_engine.api.predictive_recall import router as predictive_recall_router
from neurowave_engine.api.context_composer import router as context_composer_router
from neurowave_engine.api.memory_evolution import router as memory_evolution_router
from neurowave_engine.api.dream import router as dream_router
from neurowave_engine.api.world import router as world_router
from neurowave_engine.api.runtime import router as runtime_router, metrics_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan management. Schema is managed exclusively by
    Alembic (`alembic -c migrations/alembic.ini upgrade head` - see
    docs/DEPLOYMENT.md / k8s/README.md) - this used to also run
    `Base.metadata.create_all` here, which raced with Alembic: the very
    first `docker compose up` created every table via this hook, then the
    documented next step (`alembic upgrade head`) failed with
    "relation already exists" because Alembic's own version tracking
    never ran. Tests still create their own isolated schema directly
    (see tests/conftest.py) and are unaffected by this.
    """
    app_logger.info("Starting NeuroWeave application")
    yield
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
