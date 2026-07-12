"""Day 7: Cognitive Forgetting & Memory Evolution Engine API endpoints"""
import logging
import time
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.database import get_db_session
from app.db.models import Memory, MemoryEvent, CognitiveMemoryStateEnum
from app.schemas.memory_evolution import (
    MemoryEvolveRequest,
    MemoryEvolveResponse,
    MemoryDecayRequest,
    MemoryDecayResponse,
    DecayResult,
    MemoryArchiveRequest,
    MemoryArchiveResponse,
    MemoryReviveRequest,
    MemoryReviveResponse,
    RevivalResult,
    MemoryLifecycleResponse,
    MemoryEventItem,
    MemoryEventsResponse,
    MemoryEntropyResponse,
    EntropyBreakdown,
    CognitiveHealthResponse,
)
from app.services.memory_evolution_pipeline import MemoryEvolutionPipeline
from app.services.memory_decay_engine import MemoryDecayEngine
from app.services.memory_lifecycle_manager import MemoryLifecycleManager
from app.services.reinforcement_recovery import ReinforcementRecoveryService
from app.services.memory_health_monitor import MemoryHealthService
from app.services.memory_entropy import MemoryEntropyCalculator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/memory", tags=["memory-evolution"])


@router.post("/evolve", response_model=MemoryEvolveResponse)
async def evolve_memory(
    request: MemoryEvolveRequest,
    session: Session = Depends(get_db_session),
) -> MemoryEvolveResponse:
    """
    Run one full memory evolution pass: decay evaluation, duplicate
    resolution, obsolescence resolution, and forgetting decisions —
    the manual-trigger counterpart to the hourly/daily MemoryEvolutionWorker.
    """
    try:
        pipeline = MemoryEvolutionPipeline(session)
        result = pipeline.run(request.user_id)
        return MemoryEvolveResponse(**result)
    except Exception as e:
        logger.error(f"Memory evolution error: {e}")
        raise HTTPException(status_code=500, detail=f"Memory evolution failed: {str(e)}")


@router.post("/decay", response_model=MemoryDecayResponse)
async def decay_memory(
    request: MemoryDecayRequest,
    session: Session = Depends(get_db_session),
) -> MemoryDecayResponse:
    """Apply multi-factor decay evaluation to a user's memories."""
    try:
        start = time.time()

        query = session.query(Memory).filter(
            Memory.user_id == request.user_id,
            Memory.cognitive_state != CognitiveMemoryStateEnum.FORGOTTEN,
        )
        if request.memory_ids:
            query = query.filter(Memory.id.in_(request.memory_ids))
        memories = query.all()

        if not memories:
            raise HTTPException(status_code=404, detail="No memories found to decay")

        engine = MemoryDecayEngine(session)
        results = engine.apply_decay_batch(memories)
        session.commit()

        latency_ms = (time.time() - start) * 1000
        return MemoryDecayResponse(
            results=[
                DecayResult(
                    memory_id=r["memory_id"],
                    previous_strength=r["previous_strength"],
                    new_strength=r["new_strength"],
                    effective_decay_rate=r["effective_decay_rate"],
                    in_concept=r["in_concept"],
                    in_identity=r["in_identity"],
                )
                for r in results
            ],
            decay_latency_ms=latency_ms,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Memory decay error: {e}")
        raise HTTPException(status_code=500, detail=f"Memory decay failed: {str(e)}")


@router.post("/archive", response_model=MemoryArchiveResponse)
async def archive_memory(
    request: MemoryArchiveRequest,
    session: Session = Depends(get_db_session),
) -> MemoryArchiveResponse:
    """Manually archive a specific memory with an explicit reason."""
    try:
        memory = session.query(Memory).filter(
            Memory.id == request.memory_id, Memory.user_id == request.user_id
        ).first()
        if not memory:
            raise HTTPException(status_code=404, detail="Memory not found")

        old_state = memory.cognitive_state
        manager = MemoryLifecycleManager(session)
        result = manager.transition(memory, CognitiveMemoryStateEnum.ARCHIVED, request.reason)
        session.commit()

        return MemoryArchiveResponse(
            memory_id=request.memory_id,
            success=result["success"],
            old_state=old_state,
            new_state=memory.cognitive_state,
            reason=request.reason,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Memory archive error: {e}")
        raise HTTPException(status_code=500, detail=f"Memory archive failed: {str(e)}")


@router.post("/revive", response_model=MemoryReviveResponse)
async def revive_memory(
    request: MemoryReviveRequest,
    session: Session = Depends(get_db_session),
) -> MemoryReviveResponse:
    """
    Revive memories: pass `memory_id` to revive a specific memory directly,
    or `query` to automatically find and revive any decayed/archived/
    forgotten memories that have become relevant again (decay is reversible).
    """
    try:
        start = time.time()
        service = ReinforcementRecoveryService(session)

        if request.memory_id:
            memory = session.query(Memory).filter(
                Memory.id == request.memory_id, Memory.user_id == request.user_id
            ).first()
            if not memory:
                raise HTTPException(status_code=404, detail="Memory not found")
            revivals = [service.revive_memory(request.user_id, memory)]
        else:
            revivals = service.check_and_revive(request.user_id, request.query)

        latency_ms = (time.time() - start) * 1000
        return MemoryReviveResponse(
            revivals=[RevivalResult(**r) for r in revivals],
            revive_latency_ms=latency_ms,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Memory revival error: {e}")
        raise HTTPException(status_code=500, detail=f"Memory revival failed: {str(e)}")


@router.get("/lifecycle", response_model=MemoryLifecycleResponse)
async def get_memory_lifecycle(
    user_id: UUID,
    memory_id: UUID,
    session: Session = Depends(get_db_session),
) -> MemoryLifecycleResponse:
    """Get full lifecycle status for a single memory."""
    try:
        memory = session.query(Memory).filter(
            Memory.id == memory_id, Memory.user_id == user_id
        ).first()
        if not memory:
            raise HTTPException(status_code=404, detail="Memory not found")

        return MemoryLifecycleResponse(
            memory_id=memory.id,
            memory_type=memory.memory_type.value,
            cognitive_state=memory.cognitive_state,
            memory_strength=memory.memory_strength or 0.0,
            decay_rate=memory.decay_rate or 0.0,
            entropy_score=memory.entropy_score or 0.0,
            reinforcement_count=memory.reinforcement_count or 0,
            retrieval_count=memory.retrieval_count or 0,
            revival_count=memory.revival_count or 0,
            last_accessed=memory.last_accessed,
            last_reinforced_at=memory.last_reinforced_at,
            last_decay_at=memory.last_decay_at,
            archive_reason=memory.archive_reason,
            forget_reason=memory.forget_reason,
            created_at=memory.created_at,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Memory lifecycle error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch memory lifecycle")


@router.get("/health", response_model=CognitiveHealthResponse)
async def get_memory_health(
    user_id: UUID,
    session: Session = Depends(get_db_session),
) -> CognitiveHealthResponse:
    """Get the overall Cognitive Health Score and its contributing metrics."""
    try:
        health = MemoryHealthService(session).compute_health(user_id)
        return CognitiveHealthResponse(**health)
    except Exception as e:
        logger.error(f"Memory health error: {e}")
        raise HTTPException(status_code=500, detail="Failed to compute memory health")


@router.get("/events", response_model=MemoryEventsResponse)
async def get_memory_events(
    user_id: UUID,
    memory_id: Optional[UUID] = None,
    event_type: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=500),
    session: Session = Depends(get_db_session),
) -> MemoryEventsResponse:
    """Get the lifecycle event audit trail for a user (optionally filtered)."""
    try:
        query = session.query(MemoryEvent).filter(MemoryEvent.user_id == user_id)
        if memory_id:
            query = query.filter(MemoryEvent.memory_id == memory_id)
        if event_type:
            query = query.filter(MemoryEvent.event_type == event_type)

        events = query.order_by(MemoryEvent.timestamp.desc()).limit(limit).all()

        return MemoryEventsResponse(
            user_id=user_id,
            events=[
                MemoryEventItem(
                    id=e.id,
                    memory_id=e.memory_id,
                    event_type=e.event_type,
                    old_state=e.old_state,
                    new_state=e.new_state,
                    old_strength=e.old_strength,
                    new_strength=e.new_strength,
                    reason=e.reason,
                    confidence=e.confidence or 0.0,
                    timestamp=e.timestamp,
                )
                for e in events
            ],
        )
    except Exception as e:
        logger.error(f"Memory events error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch memory events")


@router.get("/entropy", response_model=MemoryEntropyResponse)
async def get_memory_entropy(
    user_id: UUID,
    session: Session = Depends(get_db_session),
) -> MemoryEntropyResponse:
    """Get the store-wide memory entropy (disorder) breakdown for a user."""
    try:
        entropy = MemoryEntropyCalculator(session).calculate(user_id)
        return MemoryEntropyResponse(user_id=user_id, entropy=EntropyBreakdown(**entropy))
    except Exception as e:
        logger.error(f"Memory entropy error: {e}")
        raise HTTPException(status_code=500, detail="Failed to compute memory entropy")
