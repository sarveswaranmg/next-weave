"""Day 6: Cognitive Context Composer API endpoints"""
import logging
import time
from typing import Dict, List, Tuple
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from neurowave_engine.db.database import get_db
from neurowave_engine.db.models import Memory, ContextSnapshot
from neurowave_engine.core.config import settings
from neurowave_engine.schemas.context_composer import (
    ContextComposeRequest,
    ContextComposeResponse,
    ContextEvaluateRequest,
    ContextEvaluateResponse,
    ContextCompressRequest,
    ContextCompressResponse,
    ContextNarrativeRequest,
    ContextNarrativeResponse,
    ContextGapsRequest,
    ContextGapsResponse,
    ContextHistoryResponse,
    ContextHistoryItem,
    ContextMetricsAggregateResponse,
    CognitiveStateSchema,
    CompressedMemorySchema,
    CompressionStatsSchema,
    ContextEvaluationSchema,
    KnowledgeGapsSchema,
)
from neurowave_engine.schemas.predictive_recall import GoalDetectionResult, IntentProbability, UtilityWeights as UtilityWeightsSchema
from neurowave_engine.services.goal_detector import goal_detector
from neurowave_engine.services.intent_classifier import intent_classifier
from neurowave_engine.services.context_analyzer import ContextAnalyzer
from neurowave_engine.services.utility_predictor import MemoryUtilityPredictor, UtilityWeights
from neurowave_engine.services.contradiction_resolver import ContradictionResolver
from neurowave_engine.services.knowledge_gap_detector import knowledge_gap_detector
from neurowave_engine.services.context_compression import ContextCompressionEngine, CompressedMemory
from neurowave_engine.services.state_generator import state_generator
from neurowave_engine.services.narrative_generator import narrative_generator
from neurowave_engine.services.context_evaluator import ContextEvaluator
from neurowave_engine.services.context_composer import ContextComposer
from neurowave_engine.utils.observability import CognitiveAnalytics

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/context", tags=["cognitive-context-composer"])


def _to_utility_weights(schema: UtilityWeightsSchema) -> UtilityWeights:
    if not schema:
        return None
    return UtilityWeights(
        goal_alignment=schema.goal_alignment,
        identity_alignment=schema.identity_alignment,
        concept_relevance=schema.concept_relevance,
        importance=schema.importance,
        reinforcement=schema.reinforcement,
        confidence=schema.confidence,
        recency=schema.recency,
    )


def _score_explicit_memories(
    session: Session, user_id: UUID, query: str, memory_ids: List[UUID]
) -> Tuple[Dict, Dict, List[Dict], Dict[UUID, Memory]]:
    """Fetch an explicit memory set and utility-score it against a fresh
    goal/context analysis — the shared basis for the single-stage endpoints."""
    memories = session.query(Memory).filter(
        Memory.user_id == user_id, Memory.id.in_(memory_ids)
    ).all()
    if not memories:
        raise HTTPException(status_code=404, detail="No memories found for the given ids")

    memory_by_id = {m.id: m for m in memories}
    goal_result = goal_detector.detect(query)
    intent_result = intent_classifier.classify(query)
    analyzer = ContextAnalyzer(session)
    context = analyzer.analyze(
        user_id, query, goal_result["goal"], [i["intent"] for i in intent_result["intents"]]
    )
    predictor = MemoryUtilityPredictor()
    scored = predictor.predict_batch(memories, context)
    return goal_result, context, scored, memory_by_id


@router.post("/compose", response_model=ContextComposeResponse)
async def compose_context(
    request: ContextComposeRequest,
    session: Session = Depends(get_db),
) -> ContextComposeResponse:
    """
    Run the full Cognitive Context Composer pipeline: goal detection,
    identity/concept conditioning, utility scoring, contradiction
    resolution, knowledge gap detection, compression, narrative
    generation, and quality evaluation — replacing raw memory concatenation
    with a reconstructed cognitive state.
    """
    try:
        composer = ContextComposer(session)
        result = composer.compose(
            user_id=request.user_id,
            query=request.query,
            token_budget=request.token_budget,
            memory_types=request.memory_types,
            weights=_to_utility_weights(request.weights),
        )

        return ContextComposeResponse(
            snapshot_id=result["snapshot_id"],
            goal=GoalDetectionResult(**result["goal"]),
            intents=[IntentProbability(**i) for i in result["intents"]],
            state=CognitiveStateSchema(**result["state"]),
            narrative=result["narrative"],
            final_context=result["final_context"],
            compressed_memories=[CompressedMemorySchema(**cm) for cm in result["compressed_memories"]],
            contradictions=result["contradictions"],
            knowledge_gaps=KnowledgeGapsSchema(**result["knowledge_gaps"]),
            compression=CompressionStatsSchema(**result["compression"]),
            evaluation=ContextEvaluationSchema(**result["evaluation"]),
            candidate_count=result["candidate_count"],
            token_budget=result["token_budget"],
            total_latency_ms=result["total_latency_ms"],
        )
    except Exception as e:
        logger.error(f"Context composition error: {e}")
        raise HTTPException(status_code=500, detail=f"Context composition failed: {str(e)}")


@router.post("/evaluate", response_model=ContextEvaluateResponse)
async def evaluate_context(
    request: ContextEvaluateRequest,
    session: Session = Depends(get_db),
) -> ContextEvaluateResponse:
    """Evaluate the quality of a specific memory set as a candidate context."""
    try:
        start = time.time()
        goal_result, context, scored, memory_by_id = _score_explicit_memories(
            session, request.user_id, request.query, request.memory_ids
        )

        resolver = ContradictionResolver()
        kept, contradictions = resolver.resolve(scored, memory_by_id)

        gaps = knowledge_gap_detector.detect(request.query, [memory_by_id[s["memory_id"]] for s in kept])

        compressed = [
            CompressedMemory(
                id=str(s["memory_id"]),
                memory_type=memory_by_id[s["memory_id"]].memory_type,
                content=memory_by_id[s["memory_id"]].content or "",
                importance_score=memory_by_id[s["memory_id"]].importance_score or 0.5,
                utility_score=s["utility_score"],
                source_ids=[s["memory_id"]],
            )
            for s in kept
        ]
        token_count = sum(ContextCompressionEngine().optimizer.estimate_tokens(cm.content) for cm in compressed)

        scored_by_id = {s["memory_id"]: s for s in kept}
        evaluator = ContextEvaluator()
        evaluation = evaluator.evaluate(
            required_knowledge=context["required_knowledge"],
            compressed_memories=compressed,
            scored_by_id=scored_by_id,
            duplicate_count=0,
            original_candidate_count=max(1, len(scored)),
            contradiction_count=len(contradictions),
            missing_topics=gaps["missing_topics"],
            token_count=token_count,
        )

        latency_ms = (time.time() - start) * 1000
        return ContextEvaluateResponse(
            evaluation=ContextEvaluationSchema(**evaluation),
            evaluation_latency_ms=latency_ms,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Context evaluation error: {e}")
        raise HTTPException(status_code=500, detail=f"Context evaluation failed: {str(e)}")


@router.post("/compress", response_model=ContextCompressResponse)
async def compress_context(
    request: ContextCompressRequest,
    session: Session = Depends(get_db),
) -> ContextCompressResponse:
    """Compress a specific memory set: dedup, merge concepts, fit to token budget."""
    try:
        start = time.time()
        goal_result, context, scored, memory_by_id = _score_explicit_memories(
            session, request.user_id, request.query, request.memory_ids
        )
        token_budget = request.token_budget or settings.ccc_default_token_budget

        engine = ContextCompressionEngine()
        compression = engine.compress(scored, memory_by_id, token_budget)

        latency_ms = (time.time() - start) * 1000
        return ContextCompressResponse(
            compressed_memories=[
                CompressedMemorySchema(**ContextComposer._serialize_compressed(cm))
                for cm in compression["memories"]
            ],
            compression=CompressionStatsSchema(
                original_tokens=compression["original_tokens"],
                compressed_tokens=compression["compressed_tokens"],
                compression_ratio=compression["compression_ratio"],
                duplicate_count=compression["duplicate_count"],
                merged_count=compression["merged_count"],
            ),
            compression_latency_ms=latency_ms,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Context compression error: {e}")
        raise HTTPException(status_code=500, detail=f"Context compression failed: {str(e)}")


@router.post("/narrative", response_model=ContextNarrativeResponse)
async def generate_narrative(
    request: ContextNarrativeRequest,
    session: Session = Depends(get_db),
) -> ContextNarrativeResponse:
    """Generate a coherent narrative + structured state from a specific memory set."""
    try:
        start = time.time()
        goal_result, context, scored, memory_by_id = _score_explicit_memories(
            session, request.user_id, request.query, request.memory_ids
        )

        compressed = [
            CompressedMemory(
                id=str(s["memory_id"]),
                memory_type=memory_by_id[s["memory_id"]].memory_type,
                content=memory_by_id[s["memory_id"]].content or "",
                importance_score=memory_by_id[s["memory_id"]].importance_score or 0.5,
                utility_score=s["utility_score"],
                source_ids=[s["memory_id"]],
            )
            for s in scored
        ]

        state = state_generator.generate(goal_result["goal"], context["identity_traits"], compressed)
        narrative = narrative_generator.generate(state)

        latency_ms = (time.time() - start) * 1000
        return ContextNarrativeResponse(
            narrative=narrative,
            state=CognitiveStateSchema(**state),
            narrative_latency_ms=latency_ms,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Narrative generation error: {e}")
        raise HTTPException(status_code=500, detail=f"Narrative generation failed: {str(e)}")


@router.post("/gaps", response_model=ContextGapsResponse)
async def detect_knowledge_gaps(
    request: ContextGapsRequest,
    session: Session = Depends(get_db),
) -> ContextGapsResponse:
    """Detect knowledge gaps implied by the query but not covered by retained memory."""
    try:
        start = time.time()
        if request.memory_ids:
            memories = session.query(Memory).filter(
                Memory.user_id == request.user_id, Memory.id.in_(request.memory_ids)
            ).all()
        else:
            memories = session.query(Memory).filter(
                Memory.user_id == request.user_id
            ).order_by(Memory.importance_score.desc()).limit(settings.predictive_recall_candidate_pool_size).all()

        gaps = knowledge_gap_detector.detect(request.query, memories)

        latency_ms = (time.time() - start) * 1000
        return ContextGapsResponse(
            gaps=KnowledgeGapsSchema(**gaps),
            gap_detection_latency_ms=latency_ms,
        )
    except Exception as e:
        logger.error(f"Knowledge gap detection error: {e}")
        raise HTTPException(status_code=500, detail=f"Knowledge gap detection failed: {str(e)}")


@router.get("/history", response_model=ContextHistoryResponse)
async def get_context_history(
    user_id: UUID,
    limit: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_db),
) -> ContextHistoryResponse:
    """List past Cognitive Context Composer runs for a user, most recent first."""
    try:
        snapshots = session.query(ContextSnapshot).filter(
            ContextSnapshot.user_id == user_id
        ).order_by(ContextSnapshot.created_at.desc()).limit(limit).all()

        items = [
            ContextHistoryItem(
                snapshot_id=s.id,
                query=s.query,
                detected_goal=s.detected_goal,
                context_quality=s.context_quality or 0.0,
                token_count=s.token_count or 0,
                compression_ratio=s.compression_ratio or 0.0,
                contradiction_count=s.contradiction_count or 0,
                missing_topics=s.missing_topics or [],
                created_at=s.created_at,
            )
            for s in snapshots
        ]
        return ContextHistoryResponse(user_id=user_id, snapshots=items)
    except Exception as e:
        logger.error(f"Context history error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch context history")


@router.get("/metrics", response_model=ContextMetricsAggregateResponse)
async def get_context_metrics(
    user_id: UUID,
    limit: int = Query(default=100, ge=1, le=1000),
    session: Session = Depends(get_db),
) -> ContextMetricsAggregateResponse:
    """Aggregated CCC observability metrics for a user."""
    try:
        analytics = CognitiveAnalytics(session)
        stats = analytics.get_context_composition_performance(user_id, limit=limit)
        return ContextMetricsAggregateResponse(**stats)
    except Exception as e:
        logger.error(f"Context metrics error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch context metrics")
