"""Tests for the Day 5 Predictive Recall Engine"""
import pytest
from datetime import datetime, timedelta
from uuid import uuid4

from neurowave_engine.db.models import Memory, MemoryTypeEnum
from neurowave_engine.services.goal_detector import GoalDetector
from neurowave_engine.services.intent_classifier import IntentClassifier
from neurowave_engine.services.utility_predictor import MemoryUtilityPredictor, UtilityWeights
from neurowave_engine.services.token_budget_optimizer import TokenBudgetOptimizer
from neurowave_engine.services.memory_ranker import PredictiveMemoryRanker
from neurowave_engine.services.context_assembler import ContextAssembler


def make_memory(
    memory_type=MemoryTypeEnum.SEMANTIC,
    content="Some memory content",
    summary=None,
    importance_score=0.5,
    reinforcement_score=0.5,
    memory_strength=0.5,
    decay_rate=0.05,
    days_old=1,
):
    """Build an in-memory Memory ORM instance (no DB round-trip needed)"""
    return Memory(
        id=uuid4(),
        user_id=uuid4(),
        memory_type=memory_type,
        content=content,
        summary=summary,
        importance_score=importance_score,
        reinforcement_score=reinforcement_score,
        memory_strength=memory_strength,
        decay_rate=decay_rate,
        created_at=datetime.utcnow() - timedelta(days=days_old),
        last_accessed=None,
    )


class TestGoalDetector:
    """Test goal inference from queries"""

    def test_system_design_goal(self):
        detector = GoalDetector()
        result = detector.detect("Help me design a backend architecture.")
        assert result["goal"] == "system_design"
        assert 0.0 < result["confidence"] <= 1.0

    def test_interview_preparation_goal(self):
        detector = GoalDetector()
        result = detector.detect("I have a React interview tomorrow.")
        assert result["goal"] == "interview_preparation"

    def test_startup_ideation_goal(self):
        detector = GoalDetector()
        result = detector.detect("Let's brainstorm startup ideas.")
        assert result["goal"] == "startup_ideation"

    def test_fallback_goal_for_generic_query(self):
        detector = GoalDetector()
        result = detector.detect("hello there")
        assert result["goal"] == "general_assistance"

    def test_empty_query(self):
        detector = GoalDetector()
        result = detector.detect("")
        assert result["goal"] == "general_assistance"
        assert result["confidence"] == 0.0

    def test_confidence_in_range(self):
        detector = GoalDetector()
        result = detector.detect("Explain Redis caching.")
        assert 0.0 <= result["confidence"] <= 1.0


class TestIntentClassifier:
    """Test multi-intent classification"""

    def test_multiple_intents_supported(self):
        classifier = IntentClassifier()
        result = classifier.classify("Compare Redis and Memcached to optimize my caching layer")
        intent_names = [i["intent"] for i in result["intents"]]
        assert "compare" in intent_names
        assert "optimize" in intent_names

    def test_probabilities_in_range(self):
        classifier = IntentClassifier()
        result = classifier.classify("Help me build a new feature")
        for intent in result["intents"]:
            assert 0.0 <= intent["probability"] <= 1.0

    def test_primary_intent_is_top_scored(self):
        classifier = IntentClassifier()
        result = classifier.classify("Please explain how caching works")
        assert result["primary_intent"] == result["intents"][0]["intent"]

    def test_debug_intent_detection(self):
        classifier = IntentClassifier()
        result = classifier.classify("My app keeps crashing, help me debug this error")
        assert result["primary_intent"] == "debug"


class TestMemoryUtilityPredictor:
    """Test multi-dimensional utility prediction"""

    def test_utility_score_in_range(self):
        predictor = MemoryUtilityPredictor()
        memory = make_memory(content="User prefers concise technical answers")
        context = {"keywords": ["concise"], "identity_traits": [], "concepts": [], "required_knowledge": []}
        result = predictor.predict(memory, context)
        assert 0.0 <= result["utility_score"] <= 1.0

    def test_memory_type_priority_ordering(self):
        """Identity > Concept > Procedural > Semantic > Episodic, all else equal"""
        predictor = MemoryUtilityPredictor()
        context = {"keywords": [], "identity_traits": [], "concepts": [], "required_knowledge": []}

        types_in_priority_order = [
            MemoryTypeEnum.IDENTITY,
            MemoryTypeEnum.CONCEPT,
            MemoryTypeEnum.PROCEDURAL,
            MemoryTypeEnum.SEMANTIC,
            MemoryTypeEnum.EPISODIC,
        ]
        multipliers = [predictor._type_multiplier(t) for t in types_in_priority_order]
        assert multipliers == sorted(multipliers, reverse=True)

    def test_goal_alignment_rewards_keyword_overlap(self):
        predictor = MemoryUtilityPredictor()
        memory = make_memory(content="Distributed systems and database scalability patterns")
        context_match = {
            "keywords": ["distributed", "systems", "scalability"],
            "identity_traits": [], "concepts": [], "required_knowledge": [],
        }
        context_nomatch = {
            "keywords": ["unrelated", "cooking", "recipes"],
            "identity_traits": [], "concepts": [], "required_knowledge": [],
        }
        matched = predictor.predict(memory, context_match)
        unmatched = predictor.predict(memory, context_nomatch)
        assert matched["goal_alignment"] > unmatched["goal_alignment"]

    def test_identity_alignment_boosts_identity_memories(self):
        predictor = MemoryUtilityPredictor()
        identity_memory = make_memory(memory_type=MemoryTypeEnum.IDENTITY, content="Building an AI startup")
        episodic_memory = make_memory(memory_type=MemoryTypeEnum.EPISODIC, content="Building an AI startup")
        context = {"keywords": [], "identity_traits": [], "concepts": [], "required_knowledge": []}

        identity_result = predictor.predict(identity_memory, context)
        episodic_result = predictor.predict(episodic_memory, context)
        assert identity_result["identity_alignment"] >= episodic_result["identity_alignment"]

    def test_recency_prefers_newer_memories(self):
        predictor = MemoryUtilityPredictor()
        recent = make_memory(days_old=1)
        old = make_memory(days_old=300)
        context = {"keywords": [], "identity_traits": [], "concepts": [], "required_knowledge": []}

        recent_result = predictor.predict(recent, context)
        old_result = predictor.predict(old, context)
        assert recent_result["recency"] > old_result["recency"]

    def test_selection_reason_is_populated(self):
        predictor = MemoryUtilityPredictor()
        memory = make_memory(memory_type=MemoryTypeEnum.PROCEDURAL, importance_score=0.9)
        context = {"keywords": [], "identity_traits": [], "concepts": [], "required_knowledge": []}
        result = predictor.predict(memory, context)
        assert isinstance(result["selection_reason"], str)
        assert len(result["selection_reason"]) > 0

    def test_configurable_weights_change_outcome(self):
        """Custom weights should shift the utility score vs. defaults"""
        memory = make_memory(importance_score=1.0, reinforcement_score=0.0, memory_strength=0.0, decay_rate=0.5)
        context = {"keywords": [], "identity_traits": [], "concepts": [], "required_knowledge": []}

        default_predictor = MemoryUtilityPredictor()
        importance_heavy_predictor = MemoryUtilityPredictor(
            UtilityWeights(
                goal_alignment=0.0, identity_alignment=0.0, concept_relevance=0.0,
                importance=1.0, reinforcement=0.0, confidence=0.0, recency=0.0,
            )
        )

        default_result = default_predictor.predict(memory, context)
        importance_result = importance_heavy_predictor.predict(memory, context)
        assert importance_result["utility_score"] != default_result["utility_score"]


class TestTokenBudgetOptimizer:
    """Test the knapsack-based token budget optimizer"""

    def test_knapsack_finds_optimal_combination(self):
        """Classic 0/1 knapsack: capacity=50, items=[(w=10,v=60),(w=20,v=100),(w=30,v=120)]
        Optimal is items 2+3 (weight=50, value=220), beating item 1+2 (weight=30, value=160)"""
        optimizer = TokenBudgetOptimizer(max_dp_candidates=10)
        candidates = [
            {"memory_id": "a", "utility_score": 60, "content_preview": "x" * 40},   # ~10 tokens
            {"memory_id": "b", "utility_score": 100, "content_preview": "x" * 80},  # ~20 tokens
            {"memory_id": "c", "utility_score": 120, "content_preview": "x" * 120}, # ~30 tokens
        ]
        selected = optimizer.optimize(candidates, token_budget=50, text_key="content_preview")
        selected_ids = {c["memory_id"] for c in selected}
        assert selected_ids == {"b", "c"}
        assert sum(c["utility_score"] for c in selected) == 220

    def test_respects_token_budget(self):
        optimizer = TokenBudgetOptimizer(max_dp_candidates=10)
        candidates = [
            {"memory_id": i, "utility_score": 0.5, "content_preview": "word " * 50}
            for i in range(5)
        ]
        selected = optimizer.optimize(candidates, token_budget=100, text_key="content_preview")
        total_tokens = sum(optimizer.estimate_tokens(c["content_preview"]) for c in selected)
        assert total_tokens <= 100

    def test_greedy_fallback_for_large_candidate_pools(self):
        """Above max_dp_candidates, falls back to greedy but still respects budget"""
        optimizer = TokenBudgetOptimizer(max_dp_candidates=2)
        candidates = [
            {"memory_id": i, "utility_score": 0.1 * i, "content_preview": "word " * 20}
            for i in range(1, 6)
        ]
        selected = optimizer.optimize(candidates, token_budget=50, text_key="content_preview")
        total_tokens = sum(optimizer.estimate_tokens(c["content_preview"]) for c in selected)
        assert total_tokens <= 50
        assert len(selected) > 0

    def test_empty_candidates_returns_empty(self):
        optimizer = TokenBudgetOptimizer()
        assert optimizer.optimize([], token_budget=1000) == []

    def test_zero_budget_returns_empty(self):
        optimizer = TokenBudgetOptimizer()
        candidates = [{"memory_id": "a", "utility_score": 0.9, "content_preview": "hello"}]
        assert optimizer.optimize(candidates, token_budget=0) == []


class TestPredictiveMemoryRankerDeduplication:
    """Test redundancy elimination"""

    def test_near_duplicate_memories_are_deduplicated(self):
        ranker = PredictiveMemoryRanker(session=None)
        mem_high = make_memory(content="User prefers concise technical answers always", importance_score=0.9)
        mem_low = make_memory(content="User prefers concise technical answers always please", importance_score=0.3)

        scored = [
            {"memory_id": mem_high.id, "utility_score": 0.9},
            {"memory_id": mem_low.id, "utility_score": 0.3},
        ]
        memory_by_id = {mem_high.id: mem_high, mem_low.id: mem_low}

        deduped = ranker.deduplicate(scored, memory_by_id)
        assert len(deduped) == 1
        assert deduped[0]["memory_id"] == mem_high.id

    def test_distinct_memories_are_kept(self):
        ranker = PredictiveMemoryRanker(session=None)
        mem_a = make_memory(content="Distributed systems and caching strategies")
        mem_b = make_memory(content="User is preparing for a backend interview next week")

        scored = [
            {"memory_id": mem_a.id, "utility_score": 0.7},
            {"memory_id": mem_b.id, "utility_score": 0.6},
        ]
        memory_by_id = {mem_a.id: mem_a, mem_b.id: mem_b}

        deduped = ranker.deduplicate(scored, memory_by_id)
        assert len(deduped) == 2


class TestContextAssembler:
    """Test context assembly into a compact reasoning block"""

    def test_no_raw_episodic_history_when_other_memories_exist(self):
        assembler = ContextAssembler()
        identity_mem = make_memory(memory_type=MemoryTypeEnum.IDENTITY, content="Building an AI startup")
        episodic_mem = make_memory(memory_type=MemoryTypeEnum.EPISODIC, content="Talked about the weather yesterday")

        selected = [
            {"memory_id": identity_mem.id, "utility_score": 0.9},
            {"memory_id": episodic_mem.id, "utility_score": 0.5},
        ]
        memory_by_id = {identity_mem.id: identity_mem, episodic_mem.id: episodic_mem}

        result = assembler.assemble("query", "startup_ideation", selected, memory_by_id)
        assert episodic_mem.content not in result["context_text"]
        assert identity_mem.content in result["context_text"]

    def test_episodic_included_when_nothing_else_available(self):
        assembler = ContextAssembler()
        episodic_mem = make_memory(memory_type=MemoryTypeEnum.EPISODIC, content="User asked about deployment last week")
        selected = [{"memory_id": episodic_mem.id, "utility_score": 0.5}]
        memory_by_id = {episodic_mem.id: episodic_mem}

        result = assembler.assemble("query", "general_assistance", selected, memory_by_id)
        assert episodic_mem.content in result["context_text"]

    def test_current_goal_always_present(self):
        assembler = ContextAssembler()
        result = assembler.assemble("query", "system_design", [], {})
        assert "System design" in result["context_text"]

    def test_estimated_tokens_positive(self):
        assembler = ContextAssembler()
        mem = make_memory(content="Some useful content here")
        selected = [{"memory_id": mem.id, "utility_score": 0.8}]
        result = assembler.assemble("query", "learning", selected, {mem.id: mem})
        assert result["estimated_tokens"] > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
