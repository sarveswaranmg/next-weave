"""FastAPI routes for memory ingestion"""
import logging
import time
from typing import List
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.memory import (
    MemoryIngestRequest,
    MemoryIngestResponse,
    ExtractedMemory,
)
from app.services.extraction import memory_extraction_service
from app.services.scoring import scoring_engine
from app.memory.embeddings import embedding_service
from app.memory.storage import memory_storage_service

router = APIRouter(prefix="/memory", tags=["memory"])
logger = logging.getLogger(__name__)


@router.post("/ingest", response_model=MemoryIngestResponse)
def ingest_memories(
    request: MemoryIngestRequest,
    session: Session = Depends(get_db),
) -> MemoryIngestResponse:
    """
    Ingest conversation and extract memories.

    This is the main entry point for the memory pipeline:
    1. Extract memories from conversation
    2. Score importance
    3. Generate embeddings
    4. Store in database
    """
    start_time = time.time()

    try:
        # Extract memories from conversation
        extracted = memory_extraction_service.extract_memories(request.conversation)

        if not extracted:
            return MemoryIngestResponse(
                extracted_memories=[],
                total_tokens_saved=0,
                ingestion_latency_ms=(time.time() - start_time) * 1000,
            )

        # Score memories
        scored_memories = []
        for memory in extracted:
            memory.importance_score = scoring_engine.score(memory)
            if memory.importance_score >= 0.3:  # Only store significant memories
                scored_memories.append(memory)

        if not scored_memories:
            return MemoryIngestResponse(
                extracted_memories=[],
                total_tokens_saved=0,
                ingestion_latency_ms=(time.time() - start_time) * 1000,
            )

        # Generate embeddings
        content_to_embed = [
            m.summary or m.content for m in scored_memories
        ]
        embeddings = embedding_service.embed_batch(content_to_embed)

        # Store memories
        memory_embedding_pairs = list(zip(scored_memories, embeddings))
        stored = memory_storage_service.store_memories_batch(
            session=session,
            user_id=request.user_id,
            memories=memory_embedding_pairs,
        )

        # Calculate token savings (naive approach - entire conversation)
        conversation_tokens = len(request.conversation) // 4
        stored_tokens = sum(len(m.content) // 4 for m in scored_memories)
        tokens_saved = max(0, conversation_tokens - stored_tokens)

        logger.info(
            f"Ingested {len(stored)} memories for user {request.user_id}, "
            f"saved {tokens_saved} tokens"
        )

        return MemoryIngestResponse(
            extracted_memories=scored_memories,
            total_tokens_saved=tokens_saved,
            ingestion_latency_ms=(time.time() - start_time) * 1000,
        )

    except Exception as e:
        logger.error(f"Memory ingestion error: {e}")
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")
