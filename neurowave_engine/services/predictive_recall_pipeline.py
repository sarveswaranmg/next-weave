"""
Predictive Recall Pipeline

Wires together every Day 5 component into the full cognitive recall flow:

    Query
     -> Goal Detection
     -> Intent Classification
     -> Context Analysis (identity + concept conditioning)
     -> Candidate Memory Retrieval
     -> Utility Prediction
     -> Ranking + Redundancy Elimination
     -> Token Budget Optimization
     -> Context Assembly
     -> (persisted + logged for observability/explanation)

Each stage is independently timed so latency regressions are attributable
to a specific stage rather than the pipeline as a whole.
"""
import logging
import time
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from neurowave_engine.db.models import Memory, MemoryTypeEnum, PredictiveRecallLog
from neurowave_engine.core.config import settings
from neurowave_engine.services.goal_detector import GoalDetector
from neurowave_engine.services.intent_classifier import IntentClassifier
from neurowave_engine.services.context_analyzer import ContextAnalyzer
from neurowave_engine.services.memory_ranker import PredictiveMemoryRanker
from neurowave_engine.services.context_assembler import ContextAssembler
from neurowave_engine.services.utility_predictor import UtilityWeights

logger = logging.getLogger(__name__)


class PredictiveRecallPipeline:
    """Orchestrates the end-to-end predictive recall flow for one query."""

    def __init__(self, session: Session):
        self.session = session
        self.goal_detector = GoalDetector()
        self.intent_classifier = IntentClassifier()
        self.context_analyzer = ContextAnalyzer(session)
        self.context_assembler = ContextAssembler()

    def run(
        self,
        user_id: UUID,
        query: str,
        token_budget: Optional[int] = None,
        memory_types: Optional[List[MemoryTypeEnum]] = None,
        weights: Optional[UtilityWeights] = None,
    ) -> Dict:
        """
        Execute the full predictive recall pipeline for a query.

        Returns a dict matching PredictiveRecallResponse plus the raw
        PredictiveRecallLog row (`log`) for callers that need the id.
        """
        pipeline_start = time.time()
        token_budget = token_budget or settings.predictive_recall_default_token_budget
        ranker = PredictiveMemoryRanker(self.session, weights)

        # 1. Goal Detection
        t0 = time.time()
        goal_result = self.goal_detector.detect(query)
        goal_latency_ms = (time.time() - t0) * 1000

        # 2. Intent Classification
        t0 = time.time()
        intent_result = self.intent_classifier.classify(query)
        intent_latency_ms = (time.time() - t0) * 1000
        intent_names = [i["intent"] for i in intent_result["intents"]]

        # 3. Context Analysis (identity + concept conditioning)
        context = self.context_analyzer.analyze(user_id, query, goal_result["goal"], intent_names)

        # 4. Candidate Memory Retrieval
        t0 = time.time()
        candidates = ranker.get_candidates(user_id, memory_types)
        memory_by_id = {m.id: m for m in candidates}
        candidate_latency_ms = (time.time() - t0) * 1000

        # 5. Utility Prediction
        t0 = time.time()
        scored = ranker.predictor.predict_batch(candidates, context) if candidates else []
        utility_latency_ms = (time.time() - t0) * 1000

        # 6. Ranking + Redundancy Elimination
        t0 = time.time()
        scored = [s for s in scored if s["utility_score"] >= settings.predictive_recall_min_utility]
        scored = ranker.deduplicate(scored, memory_by_id)
        for s in scored:
            memory = memory_by_id[s["memory_id"]]
            s["content_preview"] = memory.summary or memory.content or ""
        ranking_latency_ms = (time.time() - t0) * 1000

        # 7. Token Budget Optimization
        t0 = time.time()
        selected = ranker.optimizer.optimize(scored, token_budget, text_key="content_preview")
        for rank, s in enumerate(selected, start=1):
            s["retrieval_rank"] = rank
        token_optimization_latency_ms = (time.time() - t0) * 1000

        ranker.persist_scores(selected, memory_by_id)

        # 8. Context Assembly
        t0 = time.time()
        assembled = self.context_assembler.assemble(
            query, goal_result["goal"], selected, memory_by_id, token_limit=token_budget
        )
        context_assembly_latency_ms = (time.time() - t0) * 1000

        total_latency_ms = (time.time() - pipeline_start) * 1000

        explanations = [
            {
                "memory_id": s["memory_id"],
                "memory_type": memory_by_id[s["memory_id"]].memory_type,
                "content": memory_by_id[s["memory_id"]].content,
                "reason": s["selection_reason"],
                "utility": s["utility_score"],
                "rank": s["retrieval_rank"],
            }
            for s in selected
        ]

        average_utility_score = (
            sum(s["utility_score"] for s in selected) / len(selected) if selected else 0.0
        )

        latency_breakdown = {
            "goal_detection_ms": goal_latency_ms,
            "intent_classification_ms": intent_latency_ms,
            "candidate_retrieval_ms": candidate_latency_ms,
            "utility_prediction_ms": utility_latency_ms,
            "ranking_ms": ranking_latency_ms,
            "token_optimization_ms": token_optimization_latency_ms,
            "context_assembly_ms": context_assembly_latency_ms,
        }

        log = self._log_run(
            user_id=user_id,
            query=query,
            goal_result=goal_result,
            intent_result=intent_result,
            candidate_count=len(candidates),
            explanations=explanations,
            token_budget=token_budget,
            estimated_tokens=assembled["estimated_tokens"],
            average_utility_score=average_utility_score,
            latency_breakdown=latency_breakdown,
            total_latency_ms=total_latency_ms,
        )

        return {
            "recall_id": log.id,
            "goal": goal_result,
            "intents": intent_result["intents"],
            "selected_memories": explanations,
            "assembled_context": assembled,
            "candidate_count": len(candidates),
            "token_budget": token_budget,
            "average_utility_score": average_utility_score,
            "latency_breakdown_ms": latency_breakdown,
            "total_latency_ms": total_latency_ms,
        }

    def _log_run(
        self,
        user_id: UUID,
        query: str,
        goal_result: Dict,
        intent_result: Dict,
        candidate_count: int,
        explanations: List[Dict],
        token_budget: int,
        estimated_tokens: int,
        average_utility_score: float,
        latency_breakdown: Dict[str, float],
        total_latency_ms: float,
    ) -> PredictiveRecallLog:
        """Persist the run for observability and GET /retrieval/explanation"""
        try:
            log = PredictiveRecallLog(
                user_id=user_id,
                query=query,
                detected_goal=goal_result["goal"],
                goal_confidence=goal_result["confidence"],
                intents={i["intent"]: i["probability"] for i in intent_result["intents"]},
                candidate_count=candidate_count,
                selected_memory_ids=[str(e["memory_id"]) for e in explanations],
                explanations=[
                    {
                        "memory_id": str(e["memory_id"]),
                        "memory_type": e["memory_type"].value,
                        "reason": e["reason"],
                        "utility": e["utility"],
                        "rank": e["rank"],
                    }
                    for e in explanations
                ],
                token_budget=token_budget,
                estimated_tokens=estimated_tokens,
                average_utility_score=average_utility_score,
                goal_detection_latency_ms=latency_breakdown["goal_detection_ms"],
                intent_classification_latency_ms=latency_breakdown["intent_classification_ms"],
                candidate_retrieval_latency_ms=latency_breakdown["candidate_retrieval_ms"],
                utility_prediction_latency_ms=latency_breakdown["utility_prediction_ms"],
                ranking_latency_ms=latency_breakdown["ranking_ms"],
                token_optimization_latency_ms=latency_breakdown["token_optimization_ms"],
                context_assembly_latency_ms=latency_breakdown["context_assembly_ms"],
                total_latency_ms=total_latency_ms,
            )
            self.session.add(log)
            self.session.commit()
            self.session.refresh(log)
            return log
        except Exception as e:
            logger.error(f"Failed to log predictive recall run: {e}")
            self.session.rollback()
            raise
