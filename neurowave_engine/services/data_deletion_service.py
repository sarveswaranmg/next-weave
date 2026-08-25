"""
Data Deletion Service (GDPR / CCPA "right to be forgotten")

Permanently and irreversibly deletes every record associated with a user
across every table NeuroWeave has accumulated through Days 1-10 — the one
place in the codebase where "soft" (archive/forget) isn't good enough,
since the whole point of a deletion request is that the data must
actually be gone.
"""
import logging
from typing import Dict
from uuid import UUID

from sqlalchemy.orm import Session as OrmSession

from neurowave_engine.db.models import (
    User, Memory, MemoryEmbedding, RetrievalLog, MemoryConsolidation,
    ConceptMemory, MemoryCluster, ConceptRelationship, ConsolidationMetrics,
    IdentityNode, IdentityRelationship, IdentityHistory,
    PredictiveRecallLog, ContextSnapshot, ContextMetrics, MemoryEvent,
    DreamSession, KnowledgeSynthesis, IdentityEvolutionEvent,
    WorldEntity, WorldRelationship, Project, ArchitecturalDecision,
    BenchmarkRun, RuntimeMetrics, Session as UserSession,
)

logger = logging.getLogger(__name__)


class DataDeletionService:
    """Hard-deletes every trace of a user's data — GDPR/CCPA "right to be forgotten"."""

    def __init__(self, session: OrmSession):
        self.session = session

    def delete_user(self, user_id: UUID) -> Dict:
        """
        Delete all data for a user across every table (children before
        parents, respecting foreign keys). Returns a per-table row count
        for audit logging.
        """
        counts: Dict[str, int] = {}

        memory_ids = [m.id for m in self.session.query(Memory.id).filter(Memory.user_id == user_id).all()]
        context_snapshot_ids = [
            c.id for c in self.session.query(ContextSnapshot.id).filter(ContextSnapshot.user_id == user_id).all()
        ]

        # Children before parents, respecting foreign keys.
        counts["memory_embeddings"] = self._delete_by_fk(MemoryEmbedding, "memory_id", memory_ids)
        counts["memory_events"] = self._delete(MemoryEvent, user_id)
        counts["context_metrics"] = self._delete_by_fk(ContextMetrics, "snapshot_id", context_snapshot_ids)
        counts["knowledge_synthesis"] = self._delete(KnowledgeSynthesis, user_id)
        counts["identity_evolution_events"] = self._delete(IdentityEvolutionEvent, user_id)

        counts["memory_consolidations"] = self._delete(MemoryConsolidation, user_id)
        counts["retrieval_logs"] = self._delete(RetrievalLog, user_id)
        counts["memory_clusters"] = self._delete(MemoryCluster, user_id)
        counts["concept_relationships"] = self._delete(ConceptRelationship, user_id)
        counts["consolidation_metrics"] = self._delete(ConsolidationMetrics, user_id)
        counts["identity_relationships"] = self._delete(IdentityRelationship, user_id)
        counts["identity_history"] = self._delete(IdentityHistory, user_id)
        counts["predictive_recall_logs"] = self._delete(PredictiveRecallLog, user_id)
        counts["world_relationships"] = self._delete(WorldRelationship, user_id)
        counts["architectural_decisions"] = self._delete(ArchitecturalDecision, user_id)
        counts["benchmark_runs"] = self._delete(BenchmarkRun, user_id)
        counts["runtime_metrics"] = self._delete(RuntimeMetrics, user_id)
        counts["dream_sessions"] = self._delete(DreamSession, user_id)
        counts["context_snapshots"] = self._delete(ContextSnapshot, user_id)
        counts["projects"] = self._delete(Project, user_id)
        counts["world_entities"] = self._delete(WorldEntity, user_id)
        counts["identity_nodes"] = self._delete(IdentityNode, user_id)
        counts["concept_memories"] = self._delete(ConceptMemory, user_id)
        counts["memories"] = self._delete(Memory, user_id)
        counts["sessions"] = self._delete(UserSession, user_id)

        user = self.session.query(User).filter(User.id == user_id).first()
        if user:
            self.session.delete(user)
            counts["users"] = 1
        else:
            counts["users"] = 0

        self.session.commit()
        logger.info(f"Deleted all data for user {user_id}: {counts}")
        return counts

    def _delete(self, model, user_id: UUID) -> int:
        count = self.session.query(model).filter(model.user_id == user_id).count()
        self.session.query(model).filter(model.user_id == user_id).delete(synchronize_session=False)
        return count

    def _delete_by_fk(self, model, fk_field: str, ids) -> int:
        if not ids:
            return 0
        column = getattr(model, fk_field)
        count = self.session.query(model).filter(column.in_(ids)).count()
        self.session.query(model).filter(column.in_(ids)).delete(synchronize_session=False)
        return count
