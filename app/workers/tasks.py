"""Background tasks for memory processing"""
import logging
from uuid import UUID
from app.workers.celery_app import celery_app
from app.db.database import get_db_session
from app.memory.embeddings import embedding_service
from app.db.models import Memory, MemoryEmbedding
from app.services.consolidation_worker import ConsolidationWorker

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
        from app.db.database import get_db_session
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


@celery_app.task
def enforce_memory_retention_policy(user_id: str):
    """Enforce memory retention and decay"""
    logger.info(f"Retention policy enforcement for user: {user_id}")
    # TODO: Implement decay and archival logic in Phase 4
    pass


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
        from app.services.identity_extractor import IdentityExtractor
        from app.services.identity_graph import IdentityGraphService
        from app.db.database import get_db_session
        
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
        from app.services.identity_extractor import IdentityExtractor
        from app.services.identity_graph import IdentityGraphService
        from app.db.database import get_db_session
        from app.db.models import ConceptMemory
        
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
        from app.services.identity_reinforcement import IdentityReinforcementService
        from app.db.database import get_db_session
        
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
        from app.db.database import get_db_session
        from app.db.models import IdentityNode
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
        from app.services.identity_extractor import IdentityExtractor
        from app.services.identity_graph import IdentityGraphService
        from app.db.database import get_db_session
        from app.db.models import ConceptMemory
        
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
