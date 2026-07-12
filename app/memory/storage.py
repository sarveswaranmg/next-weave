"""Memory storage service"""
import logging
from typing import List, Optional
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.models import Memory, MemoryEmbedding, User, MemoryTypeEnum
from app.schemas.memory import MemoryCreate, ExtractedMemory, MemoryResponse
from datetime import datetime

logger = logging.getLogger(__name__)


class MemoryStorageService:
    """Service for storing and managing memories"""

    def store_memory(
        self,
        session: Session,
        user_id: UUID,
        memory: ExtractedMemory,
        embedding: Optional[List[float]] = None,
    ) -> Memory:
        """
        Store a memory in the database.

        Args:
            session: Database session
            user_id: User ID
            memory: Extracted memory object
            embedding: Optional embedding vector

        Returns:
            Created memory object
        """
        try:
            # Create memory record
            db_memory = Memory(
                user_id=user_id,
                memory_type=memory.memory_type,
                content=memory.content,
                summary=memory.summary,
                importance_score=memory.importance_score,
                extra_metadata=memory.metadata,
            )

            session.add(db_memory)
            session.flush()

            # Store embedding if provided
            if embedding:
                db_embedding = MemoryEmbedding(
                    memory_id=db_memory.id,
                    embedding=self._serialize_embedding(embedding),
                    model="text-embedding-3-small",
                )
                session.add(db_embedding)

            session.commit()
            logger.info(
                f"Stored memory {db_memory.id} for user {user_id}: {memory.memory_type}"
            )

            return db_memory

        except Exception as e:
            session.rollback()
            logger.error(f"Memory storage error: {e}")
            raise

    def store_memories_batch(
        self,
        session: Session,
        user_id: UUID,
        memories: List[tuple[ExtractedMemory, Optional[List[float]]]],
    ) -> List[Memory]:
        """
        Store multiple memories in batch.

        Args:
            session: Database session
            user_id: User ID
            memories: List of (memory, embedding) tuples

        Returns:
            List of created memory objects
        """
        try:
            stored_memories = []

            for memory, embedding in memories:
                db_memory = Memory(
                    user_id=user_id,
                    memory_type=memory.memory_type,
                    content=memory.content,
                    summary=memory.summary,
                    importance_score=memory.importance_score,
                    extra_metadata=memory.metadata,
                )
                session.add(db_memory)
                stored_memories.append(db_memory)

            session.flush()

            # Store embeddings
            for i, (memory, embedding) in enumerate(memories):
                if embedding:
                    db_embedding = MemoryEmbedding(
                        memory_id=stored_memories[i].id,
                        embedding=self._serialize_embedding(embedding),
                        model="text-embedding-3-small",
                    )
                    session.add(db_embedding)

            session.commit()
            logger.info(f"Stored {len(stored_memories)} memories for user {user_id}")

            return stored_memories

        except Exception as e:
            session.rollback()
            logger.error(f"Batch memory storage error: {e}")
            raise

    def get_memories_by_user(
        self,
        session: Session,
        user_id: UUID,
        memory_type: Optional[MemoryTypeEnum] = None,
        limit: int = 100,
    ) -> List[Memory]:
        """Get memories for a user"""
        try:
            query = select(Memory).where(Memory.user_id == user_id)

            if memory_type:
                query = query.where(Memory.memory_type == memory_type)

            query = query.order_by(Memory.importance_score.desc()).limit(limit)

            return session.execute(query).scalars().all()

        except Exception as e:
            logger.error(f"Failed to retrieve memories: {e}")
            return []

    def update_memory_access(
        self,
        session: Session,
        memory_id: UUID,
    ) -> None:
        """Update memory access count and timestamp"""
        try:
            memory = session.query(Memory).filter(Memory.id == memory_id).first()
            if memory:
                memory.access_count += 1
                memory.last_accessed = datetime.utcnow()
                session.commit()
        except Exception as e:
            logger.error(f"Failed to update memory access: {e}")
            session.rollback()

    @staticmethod
    def _serialize_embedding(embedding: List[float]) -> str:
        """Serialize embedding for pgvector storage"""
        # Convert to pgvector format: "[0.1, 0.2, 0.3, ...]"
        return "[" + ",".join(str(e) for e in embedding) + "]"


# Singleton instance
memory_storage_service = MemoryStorageService()
