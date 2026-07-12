"""
Dream Pipeline

Orchestrates one full offline consolidation ("dream") session:

    Replay -> Pattern Discovery -> Concept Refinement -> Consistency
    Healing -> Identity Evolution -> Graph Optimization -> Knowledge
    Synthesis -> Replay Simulation -> Compression -> Memory Health
    Evaluation

Runs entirely outside the request path of a live query (via DreamWorker/
Celery, or a manual `POST /dream/start` trigger) so it can never add
latency to user-facing inference. Every stage updates and commits a
`DreamSession` row that a concurrent `POST /dream/stop` can flip to
CANCELLED — checked cooperatively between stages, not a hard interrupt.
"""
import logging
import time
from datetime import datetime
from typing import Dict, List
from uuid import UUID
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import DreamSession, DreamSessionStatusEnum
from app.services.replay_engine import ReplayEngine
from app.services.replay_simulator import MemoryReplaySimulator
from app.services.pattern_discovery import PatternDiscoveryEngine
from app.services.concept_refiner import ConceptRefiner
from app.services.identity_evolution import IdentityEvolutionEngine
from app.services.consistency_engine import ConsistencyEngine
from app.services.graph_optimizer import GraphOptimizationEngine
from app.services.knowledge_synthesizer import KnowledgeSynthesizer
from app.services.compression_optimizer import CompressionOptimizer
from app.services.memory_health_monitor import MemoryHealthService

logger = logging.getLogger(__name__)


class DreamPipeline:
    """Runs one full dream session for a user."""

    def __init__(self, session: Session):
        self.session = session
        self.replay_engine = ReplayEngine(session)
        self.replay_simulator = MemoryReplaySimulator(session)
        self.pattern_discovery = PatternDiscoveryEngine(session)
        self.concept_refiner = ConceptRefiner(session)
        self.identity_evolution = IdentityEvolutionEngine(session)
        self.consistency_engine = ConsistencyEngine(session)
        self.graph_optimizer = GraphOptimizationEngine(session)
        self.knowledge_synthesizer = KnowledgeSynthesizer(session)
        self.compression_optimizer = CompressionOptimizer(session)
        self.health_service = MemoryHealthService(session)

    def run(self, user_id: UUID, trigger: str = "manual") -> DreamSession:
        """Run one full dream session, persisting a DreamSession record
        that's updated after every stage and checked for cancellation."""
        dream_session = DreamSession(user_id=user_id, trigger=trigger, status=DreamSessionStatusEnum.RUNNING)
        self.session.add(dream_session)
        self.session.commit()
        self.session.refresh(dream_session)

        pipeline_start = time.time()
        stage_latency: Dict[str, float] = {}

        try:
            health_before = self.health_service.compute_health(user_id)
            dream_session.health_score_before = health_before.get("cognitive_health_score", 0.0)

            t0 = time.time()
            replayed = self.replay_engine.select_for_replay(user_id)
            replay_results = self.replay_engine.replay(replayed)
            dream_session.memories_replayed = len(replay_results)
            stage_latency["replay"] = (time.time() - t0) * 1000
            if self._cancelled(dream_session):
                return self._finalize(dream_session, DreamSessionStatusEnum.CANCELLED, stage_latency, pipeline_start)

            t0 = time.time()
            patterns = self.pattern_discovery.discover(user_id)
            dream_session.patterns_discovered = len(patterns)
            stage_latency["pattern_discovery"] = (time.time() - t0) * 1000
            if self._cancelled(dream_session):
                return self._finalize(dream_session, DreamSessionStatusEnum.CANCELLED, stage_latency, pipeline_start)

            t0 = time.time()
            refinement = self.concept_refiner.refine(user_id)
            dream_session.concepts_refined = (
                len(refinement["merged"]) + len(refinement["strengthened"]) + len(refinement["retired"])
            )
            dream_session.concepts_created = len(refinement["generalized"])
            stage_latency["concept_refinement"] = (time.time() - t0) * 1000
            if self._cancelled(dream_session):
                return self._finalize(dream_session, DreamSessionStatusEnum.CANCELLED, stage_latency, pipeline_start)

            t0 = time.time()
            healing = self.consistency_engine.heal(user_id)
            dream_session.contradictions_resolved = len(healing["memory_conflicts_resolved"])
            stage_latency["consistency_healing"] = (time.time() - t0) * 1000

            t0 = time.time()
            shifts = self.identity_evolution.evolve(user_id, dream_session_id=dream_session.id)
            dream_session.identity_updates = len(shifts) + len(healing["duplicate_identities_merged"])
            stage_latency["identity_evolution"] = (time.time() - t0) * 1000
            if self._cancelled(dream_session):
                return self._finalize(dream_session, DreamSessionStatusEnum.CANCELLED, stage_latency, pipeline_start)

            t0 = time.time()
            graph_result = self.graph_optimizer.optimize(user_id)
            dream_session.graph_nodes_removed = graph_result["nodes_removed"]
            dream_session.graph_edges_strengthened = graph_result["edges_strengthened"]
            stage_latency["graph_optimization"] = (time.time() - t0) * 1000
            if self._cancelled(dream_session):
                return self._finalize(dream_session, DreamSessionStatusEnum.CANCELLED, stage_latency, pipeline_start)

            t0 = time.time()
            synthesized = self.knowledge_synthesizer.synthesize(user_id, dream_session_id=dream_session.id)
            dream_session.knowledge_synthesized = len(synthesized)
            dream_session.concepts_created += len(synthesized)
            stage_latency["knowledge_synthesis"] = (time.time() - t0) * 1000

            t0 = time.time()
            simulated = self.replay_simulator.simulate(user_id)
            stage_latency["replay_simulation"] = (time.time() - t0) * 1000

            t0 = time.time()
            compression = self.compression_optimizer.optimize(user_id)
            dream_session.compression_ratio = compression["storage_compression_ratio"]
            stage_latency["compression"] = (time.time() - t0) * 1000

            t0 = time.time()
            health_after = self.health_service.compute_health(user_id)
            dream_session.health_score_after = health_after.get("cognitive_health_score", 0.0)
            stage_latency["health_evaluation"] = (time.time() - t0) * 1000

            dream_session.memories_processed = dream_session.memories_replayed + len(simulated)
            dream_session.extra_metadata = {
                "merge_decisions": self._jsonable_list(refinement["merged"]),
                "generalized_concepts": self._jsonable_list(refinement["generalized"]),
                "retired_concepts": self._jsonable_list(refinement["retired"]),
                "identity_shifts": shifts,
                "duplicate_identities_merged": self._jsonable_list(healing["duplicate_identities_merged"]),
                "obsolete_memory_decisions": self._jsonable_list(healing["memory_conflicts_resolved"]),
                "patterns_discovered": patterns,
                "synthesized_knowledge": self._jsonable_list(synthesized),
                "replay_simulation_summary": {
                    "weakened": sum(1 for r in simulated if r["action"] == "weaken"),
                    "flagged_for_archive": sum(1 for r in simulated if r["action"] == "flag_for_archive"),
                },
                "compression": compression,
            }

            return self._finalize(dream_session, DreamSessionStatusEnum.COMPLETED, stage_latency, pipeline_start)

        except Exception as e:
            logger.error(f"Dream session failed for user {user_id}: {e}")
            self.session.rollback()
            dream_session = self.session.query(DreamSession).filter(DreamSession.id == dream_session.id).first()
            dream_session.error = str(e)
            return self._finalize(dream_session, DreamSessionStatusEnum.FAILED, stage_latency, pipeline_start)

    def stop(self, dream_session_id: UUID) -> bool:
        """Cooperatively cancel a running dream session — checked between
        pipeline stages, not a hard interrupt."""
        dream_session = self.session.query(DreamSession).filter(DreamSession.id == dream_session_id).first()
        if not dream_session or dream_session.status != DreamSessionStatusEnum.RUNNING:
            return False
        dream_session.status = DreamSessionStatusEnum.CANCELLED
        dream_session.finished_at = datetime.utcnow()
        self.session.commit()
        return True

    def _cancelled(self, dream_session: DreamSession) -> bool:
        """Check for a concurrent POST /dream/stop. Commits first: refresh()
        reloads attributes from the database, which would otherwise discard
        this stage's just-set (but not yet committed) stats on `dream_session`."""
        self.session.commit()
        self.session.refresh(dream_session)
        return dream_session.status == DreamSessionStatusEnum.CANCELLED

    def _finalize(
        self, dream_session: DreamSession, status: DreamSessionStatusEnum,
        stage_latency: Dict[str, float], pipeline_start: float,
    ) -> DreamSession:
        dream_session.status = status
        dream_session.finished_at = datetime.utcnow()
        dream_session.stage_latency_ms = stage_latency
        dream_session.total_latency_ms = (time.time() - pipeline_start) * 1000
        self.session.commit()
        self.session.refresh(dream_session)
        return dream_session

    @staticmethod
    def _jsonable_list(items: List[Dict]) -> List[Dict]:
        """Stringify UUID values so decision dicts can be stored as JSON.

        Checks `isinstance(v, UUID)` explicitly rather than `hasattr(v,
        "hex")` — floats also define a `.hex()` method (`float.hex()`),
        so the duck-typed check was silently stringifying confidence
        scores too.
        """
        return [
            {k: (str(v) if isinstance(v, UUID) else
                 ([str(x) for x in v] if isinstance(v, list) and v and isinstance(v[0], UUID) else v))
             for k, v in item.items()}
            for item in items
        ]
