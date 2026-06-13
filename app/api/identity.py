"""
Identity API Endpoints

REST API for identity graph operations.
Enables users and systems to interact with the identity engine.
"""

from typing import List, Optional
import logging
from datetime import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import (
    IdentityNode, IdentityHistory, Memory, ConceptMemory,
    CognitiveMemoryStateEnum
)
from app.services.identity_extractor import IdentityExtractor
from app.services.identity_reinforcement import IdentityReinforcementService
from app.services.identity_graph import IdentityGraphService
from app.services.identity_profile_generator import IdentityProfileGenerator
from app.services.identity_context_builder import IdentityAwareContextBuilder


logger = logging.getLogger(__name__)


# ============================================================================
# Request/Response Schemas
# ============================================================================

class IdentityNodeResponse(BaseModel):
    """Identity node response schema"""
    id: str
    node_type: str
    node_value: str
    confidence: float
    importance: float
    evidence_count: int
    reinforcement_count: int
    created_at: str

    class Config:
        from_attributes = True


class IdentityTraitResponse(BaseModel):
    """Identity trait response"""
    value: str
    confidence: float
    importance: float = 0.5
    reinforcement_count: int = 0


class UserProfileResponse(BaseModel):
    """User identity profile response"""
    user_id: str
    generated_at: str
    summary: str
    goals: List[IdentityTraitResponse]
    interests: List[IdentityTraitResponse]
    communication_style: dict
    behavioral_traits: List[IdentityTraitResponse]
    values: List[IdentityTraitResponse]
    skills: List[IdentityTraitResponse]
    confidence_metrics: dict


class IdentityGraphResponse(BaseModel):
    """Identity graph statistics response"""
    nodes: int
    edges: int
    density: float
    avg_degree_centrality: float
    weakly_connected_components: int


class ConsolidatedIdentityResponse(BaseModel):
    """Response for extraction/consolidation operations"""
    user_id: str
    operation: str
    timestamp: str
    traits_extracted: int
    nodes_created: int
    graph_updated: bool


class ExtractionRequest(BaseModel):
    """Request to extract identity from memories/concepts"""
    use_concepts: bool = True  # If true, extract from concepts; if false, from memories
    num_items: int = Field(default=20, ge=1, le=100)  # How many to analyze


class ReinforceRequest(BaseModel):
    """Request to reinforce an identity trait"""
    confidence_boost: float = Field(default=0.1, ge=0.0, le=1.0)
    evidence_source: str = "user_interaction"
    source_ids: List[str] = []


class RebuildRequest(BaseModel):
    """Request to rebuild entire identity graph"""
    include_low_confidence: bool = False
    force_rebuild: bool = False


# ============================================================================
# Router Setup
# ============================================================================

router = APIRouter(prefix="/identity", tags=["identity"])


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/extract", response_model=ConsolidatedIdentityResponse)
async def extract_identity(
    request: ExtractionRequest,
    user_id: str = Query(..., description="User ID"),
    db: Session = Depends(get_db)
):
    """
    Extract identity traits from memories or concepts.
    
    POST /identity/extract?user_id=<user_id>
    
    Analyzes recent memories or concepts to extract identity traits.
    Creates new IdentityNode objects for discovered traits.
    """
    logger.info(f"Extracting identity for user {user_id}")
    
    try:
        extractor = IdentityExtractor(db)
        
        if request.use_concepts:
            # Extract from concepts (more efficient)
            concepts = db.query(ConceptMemory).filter(
                ConceptMemory.user_id == user_id
            ).order_by(
                ConceptMemory.confidence.desc()
            ).limit(request.num_items).all()
            
            if not concepts:
                raise HTTPException(status_code=404, detail="No concepts found for extraction")
            
            extracted_traits = extractor.extract_from_concepts(user_id, concepts)
        else:
            # Extract from memories
            memories = db.query(Memory).filter(
                Memory.user_id == user_id
            ).order_by(
                Memory.created_at.desc()
            ).limit(request.num_items).all()
            
            if not memories:
                raise HTTPException(status_code=404, detail="No memories found for extraction")
            
            extracted_traits = extractor.extract_from_memories(user_id, memories)
        
        # Create identity nodes
        created_nodes = extractor.create_identity_nodes(user_id, extracted_traits)
        
        # Build graph
        graph_service = IdentityGraphService(db)
        graph_service.build_graph_for_user(user_id)
        
        total_traits = sum(len(v) for v in extracted_traits.values())
        
        return ConsolidatedIdentityResponse(
            user_id=str(user_id),
            operation="extract_identity",
            timestamp=datetime.utcnow().isoformat(),
            traits_extracted=total_traits,
            nodes_created=len(created_nodes),
            graph_updated=True
        )
        
    except Exception as e:
        logger.error(f"Identity extraction failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/profile", response_model=UserProfileResponse)
async def get_identity_profile(
    user_id: str = Query(..., description="User ID"),
    include_evolution: bool = Query(default=True),
    min_confidence: float = Query(default=0.5, ge=0.0, le=1.0),
    db: Session = Depends(get_db)
):
    """
    Get comprehensive identity profile for user.
    
    GET /identity/profile?user_id=<user_id>
    
    Returns aggregated identity profile including goals, interests,
    communication style, traits, values, and skills.
    """
    logger.info(f"Fetching identity profile for user {user_id}")
    
    try:
        generator = IdentityProfileGenerator(db)
        profile = generator.generate_profile(
            user_id,
            include_evolution=include_evolution,
            min_confidence=min_confidence
        )
        
        if not profile:
            raise HTTPException(status_code=404, detail="No identity profile found")
        
        return UserProfileResponse(**profile)
        
    except Exception as e:
        logger.error(f"Profile generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/graph", response_model=IdentityGraphResponse)
async def get_identity_graph_stats(
    user_id: str = Query(..., description="User ID"),
    db: Session = Depends(get_db)
):
    """
    Get identity graph statistics.
    
    GET /identity/graph?user_id=<user_id>
    
    Returns information about the structure of the user's identity graph.
    """
    logger.info(f"Fetching graph statistics for user {user_id}")
    
    try:
        graph_service = IdentityGraphService(db)
        stats = graph_service.get_graph_statistics(user_id)
        
        if not stats or stats.get("nodes", 0) == 0:
            raise HTTPException(status_code=404, detail="No identity graph found")
        
        return IdentityGraphResponse(**stats)
        
    except Exception as e:
        logger.error(f"Graph statistics retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reinforce", response_model=dict)
async def reinforce_trait(
    node_id: str = Query(..., description="Identity node ID"),
    user_id: str = Query(..., description="User ID"),
    request: ReinforceRequest = None,
    db: Session = Depends(get_db)
):
    """
    Reinforce an identity trait with new evidence.
    
    POST /identity/reinforce?user_id=<user_id>&node_id=<node_id>
    
    Updates trait confidence and records evidence.
    """
    logger.info(f"Reinforcing trait {node_id} for user {user_id}")
    
    if not request:
        request = ReinforceRequest()
    
    try:
        service = IdentityReinforcementService(db)
        success, node = service.reinforce_trait(
            user_id,
            node_id,
            confidence_boost=request.confidence_boost,
            evidence_source=request.evidence_source,
            source_ids=request.source_ids
        )
        
        if not success:
            raise HTTPException(status_code=404, detail="Node not found")
        
        # Propagate reinforcement
        propagation = service.propagate_reinforcement(user_id, node_id)
        
        return {
            "success": True,
            "node_id": node_id,
            "new_confidence": node.confidence,
            "propagated_nodes": propagation.get("traits_affected", 0),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Trait reinforcement failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history", response_model=dict)
async def get_identity_history(
    user_id: str = Query(..., description="User ID"),
    days: int = Query(default=30, ge=1, le=365),
    event_type: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    """
    Get identity evolution history.
    
    GET /identity/history?user_id=<user_id>&days=30
    
    Returns historical tracking of identity changes.
    """
    logger.info(f"Fetching identity history for user {user_id}")
    
    try:
        from datetime import timedelta
        
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        query = db.query(IdentityHistory).filter(
            IdentityHistory.user_id == user_id,
            IdentityHistory.created_at >= cutoff_date
        )
        
        if event_type:
            query = query.filter(IdentityHistory.event_type == event_type)
        
        history = query.order_by(
            IdentityHistory.created_at.desc()
        ).limit(100).all()
        
        if not history:
            return {
                "user_id": str(user_id),
                "events": [],
                "total_events": 0,
                "date_range": f"Last {days} days"
            }
        
        # Process history
        events = []
        for h in history:
            events.append({
                "timestamp": h.created_at.isoformat(),
                "node_type": h.node_type,
                "node_value": h.node_value,
                "old_confidence": h.old_confidence,
                "new_confidence": h.new_confidence,
                "confidence_delta": h.confidence_delta,
                "event_type": h.event_type,
                "change_reason": h.change_reason
            })
        
        return {
            "user_id": str(user_id),
            "events": events,
            "total_events": len(events),
            "date_range": f"Last {days} days"
        }
        
    except Exception as e:
        logger.error(f"History retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rebuild", response_model=ConsolidatedIdentityResponse)
async def rebuild_identity_graph(
    user_id: str = Query(..., description="User ID"),
    request: RebuildRequest = None,
    db: Session = Depends(get_db)
):
    """
    Rebuild entire identity graph from scratch.
    
    POST /identity/rebuild?user_id=<user_id>
    
    Extracts identity from all memories/concepts and rebuilds the graph.
    Useful for major updates or corrections.
    """
    logger.info(f"Rebuilding identity graph for user {user_id}")
    
    if not request:
        request = RebuildRequest()
    
    try:
        # Get all memories
        memories = db.query(Memory).filter(
            Memory.user_id == user_id
        ).order_by(
            Memory.created_at.desc()
        ).limit(500).all()
        
        # Get all concepts
        concepts = db.query(ConceptMemory).filter(
            ConceptMemory.user_id == user_id
        ).order_by(
            ConceptMemory.confidence.desc()
        ).limit(100).all()
        
        # Extract from concepts (higher signal)
        extractor = IdentityExtractor(db)
        extracted_traits = extractor.extract_from_concepts(user_id, concepts)
        
        # Also extract from memories
        extracted_from_mem = extractor.extract_from_memories(user_id, memories)
        
        # Merge traits
        for key in extracted_traits:
            extracted_traits[key].extend(extracted_from_mem.get(key, []))
        
        # Create nodes
        created_nodes = extractor.create_identity_nodes(user_id, extracted_traits)
        
        # Rebuild graph
        graph_service = IdentityGraphService(db)
        graph_service.build_graph_for_user(user_id)
        
        total_traits = sum(len(v) for v in extracted_traits.values())
        
        return ConsolidatedIdentityResponse(
            user_id=str(user_id),
            operation="rebuild_identity_graph",
            timestamp=datetime.utcnow().isoformat(),
            traits_extracted=total_traits,
            nodes_created=len(created_nodes),
            graph_updated=True
        )
        
    except Exception as e:
        logger.error(f"Graph rebuild failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Additional Helper Endpoints
# ============================================================================

@router.get("/context")
async def get_context_for_query(
    query: str = Query(..., description="User query"),
    user_id: str = Query(..., description="User ID"),
    db: Session = Depends(get_db)
):
    """
    Get personalized context for a query using identity.
    
    GET /identity/context?user_id=<user_id>&query=<query>
    
    Returns identity-aware retrieval context.
    """
    logger.info(f"Building context for user {user_id}, query: {query}")
    
    try:
        builder = IdentityAwareContextBuilder(db)
        
        # Get top concepts (simplified - in production would use full retrieval)
        concepts = db.query(ConceptMemory).filter(
            ConceptMemory.user_id == user_id
        ).order_by(
            ConceptMemory.confidence.desc()
        ).limit(10).all()
        
        context = builder.build_personalized_context(user_id, query, concepts)
        guidance = builder.get_response_guidance(user_id)
        
        return {
            "user_id": str(user_id),
            "query": query,
            "context": context,
            "guidance": guidance,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Context building failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_identity_status(
    user_id: str = Query(..., description="User ID"),
    db: Session = Depends(get_db)
):
    """
    Get current identity system status for user.
    
    GET /identity/status?user_id=<user_id>
    
    Returns summary of identity graph state.
    """
    logger.info(f"Fetching identity status for user {user_id}")
    
    try:
        nodes = db.query(IdentityNode).filter(
            IdentityNode.user_id == user_id
        ).all()
        
        if not nodes:
            return {
                "user_id": str(user_id),
                "status": "no_identity",
                "node_count": 0,
                "message": "No identity data available. Run extraction."
            }
        
        high_conf = sum(1 for n in nodes if n.confidence >= 0.7)
        
        return {
            "user_id": str(user_id),
            "status": "active",
            "node_count": len(nodes),
            "high_confidence_traits": high_conf,
            "avg_confidence": sum(n.confidence for n in nodes) / len(nodes),
            "last_update": max(n.updated_at for n in nodes).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Status check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
