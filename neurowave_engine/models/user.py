"""User repository and operations"""
import logging
from typing import Optional
from uuid import UUID
from sqlalchemy.orm import Session
from neurowave_engine.db.models import User

logger = logging.getLogger(__name__)


class UserRepository:
    """Repository for user operations"""

    @staticmethod
    def get_or_create(session: Session, external_id: str, name: Optional[str] = None, email: Optional[str] = None) -> User:
        """Get existing user or create new one"""
        user = session.query(User).filter(User.external_id == external_id).first()
        
        if user:
            return user
        
        user = User(
            external_id=external_id,
            name=name,
            email=email,
        )
        session.add(user)
        session.commit()
        logger.info(f"Created new user: {external_id}")
        return user

    @staticmethod
    def get_by_id(session: Session, user_id: UUID) -> Optional[User]:
        """Get user by ID"""
        return session.query(User).filter(User.id == user_id).first()

    @staticmethod
    def get_by_external_id(session: Session, external_id: str) -> Optional[User]:
        """Get user by external ID"""
        return session.query(User).filter(User.external_id == external_id).first()
