"""
Shared pytest fixtures: an in-memory SQLite session plus a tenant/user
pair. Consolidates what used to be 6 near-identical per-file fixture
definitions (some named `session`, some `db_session`; some named `user`,
some `test_user`) into one place. Both name variants are kept as aliases
so existing test bodies didn't need renaming across the suite.
"""
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base, Tenant, User


@pytest.fixture
def db_session():
    # StaticPool + check_same_thread=False: FastAPI's TestClient runs sync
    # path operations in a worker thread, but a plain in-memory SQLite
    # connection is thread-affine by default - without this, any test
    # driving requests through TestClient (see test_auth_rbac.py) fails
    # with "no such table" / cross-thread sqlite3 errors even though the
    # tables were just created on the same engine.
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def session(db_session):
    """Alias of `db_session` - several test files historically used this name."""
    return db_session


@pytest.fixture
def tenant(db_session):
    t = Tenant(id=uuid.uuid4(), name="Test Tenant", email=f"tenant-{uuid.uuid4()}@example.com")
    db_session.add(t)
    db_session.commit()
    return t


@pytest.fixture
def user(db_session, tenant):
    u = User(
        id=uuid.uuid4(), tenant_id=tenant.id, external_id=f"test-user-{uuid.uuid4()}",
        name="Test User", email=f"user-{uuid.uuid4()}@example.com",
    )
    db_session.add(u)
    db_session.commit()
    return u


@pytest.fixture
def test_user(user):
    """Alias of `user` - test_consolidation.py/test_identity.py historically used this name."""
    return user
