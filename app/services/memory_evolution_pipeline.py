"""
Memory Evolution Pipeline

Orchestrates one full evolution pass over a user's memory store:

    Decay Evaluation -> Duplicate Resolution -> Conflict (Obsolescence)
    Resolution -> Forgetting Decision -> Entropy Recalculation

This is what the background MemoryEvolutionWorker runs hourly/daily, and
what `POST /memory/evolve` triggers manually.
"""
import logging
import time
from typing import Dict
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import Memory, CognitiveMemoryStateEnum
from app.services.memory_decay_engine import MemoryDecayEngine
from app.services.duplicate_resolver import DuplicateResolver
from app.services.obsolete_memory_detector import ObsoleteMemoryDetector
from app.services.forgetting_engine import ForgettingEngine
from app.services.memory_lifecycle_manager import MemoryLifecycleManager
from app.services.memory_entropy import MemoryEntropyCalculator
from app.services.memory_health_monitor import MemoryHealthService

logger = logging.getLogger(__name__)

INACTIVE_STATES = (CognitiveMemoryStateEnum.ARCHIVED, CognitiveMemoryStateEnum.FORGOTTEN)


class MemoryEvolutionPipeline:
    """Runs the full Day 7 evolution pass for a user."""

    def __init__(self, session: Session):
        self.session = session
        self.decay_engine = MemoryDecayEngine(session)
        self.duplicate_resolver = DuplicateResolver(session)
        self.obsolete_detector = ObsoleteMemoryDetector(session)
        self.forgetting_engine = ForgettingEngine(session)
        self.lifecycle_manager = MemoryLifecycleManager(session)
        self.entropy_calculator = MemoryEntropyCalculator(session)

    def run(self, user_id: UUID) -> Dict:
        """Run one full evolution pass and return a summary report."""
        start = time.time()

        memories = self.session.query(Memory).filter(
            Memory.user_id == user_id,
            Memory.cognitive_state != CognitiveMemoryStateEnum.FORGOTTEN,
        ).all()

        if not memories:
            return self._empty_report(user_id, time.time() - start)

        # 1. Decay Evaluation (multi-factor strength decay, then state transitions)
        decay_results = self.decay_engine.apply_decay_batch(memories)
        for memory in memories:
            self.lifecycle_manager.evaluate_after_decay(memory)
        self.session.commit()

        # 2. Duplicate Resolution
        active_memories = [m for m in memories if m.cognitive_state not in INACTIVE_STATES]
        merge_decisions = self.duplicate_resolver.resolve(user_id, active_memories)

        # 3. Conflict / Obsolescence Resolution (on what wasn't just merged away)
        remaining = [m for m in active_memories if m.cognitive_state not in INACTIVE_STATES]
        obsolete_decisions = self.obsolete_detector.detect_and_resolve(user_id, remaining)

        # 4. Forgetting Decision (over everything still not soft-forgotten)
        still_active = self.session.query(Memory).filter(
            Memory.user_id == user_id,
            Memory.cognitive_state != CognitiveMemoryStateEnum.FORGOTTEN,
        ).all()
        forgetting_decisions = self.forgetting_engine.evaluate_batch(still_active)

        # 5. Entropy Recalculation
        final_memories = self.session.query(Memory).filter(
            Memory.user_id == user_id,
            Memory.cognitive_state != CognitiveMemoryStateEnum.FORGOTTEN,
        ).all()
        entropy = self.entropy_calculator.calculate(user_id, memories=final_memories)
        self.entropy_calculator.apply_per_memory_scores(final_memories, entropy)
        self.session.commit()

        health = MemoryHealthService(self.session).compute_health(user_id)

        total_latency_ms = (time.time() - start) * 1000

        return {
            "user_id": user_id,
            "memories_evaluated": len(memories),
            "decayed_count": len(decay_results),
            "merged_clusters": len(merge_decisions),
            "merge_decisions": merge_decisions,
            "obsolete_resolved": len(obsolete_decisions),
            "obsolete_decisions": obsolete_decisions,
            "forgetting_decisions": forgetting_decisions,
            "archived_count": sum(1 for d in forgetting_decisions if d["decision"] == "Archived"),
            "forgotten_count": sum(1 for d in forgetting_decisions if d["decision"] == "Forgotten"),
            "entropy": entropy,
            "health": health,
            "total_latency_ms": total_latency_ms,
        }

    def _empty_report(self, user_id: UUID, elapsed: float) -> Dict:
        return {
            "user_id": user_id, "memories_evaluated": 0, "decayed_count": 0,
            "merged_clusters": 0, "merge_decisions": [], "obsolete_resolved": 0,
            "obsolete_decisions": [], "forgetting_decisions": [], "archived_count": 0,
            "forgotten_count": 0, "entropy": {}, "health": {}, "total_latency_ms": elapsed * 1000,
        }
