"""Memory repository and operations"""
import logging
from typing import List, Optional
from uuid import UUID
from sqlalchemy.orm import Session
from app.db.models import Memory, MemoryTypeEnum

logger = logging.getLogger(__name__)


class MemoryRepository:
    """Repository for memory operations"""

    @staticmethod
    def get_by_id(session: Session, memory_id: UUID) -> Optional[Memory]:
        """Get memory by ID"""
        return session.query(Memory).filter(Memory.id == memory_id).first()

    @staticmethod
    def get_by_user(
        session: Session,
        user_id: UUID,
        memory_type: Optional[MemoryTypeEnum] = None,
        limit: int = 100,
    ) -> List[Memory]:
        """Get memories by user"""
        query = session.query(Memory).filter(Memory.user_id == user_id)
        
        if memory_type:
            query = query.filter(Memory.memory_type == memory_type)
        
        return query.order_by(Memory.importance_score.desc()).limit(limit).all()

    @staticmethod
    def delete(session: Session, memory_id: UUID) -> bool:
        """Delete memory by ID"""
        memory = session.query(Memory).filter(Memory.id == memory_id).first()
        
        if not memory:
            return False
        
        session.delete(memory)
        session.commit()
        logger.info(f"Deleted memory: {memory_id}")
        return True

    @staticmethod
    def update_importance(session: Session, memory_id: UUID, importance_score: float) -> bool:
        """Update memory importance score"""
        memory = session.query(Memory).filter(Memory.id == memory_id).first()
        
        if not memory:
            return False
        
        memory.importance_score = max(0.0, min(1.0, importance_score))
        session.commit()
        return True
