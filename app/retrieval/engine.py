"""Memory retrieval engine with cognitive importance scoring"""
import logging
import math
from typing import List, Optional, Tuple
from uuid import UUID
from datetime import datetime, timedelta
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import Session
from app.db.models import Memory, MemoryEmbedding, MemoryTypeEnum, CognitiveMemoryStateEnum
from app.schemas.memory import MemoryResponse, CompressedContext
from app.memory.embeddings import embedding_service

logger = logging.getLogger(__name__)


class MemoryRetrievalEngine:
    """
    Cognitive retrieval engine for memories.

    Retrieves only relevant structured memories instead of raw conversations.
    """

    def __init__(self):
        self.embedding_service = embedding_service

    def retrieve_relevant_memories(
        self,
        session: Session,
        user_id: UUID,
        query: str,
        top_k: int = 10,
        memory_types: Optional[List[MemoryTypeEnum]] = None,
        min_importance: float = 0.0,
    ) -> Tuple[List[Memory], float]:
        """
        Retrieve relevant memories using cognitive importance scoring.
        
        Ranking formula: retrieval_score = (
            semantic_similarity * 0.40 +
            importance_score * 0.30 +
            recency * 0.15 +
            reinforcement * 0.15
        )

        Args:
            session: Database session
            user_id: User ID
            query: Query text
            top_k: Number of results to return
            memory_types: Optional filter by memory type
            min_importance: Minimum importance score filter

        Returns:
            Tuple of (retrieved memories, query latency in ms)
        """
        import time
        start_time = time.time()

        try:
            # Generate query embedding
            query_embedding = self.embedding_service.embed_text(query)

            # Build base query - exclude archived memories unless explicitly requested
            base_query = select(Memory).where(
                and_(
                    Memory.user_id == user_id,
                    Memory.importance_score >= min_importance,
                    Memory.cognitive_state != CognitiveMemoryStateEnum.ARCHIVED,
                )
            )

            # Apply memory type filter
            if memory_types:
                base_query = base_query.where(Memory.memory_type.in_(memory_types))

            # Get all candidate memories
            all_memories = session.execute(base_query).scalars().all()

            # Score each memory using cognitive importance ranking
            scored_memories = []
            now = datetime.utcnow()
            
            for memory in all_memories:
                # Calculate semantic similarity
                semantic_sim = 0.0
                if memory.embeddings:
                    embedding = memory.embeddings[0]
                    semantic_sim = self._cosine_similarity(
                        query_embedding,
                        self._deserialize_embedding(embedding.embedding),
                    )
                
                # Calculate recency score (newer = higher)
                days_old = (now - memory.created_at).days
                recency = max(0.0, 1.0 - (days_old / 365.0))  # Normalize to 1 year
                
                # Calculate reinforcement score (based on reinforcement count and strength)
                reinforcement = min(
                    1.0,
                    (memory.reinforcement_count * 0.1) * memory.memory_strength
                )
                
                # Get importance score (use new cognitive importance if available)
                importance = memory.importance_score if memory.importance_score > 0 else 0.5
                
                # Apply cognitive ranking formula
                retrieval_score = (
                    semantic_sim * 0.40 +
                    importance * 0.30 +
                    recency * 0.15 +
                    reinforcement * 0.15
                )
                
                scored_memories.append((memory, retrieval_score))

            # Sort by retrieval score (descending)
            scored_memories.sort(key=lambda x: x[1], reverse=True)
            retrieved = [memory for memory, _ in scored_memories[:top_k]]

            # Update access counts
            for memory in retrieved:
                memory.access_count = (memory.access_count or 0) + 1
                memory.last_accessed = datetime.utcnow()
            session.commit()

            latency_ms = (time.time() - start_time) * 1000
            logger.info(
                f"Retrieved {len(retrieved)} memories for user {user_id} "
                f"using cognitive ranking in {latency_ms:.2f}ms"
            )

            return retrieved, latency_ms

        except Exception as e:
            logger.error(f"Memory retrieval error: {e}")
            latency_ms = (time.time() - start_time) * 1000
            return [], latency_ms

    def compress_context(
        self,
        memories: List[Memory],
        query: str,
        token_limit: int = 2000,
    ) -> CompressedContext:
        """
        Compress retrieved memories into optimized context.

        Args:
            memories: Retrieved memories
            query: Original query
            token_limit: Maximum token limit for context

        Returns:
            Compressed context object
        """
        # Group memories by type
        by_type = {}
        for memory in memories:
            if memory.memory_type not in by_type:
                by_type[memory.memory_type] = []
            by_type[memory.memory_type].append(memory)

        # Build user profile
        user_profile_lines = []

        # Add procedural memories
        if MemoryTypeEnum.PROCEDURAL in by_type:
            user_profile_lines.append("Interaction Style:")
            for mem in by_type[MemoryTypeEnum.PROCEDURAL][:3]:
                user_profile_lines.append(f"- {mem.content}")

        # Add identity memories
        if MemoryTypeEnum.IDENTITY in by_type:
            user_profile_lines.append("\nUser Profile:")
            for mem in by_type[MemoryTypeEnum.IDENTITY][:3]:
                user_profile_lines.append(f"- {mem.content}")

        # Add semantic memories
        if MemoryTypeEnum.SEMANTIC in by_type:
            user_profile_lines.append("\nPreferences & Knowledge:")
            for mem in by_type[MemoryTypeEnum.SEMANTIC][:3]:
                user_profile_lines.append(f"- {mem.content}")

        user_profile = "\n".join(user_profile_lines) if user_profile_lines else "No prior context."

        # Format relevant memories
        relevant_memory_lines = [f"Query: {query}", "\nRelevant Context:"]
        token_count = self._estimate_tokens(user_profile)

        for memory in memories:
            if token_count >= token_limit:
                break

            line = f"- [{memory.memory_type.value}] {memory.summary or memory.content}"
            tokens = self._estimate_tokens(line)

            if token_count + tokens <= token_limit:
                relevant_memory_lines.append(line)
                token_count += tokens

        context_summary = "\n".join(relevant_memory_lines)

        # Calculate token reduction
        total_tokens_if_raw = self._estimate_tokens(
            "\n".join([f"- {m.content}" for m in memories])
        )
        reduction_percent = (
            ((total_tokens_if_raw - token_count) / total_tokens_if_raw * 100)
            if total_tokens_if_raw > 0
            else 0
        )

        return CompressedContext(
            user_profile=user_profile,
            relevant_memories=[m.summary or m.content for m in memories],
            context_summary=context_summary,
            estimated_tokens=token_count,
        )

    @staticmethod
    def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors"""
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0

        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        magnitude1 = math.sqrt(sum(a * a for a in vec1))
        magnitude2 = math.sqrt(sum(b * b for b in vec2))

        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0

        return dot_product / (magnitude1 * magnitude2)

    @staticmethod
    def _deserialize_embedding(embedding_str: str) -> List[float]:
        """Deserialize embedding from pgvector format"""
        try:
            # Remove brackets and parse
            if isinstance(embedding_str, str):
                embedding_str = embedding_str.strip("[]")
                return [float(x.strip()) for x in embedding_str.split(",")]
            return embedding_str
        except Exception as e:
            logger.warning(f"Failed to deserialize embedding: {e}")
            return []

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Rough token estimation (1 token ≈ 4 characters)"""
        return len(text) // 4


# Singleton instance
memory_retrieval_engine = MemoryRetrievalEngine()
