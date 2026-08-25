"""
Memory Compression Optimizer

Targets continuous storage reduction while preserving reasoning quality:
reclaims embeddings for memories that are no longer retrieval-eligible
(archived/forgotten — safe to regenerate if the memory is ever revived,
since the source memory row itself is never deleted), and reports the
combined storage picture after Day 7/8's other compression levers
(duplicate memory merging, duplicate concept merging, dead graph node
pruning) have run earlier in the same dream session.
"""
import logging
from typing import Dict
from uuid import UUID

from sqlalchemy.orm import Session

from neurowave_engine.db.models import Memory, MemoryEmbedding, CognitiveMemoryStateEnum
from neurowave_engine.services.token_budget_optimizer import TokenBudgetOptimizer

logger = logging.getLogger(__name__)

INACTIVE_STATES = (CognitiveMemoryStateEnum.ARCHIVED, CognitiveMemoryStateEnum.FORGOTTEN)


class CompressionOptimizer:
    """Reclaims storage from memories/embeddings that no longer earn their keep."""

    def __init__(self, session: Session):
        self.session = session

    def optimize(self, user_id: UUID) -> Dict:
        """
        Returns:
            Dict with embeddings_reclaimed, total/active memory counts,
            token estimates, and the resulting storage_compression_ratio.
        """
        all_memories = self.session.query(Memory).filter(Memory.user_id == user_id).all()
        inactive_ids = {m.id for m in all_memories if m.cognitive_state in INACTIVE_STATES}

        embeddings_reclaimed = 0
        if inactive_ids:
            stray_embeddings = self.session.query(MemoryEmbedding).filter(
                MemoryEmbedding.memory_id.in_(inactive_ids)
            ).all()
            embeddings_reclaimed = len(stray_embeddings)
            for embedding in stray_embeddings:
                self.session.delete(embedding)
            self.session.commit()

        active_memories = [m for m in all_memories if m.id not in inactive_ids]
        optimizer = TokenBudgetOptimizer()
        active_tokens = sum(optimizer.estimate_tokens(m.content or "") for m in active_memories)
        total_tokens = sum(optimizer.estimate_tokens(m.content or "") for m in all_memories)
        compression_ratio = (
            max(0.0, (total_tokens - active_tokens) / total_tokens) if total_tokens > 0 else 0.0
        )

        return {
            "embeddings_reclaimed": embeddings_reclaimed,
            "total_memories": len(all_memories),
            "active_memories": len(active_memories),
            "active_token_estimate": active_tokens,
            "total_token_estimate": total_tokens,
            "storage_compression_ratio": round(compression_ratio, 4),
        }
