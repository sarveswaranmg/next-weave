"""
Memory — the zero-server, mem0-style entry point.

    from neurowave import Memory

    m = Memory()  # local ./neurowave.db, no Docker/Postgres/Redis/Celery
    m.chat(user_id="alice", message="I'm building a Rust backend for a startup called Nexus.")
    m.chat(user_id="alice", message="What language am I using again?")

Runs the exact same `RuntimeOrchestrator` cognitive pipeline as the hosted
server, in-process against a local SQLite file, instead of over HTTP against
a running NeuroWeave deployment. For a multi-tenant, horizontally-scaled
deployment, use `CognitiveAgent`/`NeuroWeaveClient` against a real server
instead — this class is for single-process, single-tenant embedding (a CLI
tool, a notebook, a small service) where standing up infrastructure isn't
worth it.

Requires the `neurowave-engine` package (`pip install "neurowave[embedded]"`).
"""
import uuid
from typing import Any, Dict, List, Optional
from uuid import UUID

try:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "Memory requires the embedded extra: pip install \"neurowave[embedded]\""
    ) from e

try:
    from neurowave_engine.db.models import Tenant
    from neurowave_engine.db.database import Base
    from neurowave_engine.retrieval.engine import MemoryRetrievalEngine
    from neurowave_engine.services.data_deletion_service import DataDeletionService
    from neurowave_engine.services.runtime_orchestrator import RuntimeOrchestrator
    from neurowave_engine.services.tenancy import get_or_create_owned_user
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "Memory requires the embedded extra: pip install \"neurowave[embedded]\""
    ) from e

# Fixed namespace so an arbitrary caller-supplied string user_id (e.g.
# "alice") maps deterministically to the same UUID every time, across
# process restarts, without the caller having to generate/track UUIDs
# themselves - the rest of the pipeline (RuntimeOrchestrator, the `users`
# table's FK) is UUID-typed throughout.
_USER_ID_NAMESPACE = uuid.UUID("2f1a9e2a-3c9a-4a5b-8f1e-8b6a2c9d4e10")


def _to_uuid(value: Any) -> UUID:
    try:
        return UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return uuid.uuid5(_USER_ID_NAMESPACE, str(value))


class Memory:
    """Embedded, single-tenant NeuroWeave memory layer — no server required."""

    def __init__(
        self,
        db_path: str = "./neurowave.db",
        provider: str = "google",
        model: Optional[str] = None,
        tenant_name: str = "local",
    ):
        self.provider = provider
        self.model = model
        engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        self._session_factory = sessionmaker(bind=engine)
        self._retrieval_engine = MemoryRetrievalEngine()
        self._tenant_id = self._get_or_create_tenant(tenant_name)

    def _get_or_create_tenant(self, name: str) -> UUID:
        session = self._session_factory()
        try:
            tenant = session.query(Tenant).filter(Tenant.name == name).first()
            if tenant:
                return tenant.id
            tenant = Tenant(id=uuid.uuid4(), name=name, email=f"{name}@local.neurowave")
            session.add(tenant)
            session.commit()
            session.refresh(tenant)
            return tenant.id
        finally:
            session.close()

    def chat(self, user_id: str, message: str, **kwargs: Any) -> Dict[str, Any]:
        """Run one full cognitive turn (memory + world model + predictive
        recall + context composition + LLM call) and return the response."""
        session = self._session_factory()
        try:
            result = RuntimeOrchestrator(session).chat(
                user_id=_to_uuid(user_id),
                tenant_id=self._tenant_id,
                message=message,
                provider=kwargs.pop("provider", self.provider),
                model=kwargs.pop("model", self.model),
                schedule_background=kwargs.pop("schedule_background", False),
                **kwargs,
            )
            result["user_id"] = user_id
            return result
        finally:
            session.close()

    def add(self, user_id: str, content: str) -> Dict[str, Any]:
        """Store one piece of content directly as a memory, without running
        a full chat turn (no LLM call)."""
        session = self._session_factory()
        try:
            uid = _to_uuid(user_id)
            get_or_create_owned_user(session, uid, self._tenant_id)
            memory = RuntimeOrchestrator(session).ingest(uid, content)
            return {
                "id": str(memory.id),
                "content": memory.content,
                "memory_type": memory.memory_type.value,
                "importance_score": memory.importance_score,
            }
        finally:
            session.close()

    def search(self, query: str, user_id: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """Retrieve the most relevant memories for a query, ranked by the
        same cognitive scoring the chat pipeline uses internally."""
        session = self._session_factory()
        try:
            memories, _latency_ms = self._retrieval_engine.retrieve_relevant_memories(
                session, _to_uuid(user_id), query, top_k=top_k,
            )
            return [
                {
                    "id": str(m.id),
                    "content": m.content,
                    "memory_type": m.memory_type.value,
                    "importance_score": m.importance_score,
                }
                for m in memories
            ]
        finally:
            session.close()

    def forget_user(self, user_id: str) -> Dict[str, Any]:
        """GDPR/CCPA right to be forgotten: permanently delete all of this
        user's data."""
        session = self._session_factory()
        try:
            counts = DataDeletionService(session).delete_user(_to_uuid(user_id))
            return {"user_id": user_id, "deleted_counts": counts}
        finally:
            session.close()

    def close(self) -> None:
        pass

    def __enter__(self) -> "Memory":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
