"""Day 5: Predictive Recall Engine API endpoints"""
import logging
import time
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from neurowave_engine.db.database import get_db
from neurowave_engine.db.models import Memory, PredictiveRecallLog
from neurowave_engine.schemas.predictive_recall import (
    GoalDetectionRequest,
    GoalDetectionResponse,
    GoalDetectionResult,
    IntentClassificationRequest,
    IntentClassificationResponse,
    IntentProbability,
    UtilityScoreRequest,
    UtilityScoreResponse,
    MemoryUtilityBreakdown,
    PredictiveRecallRequest,
    PredictiveRecallResponse,
    MemoryExplanation,
    AssembledContext,
    ContextAssembleRequest,
    ContextAssembleResponse,
    RetrievalExplanationResponse,
    UtilityWeights as UtilityWeightsSchema,
)
from neurowave_engine.services.goal_detector import goal_detector
from neurowave_engine.services.intent_classifier import intent_classifier
from neurowave_engine.services.context_analyzer import ContextAnalyzer
from neurowave_engine.services.memory_ranker import PredictiveMemoryRanker
from neurowave_engine.services.context_assembler import context_assembler
from neurowave_engine.services.predictive_recall_pipeline import PredictiveRecallPipeline
from neurowave_engine.services.utility_predictor import UtilityWeights
from neurowave_engine.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["predictive-recall"])


def _to_utility_weights(schema: Optional[UtilityWeightsSchema]) -> Optional[UtilityWeights]:
    """Convert the API-facing weights schema into the service-layer dataclass"""
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


@router.post("/goal-detect", response_model=GoalDetectionResponse)
async def detect_goal(request: GoalDetectionRequest) -> GoalDetectionResponse:
    """Infer the user's actual objective from a query (not literal keywords)"""
    start = time.time()
    result = goal_detector.detect(request.query)
    latency_ms = (time.time() - start) * 1000
    return GoalDetectionResponse(
        result=GoalDetectionResult(**result),
        detection_latency_ms=latency_ms,
    )


@router.post("/intent-classify", response_model=IntentClassificationResponse)
async def classify_intent(request: IntentClassificationRequest) -> IntentClassificationResponse:
    """Classify one or more simultaneous intents behind a query, with probabilities"""
    start = time.time()
    result = intent_classifier.classify(request.query, top_k=request.top_k)
    latency_ms = (time.time() - start) * 1000
    return IntentClassificationResponse(
        intents=[IntentProbability(**i) for i in result["intents"]],
        primary_intent=result["primary_intent"],
        classification_latency_ms=latency_ms,
    )


@router.post("/utility-score", response_model=UtilityScoreResponse)
async def score_utility(
    request: UtilityScoreRequest,
    session: Session = Depends(get_db),
) -> UtilityScoreResponse:
    """Score candidate memories for predicted usefulness against a query (not similarity)"""
    try:
        start = time.time()

        goal_result = goal_detector.detect(request.query)
        intent_result = intent_classifier.classify(request.query)
        analyzer = ContextAnalyzer(session)
        context = analyzer.analyze(
            request.user_id,
            request.query,
            goal_result["goal"],
            [i["intent"] for i in intent_result["intents"]],
        )

        memory_query = session.query(Memory).filter(Memory.user_id == request.user_id)
        if request.memory_ids:
            memory_query = memory_query.filter(Memory.id.in_(request.memory_ids))
        else:
            memory_query = memory_query.limit(settings.predictive_recall_candidate_pool_size)
        memories = memory_query.all()

        if not memories:
            raise HTTPException(status_code=404, detail="No memories found to score")

        ranker = PredictiveMemoryRanker(session, _to_utility_weights(request.weights))
        scores = ranker.predictor.predict_batch(memories, context)

        latency_ms = (time.time() - start) * 1000

        return UtilityScoreResponse(
            goal=GoalDetectionResult(**goal_result),
            scores=[MemoryUtilityBreakdown(**s) for s in scores],
            scoring_latency_ms=latency_ms,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Utility scoring error: {e}")
        raise HTTPException(status_code=500, detail=f"Utility scoring failed: {str(e)}")


@router.post("/context/assemble", response_model=ContextAssembleResponse)
async def assemble_context(
    request: ContextAssembleRequest,
    session: Session = Depends(get_db),
) -> ContextAssembleResponse:
    """Assemble a compact reasoning context from an explicit set of memories"""
    try:
        start = time.time()

        memories = session.query(Memory).filter(
            Memory.user_id == request.user_id,
            Memory.id.in_(request.memory_ids),
        ).all()

        if not memories:
            raise HTTPException(status_code=404, detail="No memories found for the given ids")

        goal_result = goal_detector.detect(request.query)
        memory_by_id = {m.id: m for m in memories}

        # These memories were explicitly chosen by the caller (not ranked by
        # this pipeline), so importance score stands in as the ranking basis
        # for section ordering within the assembled context.
        selected = [
            {
                "memory_id": m.id,
                "utility_score": m.importance_score or 0.5,
                "selection_reason": "Explicitly requested for context assembly",
                "retrieval_rank": idx + 1,
            }
            for idx, m in enumerate(memories)
        ]

        token_limit = request.token_limit or settings.predictive_recall_default_token_budget
        assembled = context_assembler.assemble(
            request.query, goal_result["goal"], selected, memory_by_id, token_limit=token_limit
        )

        latency_ms = (time.time() - start) * 1000

        return ContextAssembleResponse(
            assembled_context=AssembledContext(**assembled),
            assembly_latency_ms=latency_ms,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Context assembly error: {e}")
        raise HTTPException(status_code=500, detail=f"Context assembly failed: {str(e)}")


@router.post("/predictive-recall", response_model=PredictiveRecallResponse)
async def predictive_recall(
    request: PredictiveRecallRequest,
    session: Session = Depends(get_db),
) -> PredictiveRecallResponse:
    """
    Run the full predictive recall pipeline.

    Replaces similarity search with utility prediction: goal detection,
    intent classification, identity/concept-conditioned utility scoring,
    redundancy elimination, constrained token-budget optimization, and
    context assembly.
    """
    try:
        pipeline = PredictiveRecallPipeline(session)
        result = pipeline.run(
            user_id=request.user_id,
            query=request.query,
            token_budget=request.token_budget,
            memory_types=request.memory_types,
            weights=_to_utility_weights(request.weights),
        )

        return PredictiveRecallResponse(
            recall_id=result["recall_id"],
            goal=GoalDetectionResult(**result["goal"]),
            intents=[IntentProbability(**i) for i in result["intents"]],
            selected_memories=[MemoryExplanation(**e) for e in result["selected_memories"]],
            assembled_context=AssembledContext(**result["assembled_context"]),
            candidate_count=result["candidate_count"],
            token_budget=result["token_budget"],
            average_utility_score=result["average_utility_score"],
            latency_breakdown_ms=result["latency_breakdown_ms"],
            total_latency_ms=result["total_latency_ms"],
        )
    except Exception as e:
        logger.error(f"Predictive recall error: {e}")
        raise HTTPException(status_code=500, detail=f"Predictive recall failed: {str(e)}")


@router.get("/retrieval/explanation", response_model=RetrievalExplanationResponse)
async def get_retrieval_explanation(
    user_id: UUID,
    recall_id: Optional[UUID] = None,
    session: Session = Depends(get_db),
) -> RetrievalExplanationResponse:
    """
    Get the decision trail for a predictive recall run: why each memory was
    selected. Defaults to the user's most recent run if recall_id is omitted.
    """
    try:
        query = session.query(PredictiveRecallLog).filter(PredictiveRecallLog.user_id == user_id)
        if recall_id:
            query = query.filter(PredictiveRecallLog.id == recall_id)
        log = query.order_by(PredictiveRecallLog.created_at.desc()).first()

        if not log:
            raise HTTPException(status_code=404, detail="No predictive recall runs found for this user")

        explanations = [
            MemoryExplanation(
                memory_id=UUID(e["memory_id"]),
                memory_type=e["memory_type"],
                content="",  # Full content omitted from the log; see /memory/retrieve
                reason=e["reason"],
                utility=e["utility"],
                rank=e["rank"],
            )
            for e in (log.explanations or [])
        ]

        return RetrievalExplanationResponse(
            recall_id=log.id,
            user_id=log.user_id,
            query=log.query,
            goal=log.detected_goal or "",
            goal_confidence=log.goal_confidence or 0.0,
            intents=log.intents or {},
            explanations=explanations,
            created_at=log.created_at,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Retrieval explanation error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch explanation: {str(e)}")
