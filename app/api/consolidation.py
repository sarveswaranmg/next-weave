"""API endpoints for semantic consolidation and concepts"""
import logging
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import (
    ConceptMemory, MemoryCluster, ConceptRelationship,
    ConsolidationMetrics, User
)
from app.services.consolidation_worker import ConsolidationWorker
from app.services.concept_graph import ConceptGraph
from app.schemas.memory import MemoryResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/semantic", tags=["semantic-consolidation"])

# Service instances
consolidation_worker = ConsolidationWorker()
concept_graph = ConceptGraph()


# ============================================================================
# SCHEMAS
# ============================================================================

from pydantic import BaseModel

class ConceptResponse(BaseModel):
    id: str
    concept_name: str
    description: str
    confidence: float
    support_count: int
    supporting_memory_ids: List[str]
    reinforcement_count: int
    created_at: str

    class Config:
        from_attributes = True


class ClusterResponse(BaseModel):
    id: str
    cluster_id: str
    theme: Optional[str]
    member_count: int
    confidence: float
    consolidation_status: str

    class Config:
        from_attributes = True


class ConceptRelationshipResponse(BaseModel):
    id: str
    source_concept_id: str
    target_concept_id: str
    relationship_type: str
    strength: float
    reinforcement_count: int

    class Config:
        from_attributes = True


class ConsolidationMetricsResponse(BaseModel):
    consolidation_run_id: str
    total_memories: int
    concept_count: int
    cluster_count: int
    memory_reduction_percentage: float
    compression_ratio: float
    token_reduction: int
    processing_time_ms: float
    avg_concept_confidence: float

    class Config:
        from_attributes = True


class GraphResponse(BaseModel):
    nodes: int
    edges: int
    density: float
    avg_clustering_coefficient: float


class ConceptGraphSubgraph(BaseModel):
    center_id: str
    nodes: List[dict]
    edges: List[dict]


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.post("/consolidate")
def trigger_consolidation(
    session: Session = Depends(get_db),
) -> dict:
    """
    Trigger semantic consolidation pipeline for current user.
    
    This runs:
    - Memory clustering
    - Concept extraction
    - Relationship discovery
    - State updates
    - Metrics recording
    """
    try:
        # Get user from context (would be set by auth middleware in production)
        user_id = UUID("00000000-0000-0000-0000-000000000000")  # Placeholder

        logger.info(f"Consolidation triggered for user {user_id}")

        metrics = consolidation_worker.consolidate_user_memories(user_id)

        if not metrics:
            raise HTTPException(status_code=400, detail="Consolidation failed")

        return {
            "status": "success",
            "message": "Consolidation complete",
            "run_id": metrics.consolidation_run_id,
            "concepts_created": metrics.concept_count,
            "compression_ratio": metrics.compression_ratio,
            "memory_reduction_percentage": metrics.memory_reduction_percentage,
        }

    except Exception as e:
        logger.error(f"Consolidation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/concepts")
def list_concepts(
    user_id: UUID = Query(...),
    limit: int = Query(50, ge=1, le=500),
    min_confidence: float = Query(0.0, ge=0.0, le=1.0),
    session: Session = Depends(get_db),
) -> List[ConceptResponse]:
    """
    List semantic concepts for a user.
    
    Supports filtering by:
    - Confidence threshold
    - Result limit
    """
    try:
        query = session.query(ConceptMemory).filter(
            ConceptMemory.user_id == user_id,
            ConceptMemory.confidence >= min_confidence,
        ).order_by(
            ConceptMemory.confidence.desc(),
        ).limit(limit)

        concepts = query.all()
        return [ConceptResponse.from_orm(c) for c in concepts]

    except Exception as e:
        logger.error(f"Error listing concepts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/concepts/{concept_id}")
def get_concept(
    concept_id: UUID,
    session: Session = Depends(get_db),
) -> ConceptResponse:
    """
    Get detailed information about a concept.
    
    Includes:
    - Description and confidence
    - Supporting memories
    - Related concepts
    - Reinforcement history
    """
    try:
        concept = session.query(ConceptMemory).filter(
            ConceptMemory.id == concept_id
        ).first()

        if not concept:
            raise HTTPException(status_code=404, detail="Concept not found")

        return ConceptResponse.from_orm(concept)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting concept: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/concepts/{concept_id}/reinforce")
def reinforce_concept(
    concept_id: UUID,
    session: Session = Depends(get_db),
) -> ConceptResponse:
    """
    Reinforce a concept (increase confidence).
    
    Increases confidence when concept is reused.
    """
    try:
        concept = session.query(ConceptMemory).filter(
            ConceptMemory.id == concept_id
        ).first()

        if not concept:
            raise HTTPException(status_code=404, detail="Concept not found")

        # Increase confidence (capped at 1.0)
        old_conf = concept.confidence
        concept.confidence = min(1.0, concept.confidence + 0.05)
        concept.reinforcement_count += 1

        session.commit()

        logger.info(f"Reinforced concept {concept_id}: {old_conf:.2f} → {concept.confidence:.2f}")

        return ConceptResponse.from_orm(concept)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reinforcing concept: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/graph")
def get_concept_graph(
    user_id: UUID = Query(...),
    session: Session = Depends(get_db),
) -> GraphResponse:
    """
    Get semantic knowledge graph statistics.
    
    Returns:
    - Node count (concepts)
    - Edge count (relationships)
    - Graph density
    - Clustering coefficient
    """
    try:
        concept_graph.build_graph_for_user(session, user_id)
        stats = concept_graph.get_graph_statistics()

        return GraphResponse(
            nodes=stats['node_count'],
            edges=stats['edge_count'],
            density=stats['density'],
            avg_clustering_coefficient=stats['avg_clustering'],
        )

    except Exception as e:
        logger.error(f"Error getting graph: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/graph/{concept_id}")
def get_concept_neighborhood(
    concept_id: UUID,
    user_id: UUID = Query(...),
    depth: int = Query(2, ge=1, le=5),
    session: Session = Depends(get_db),
) -> ConceptGraphSubgraph:
    """
    Get subgraph around a concept.
    
    Returns related concepts with specified depth.
    """
    try:
        concept_graph.build_graph_for_user(session, user_id)
        subgraph = concept_graph.export_subgraph(concept_id, depth=depth)

        if not subgraph:
            raise HTTPException(status_code=404, detail="Concept not found in graph")

        return ConceptGraphSubgraph(**subgraph)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting subgraph: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/clusters")
def list_clusters(
    user_id: UUID = Query(...),
    limit: int = Query(50, ge=1, le=500),
    session: Session = Depends(get_db),
) -> List[ClusterResponse]:
    """
    List memory clusters.
    
    Shows clustering results from consolidation runs.
    """
    try:
        clusters = session.query(MemoryCluster).filter(
            MemoryCluster.user_id == user_id,
        ).order_by(
            MemoryCluster.confidence.desc(),
        ).limit(limit).all()

        return [ClusterResponse.from_orm(c) for c in clusters]

    except Exception as e:
        logger.error(f"Error listing clusters: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics")
def get_consolidation_metrics(
    user_id: UUID = Query(...),
    limit: int = Query(10, ge=1, le=100),
    session: Session = Depends(get_db),
) -> List[ConsolidationMetricsResponse]:
    """
    Get consolidation metrics history.
    
    Shows:
    - Memory compression ratios
    - Concept generation rates
    - Processing time
    - Graph growth
    """
    try:
        metrics = session.query(ConsolidationMetrics).filter(
            ConsolidationMetrics.user_id == user_id,
        ).order_by(
            ConsolidationMetrics.consolidation_timestamp.desc(),
        ).limit(limit).all()

        return [ConsolidationMetricsResponse.from_orm(m) for m in metrics]

    except Exception as e:
        logger.error(f"Error getting metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/concepts/search")
def search_concepts(
    user_id: UUID = Query(...),
    query: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    session: Session = Depends(get_db),
) -> List[ConceptResponse]:
    """
    Search concepts by name or description.
    
    Useful for finding relevant concepts.
    """
    try:
        from sqlalchemy import or_

        search_term = f"%{query}%"

        concepts = session.query(ConceptMemory).filter(
            ConceptMemory.user_id == user_id,
            or_(
                ConceptMemory.concept_name.ilike(search_term),
                ConceptMemory.description.ilike(search_term),
            ),
        ).order_by(
            ConceptMemory.confidence.desc(),
        ).limit(limit).all()

        return [ConceptResponse.from_orm(c) for c in concepts]

    except Exception as e:
        logger.error(f"Error searching concepts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/concepts/{concept_id}/related")
def get_related_concepts(
    concept_id: UUID,
    user_id: UUID = Query(...),
    depth: int = Query(2, ge=1, le=5),
    limit: int = Query(20, ge=1, le=100),
    session: Session = Depends(get_db),
) -> List[ConceptResponse]:
    """
    Get concepts related to a specific concept.
    
    Uses graph traversal to find connected concepts.
    """
    try:
        concept_graph.build_graph_for_user(session, user_id)

        related = concept_graph.find_related_concepts(
            concept_id,
            depth=depth,
            max_results=limit,
        )

        if not related:
            return []

        # Get concept objects
        related_ids = [rel[0] for rel in related]
        concepts = session.query(ConceptMemory).filter(
            ConceptMemory.id.in_(related_ids)
        ).all()

        return [ConceptResponse.from_orm(c) for c in concepts]

    except Exception as e:
        logger.error(f"Error getting related concepts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/clusters/create")
def create_manual_cluster(
    user_id: UUID = Query(...),
    memory_ids: List[str] = Query(...),
    theme: Optional[str] = Query(None),
    session: Session = Depends(get_db),
) -> ClusterResponse:
    """
    Manually create a memory cluster.
    
    Useful for grouping memories that should be consolidated.
    """
    try:
        cluster = MemoryCluster(
            user_id=user_id,
            cluster_id=f"manual_{len(memory_ids)}_{hash(str(memory_ids))}",
            theme=theme,
            memory_ids=memory_ids,
            member_count=len(memory_ids),
            consolidation_status="pending",
        )

        session.add(cluster)
        session.commit()

        logger.info(f"Created manual cluster with {len(memory_ids)} memories")

        return ClusterResponse.from_orm(cluster)

    except Exception as e:
        logger.error(f"Error creating cluster: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
def get_consolidation_status(
    user_id: UUID = Query(...),
    session: Session = Depends(get_db),
) -> dict:
    """
    Get current consolidation status for user.
    
    Shows:
    - Total concepts
    - Compression ratio
    - Last consolidation time
    - Graph statistics
    """
    try:
        # Get concept count
        concept_count = session.query(ConceptMemory).filter(
            ConceptMemory.user_id == user_id
        ).count()

        # Get memory count
        from app.db.models import Memory
        memory_count = session.query(Memory).filter(
            Memory.user_id == user_id
        ).count()

        # Get latest metrics
        latest_metrics = session.query(ConsolidationMetrics).filter(
            ConsolidationMetrics.user_id == user_id
        ).order_by(
            ConsolidationMetrics.consolidation_timestamp.desc()
        ).first()

        concept_graph.build_graph_for_user(session, user_id)
        graph_stats = concept_graph.get_graph_statistics()

        return {
            "concept_count": concept_count,
            "memory_count": memory_count,
            "compression_ratio": memory_count / concept_count if concept_count > 0 else 0,
            "graph_nodes": graph_stats['node_count'],
            "graph_edges": graph_stats['edge_count'],
            "graph_density": graph_stats['density'],
            "last_consolidation": latest_metrics.consolidation_timestamp if latest_metrics else None,
            "last_compression_ratio": latest_metrics.compression_ratio if latest_metrics else None,
        }

    except Exception as e:
        logger.error(f"Error getting status: {e}")
        raise HTTPException(status_code=500, detail=str(e))
