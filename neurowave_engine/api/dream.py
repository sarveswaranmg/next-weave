"""Day 8: Offline Cognitive Consolidation Engine ("Dream Mode") API endpoints"""
import logging
import time
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from neurowave_engine.db.database import get_db
from neurowave_engine.db.models import DreamSession, DreamSessionStatusEnum
from neurowave_engine.schemas.dream import (
    DreamStartRequest,
    DreamSessionResponse,
    DreamStopRequest,
    DreamStopResponse,
    DreamHistoryResponse,
    DreamReplayRequest,
    DreamReplayResponse,
    ReplayResult,
    DreamRefineRequest,
    DreamRefineResponse,
    DreamSynthesizeRequest,
    DreamSynthesizeResponse,
    SynthesisResult,
    DreamStatisticsResponse,
)
from neurowave_engine.services.dream_pipeline import DreamPipeline
from neurowave_engine.services.replay_engine import ReplayEngine
from neurowave_engine.services.concept_refiner import ConceptRefiner
from neurowave_engine.services.knowledge_synthesizer import KnowledgeSynthesizer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dream", tags=["dream-mode"])


@router.post("/start", response_model=DreamSessionResponse)
async def start_dream(
    request: DreamStartRequest,
    session: Session = Depends(get_db),
) -> DreamSessionResponse:
    """
    Start (run) a full offline consolidation session: replay, pattern
    discovery, concept refinement, consistency healing, identity
    evolution, graph optimization, knowledge synthesis, replay simulation,
    compression, and health evaluation.
    """
    try:
        pipeline = DreamPipeline(session)
        dream_session = pipeline.run(request.user_id, trigger=request.trigger)
        return DreamSessionResponse.model_validate(dream_session)
    except Exception as e:
        logger.error(f"Dream start error: {e}")
        raise HTTPException(status_code=500, detail=f"Dream session failed: {str(e)}")


@router.post("/stop", response_model=DreamStopResponse)
async def stop_dream(
    request: DreamStopRequest,
    session: Session = Depends(get_db),
) -> DreamStopResponse:
    """Cooperatively cancel a running dream session."""
    try:
        pipeline = DreamPipeline(session)
        success = pipeline.stop(request.dream_session_id)

        dream_session = session.query(DreamSession).filter(
            DreamSession.id == request.dream_session_id
        ).first()
        if not dream_session:
            raise HTTPException(status_code=404, detail="Dream session not found")

        return DreamStopResponse(
            dream_session_id=request.dream_session_id,
            success=success,
            status=dream_session.status.value,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Dream stop error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to stop dream session: {str(e)}")


@router.get("/status", response_model=DreamSessionResponse)
async def get_dream_status(
    user_id: UUID,
    dream_session_id: Optional[UUID] = None,
    session: Session = Depends(get_db),
) -> DreamSessionResponse:
    """Get the status of a dream session (defaults to the most recent one for the user)."""
    try:
        query = session.query(DreamSession).filter(DreamSession.user_id == user_id)
        if dream_session_id:
            query = query.filter(DreamSession.id == dream_session_id)

        dream_session = query.order_by(DreamSession.started_at.desc()).first()
        if not dream_session:
            raise HTTPException(status_code=404, detail="No dream sessions found for this user")

        return DreamSessionResponse.model_validate(dream_session)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Dream status error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch dream status")


@router.get("/history", response_model=DreamHistoryResponse)
async def get_dream_history(
    user_id: UUID,
    limit: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_db),
) -> DreamHistoryResponse:
    """List past dream sessions for a user, most recent first."""
    try:
        sessions = session.query(DreamSession).filter(
            DreamSession.user_id == user_id
        ).order_by(DreamSession.started_at.desc()).limit(limit).all()

        return DreamHistoryResponse(
            user_id=user_id,
            sessions=[DreamSessionResponse.model_validate(s) for s in sessions],
        )
    except Exception as e:
        logger.error(f"Dream history error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch dream history")


@router.post("/replay", response_model=DreamReplayResponse)
async def run_replay(
    request: DreamReplayRequest,
    session: Session = Depends(get_db),
) -> DreamReplayResponse:
    """Run a standalone replay pass: select and rebuild understanding for high-value memories."""
    try:
        start = time.time()
        engine = ReplayEngine(session)
        selected = engine.select_for_replay(request.user_id, batch_size=request.batch_size)
        results = engine.replay(selected)
        latency_ms = (time.time() - start) * 1000

        return DreamReplayResponse(
            replayed=[ReplayResult(**r) for r in results],
            replay_latency_ms=latency_ms,
        )
    except Exception as e:
        logger.error(f"Dream replay error: {e}")
        raise HTTPException(status_code=500, detail=f"Replay failed: {str(e)}")


@router.post("/refine", response_model=DreamRefineResponse)
async def run_refine(
    request: DreamRefineRequest,
    session: Session = Depends(get_db),
) -> DreamRefineResponse:
    """Run a standalone concept refinement pass: merge, generalize, strengthen, retire."""
    try:
        start = time.time()
        refiner = ConceptRefiner(session)
        result = refiner.refine(request.user_id)
        latency_ms = (time.time() - start) * 1000

        return DreamRefineResponse(
            merged=DreamPipeline._jsonable_list(result["merged"]),
            generalized=DreamPipeline._jsonable_list(result["generalized"]),
            strengthened=DreamPipeline._jsonable_list(result["strengthened"]),
            retired=DreamPipeline._jsonable_list(result["retired"]),
            refine_latency_ms=latency_ms,
        )
    except Exception as e:
        logger.error(f"Dream refine error: {e}")
        raise HTTPException(status_code=500, detail=f"Concept refinement failed: {str(e)}")


@router.post("/synthesize", response_model=DreamSynthesizeResponse)
async def run_synthesize(
    request: DreamSynthesizeRequest,
    session: Session = Depends(get_db),
) -> DreamSynthesizeResponse:
    """Run a standalone knowledge synthesis pass: generate new higher-order concepts."""
    try:
        start = time.time()
        synthesizer = KnowledgeSynthesizer(session)
        results = synthesizer.synthesize(request.user_id)
        latency_ms = (time.time() - start) * 1000

        return DreamSynthesizeResponse(
            synthesized=[SynthesisResult(**r) for r in results],
            synthesize_latency_ms=latency_ms,
        )
    except Exception as e:
        logger.error(f"Dream synthesize error: {e}")
        raise HTTPException(status_code=500, detail=f"Knowledge synthesis failed: {str(e)}")


@router.get("/statistics", response_model=DreamStatisticsResponse)
async def get_dream_statistics(
    user_id: UUID,
    limit: int = Query(default=100, ge=1, le=1000),
    session: Session = Depends(get_db),
) -> DreamStatisticsResponse:
    """Aggregated Dream Mode observability metrics for a user."""
    try:
        sessions = session.query(DreamSession).filter(
            DreamSession.user_id == user_id
        ).order_by(DreamSession.started_at.desc()).limit(limit).all()

        if not sessions:
            return DreamStatisticsResponse(
                user_id=user_id, total_sessions=0, completed_sessions=0, cancelled_sessions=0,
                failed_sessions=0, average_dream_duration_ms=0.0, average_memories_replayed=0.0,
                average_patterns_discovered=0.0, average_concepts_created=0.0,
                average_identity_updates=0.0, average_graph_nodes_removed=0.0,
                average_graph_edges_strengthened=0.0, average_compression_ratio=0.0,
                average_health_improvement=0.0, total_knowledge_synthesized=0,
                total_patterns_discovered=0,
            )

        count = len(sessions)
        completed = [s for s in sessions if s.status == DreamSessionStatusEnum.COMPLETED]
        health_improvements = [
            (s.health_score_after - s.health_score_before)
            for s in completed
            if s.health_score_after is not None and s.health_score_before is not None
        ]

        return DreamStatisticsResponse(
            user_id=user_id,
            total_sessions=count,
            completed_sessions=len(completed),
            cancelled_sessions=sum(1 for s in sessions if s.status == DreamSessionStatusEnum.CANCELLED),
            failed_sessions=sum(1 for s in sessions if s.status == DreamSessionStatusEnum.FAILED),
            average_dream_duration_ms=sum(s.total_latency_ms or 0.0 for s in sessions) / count,
            average_memories_replayed=sum(s.memories_replayed or 0 for s in sessions) / count,
            average_patterns_discovered=sum(s.patterns_discovered or 0 for s in sessions) / count,
            average_concepts_created=sum(s.concepts_created or 0 for s in sessions) / count,
            average_identity_updates=sum(s.identity_updates or 0 for s in sessions) / count,
            average_graph_nodes_removed=sum(s.graph_nodes_removed or 0 for s in sessions) / count,
            average_graph_edges_strengthened=sum(s.graph_edges_strengthened or 0 for s in sessions) / count,
            average_compression_ratio=sum(s.compression_ratio or 0.0 for s in sessions) / count,
            average_health_improvement=(
                sum(health_improvements) / len(health_improvements) if health_improvements else 0.0
            ),
            total_knowledge_synthesized=sum(s.knowledge_synthesized or 0 for s in sessions),
            total_patterns_discovered=sum(s.patterns_discovered or 0 for s in sessions),
        )
    except Exception as e:
        logger.error(f"Dream statistics error: {e}")
        raise HTTPException(status_code=500, detail="Failed to compute dream statistics")
