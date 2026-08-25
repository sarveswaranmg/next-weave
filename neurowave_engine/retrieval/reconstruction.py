"""Context reconstruction service"""
import logging
from typing import List, Optional, Tuple
from uuid import UUID
from sqlalchemy.orm import Session
from neurowave_engine.db.models import Memory, MemoryTypeEnum, RetrievalLog
from neurowave_engine.retrieval.engine import memory_retrieval_engine
from datetime import datetime
import json

logger = logging.getLogger(__name__)


class ContextReconstructionService:
    """
    Service for reconstructing compressed context for LLM injection.

    Minimizes token usage while maximizing relevance.
    """

    def __init__(self):
        self.retrieval_engine = memory_retrieval_engine

    def reconstruct_context(
        self,
        session: Session,
        user_id: UUID,
        query: str,
        include_procedural: bool = True,
        context_token_limit: Optional[int] = None,
    ) -> Tuple[str, int, float]:
        """
        Reconstruct compressed context for LLM.

        Args:
            session: Database session
            user_id: User ID
            query: Query/prompt
            include_procedural: Whether to include procedural memories
            context_token_limit: Maximum token limit

        Returns:
            Tuple of (reconstructed context, estimated tokens, latency_ms)
        """
        import time
        start_time = time.time()

        try:
            # Determine memory types to retrieve
            memory_types = [
                MemoryTypeEnum.PROCEDURAL,
                MemoryTypeEnum.IDENTITY,
                MemoryTypeEnum.SEMANTIC,
                MemoryTypeEnum.EPISODIC,
            ]

            if not include_procedural:
                memory_types.remove(MemoryTypeEnum.PROCEDURAL)

            # Retrieve relevant memories
            relevant_memories, retrieval_latency = self.retrieval_engine.retrieve_relevant_memories(
                session=session,
                user_id=user_id,
                query=query,
                top_k=10,
                memory_types=memory_types,
                min_importance=0.2,
            )

            if not relevant_memories:
                return "", 0, time.time() - start_time

            # Compress context
            compressed = self.retrieval_engine.compress_context(
                memories=relevant_memories,
                query=query,
                token_limit=context_token_limit or 2000,
            )

            # Log retrieval
            self._log_retrieval(
                session=session,
                user_id=user_id,
                query=query,
                retrieved_memory_ids=[str(m.id) for m in relevant_memories],
                retrieval_latency_ms=retrieval_latency,
                context_token_count=compressed.estimated_tokens,
            )

            latency_ms = (time.time() - start_time) * 1000

            return (
                compressed.context_summary,
                compressed.estimated_tokens,
                latency_ms,
            )

        except Exception as e:
            logger.error(f"Context reconstruction error: {e}")
            return "", 0, time.time() - start_time

    def _log_retrieval(
        self,
        session: Session,
        user_id: UUID,
        query: str,
        retrieved_memory_ids: List[str],
        retrieval_latency_ms: float,
        context_token_count: int,
    ) -> None:
        """Log retrieval operation for analytics"""
        try:
            log = RetrievalLog(
                user_id=user_id,
                query=query,
                retrieved_memory_ids=retrieved_memory_ids,
                retrieval_latency_ms=retrieval_latency_ms,
                context_token_count=context_token_count,
            )
            session.add(log)
            session.commit()
        except Exception as e:
            logger.warning(f"Failed to log retrieval: {e}")


# Singleton instance
context_reconstruction_service = ContextReconstructionService()
