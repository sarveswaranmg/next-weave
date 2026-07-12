"""Database connection and session management"""
from sqlalchemy import create_engine, event
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base, Session, sessionmaker
from app.core.config import settings
from contextlib import contextmanager
import logging

logger = logging.getLogger(__name__)


def _async_database_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("sqlite://"):
        return url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    return url


# SQLite's pools (used for local/test runs) don't accept pool_size/max_overflow.
_is_sqlite = settings.database_url.startswith("sqlite://")
_pool_kwargs = (
    {}
    if _is_sqlite
    else {
        "pool_size": settings.database_pool_size,
        "max_overflow": settings.database_max_overflow,
    }
)

# For async operations
async_engine = create_async_engine(
    _async_database_url(settings.database_url),
    echo=settings.debug,
    pool_pre_ping=True,
    **_pool_kwargs,
)

# For synchronous operations
sync_engine = create_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
    **_pool_kwargs,
)

AsyncSessionLocal = async_sessionmaker(
    async_engine, class_=AsyncSession, expire_on_commit=False
)

SessionLocal = sessionmaker(sync_engine, expire_on_commit=False)

Base = declarative_base()


async def get_async_session() -> AsyncSession:
    """Get async database session"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception as e:
            logger.error(f"Database session error: {e}")
            raise


def get_db_session() -> Session:
    """Get synchronous database session"""
    return SessionLocal()


def get_db():
    """FastAPI dependency yielding a synchronous session that auto-closes"""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def get_sync_session():
    """Context manager for synchronous sessions"""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
