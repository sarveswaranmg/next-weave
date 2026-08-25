"""Background tasks for memory processing"""
import logging
from typing import Dict
from uuid import UUID
from neurowave_engine.workers.celery_app import celery_app
from neurowave_engine.db.database import get_db_session
from neurowave_engine.memory.embeddings import embedding_service
from neurowave_engine.db.models import Memory, MemoryEmbedding
from neurowave_engine.services.consolidation_worker import ConsolidationWorker

logger = logging.getLogger(__name__)

# Initialize consolidation worker
consolidation_worker = ConsolidationWorker()


@celery_app.task(bind=True, max_retries=3)
def generate_embeddings_for_memory(self, memory_id: str):
    """Generate embedding for a memory in background"""
    try:
        session = get_db_session()
        memory = session.query(Memory).filter(Memory.id == UUID(memory_id)).first()
        
        if not memory:
            logger.warning(f"Memory not found: {memory_id}")
            return
        
        # Generate embedding
        content = memory.summary or memory.content
        embedding = embedding_service.embed_text(content)
        
        # Store embedding
        db_embedding = MemoryEmbedding(
            memory_id=memory.id,
            embedding=_serialize_embedding(embedding),
            model="text-embedding-3-small",
        )
        session.add(db_embedding)
        session.commit()
        
        logger.info(f"Generated embedding for memory: {memory_id}")
        
    except Exception as exc:
        logger.error(f"Error generating embedding: {exc}")
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(bind=True, max_retries=3)
def consolidate_user_memories_task(self, user_id: str):
    """
    Day 3: Semantic consolidation pipeline.
    
    Runs:
    - Memory clustering
    - Concept extraction
    - Knowledge graph building
    - Metric recording
    """
    try:
        logger.info(f"Starting consolidation for user: {user_id}")
        
        metrics = consolidation_worker.consolidate_user_memories(UUID(user_id))
        
        if metrics:
            logger.info(f"Consolidation complete: {metrics.concept_count} concepts, "
                       f"compression_ratio={metrics.compression_ratio:.2f}")
            return {
                "status": "success",
                "concepts_created": metrics.concept_count,
                "compression_ratio": metrics.compression_ratio,
                "memory_reduction_percentage": metrics.memory_reduction_percentage,
            }
        else:
            logger.warning(f"Consolidation returned no metrics for user: {user_id}")
            return {"status": "failed", "reason": "No metrics returned"}
        
    except Exception as exc:
        logger.error(f"Consolidation error: {exc}")
        raise self.retry(exc=exc, countdown=300, max_retries=2)


@celery_app.task
def periodic_consolidation(batch_size: int = 10):
    """
    Periodic consolidation for all active users.
    
    Runs every hour (configurable in celery beat schedule).
    Consolidates memories for users with new content.
    """
    try:
        from neurowave_engine.db.database import get_db_session
        from sqlalchemy import func, and_
        from datetime import datetime, timedelta
        
        session = get_db_session()
        
        # Find users with memories created in last hour
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        
        users_to_consolidate = session.query(Memory.user_id).filter(
            Memory.created_at >= one_hour_ago
        ).distinct().limit(batch_size).all()
        
        user_ids = [u[0] for u in users_to_consolidate]
        
        logger.info(f"Starting periodic consolidation for {len(user_ids)} users")
        
        results = []
        for user_id in user_ids:
            try:
                result = consolidation_worker.consolidate_user_memories(user_id)
                if result:
                    results.append({
                        "user_id": str(user_id),
                        "concepts_created": result.concept_count,
                    })
            except Exception as e:
                logger.error(f"Error consolidating user {user_id}: {e}")
        
        logger.info(f"Periodic consolidation complete: {len(results)} users processed")
        return {"users_processed": len(results), "results": results}
        
    except Exception as e:
        logger.error(f"Periodic consolidation error: {e}")
        return {"status": "failed", "error": str(e)}


@celery_app.task(bind=True, max_retries=3)
def enforce_memory_retention_policy(self, user_id: str):
    """
    Day 7: Run one full memory evolution pass for a user - decay,
    duplicate resolution, obsolescence resolution, and forgetting.
    """
    try:
        from uuid import UUID
        from neurowave_engine.services.memory_evolution_pipeline import MemoryEvolutionPipeline

        logger.info(f"Retention policy enforcement for user: {user_id}")

        session = get_db_session()
        pipeline = MemoryEvolutionPipeline(session)
        report = pipeline.run(UUID(user_id))

        logger.info(
            f"Retention policy complete for {user_id}: "
            f"{report['decayed_count']} decayed, {report['merged_clusters']} merged, "
            f"{report['archived_count']} archived, {report['forgotten_count']} forgotten"
        )

        return {
            "status": "success",
            "memories_evaluated": report["memories_evaluated"],
            "merged_clusters": report["merged_clusters"],
            "archived_count": report["archived_count"],
            "forgotten_count": report["forgotten_count"],
            "cognitive_health_score": report.get("health", {}).get("cognitive_health_score"),
        }

    except Exception as exc:
        logger.error(f"Memory evolution error: {exc}")
        raise self.retry(exc=exc, countdown=300, max_retries=2)


def _serialize_embedding(embedding: list) -> str:
    """Serialize embedding for pgvector storage"""
    return "[" + ",".join(str(e) for e in embedding) + "]"


# ============================================================================
# DAY 4: IDENTITY GRAPH ENGINE - NEW TASKS
# ============================================================================

@celery_app.task(bind=True, max_retries=3)
def extract_identity_from_memories_task(self, user_id: str, num_items: int = 50):
    """
    Extract identity traits from user's memories.
    
    Runs in background to analyze memories and extract goals,
    interests, traits, communication style, and values.
    """
    try:
        from neurowave_engine.services.identity_extractor import IdentityExtractor
        from neurowave_engine.services.identity_graph import IdentityGraphService
        from neurowave_engine.db.database import get_db_session
        
        logger.info(f"Starting identity extraction for user: {user_id}")
        
        session = get_db_session()
        
        # Get memories
        memories = session.query(Memory).filter(
            Memory.user_id == UUID(user_id)
        ).order_by(
            Memory.created_at.desc()
        ).limit(num_items).all()
        
        if not memories:
            logger.warning(f"No memories found for identity extraction: {user_id}")
            return {"status": "no_memories"}
        
        # Extract traits
        extractor = IdentityExtractor(session)
        extracted_traits = extractor.extract_from_memories(user_id, memories)
        
        # Create nodes
        created_nodes = extractor.create_identity_nodes(user_id, extracted_traits)
        
        # Build graph
        graph_service = IdentityGraphService(session)
        graph_service.build_graph_for_user(user_id)
        
        logger.info(f"Identity extraction complete: {len(created_nodes)} nodes created")
        
        return {
            "status": "success",
            "nodes_created": len(created_nodes),
            "traits_extracted": sum(len(v) for v in extracted_traits.values())
        }
        
    except Exception as exc:
        logger.error(f"Identity extraction error: {exc}")
        raise self.retry(exc=exc, countdown=60, max_retries=2)


@celery_app.task(bind=True, max_retries=3)
def extract_identity_from_concepts_task(self, user_id: str, num_items: int = 100):
    """
    Extract identity traits from user's concepts.
    
    More efficient than memory extraction - uses consolidated concepts.
    """
    try:
        from neurowave_engine.services.identity_extractor import IdentityExtractor
        from neurowave_engine.services.identity_graph import IdentityGraphService
        from neurowave_engine.db.database import get_db_session
        from neurowave_engine.db.models import ConceptMemory
        
        logger.info(f"Starting identity extraction from concepts for user: {user_id}")
        
        session = get_db_session()
        
        # Get concepts
        concepts = session.query(ConceptMemory).filter(
            ConceptMemory.user_id == UUID(user_id)
        ).order_by(
            ConceptMemory.confidence.desc()
        ).limit(num_items).all()
        
        if not concepts:
            logger.warning(f"No concepts found for identity extraction: {user_id}")
            return {"status": "no_concepts"}
        
        # Extract traits
        extractor = IdentityExtractor(session)
        extracted_traits = extractor.extract_from_concepts(user_id, concepts)
        
        # Create nodes
        created_nodes = extractor.create_identity_nodes(user_id, extracted_traits)
        
        # Build graph
        graph_service = IdentityGraphService(session)
        graph_service.build_graph_for_user(user_id)
        
        logger.info(f"Identity extraction from concepts complete: {len(created_nodes)} nodes")
        
        return {
            "status": "success",
            "nodes_created": len(created_nodes),
            "traits_extracted": sum(len(v) for v in extracted_traits.values())
        }
        
    except Exception as exc:
        logger.error(f"Concept-based identity extraction error: {exc}")
        raise self.retry(exc=exc, countdown=60, max_retries=2)


@celery_app.task
def apply_identity_decay_task(user_id: str):
    """
    Apply confidence decay to identity traits.
    
    Periodically decreases confidence in traits that aren't reinforced.
    """
    try:
        from neurowave_engine.services.identity_reinforcement import IdentityReinforcementService
        from neurowave_engine.db.database import get_db_session
        
        logger.info(f"Applying identity decay for user: {user_id}")
        
        session = get_db_session()
        service = IdentityReinforcementService(session)
        
        decay_stats = service.apply_decay(user_id)
        
        logger.info(f"Identity decay complete: {decay_stats['traits_decayed']} traits decayed")
        
        return decay_stats
        
    except Exception as e:
        logger.error(f"Identity decay error: {e}")
        return {"status": "failed", "error": str(e)}


@celery_app.task
def periodic_identity_reinforcement(batch_size: int = 10):
    """
    Periodic identity reinforcement and graph updates.
    
    Runs hourly (configurable in celery beat schedule).
    Reinforces high-confidence traits and propagates importance.
    """
    try:
        from neurowave_engine.db.database import get_db_session
        from neurowave_engine.db.models import IdentityNode
        from datetime import datetime, timedelta
        from sqlalchemy import and_
        
        logger.info(f"Starting periodic identity reinforcement")
        
        session = get_db_session()
        
        # Find high-value nodes for reinforcement
        week_ago = datetime.utcnow() - timedelta(days=7)
        high_value = session.query(IdentityNode).filter(
            and_(
                IdentityNode.confidence >= 0.7,
                IdentityNode.last_reinforced_at < week_ago
            )
        ).limit(batch_size * 5).all()
        
        logger.info(f"Found {len(high_value)} high-value traits to reinforce")
        
        # Group by user
        users_to_process = list(set([str(n.user_id) for n in high_value]))
        
        results = []
        for user_id in users_to_process[:batch_size]:
            try:
                # Apply decay
                apply_identity_decay_task.delay(user_id)
                results.append({"user_id": user_id, "status": "scheduled"})
            except Exception as e:
                logger.error(f"Error scheduling reinforcement for user {user_id}: {e}")
        
        logger.info(f"Periodic identity reinforcement scheduled: {len(results)} users")
        
        return {"users_processed": len(results)}
        
    except Exception as e:
        logger.error(f"Periodic identity reinforcement error: {e}")
        return {"status": "failed", "error": str(e)}


@celery_app.task
def rebuild_identity_graph_task(user_id: str):
    """
    Rebuild user's entire identity graph.
    
    Used when major corrections or updates are needed.
    """
    try:
        from neurowave_engine.services.identity_extractor import IdentityExtractor
        from neurowave_engine.services.identity_graph import IdentityGraphService
        from neurowave_engine.db.database import get_db_session
        from neurowave_engine.db.models import ConceptMemory
        
        logger.info(f"Rebuilding identity graph for user: {user_id}")
        
        session = get_db_session()
        
        # Extract from concepts (primary signal)
        concepts = session.query(ConceptMemory).filter(
            ConceptMemory.user_id == UUID(user_id)
        ).all()
        
        extractor = IdentityExtractor(session)
        extracted_traits = extractor.extract_from_concepts(user_id, concepts)
        
        # Create nodes
        created_nodes = extractor.create_identity_nodes(user_id, extracted_traits)
        
        # Build graph
        graph_service = IdentityGraphService(session)
        graph = graph_service.build_graph_for_user(user_id)
        
        logger.info(
            f"Identity graph rebuilt: {len(created_nodes)} nodes, "
            f"{graph.number_of_edges()} edges"
        )
        
        return {
            "status": "success",
            "nodes": len(created_nodes),
            "edges": graph.number_of_edges()
        }
        
    except Exception as e:
        logger.error(f"Identity graph rebuild error: {e}")
        return {"status": "failed", "error": str(e)}


# ============================================================================
# DAY 7: COGNITIVE FORGETTING & MEMORY EVOLUTION ENGINE - NEW TASKS
# ============================================================================

@celery_app.task
def hourly_memory_evolution(batch_size: int = 20):
    """
    MemoryEvolutionWorker - hourly pass.

    Evolves memory for users with recent activity (new memories or
    accesses in the last hour), so decay/duplicate/obsolescence cleanup
    stays close to real-time for active users without scanning everyone.
    """
    try:
        from datetime import datetime, timedelta

        session = get_db_session()
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)

        active_users = session.query(Memory.user_id).filter(
            (Memory.created_at >= one_hour_ago) | (Memory.last_accessed >= one_hour_ago)
        ).distinct().limit(batch_size).all()
        user_ids = [u[0] for u in active_users]

        logger.info(f"Hourly memory evolution: {len(user_ids)} active users")

        results = []
        for user_id in user_ids:
            try:
                enforce_memory_retention_policy.delay(str(user_id))
                results.append({"user_id": str(user_id), "status": "scheduled"})
            except Exception as e:
                logger.error(f"Error scheduling evolution for user {user_id}: {e}")

        return {"users_scheduled": len(results)}

    except Exception as e:
        logger.error(f"Hourly memory evolution error: {e}")
        return {"status": "failed", "error": str(e)}


@celery_app.task
def daily_memory_evolution_sweep(batch_size: int = 200):
    """
    MemoryEvolutionWorker - daily full sweep.

    Evolves memory for every user with at least one non-forgotten memory,
    catching users who weren't active enough in the last hour to be
    picked up by `hourly_memory_evolution` but whose memories still need
    time-based decay/archival evaluation.
    """
    try:
        from neurowave_engine.db.models import CognitiveMemoryStateEnum

        session = get_db_session()
        all_users = session.query(Memory.user_id).filter(
            Memory.cognitive_state != CognitiveMemoryStateEnum.FORGOTTEN
        ).distinct().limit(batch_size).all()
        user_ids = [u[0] for u in all_users]

        logger.info(f"Daily memory evolution sweep: {len(user_ids)} users")

        results = []
        for user_id in user_ids:
            try:
                enforce_memory_retention_policy.delay(str(user_id))
                results.append({"user_id": str(user_id), "status": "scheduled"})
            except Exception as e:
                logger.error(f"Error scheduling evolution for user {user_id}: {e}")

        return {"users_scheduled": len(results)}

    except Exception as e:
        logger.error(f"Daily memory evolution sweep error: {e}")
        return {"status": "failed", "error": str(e)}


@celery_app.task(bind=True, max_retries=3)
def check_reinforcement_recovery_task(self, user_id: str, query: str):
    """Check whether a new query revives any decayed/archived memories."""
    try:
        from uuid import UUID
        from neurowave_engine.services.reinforcement_recovery import ReinforcementRecoveryService

        session = get_db_session()
        service = ReinforcementRecoveryService(session)
        revivals = service.check_and_revive(UUID(user_id), query)

        logger.info(f"Reinforcement recovery for {user_id}: {len(revivals)} memories revived")
        return {"status": "success", "revived_count": len(revivals)}

    except Exception as exc:
        logger.error(f"Reinforcement recovery error: {exc}")
        raise self.retry(exc=exc, countdown=60, max_retries=2)


# ============================================================================
# DAY 8: OFFLINE COGNITIVE CONSOLIDATION ENGINE ("DREAM MODE") - NEW TASKS
# ============================================================================

@celery_app.task(bind=True, max_retries=2)
def dream_worker_task(self, user_id: str, trigger: str = "manual"):
    """
    DreamWorker - runs one full offline consolidation session for a user:
    replay, pattern discovery, concept refinement, consistency healing,
    identity evolution, graph optimization, knowledge synthesis, replay
    simulation, compression, and health evaluation.
    """
    try:
        from uuid import UUID
        from neurowave_engine.services.dream_pipeline import DreamPipeline

        logger.info(f"Starting dream session for user {user_id} (trigger={trigger})")

        session = get_db_session()
        pipeline = DreamPipeline(session)
        dream_session = pipeline.run(UUID(user_id), trigger=trigger)

        logger.info(
            f"Dream session {dream_session.status.value} for {user_id}: "
            f"{dream_session.memories_replayed} replayed, {dream_session.patterns_discovered} patterns, "
            f"{dream_session.knowledge_synthesized} synthesized, health "
            f"{dream_session.health_score_before} -> {dream_session.health_score_after}"
        )

        return {
            "status": dream_session.status.value,
            "dream_session_id": str(dream_session.id),
            "memories_replayed": dream_session.memories_replayed,
            "patterns_discovered": dream_session.patterns_discovered,
            "knowledge_synthesized": dream_session.knowledge_synthesized,
            "health_score_before": dream_session.health_score_before,
            "health_score_after": dream_session.health_score_after,
        }

    except Exception as exc:
        logger.error(f"Dream worker error: {exc}")
        raise self.retry(exc=exc, countdown=300, max_retries=1)


@celery_app.task
def replay_worker_task(user_id: str, batch_size: int = None):
    """ReplayWorker - standalone replay pass (used by POST /dream/replay)."""
    try:
        from uuid import UUID
        from neurowave_engine.services.replay_engine import ReplayEngine

        session = get_db_session()
        engine = ReplayEngine(session)
        selected = engine.select_for_replay(UUID(user_id), batch_size=batch_size)
        results = engine.replay(selected)
        return {"status": "success", "replayed_count": len(results)}
    except Exception as e:
        logger.error(f"Replay worker error: {e}")
        return {"status": "failed", "error": str(e)}


@celery_app.task
def concept_worker_task(user_id: str):
    """ConceptWorker - standalone concept refinement pass (POST /dream/refine)."""
    try:
        from uuid import UUID
        from neurowave_engine.services.concept_refiner import ConceptRefiner

        session = get_db_session()
        refiner = ConceptRefiner(session)
        result = refiner.refine(UUID(user_id))
        return {
            "status": "success",
            "merged": len(result["merged"]),
            "generalized": len(result["generalized"]),
            "strengthened": len(result["strengthened"]),
            "retired": len(result["retired"]),
        }
    except Exception as e:
        logger.error(f"Concept worker error: {e}")
        return {"status": "failed", "error": str(e)}


@celery_app.task
def graph_worker_task(user_id: str):
    """GraphWorker - standalone concept/identity graph optimization pass."""
    try:
        from uuid import UUID
        from neurowave_engine.services.graph_optimizer import GraphOptimizationEngine

        session = get_db_session()
        optimizer = GraphOptimizationEngine(session)
        result = optimizer.optimize(UUID(user_id))
        return {"status": "success", **{k: v for k, v in result.items() if isinstance(v, int)}}
    except Exception as e:
        logger.error(f"Graph worker error: {e}")
        return {"status": "failed", "error": str(e)}


@celery_app.task
def compression_worker_task(user_id: str):
    """CompressionWorker - standalone storage compression pass."""
    try:
        from uuid import UUID
        from neurowave_engine.services.compression_optimizer import CompressionOptimizer

        session = get_db_session()
        optimizer = CompressionOptimizer(session)
        result = optimizer.optimize(UUID(user_id))
        return {"status": "success", **result}
    except Exception as e:
        logger.error(f"Compression worker error: {e}")
        return {"status": "failed", "error": str(e)}


def _run_scheduled_dreams(trigger: str, batch_size: int) -> Dict:
    """Shared scheduler-tick logic for hourly/daily/weekly/idle dream ticks."""
    from neurowave_engine.services.dream_scheduler import DreamScheduler

    session = get_db_session()
    scheduler = DreamScheduler(session)
    user_ids = scheduler.eligible_users(trigger=trigger, limit=batch_size)

    logger.info(f"{trigger} dream tick: {len(user_ids)} users eligible")

    scheduled = []
    for user_id in user_ids:
        try:
            dream_worker_task.delay(str(user_id), trigger=trigger)
            scheduled.append(str(user_id))
        except Exception as e:
            logger.error(f"Error scheduling dream session for user {user_id}: {e}")

    return {"trigger": trigger, "users_scheduled": len(scheduled)}


@celery_app.task
def hourly_dream_tick(batch_size: int = 20):
    """DreamScheduler - hourly tick: light-touch consolidation for users
    with recent memory growth."""
    return _run_scheduled_dreams("hourly", batch_size)


@celery_app.task
def daily_dream_tick(batch_size: int = 100):
    """DreamScheduler - daily tick: broader coverage sweep."""
    return _run_scheduled_dreams("daily", batch_size)


@celery_app.task
def weekly_dream_tick(batch_size: int = 500):
    """DreamScheduler - weekly tick: full-store deep consolidation."""
    return _run_scheduled_dreams("weekly", batch_size)


@celery_app.task
def idle_triggered_dream_tick(batch_size: int = 50):
    """DreamScheduler - idle-triggered tick: runs dream sessions only for
    users with no live retrieval/composition activity in the idle window,
    so consolidation never competes with a user who's actively engaged."""
    return _run_scheduled_dreams("idle", batch_size)
