"""
Identity Reinforcement Service

Updates identity trait confidence based on new evidence.
Propagates reinforcement through the identity graph.
Tracks trait evolution and decay.
"""

from typing import List, Optional, Dict, Tuple
import logging
from datetime import datetime, timedelta
import uuid

from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.db.models import (
    IdentityNode, IdentityRelationship, IdentityHistory, Memory, ConceptMemory
)


logger = logging.getLogger(__name__)


class IdentityReinforcementService:
    """
    Reinforces and updates identity traits based on evidence.
    
    Responsibilities:
    - Update trait confidence when new evidence appears
    - Track reinforcement history
    - Propagate confidence through relationships
    - Detect trait emergence and decay
    - Handle value conflicts
    """

    def __init__(self, db: Session):
        """Initialize service with database session."""
        self.db = db
        self.confidence_update_rate = 0.7  # EMA weight for updates
        self.decay_rate_daily = 0.02  # Confidence decay per day without evidence
        self.max_propagation_depth = 3  # How far to propagate reinforcement

    def reinforce_trait(
        self,
        user_id: str,
        node_id: str,
        confidence_boost: float = 0.1,
        evidence_source: str = "user_interaction",
        source_ids: List[str] = None
    ) -> Tuple[bool, Optional[IdentityNode]]:
        """
        Reinforce a trait with new evidence.
        
        Args:
            user_id: User ID
            node_id: Identity node ID
            confidence_boost: How much to boost confidence (0.0-1.0)
            evidence_source: What triggered the reinforcement
            source_ids: IDs of memories/concepts providing evidence
            
        Returns:
            Tuple of (success, updated_node)
        """
        node = self.db.query(IdentityNode).filter_by(
            id=node_id,
            user_id=user_id
        ).first()

        if not node:
            logger.warning(f"Identity node {node_id} not found for user {user_id}")
            return False, None

        old_confidence = node.confidence

        # Update confidence using exponential moving average
        new_confidence = (
            self.confidence_update_rate * (old_confidence + confidence_boost) +
            (1 - self.confidence_update_rate) * old_confidence
        )
        new_confidence = max(0.0, min(1.0, new_confidence))

        # Update node
        node.confidence = new_confidence
        node.reinforcement_count += 1
        node.evidence_count += 1
        node.last_reinforced_at = datetime.utcnow()

        # Add supporting evidence
        if source_ids:
            existing_ids = set(node.supporting_memory_ids or [])
            existing_ids.update(source_ids)
            node.supporting_memory_ids = list(existing_ids)[:50]  # Keep last 50

        # Record history
        history = IdentityHistory(
            id=uuid.uuid4(),
            user_id=user_id,
            node_id=node_id,
            node_type=node.node_type,
            node_value=node.node_value,
            old_confidence=old_confidence,
            new_confidence=new_confidence,
            confidence_delta=new_confidence - old_confidence,
            change_reason=evidence_source,
            triggering_memory_ids=source_ids or [],
            event_type="reinforced"
        )
        self.db.add(history)
        self.db.commit()

        logger.info(
            f"Reinforced trait {node.node_value} (type={node.node_type}) "
            f"for user {user_id}: {old_confidence:.2f} → {new_confidence:.2f}"
        )

        return True, node

    def propagate_reinforcement(
        self,
        user_id: str,
        source_node_id: str,
        reinforcement_factor: float = 0.5,
        max_depth: int = None
    ) -> Dict:
        """
        Propagate reinforcement through the identity graph.
        
        When a trait is reinforced, strengthen related traits.
        
        Args:
            user_id: User ID
            source_node_id: Starting node ID
            reinforcement_factor: How much reinforcement spreads (0.0-1.0)
            max_depth: Maximum traversal depth
            
        Returns:
            Statistics about propagation
        """
        max_depth = max_depth or self.max_propagation_depth
        visited = set()
        queue = [(source_node_id, 0)]  # (node_id, depth)
        propagated = []

        while queue:
            node_id, depth = queue.pop(0)

            if node_id in visited or depth > max_depth:
                continue

            visited.add(node_id)

            # Get related nodes
            relationships = self.db.query(IdentityRelationship).filter(
                and_(
                    IdentityRelationship.user_id == user_id,
                    IdentityRelationship.source_node_id == node_id
                )
            ).all()

            for rel in relationships:
                # Propagate based on relationship type
                if rel.relationship_type in ["reinforces", "related_to"]:
                    target = self.db.query(IdentityNode).filter_by(
                        id=rel.target_node_id
                    ).first()

                    if target and rel.target_node_id not in visited:
                        # Calculate propagated confidence
                        propagated_boost = (
                            reinforcement_factor * rel.strength * (1 - depth / max_depth)
                        )

                        old_conf = target.confidence
                        new_conf = min(1.0, target.confidence + propagated_boost)
                        target.confidence = new_conf

                        # Strengthen relationship
                        rel.strength = min(1.0, rel.strength + 0.05)
                        rel.reinforcement_count += 1
                        rel.last_reinforced_at = datetime.utcnow()

                        propagated.append({
                            "node_id": rel.target_node_id,
                            "old_confidence": old_conf,
                            "new_confidence": new_conf,
                            "boost": propagated_boost,
                            "depth": depth + 1
                        })

                        # Add to queue for further propagation
                        queue.append((rel.target_node_id, depth + 1))

        self.db.commit()

        logger.info(
            f"Propagated reinforcement from node {source_node_id}: "
            f"reached {len(propagated)} related traits"
        )

        return {
            "source_node_id": source_node_id,
            "traits_affected": len(propagated),
            "max_depth_reached": max(d[1] for d in [(n, d) for n, d in queue] if queue),
            "propagated_nodes": propagated
        }

    def detect_trait_emergence(
        self,
        user_id: str,
        min_confidence: float = 0.6
    ) -> List[IdentityNode]:
        """
        Detect newly emerged strong traits.
        
        Args:
            user_id: User ID
            min_confidence: Minimum confidence threshold
            
        Returns:
            List of emerging traits
        """
        emerging = self.db.query(IdentityNode).filter(
            and_(
                IdentityNode.user_id == user_id,
                IdentityNode.confidence >= min_confidence,
                IdentityNode.evidence_count <= 3  # Recent
            )
        ).order_by(
            IdentityNode.confidence.desc()
        ).all()

        logger.info(f"Detected {len(emerging)} emerging traits for user {user_id}")
        return emerging

    def detect_trait_decay(
        self,
        user_id: str,
        days_without_evidence: int = 30,
        min_decay: float = 0.1
    ) -> List[Tuple[IdentityNode, float]]:
        """
        Detect traits losing confidence due to lack of evidence.
        
        Args:
            user_id: User ID
            days_without_evidence: Days since last reinforcement
            min_decay: Minimum decay threshold
            
        Returns:
            List of (node, decay_amount) tuples
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days_without_evidence)

        decaying = self.db.query(IdentityNode).filter(
            and_(
                IdentityNode.user_id == user_id,
                IdentityNode.last_reinforced_at < cutoff_date,
                IdentityNode.confidence > 0.3
            )
        ).all()

        decayed_nodes = []
        for node in decaying:
            days_elapsed = (
                (datetime.utcnow() - node.last_reinforced_at).days
            )
            decay_amount = days_elapsed * node.decay_rate

            if decay_amount >= min_decay:
                decayed_nodes.append((node, decay_amount))

        logger.info(f"Detected {len(decayed_nodes)} decaying traits for user {user_id}")
        return decayed_nodes

    def apply_decay(self, user_id: str) -> Dict:
        """
        Apply confidence decay to traits without recent evidence.
        
        Args:
            user_id: User ID
            
        Returns:
            Decay statistics
        """
        nodes = self.db.query(IdentityNode).filter(
            IdentityNode.user_id == user_id
        ).all()

        decayed_count = 0
        total_decay = 0.0

        for node in nodes:
            days_elapsed = (
                (datetime.utcnow() - (node.last_reinforced_at or node.created_at)).days
            )
            decay = days_elapsed * node.decay_rate

            if decay > 0.01:  # Minimum decay threshold
                old_confidence = node.confidence
                node.confidence = max(0.0, node.confidence - decay)
                total_decay += (old_confidence - node.confidence)

                if node.confidence < 0.2:
                    decayed_count += 1
                    event_type = "declined"
                else:
                    event_type = "decayed"

                # Record history
                history = IdentityHistory(
                    id=uuid.uuid4(),
                    user_id=user_id,
                    node_id=node.id,
                    node_type=node.node_type,
                    node_value=node.node_value,
                    old_confidence=old_confidence,
                    new_confidence=node.confidence,
                    confidence_delta=-decay,
                    change_reason="natural_decay",
                    event_type=event_type
                )
                self.db.add(history)

        self.db.commit()

        logger.info(
            f"Applied decay to user {user_id}: {decayed_count} traits "
            f"dropped below threshold, total decay: {total_decay:.2f}"
        )

        return {
            "traits_decayed": decayed_count,
            "total_decay": total_decay,
            "avg_decay_per_trait": total_decay / len(nodes) if nodes else 0
        }

    def detect_value_conflicts(self, user_id: str) -> List[Dict]:
        """
        Detect potential conflicts between user values.
        
        Example: "independence" vs "collaboration"
        
        Args:
            user_id: User ID
            
        Returns:
            List of detected conflicts
        """
        # Common conflict pairs (can be expanded)
        conflict_pairs = [
            ("independence", "collaboration"),
            ("speed", "excellence"),
            ("innovation", "stability"),
            ("specialization", "generalization"),
            ("risk_tolerant", "methodical"),
        ]

        nodes = self.db.query(IdentityNode).filter(
            IdentityNode.user_id == user_id,
            IdentityNode.confidence >= 0.6
        ).all()

        node_dict = {node.node_value: node for node in nodes}
        conflicts = []

        for val1, val2 in conflict_pairs:
            if val1 in node_dict and val2 in node_dict:
                node1 = node_dict[val1]
                node2 = node_dict[val2]
                
                # Check if both are strong
                if node1.confidence >= 0.6 and node2.confidence >= 0.6:
                    conflicts.append({
                        "trait1": val1,
                        "trait2": val2,
                        "confidence1": node1.confidence,
                        "confidence2": node2.confidence,
                        "conflict_level": min(node1.confidence, node2.confidence)
                    })

        logger.info(f"Detected {len(conflicts)} potential value conflicts for user {user_id}")
        return conflicts

    def align_conflicting_traits(
        self,
        user_id: str,
        trait1_id: str,
        trait2_id: str
    ) -> bool:
        """
        Create or strengthen relationship between conflicting traits.
        
        Helps user understand how they can balance conflicting values.
        
        Args:
            user_id: User ID
            trait1_id: First trait ID
            trait2_id: Second trait ID
            
        Returns:
            Success
        """
        # Check if relationship exists
        existing = self.db.query(IdentityRelationship).filter(
            and_(
                IdentityRelationship.user_id == user_id,
                IdentityRelationship.source_node_id == trait1_id,
                IdentityRelationship.target_node_id == trait2_id
            )
        ).first()

        if existing:
            # Strengthen existing relationship
            existing.strength = min(1.0, existing.strength + 0.1)
            existing.reinforcement_count += 1
            existing.relationship_type = "balances"
        else:
            # Create new relationship
            rel = IdentityRelationship(
                id=uuid.uuid4(),
                user_id=user_id,
                source_node_id=trait1_id,
                target_node_id=trait2_id,
                relationship_type="balances",
                strength=0.6
            )
            self.db.add(rel)

        self.db.commit()
        logger.info(f"Aligned conflicting traits for user {user_id}")
        return True

    def get_reinforcement_stats(self, user_id: str) -> Dict:
        """
        Get reinforcement statistics for user's identity.
        
        Args:
            user_id: User ID
            
        Returns:
            Reinforcement metrics
        """
        nodes = self.db.query(IdentityNode).filter(
            IdentityNode.user_id == user_id
        ).all()

        if not nodes:
            return {}

        total_reinforcements = sum(n.reinforcement_count for n in nodes)
        avg_confidence = sum(n.confidence for n in nodes) / len(nodes)

        history = self.db.query(IdentityHistory).filter(
            IdentityHistory.user_id == user_id
        ).all()

        reinforced_events = sum(1 for h in history if h.event_type == "reinforced")
        decayed_events = sum(1 for h in history if h.event_type == "decayed")

        return {
            "total_traits": len(nodes),
            "total_reinforcements": total_reinforcements,
            "avg_confidence": avg_confidence,
            "reinforced_events": reinforced_events,
            "decayed_events": decayed_events,
            "avg_evidence_per_trait": sum(n.evidence_count for n in nodes) / len(nodes)
        }
