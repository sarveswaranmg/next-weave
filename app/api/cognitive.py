"""Cognitive memory scoring and reinforcement API endpoints"""
import logging
import time
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

from app.db.database import get_db_session
from app.schemas.memory import (
    MemoryScoreRequest,
    MemoryScoreResponse,
    MemoryReinforceRequest,
    MemoryReinforceResponse,
    MemoryImportanceResponse,
    MemoryCognitiveStatsResponse,
    CognitiveScoreDimensions,
    CognitiveAnalysisResult,
)
from app.services.cognitive_scoring import score_memory, HybridScoringEngine
from app.services.reinforcement import MemoryReinforcementEngine
from app.services.memory_state import MemoryStateMachine
from app.db.models import Memory, CognitiveMemoryStateEnum

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/cognitive",
    tags=["cognitive"],
    responses={404: {"description": "Not found"}},
)


@router.post("/score", response_model=MemoryScoreResponse)
async def analyze_and_score_memory(
    request: MemoryScoreRequest,
    session: Session = Depends(get_db_session),
) -> MemoryScoreResponse:
    """
    Analyze a memory and compute cognitive importance scores
    
    Uses hybrid scoring: LLM analysis + heuristic validation
    """
    try:
        start_time = time.time()
        
        # Get memory from database
        memory = session.query(Memory).filter(
            Memory.id == request.memory_id,
            Memory.user_id == request.user_id
        ).first()
        
        if not memory:
            raise HTTPException(status_code=404, detail="Memory not found")
        
        # Score the memory
        scores = score_memory(
            memory.content,
            memory.memory_type,
            use_llm=request.use_llm
        )
        
        # Update memory with scores
        memory.future_utility_score = scores.get("future_utility_score", 0.5)
        memory.identity_impact_score = scores.get("identity_impact_score", 0.5)
        memory.emotional_salience_score = scores.get("emotional_salience_score", 0.5)
        memory.reinforcement_score = scores.get("reinforcement_score", 0.5)
        memory.temporal_persistence_score = scores.get("temporal_persistence_score", 0.5)
        memory.importance_score = scores.get("importance_score", 0.5)
        memory.cognitive_state = scores.get("cognitive_state", CognitiveMemoryStateEnum.ACTIVE)
        memory.memory_strength = scores.get("memory_strength", 0.5)
        memory.decay_rate = scores.get("decay_rate", 0.05)
        
        session.commit()
        
        analysis_latency_ms = (time.time() - start_time) * 1000
        
        return MemoryScoreResponse(
            analysis=CognitiveAnalysisResult(
                memory_id=request.memory_id,
                future_utility_score=memory.future_utility_score,
                identity_impact_score=memory.identity_impact_score,
                emotional_salience_score=memory.emotional_salience_score,
                reinforcement_score=memory.reinforcement_score,
                temporal_persistence_score=memory.temporal_persistence_score,
                cognitive_importance_score=memory.importance_score,
                cognitive_state=memory.cognitive_state,
                memory_strength=memory.memory_strength,
                decay_rate=memory.decay_rate,
                analysis_latency_ms=analysis_latency_ms,
                explanation=scores.get("reasoning", "Cognitive analysis completed")
            ),
            dimensions=CognitiveScoreDimensions(
                future_utility=memory.future_utility_score,
                identity_impact=memory.identity_impact_score,
                emotional_salience=memory.emotional_salience_score,
                reinforcement=memory.reinforcement_score,
                temporal_persistence=memory.temporal_persistence_score
            ),
            updated_at=memory.updated_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Memory scoring error: {e}")
        raise HTTPException(status_code=500, detail=f"Scoring failed: {str(e)}")


@router.post("/reinforce", response_model=MemoryReinforceResponse)
async def reinforce_memory(
    request: MemoryReinforceRequest,
    session: Session = Depends(get_db_session),
) -> MemoryReinforceResponse:
    """
    Reinforce a memory when concepts repeat or memory is accessed
    
    Increases memory strength and adjusts decay rate
    """
    try:
        # Get memory from database
        memory = session.query(Memory).filter(
            Memory.id == request.memory_id,
            Memory.user_id == request.user_id
        ).first()
        
        if not memory:
            raise HTTPException(status_code=404, detail="Memory not found")
        
        start_time = time.time()
        
        # Use reinforcement engine
        engine = MemoryReinforcementEngine(session)
        result = engine.reinforce_memory(
            str(request.memory_id),
            reinforcement_context=request.reinforcement_context,
            strength_increase=0.1
        )
        
        reinforcement_latency_ms = (time.time() - start_time) * 1000
        
        if not result.get("success", False):
            raise HTTPException(status_code=404, detail=result.get("error", "Reinforcement failed"))
        
        # Refresh memory from database
        session.refresh(memory)
        
        return MemoryReinforceResponse(
            memory_id=request.memory_id,
            previous_strength=result["previous_strength"],
            new_strength=result["new_strength"],
            reinforcement_count=result["reinforcement_count"],
            cognitive_state=result["new_state"],
            decay_rate=result["decay_rate"],
            last_reinforced_at=result["last_reinforced_at"],
            reinforcement_latency_ms=reinforcement_latency_ms
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Memory reinforcement error: {e}")
        raise HTTPException(status_code=500, detail=f"Reinforcement failed: {str(e)}")


@router.get("/importance/{memory_id}", response_model=MemoryImportanceResponse)
async def get_memory_importance(
    memory_id: UUID,
    user_id: UUID,
    session: Session = Depends(get_db_session),
) -> MemoryImportanceResponse:
    """Get detailed importance and cognitive information for a specific memory"""
    try:
        memory = session.query(Memory).filter(
            Memory.id == memory_id,
            Memory.user_id == user_id
        ).first()
        
        if not memory:
            raise HTTPException(status_code=404, detail="Memory not found")
        
        return MemoryImportanceResponse(
            memory_id=memory_id,
            memory_type=memory.memory_type,
            content_preview=memory.content[:100] if memory.content else "",
            cognitive_state=memory.cognitive_state,
            memory_strength=memory.memory_strength,
            importance_score=memory.importance_score,
            cognitive_scores=CognitiveScoreDimensions(
                future_utility=memory.future_utility_score,
                identity_impact=memory.identity_impact_score,
                emotional_salience=memory.emotional_salience_score,
                reinforcement=memory.reinforcement_score,
                temporal_persistence=memory.temporal_persistence_score
            ),
            reinforcement_count=memory.reinforcement_count,
            retrieval_count=memory.retrieval_count,
            last_accessed=memory.last_accessed,
            last_reinforced_at=memory.last_reinforced_at,
            created_at=memory.created_at,
            decay_rate=memory.decay_rate
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting memory importance: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve memory importance")


@router.get("/stats", response_model=MemoryCognitiveStatsResponse)
async def get_cognitive_stats(
    user_id: UUID,
    session: Session = Depends(get_db_session),
) -> MemoryCognitiveStatsResponse:
    """Get comprehensive cognitive memory statistics for a user"""
    try:
        memories = session.query(Memory).filter(Memory.user_id == user_id).all()
        
        if not memories:
            return MemoryCognitiveStatsResponse(
                total_memories=0,
                average_importance_score=0.0,
                average_memory_strength=0.0,
                memory_state_distribution={},
                memory_type_distribution={},
                average_reinforcement_count=0.0,
                average_retrieval_count=0.0,
                total_active_memories=0,
                total_dormant_memories=0,
                total_decaying_memories=0,
                total_archived_memories=0,
                importance_distribution={},
                temporal_persistence_average=0.0,
                identity_impact_average=0.0,
                emotional_salience_average=0.0,
            )
        
        # Calculate statistics
        state_dist = {}
        type_dist = {}
        importance_dist = {"high": 0, "medium": 0, "low": 0}
        
        total_importance = 0.0
        total_strength = 0.0
        total_reinforcement = 0.0
        total_retrieval = 0.0
        total_persistence = 0.0
        total_identity = 0.0
        total_salience = 0.0
        
        for memory in memories:
            # State distribution
            state = str(memory.cognitive_state)
            state_dist[state] = state_dist.get(state, 0) + 1
            
            # Type distribution
            mem_type = str(memory.memory_type)
            type_dist[mem_type] = type_dist.get(mem_type, 0) + 1
            
            # Importance distribution
            if memory.importance_score >= 0.70:
                importance_dist["high"] += 1
            elif memory.importance_score >= 0.40:
                importance_dist["medium"] += 1
            else:
                importance_dist["low"] += 1
            
            # Aggregate scores
            total_importance += memory.importance_score or 0.0
            total_strength += memory.memory_strength or 0.0
            total_reinforcement += memory.reinforcement_count or 0.0
            total_retrieval += memory.retrieval_count or 0.0
            total_persistence += memory.temporal_persistence_score or 0.0
            total_identity += memory.identity_impact_score or 0.0
            total_salience += memory.emotional_salience_score or 0.0
        
        count = len(memories)
        
        return MemoryCognitiveStatsResponse(
            total_memories=count,
            average_importance_score=total_importance / count if count > 0 else 0.0,
            average_memory_strength=total_strength / count if count > 0 else 0.0,
            memory_state_distribution=state_dist,
            memory_type_distribution=type_dist,
            average_reinforcement_count=total_reinforcement / count if count > 0 else 0.0,
            average_retrieval_count=total_retrieval / count if count > 0 else 0.0,
            total_active_memories=state_dist.get("active", 0),
            total_dormant_memories=state_dist.get("dormant", 0),
            total_decaying_memories=state_dist.get("decaying", 0),
            total_archived_memories=state_dist.get("archived", 0),
            importance_distribution=importance_dist,
            temporal_persistence_average=total_persistence / count if count > 0 else 0.0,
            identity_impact_average=total_identity / count if count > 0 else 0.0,
            emotional_salience_average=total_salience / count if count > 0 else 0.0,
        )
        
    except Exception as e:
        logger.error(f"Error getting cognitive stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve statistics")
