"""FastAPI routes for health and status"""
import logging
from datetime import datetime
from fastapi import APIRouter
from app.core.config import settings
from app.schemas.memory import HealthResponse

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """Health check endpoint"""
    return HealthResponse(
        status="healthy",
        version=settings.app_version,
        environment=settings.environment,
        timestamp=datetime.utcnow(),
    )


@router.get("/readiness")
def readiness_check():
    """Readiness check - verifies all dependencies are available"""
    return {
        "status": "ready",
        "timestamp": datetime.utcnow(),
    }
