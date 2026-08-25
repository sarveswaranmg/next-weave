"""FastAPI routes for memory retrieval"""
import logging
import time
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from neurowave_engine.db.database import get_db
from neurowave_engine.db.models import MemoryTypeEnum
from neurowave_engine.schemas.memory import (
    MemoryRetrievalRequest,
    MemoryRetrievalResponse,
    MemoryReconstructRequest,
    MemoryReconstructResponse,
    MemoryResponse,
    CompressedContext,
)
from neurowave_engine.retrieval.engine import memory_retrieval_engine
from neurowave_engine.retrieval.reconstruction import context_reconstruction_service

router = APIRouter(prefix="/memory", tags=["retrieval"])
logger = logging.getLogger(__name__)


@router.post("/retrieve", response_model=MemoryRetrievalResponse)
def retrieve_memories(
    request: MemoryRetrievalRequest,
    session: Session = Depends(get_db),
) -> MemoryRetrievalResponse:
    """
    Retrieve relevant memories for a query.

    Returns semantic similarities rather than raw chat history.
    """
    start_time = time.time()

    try:
        # Retrieve relevant memories
        retrieved, retrieval_latency = memory_retrieval_engine.retrieve_relevant_memories(
            session=session,
            user_id=request.user_id,
            query=request.query,
            top_k=request.top_k or 10,
            memory_types=request.memory_types,
            min_importance=request.min_importance or 0.0,
        )

        if not retrieved:
            return MemoryRetrievalResponse(
                retrieved_memories=[],
                compressed_context=CompressedContext(
                    user_profile="No prior context.",
                    relevant_memories=[],
                    context_summary="No relevant memories found.",
                    estimated_tokens=0,
                ),
                retrieval_latency_ms=retrieval_latency,
                context_token_reduction_percent=0.0,
            )

        # Compress context
        compressed = memory_retrieval_engine.compress_context(
            memories=retrieved,
            query=request.query,
        )

        # Convert to response format
        memory_responses = [
            MemoryResponse(
                id=m.id,
                user_id=m.user_id,
                memory_type=m.memory_type,
                content=m.content,
                summary=m.summary,
                importance_score=m.importance_score,
                reinforcement_count=m.reinforcement_count,
                access_count=m.access_count,
                last_accessed=m.last_accessed,
                created_at=m.created_at,
                updated_at=m.updated_at,
                metadata=m.extra_metadata,
            )
            for m in retrieved
        ]

        # Calculate reduction percent
        raw_tokens = sum(len(m.content) // 4 for m in retrieved)
        reduction_percent = (
            ((raw_tokens - compressed.estimated_tokens) / raw_tokens * 100)
            if raw_tokens > 0
            else 0
        )

        total_latency = (time.time() - start_time) * 1000

        return MemoryRetrievalResponse(
            retrieved_memories=memory_responses,
            compressed_context=compressed,
            retrieval_latency_ms=total_latency,
            context_token_reduction_percent=reduction_percent,
        )

    except Exception as e:
        logger.error(f"Memory retrieval error: {e}")
        raise HTTPException(status_code=500, detail=f"Retrieval failed: {str(e)}")


@router.post("/reconstruct", response_model=MemoryReconstructResponse)
def reconstruct_context(
    request: MemoryReconstructRequest,
    session: Session = Depends(get_db),
) -> MemoryReconstructResponse:
    """
    Reconstruct compressed context for LLM injection.

    Minimizes token usage while maintaining relevance.
    """
    start_time = time.time()

    try:
        context, token_count, latency = context_reconstruction_service.reconstruct_context(
            session=session,
            user_id=request.user_id,
            query=request.query,
            include_procedural=request.include_procedural,
            context_token_limit=request.context_token_limit,
        )

        total_latency = (time.time() - start_time) * 1000

        return MemoryReconstructResponse(
            reconstructed_context=context,
            source_memory_count=10,  # This would be retrieved from logs
            estimated_tokens=token_count,
            reconstruction_latency_ms=total_latency,
        )

    except Exception as e:
        logger.error(f"Context reconstruction error: {e}")
        raise HTTPException(
            status_code=500, detail=f"Reconstruction failed: {str(e)}"
        )
