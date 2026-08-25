"""Observability and analytics for cognitive memory system"""
import logging
import json
from typing import Dict, Optional, List
from datetime import datetime
from dataclasses import dataclass, asdict
from sqlalchemy.orm import Session
from neurowave_engine.db.models import (
    Memory, RetrievalLog, CognitiveMemoryStateEnum, PredictiveRecallLog,
    ContextSnapshot, ContextMetrics,
)

logger = logging.getLogger(__name__)


@dataclass
class CognitiveMetrics:
    """Structured cognitive metrics"""
    timestamp: datetime
    user_id: str
    metric_type: str  # "score", "retrieve", "reinforce", "decay"
    memory_id: str
    memory_type: str
    cognitive_state: str
    importance_score: float
    memory_strength: float
    operation_latency_ms: float
    additional_context: Optional[Dict] = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        data = asdict(self)
        data["timestamp"] = data["timestamp"].isoformat()
        return data
    
    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict())


class CognitiveObservability:
    """Observability system for cognitive memory operations"""
    
    def __init__(self, session: Optional[Session] = None):
        """Initialize observability system"""
        self.session = session
        self.metrics_buffer = []
        self.buffer_size = 100  # Flush every N metrics
    
    def log_scoring_metric(
        self,
        user_id: str,
        memory_id: str,
        memory_type: str,
        importance_score: float,
        memory_strength: float,
        cognitive_state: str,
        latency_ms: float,
        context: Optional[Dict] = None
    ) -> None:
        """Log cognitive scoring operation"""
        metric = CognitiveMetrics(
            timestamp=datetime.utcnow(),
            user_id=user_id,
            metric_type="score",
            memory_id=memory_id,
            memory_type=memory_type,
            cognitive_state=cognitive_state,
            importance_score=importance_score,
            memory_strength=memory_strength,
            operation_latency_ms=latency_ms,
            additional_context=context
        )
        
        self._add_metric(metric)
        logger.info(f"Scoring metric: {metric.to_json()}")
    
    def log_retrieval_metric(
        self,
        user_id: str,
        query: str,
        retrieved_memory_ids: List[str],
        importance_scores: List[float],
        latency_ms: float,
        context: Optional[Dict] = None
    ) -> None:
        """Log retrieval operation"""
        avg_importance = sum(importance_scores) / len(importance_scores) if importance_scores else 0.0
        
        additional = {
            "query": query,
            "retrieved_count": len(retrieved_memory_ids),
            "average_importance": avg_importance,
            "retrieved_ids": retrieved_memory_ids,
            **(context or {})
        }
        
        metric = CognitiveMetrics(
            timestamp=datetime.utcnow(),
            user_id=user_id,
            metric_type="retrieve",
            memory_id="batch",
            memory_type="mixed",
            cognitive_state="retrieved",
            importance_score=avg_importance,
            memory_strength=0.0,
            operation_latency_ms=latency_ms,
            additional_context=additional
        )
        
        self._add_metric(metric)
        logger.info(f"Retrieval metric: latency={latency_ms:.2f}ms, count={len(retrieved_memory_ids)}")
    
    def log_reinforcement_metric(
        self,
        user_id: str,
        memory_id: str,
        previous_strength: float,
        new_strength: float,
        reinforcement_count: int,
        latency_ms: float
    ) -> None:
        """Log reinforcement operation"""
        context = {
            "reinforcement_count": reinforcement_count,
            "strength_increase": new_strength - previous_strength,
        }
        
        metric = CognitiveMetrics(
            timestamp=datetime.utcnow(),
            user_id=user_id,
            metric_type="reinforce",
            memory_id=memory_id,
            memory_type="reinforced",
            cognitive_state="reinforced",
            importance_score=new_strength,
            memory_strength=new_strength,
            operation_latency_ms=latency_ms,
            additional_context=context
        )
        
        self._add_metric(metric)
        logger.info(f"Reinforcement metric: strength {previous_strength:.2f} → {new_strength:.2f}")
    
    def log_decay_metric(
        self,
        user_id: str,
        memory_id: str,
        previous_state: str,
        new_state: str,
        previous_strength: float,
        new_strength: float,
        days_since_access: int
    ) -> None:
        """Log memory decay operation"""
        context = {
            "previous_state": previous_state,
            "new_state": new_state,
            "days_since_access": days_since_access,
            "strength_decrease": previous_strength - new_strength,
        }
        
        metric = CognitiveMetrics(
            timestamp=datetime.utcnow(),
            user_id=user_id,
            metric_type="decay",
            memory_id=memory_id,
            memory_type="decayed",
            cognitive_state=new_state,
            importance_score=new_strength,
            memory_strength=new_strength,
            operation_latency_ms=0.0,
            additional_context=context
        )
        
        self._add_metric(metric)
        logger.info(f"Decay metric: {previous_state} → {new_state} after {days_since_access} days")
    
    def log_predictive_recall_metric(
        self,
        user_id: str,
        query: str,
        goal: str,
        goal_confidence: float,
        selected_count: int,
        average_utility_score: float,
        estimated_tokens: int,
        total_latency_ms: float,
        context: Optional[Dict] = None
    ) -> None:
        """Log a predictive recall pipeline run (Day 5)"""
        additional = {
            "query": query,
            "goal": goal,
            "goal_confidence": goal_confidence,
            "selected_count": selected_count,
            "estimated_tokens": estimated_tokens,
            **(context or {})
        }

        metric = CognitiveMetrics(
            timestamp=datetime.utcnow(),
            user_id=user_id,
            metric_type="predictive_recall",
            memory_id="batch",
            memory_type="mixed",
            cognitive_state="predicted",
            importance_score=average_utility_score,
            memory_strength=0.0,
            operation_latency_ms=total_latency_ms,
            additional_context=additional
        )

        self._add_metric(metric)
        logger.info(
            f"Predictive recall metric: goal={goal}, utility={average_utility_score:.2f}, "
            f"latency={total_latency_ms:.2f}ms, selected={selected_count}"
        )

    def _add_metric(self, metric: CognitiveMetrics) -> None:
        """Add metric to buffer"""
        self.metrics_buffer.append(metric)
        
        # Flush if buffer is full
        if len(self.metrics_buffer) >= self.buffer_size:
            self.flush_metrics()
    
    def flush_metrics(self) -> None:
        """Flush metrics buffer"""
        if not self.metrics_buffer:
            return
        
        try:
            # Log summary
            logger.info(f"Flushing {len(self.metrics_buffer)} metrics")
            
            # Could send to external observability system here
            # (e.g., Datadog, New Relic, CloudWatch, etc.)
            
            self.metrics_buffer = []
        except Exception as e:
            logger.error(f"Error flushing metrics: {e}")


class CognitiveAnalytics:
    """Analytics for cognitive memory operations"""
    
    def __init__(self, session: Session):
        """Initialize analytics"""
        self.session = session
    
    def get_user_cognitive_timeline(
        self,
        user_id: str,
        days_back: int = 30
    ) -> Dict:
        """Get timeline of cognitive operations"""
        from datetime import timedelta
        
        cutoff = datetime.utcnow() - timedelta(days=days_back)
        
        memories = self.session.query(Memory).filter(
            Memory.user_id == user_id,
            Memory.created_at >= cutoff
        ).all()
        
        timeline = {
            "user_id": str(user_id),
            "period_days": days_back,
            "memories_created": len(memories),
            "memories_by_state": {},
            "memories_by_type": {},
            "average_importance": 0.0,
            "average_strength": 0.0,
            "state_transitions": 0,
        }
        
        total_importance = 0.0
        total_strength = 0.0
        
        for memory in memories:
            # Track by state
            state = str(memory.cognitive_state)
            timeline["memories_by_state"][state] = timeline["memories_by_state"].get(state, 0) + 1
            
            # Track by type
            mem_type = str(memory.memory_type)
            timeline["memories_by_type"][mem_type] = timeline["memories_by_type"].get(mem_type, 0) + 1
            
            # Accumulate for average
            total_importance += memory.importance_score or 0.0
            total_strength += memory.memory_strength or 0.0
        
        count = len(memories)
        if count > 0:
            timeline["average_importance"] = total_importance / count
            timeline["average_strength"] = total_strength / count
        
        return timeline
    
    def get_memory_lifecycle_stats(self, user_id: str) -> Dict:
        """Get statistics on memory lifecycle"""
        memories = self.session.query(Memory).filter(Memory.user_id == user_id).all()
        
        active = sum(1 for m in memories if m.cognitive_state == CognitiveMemoryStateEnum.ACTIVE)
        reinforced = sum(1 for m in memories if m.cognitive_state == CognitiveMemoryStateEnum.REINFORCED)
        semantic = sum(1 for m in memories if m.cognitive_state == CognitiveMemoryStateEnum.SEMANTIC_CANDIDATE)
        dormant = sum(1 for m in memories if m.cognitive_state == CognitiveMemoryStateEnum.DORMANT)
        decaying = sum(1 for m in memories if m.cognitive_state == CognitiveMemoryStateEnum.DECAYING)
        archived = sum(1 for m in memories if m.cognitive_state == CognitiveMemoryStateEnum.ARCHIVED)
        
        total_reinforcement = sum(m.reinforcement_count or 0 for m in memories)
        total_retrieval = sum(m.retrieval_count or 0 for m in memories)
        
        return {
            "user_id": str(user_id),
            "total_memories": len(memories),
            "states": {
                "active": active,
                "reinforced": reinforced,
                "semantic_candidate": semantic,
                "dormant": dormant,
                "decaying": decaying,
                "archived": archived,
            },
            "total_reinforcements": total_reinforcement,
            "total_retrievals": total_retrieval,
            "average_reinforcement_per_memory": total_reinforcement / len(memories) if memories else 0,
            "average_retrieval_per_memory": total_retrieval / len(memories) if memories else 0,
        }
    
    def get_importance_distribution(self, user_id: str) -> Dict:
        """Get distribution of memory importance scores"""
        memories = self.session.query(Memory).filter(Memory.user_id == user_id).all()
        
        buckets = {
            "0.0-0.2": 0,
            "0.2-0.4": 0,
            "0.4-0.6": 0,
            "0.6-0.8": 0,
            "0.8-1.0": 0,
        }
        
        for memory in memories:
            score = memory.importance_score or 0.5
            if score < 0.2:
                buckets["0.0-0.2"] += 1
            elif score < 0.4:
                buckets["0.2-0.4"] += 1
            elif score < 0.6:
                buckets["0.4-0.6"] += 1
            elif score < 0.8:
                buckets["0.6-0.8"] += 1
            else:
                buckets["0.8-1.0"] += 1
        
        return {
            "user_id": str(user_id),
            "distribution": buckets,
            "total_memories": len(memories),
        }
    
    def get_retrieval_performance(self, user_id: str, limit: int = 100) -> Dict:
        """Get retrieval performance statistics"""
        logs = self.session.query(RetrievalLog).filter(
            RetrievalLog.user_id == user_id
        ).order_by(RetrievalLog.created_at.desc()).limit(limit).all()
        
        if not logs:
            return {
                "user_id": str(user_id),
                "retrieval_count": 0,
                "average_latency_ms": 0.0,
                "average_retrieved_count": 0,
                "average_token_count": 0,
            }
        
        total_latency = sum(log.retrieval_latency_ms or 0.0 for log in logs)
        total_retrieved = sum(len(log.retrieved_memory_ids or []) for log in logs)
        total_tokens = sum(log.context_token_count or 0 for log in logs)
        
        count = len(logs)
        
        return {
            "user_id": str(user_id),
            "retrieval_count": count,
            "average_latency_ms": total_latency / count if count > 0 else 0.0,
            "average_retrieved_count": total_retrieved / count if count > 0 else 0,
            "average_token_count": total_tokens / count if count > 0 else 0,
            "min_latency_ms": min(log.retrieval_latency_ms or 0.0 for log in logs),
            "max_latency_ms": max(log.retrieval_latency_ms or 0.0 for log in logs),
        }

    def get_predictive_recall_performance(self, user_id: str, limit: int = 100) -> Dict:
        """
        Get Day 5 predictive recall performance statistics.

        Tracks: average utility score, average retrieved memories, average
        prompt tokens, prediction latency breakdown, and goal distribution —
        the observability surface called for by the Predictive Recall Engine.
        """
        logs = self.session.query(PredictiveRecallLog).filter(
            PredictiveRecallLog.user_id == user_id
        ).order_by(PredictiveRecallLog.created_at.desc()).limit(limit).all()

        if not logs:
            return {
                "user_id": str(user_id),
                "run_count": 0,
                "average_utility_score": 0.0,
                "average_selected_memories": 0.0,
                "average_prompt_tokens": 0.0,
                "average_candidate_count": 0.0,
                "average_total_latency_ms": 0.0,
                "latency_breakdown_ms": {},
                "goal_distribution": {},
            }

        count = len(logs)
        total_utility = sum(log.average_utility_score or 0.0 for log in logs)
        total_selected = sum(len(log.selected_memory_ids or []) for log in logs)
        total_tokens = sum(log.estimated_tokens or 0 for log in logs)
        total_candidates = sum(log.candidate_count or 0 for log in logs)
        total_latency = sum(log.total_latency_ms or 0.0 for log in logs)

        goal_distribution: Dict[str, int] = {}
        for log in logs:
            goal = log.detected_goal or "unknown"
            goal_distribution[goal] = goal_distribution.get(goal, 0) + 1

        latency_breakdown = {
            "goal_detection_ms": sum(log.goal_detection_latency_ms or 0.0 for log in logs) / count,
            "intent_classification_ms": sum(log.intent_classification_latency_ms or 0.0 for log in logs) / count,
            "candidate_retrieval_ms": sum(log.candidate_retrieval_latency_ms or 0.0 for log in logs) / count,
            "utility_prediction_ms": sum(log.utility_prediction_latency_ms or 0.0 for log in logs) / count,
            "ranking_ms": sum(log.ranking_latency_ms or 0.0 for log in logs) / count,
            "token_optimization_ms": sum(log.token_optimization_latency_ms or 0.0 for log in logs) / count,
            "context_assembly_ms": sum(log.context_assembly_latency_ms or 0.0 for log in logs) / count,
        }

        return {
            "user_id": str(user_id),
            "run_count": count,
            "average_utility_score": total_utility / count,
            "average_selected_memories": total_selected / count,
            "average_prompt_tokens": total_tokens / count,
            "average_candidate_count": total_candidates / count,
            "average_total_latency_ms": total_latency / count,
            "latency_breakdown_ms": latency_breakdown,
            "goal_distribution": goal_distribution,
        }

    def get_context_composition_performance(self, user_id: str, limit: int = 100) -> Dict:
        """
        Get Day 6 Cognitive Context Composer performance statistics.

        Tracks: average context size, compression ratio, quality score,
        contradiction count, knowledge gaps detected, and latency — the
        observability surface called for by the CCC.
        """
        snapshots = self.session.query(ContextSnapshot).filter(
            ContextSnapshot.user_id == user_id
        ).order_by(ContextSnapshot.created_at.desc()).limit(limit).all()

        if not snapshots:
            return {
                "user_id": str(user_id),
                "snapshot_count": 0,
                "average_quality_score": 0.0,
                "average_coverage": 0.0,
                "average_redundancy": 0.0,
                "average_identity_alignment": 0.0,
                "average_goal_alignment": 0.0,
                "average_compression_ratio": 0.0,
                "average_token_count": 0.0,
                "average_contradiction_count": 0.0,
                "average_missing_topics": 0.0,
                "average_latency_ms": 0.0,
            }

        count = len(snapshots)
        snapshot_ids = [s.id for s in snapshots]
        metrics = self.session.query(ContextMetrics).filter(
            ContextMetrics.snapshot_id.in_(snapshot_ids)
        ).all()
        metrics_count = len(metrics) or 1

        return {
            "user_id": str(user_id),
            "snapshot_count": count,
            "average_quality_score": sum(s.context_quality or 0.0 for s in snapshots) / count,
            "average_coverage": sum(m.coverage or 0.0 for m in metrics) / metrics_count,
            "average_redundancy": sum(m.redundancy or 0.0 for m in metrics) / metrics_count,
            "average_identity_alignment": sum(m.identity_alignment or 0.0 for m in metrics) / metrics_count,
            "average_goal_alignment": sum(m.goal_alignment or 0.0 for m in metrics) / metrics_count,
            "average_compression_ratio": sum(s.compression_ratio or 0.0 for s in snapshots) / count,
            "average_token_count": sum(s.token_count or 0 for s in snapshots) / count,
            "average_contradiction_count": sum(s.contradiction_count or 0 for s in snapshots) / count,
            "average_missing_topics": sum(len(s.missing_topics or []) for s in snapshots) / count,
            "average_latency_ms": sum(s.total_latency_ms or 0.0 for s in snapshots) / count,
        }


# Global observability instance
_observability: Optional[CognitiveObservability] = None


def get_observability() -> CognitiveObservability:
    """Get or create observability instance"""
    global _observability
    if _observability is None:
        _observability = CognitiveObservability()
    return _observability
