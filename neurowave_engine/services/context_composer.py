"""
Cognitive Context Composer

The bridge between memory and reasoning. Where Day 5 answers "which
memories are worth retrieving," Day 6 answers "what should the LLM actually
understand before it reasons" — never simply concatenating retrieved
memories, but reconstructing them into a compact cognitive state the way
human recall reconstructs rather than replays.

Pipeline:
    Query -> Goal Detection -> Identity/Concept Context -> Candidate
    Retrieval -> Utility Scoring -> Contradiction Resolution -> Knowledge
    Gap Detection -> Compression -> State Generation -> Narrative
    Generation -> Quality Evaluation -> Final Cognitive Context
"""
import logging
import time
from typing import Dict, Iterator, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from neurowave_engine.db.models import MemoryTypeEnum, ContextSnapshot, ContextMetrics
from neurowave_engine.core.config import settings
from neurowave_engine.services.goal_detector import GoalDetector
from neurowave_engine.services.intent_classifier import IntentClassifier
from neurowave_engine.services.context_analyzer import ContextAnalyzer
from neurowave_engine.services.memory_ranker import PredictiveMemoryRanker
from neurowave_engine.services.contradiction_resolver import ContradictionResolver
from neurowave_engine.services.knowledge_gap_detector import KnowledgeGapDetector
from neurowave_engine.services.context_compression import ContextCompressionEngine
from neurowave_engine.services.state_generator import StateGenerator
from neurowave_engine.services.narrative_generator import NarrativeGenerator
from neurowave_engine.services.context_evaluator import ContextEvaluator
from neurowave_engine.services.utility_predictor import UtilityWeights

logger = logging.getLogger(__name__)


class ContextComposer:
    """Orchestrates the full Cognitive Context Composer pipeline."""

    def __init__(self, session: Session):
        self.session = session
        self.goal_detector = GoalDetector()
        self.intent_classifier = IntentClassifier()
        self.context_analyzer = ContextAnalyzer(session)
        self.contradiction_resolver = ContradictionResolver()
        self.gap_detector = KnowledgeGapDetector()
        self.compression_engine = ContextCompressionEngine()
        self.state_generator = StateGenerator()
        self.narrative_generator = NarrativeGenerator()
        self.context_evaluator = ContextEvaluator()

    def compose(
        self,
        user_id: UUID,
        query: str,
        token_budget: Optional[int] = None,
        memory_types: Optional[List[MemoryTypeEnum]] = None,
        weights: Optional[UtilityWeights] = None,
    ) -> Dict:
        """Run the full pipeline and persist a ContextSnapshot + ContextMetrics."""
        pipeline_start = time.time()
        token_budget = token_budget or settings.ccc_default_token_budget

        goal_result, intent_result, context, kept, memory_by_id, original_candidate_count = self._gather(
            user_id, query, token_budget, memory_types, weights
        )

        kept, contradictions = self.contradiction_resolver.resolve(kept, memory_by_id)

        gaps = self.gap_detector.detect(query, [memory_by_id[s["memory_id"]] for s in kept])

        compression = self.compression_engine.compress(kept, memory_by_id, token_budget)
        compressed_memories = compression["memories"]

        state = self.state_generator.generate(goal_result["goal"], context["identity_traits"], compressed_memories)
        narrative = self.narrative_generator.generate(state)

        scored_by_id = {s["memory_id"]: s for s in kept}
        evaluation = self.context_evaluator.evaluate(
            required_knowledge=context["required_knowledge"],
            compressed_memories=compressed_memories,
            scored_by_id=scored_by_id,
            duplicate_count=compression["duplicate_count"],
            original_candidate_count=max(1, original_candidate_count),
            contradiction_count=len(contradictions),
            missing_topics=gaps["missing_topics"],
            token_count=compression["compressed_tokens"],
        )

        final_context_text = self._assemble_final_text(narrative, state, gaps)
        total_latency_ms = (time.time() - pipeline_start) * 1000

        snapshot = self._persist(
            user_id=user_id,
            query=query,
            goal_result=goal_result,
            final_context_text=final_context_text,
            narrative=narrative,
            evaluation=evaluation,
            compression=compression,
            contradictions=contradictions,
            gaps=gaps,
            source_memory_ids=[str(s["memory_id"]) for s in kept],
            total_latency_ms=total_latency_ms,
        )

        return {
            "snapshot_id": snapshot.id,
            "goal": goal_result,
            "intents": intent_result["intents"],
            "state": state,
            "narrative": narrative,
            "final_context": final_context_text,
            "compressed_memories": [self._serialize_compressed(cm) for cm in compressed_memories],
            "contradictions": contradictions,
            "knowledge_gaps": gaps,
            "compression": {
                "original_tokens": compression["original_tokens"],
                "compressed_tokens": compression["compressed_tokens"],
                "compression_ratio": compression["compression_ratio"],
                "duplicate_count": compression["duplicate_count"],
                "merged_count": compression["merged_count"],
            },
            "evaluation": evaluation,
            "candidate_count": original_candidate_count,
            "token_budget": token_budget,
            "total_latency_ms": total_latency_ms,
        }

    def compose_streaming(
        self,
        user_id: UUID,
        query: str,
        token_budget: Optional[int] = None,
        memory_types: Optional[List[MemoryTypeEnum]] = None,
        weights: Optional[UtilityWeights] = None,
    ) -> Iterator[Dict]:
        """
        Yield partial results after each pipeline stage, for consumers that
        want to render progressively (e.g. an SSE endpoint) instead of
        blocking on the full composition. Runs the same stages as
        `compose()`, in the same order, but does not persist a snapshot —
        callers that need persistence should use `compose()`.
        """
        token_budget = token_budget or settings.ccc_default_token_budget

        goal_result, intent_result, context, scored, memory_by_id, candidate_count = self._gather(
            user_id, query, token_budget, memory_types, weights
        )
        yield {"stage": "goal_detection", "data": goal_result}
        yield {"stage": "intent_classification", "data": intent_result}
        yield {
            "stage": "context_analysis",
            "data": {"identity_traits": len(context["identity_traits"]), "concepts": len(context["concepts"])},
        }
        yield {"stage": "utility_prediction", "data": {"candidate_count": candidate_count, "scored_count": len(scored)}}

        kept, contradictions = self.contradiction_resolver.resolve(scored, memory_by_id)
        yield {"stage": "contradiction_resolution", "data": {"contradictions": contradictions}}

        gaps = self.gap_detector.detect(query, [memory_by_id[s["memory_id"]] for s in kept])
        yield {"stage": "knowledge_gaps", "data": gaps}

        compression = self.compression_engine.compress(kept, memory_by_id, token_budget)
        yield {
            "stage": "compression",
            "data": {
                "compression_ratio": compression["compression_ratio"],
                "compressed_tokens": compression["compressed_tokens"],
            },
        }

        state = self.state_generator.generate(goal_result["goal"], context["identity_traits"], compression["memories"])
        narrative = self.narrative_generator.generate(state)
        yield {"stage": "narrative", "data": {"narrative": narrative, "state_text": state["text"]}}

        final_context_text = self._assemble_final_text(narrative, state, gaps)
        yield {"stage": "final_context", "data": {"final_context": final_context_text}}

    def _gather(self, user_id, query, token_budget, memory_types, weights):
        """Shared setup for compose() and compose_streaming(): goal, intent,
        context analysis, and utility-scored/deduped candidates."""
        ranker = PredictiveMemoryRanker(self.session, weights)

        goal_result = self.goal_detector.detect(query)
        intent_result = self.intent_classifier.classify(query)
        intent_names = [i["intent"] for i in intent_result["intents"]]

        context = self.context_analyzer.analyze(user_id, query, goal_result["goal"], intent_names)

        candidates = ranker.get_candidates(user_id, memory_types)
        memory_by_id = {m.id: m for m in candidates}

        scored = ranker.predictor.predict_batch(candidates, context) if candidates else []
        scored = [s for s in scored if s["utility_score"] >= settings.predictive_recall_min_utility]
        scored = ranker.deduplicate(scored, memory_by_id)

        return goal_result, intent_result, context, scored, memory_by_id, len(candidates)

    @staticmethod
    def _serialize_compressed(cm) -> Dict:
        return {
            "id": cm.id,
            "memory_type": cm.memory_type,
            "content": cm.content,
            "utility_score": cm.utility_score,
            "merged": cm.merged,
            "source_ids": [str(sid) for sid in cm.source_ids],
        }

    @staticmethod
    def _assemble_final_text(narrative: str, state: Dict, gaps: Dict) -> str:
        parts = [narrative, "", state["text"]]
        if gaps.get("missing_topics"):
            parts.append("")
            parts.append("Knowledge Gaps:")
            parts.extend(f"- {topic}" for topic in gaps["missing_topics"])
        return "\n".join(parts).strip()

    def _persist(
        self,
        user_id: UUID,
        query: str,
        goal_result: Dict,
        final_context_text: str,
        narrative: str,
        evaluation: Dict,
        compression: Dict,
        contradictions: List[Dict],
        gaps: Dict,
        source_memory_ids: List[str],
        total_latency_ms: float,
    ) -> ContextSnapshot:
        """Persist the run as a ContextSnapshot + ContextMetrics pair."""
        try:
            snapshot = ContextSnapshot(
                user_id=user_id,
                query=query,
                detected_goal=goal_result["goal"],
                generated_context=final_context_text,
                narrative=narrative,
                context_quality=evaluation["quality_score"],
                token_count=compression["compressed_tokens"],
                original_token_count=compression["original_tokens"],
                compression_ratio=compression["compression_ratio"],
                contradiction_count=len(contradictions),
                missing_topics=gaps["missing_topics"],
                source_memory_ids=source_memory_ids,
                total_latency_ms=total_latency_ms,
            )
            self.session.add(snapshot)
            self.session.flush()

            metrics = ContextMetrics(
                snapshot_id=snapshot.id,
                coverage=evaluation["coverage"],
                redundancy=evaluation["redundancy"],
                identity_alignment=evaluation["identity_alignment"],
                goal_alignment=evaluation["goal_alignment"],
                quality_score=evaluation["quality_score"],
            )
            self.session.add(metrics)
            self.session.commit()
            self.session.refresh(snapshot)
            return snapshot
        except Exception as e:
            logger.error(f"Failed to persist context snapshot: {e}")
            self.session.rollback()
            raise
