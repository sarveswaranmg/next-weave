"""Database connection and session management"""
from contextlib import contextmanager
import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, Session, sessionmaker

from neurowave_engine.core.config import settings

logger = logging.getLogger(__name__)

Base = declarative_base()

# Engines/sessionmakers are built lazily, on first actual use, rather than
# at import time. This module is transitively imported by nearly every
# service (anything that touches `Base`/models), and `settings.database_url`
# defaults to a Postgres DSN - eagerly building a Postgres-shaped engine here
# would force `asyncpg`/`psycopg2-binary` to be importable just to import
# this module, even for an embedded/SQLite-only caller (see the `neurowave`
# SDK's `Memory`, which builds its own separate SQLite engine directly and
# never touches any of this).
_sync_engine = None
_async_engine = None
_SessionLocal = None
_AsyncSessionLocal = None


def _async_database_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("sqlite://"):
        return url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    return url


def _pool_kwargs() -> dict:
    # SQLite's pools (used for local/test/embedded runs) don't accept
    # pool_size/max_overflow.
    if settings.database_url.startswith("sqlite://"):
        return {}
    return {"pool_size": settings.database_pool_size, "max_overflow": settings.database_max_overflow}


def get_sync_engine():
    global _sync_engine
    if _sync_engine is None:
        _sync_engine = create_engine(
            settings.database_url, echo=settings.debug, pool_pre_ping=True, **_pool_kwargs(),
        )
    return _sync_engine


def get_async_engine():
    global _async_engine
    if _async_engine is None:
        from sqlalchemy.ext.asyncio import create_async_engine
        _async_engine = create_async_engine(
            _async_database_url(settings.database_url), echo=settings.debug, pool_pre_ping=True, **_pool_kwargs(),
        )
    return _async_engine


def _session_local() -> sessionmaker:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(get_sync_engine(), expire_on_commit=False)
    return _SessionLocal


def _async_session_local():
    global _AsyncSessionLocal
    if _AsyncSessionLocal is None:
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
        _AsyncSessionLocal = async_sessionmaker(get_async_engine(), class_=AsyncSession, expire_on_commit=False)
    return _AsyncSessionLocal


async def get_async_session():
    """Get async database session"""
    async with _async_session_local()() as session:
        try:
            yield session
        except Exception as e:
            logger.error(f"Database session error: {e}")
            raise


def get_db_session() -> Session:
    """Get synchronous database session"""
    return _session_local()()


def get_db():
    """FastAPI dependency yielding a synchronous session that auto-closes"""
    session = _session_local()()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def get_sync_session():
    """Context manager for synchronous sessions"""
    session = _session_local()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
