"""Tests for the Day 6 Cognitive Context Composer"""
import pytest
from datetime import datetime, timedelta
from uuid import uuid4

from neurowave_engine.db.models import Memory, MemoryTypeEnum
from neurowave_engine.services.contradiction_resolver import ContradictionResolver
from neurowave_engine.services.knowledge_gap_detector import KnowledgeGapDetector
from neurowave_engine.services.context_compression import ContextCompressionEngine, CompressedMemory
from neurowave_engine.services.state_generator import StateGenerator
from neurowave_engine.services.narrative_generator import NarrativeGenerator
from neurowave_engine.services.context_evaluator import ContextEvaluator


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


def make_scored(memory, utility_score=0.7, **extra):
    base = {
        "memory_id": memory.id,
        "utility_score": utility_score,
        "goal_alignment": extra.get("goal_alignment", 0.5),
        "identity_alignment": extra.get("identity_alignment", 0.5),
        "concept_relevance": extra.get("concept_relevance", 0.5),
        "importance": extra.get("importance", 0.5),
        "reinforcement": extra.get("reinforcement", 0.5),
        "confidence": extra.get("confidence", 0.5),
        "recency": extra.get("recency", 0.5),
        "selection_reason": "test",
    }
    return base


class TestContradictionResolver:
    """Test conflict detection and resolution"""

    def test_detects_preference_contradiction(self):
        old_mem = make_memory(
            memory_type=MemoryTypeEnum.SEMANTIC,
            content="User prefers React for frontend development",
            days_old=200,
            reinforcement_score=0.3,
        )
        new_mem = make_memory(
            memory_type=MemoryTypeEnum.SEMANTIC,
            content="User prefers Rust for frontend development",
            days_old=1,
            reinforcement_score=0.7,
        )
        scored = [make_scored(old_mem), make_scored(new_mem)]
        memory_by_id = {old_mem.id: old_mem, new_mem.id: new_mem}

        resolver = ContradictionResolver()
        kept, contradictions = resolver.resolve(scored, memory_by_id)

        assert len(contradictions) == 1
        assert len(kept) == 1
        # Newer, more reinforced memory should win
        assert kept[0]["memory_id"] == new_mem.id
        assert contradictions[0]["kept_memory_id"] == new_mem.id
        assert contradictions[0]["superseded_memory_id"] == old_mem.id

    def test_no_contradiction_for_unrelated_memories(self):
        mem_a = make_memory(content="User prefers concise technical answers")
        mem_b = make_memory(content="User is preparing for a backend interview")
        scored = [make_scored(mem_a), make_scored(mem_b)]
        memory_by_id = {mem_a.id: mem_a, mem_b.id: mem_b}

        resolver = ContradictionResolver()
        kept, contradictions = resolver.resolve(scored, memory_by_id)

        assert len(contradictions) == 0
        assert len(kept) == 2

    def test_episodic_memories_never_flagged(self):
        mem_a = make_memory(memory_type=MemoryTypeEnum.EPISODIC, content="User prefers React today")
        mem_b = make_memory(memory_type=MemoryTypeEnum.EPISODIC, content="User prefers Rust today")
        scored = [make_scored(mem_a), make_scored(mem_b)]
        memory_by_id = {mem_a.id: mem_a, mem_b.id: mem_b}

        resolver = ContradictionResolver()
        kept, contradictions = resolver.resolve(scored, memory_by_id)

        assert len(contradictions) == 0
        assert len(kept) == 2


class TestKnowledgeGapDetector:
    """Test missing-knowledge detection"""

    def test_detects_gaps_for_distributed_cache_query(self):
        memories = [
            make_memory(content="User has experience with Redis"),
            make_memory(content="User is interested in backend scaling"),
        ]
        detector = KnowledgeGapDetector()
        result = detector.detect("Design a distributed cache.", memories)

        missing_lower = [t.lower() for t in result["missing_topics"]]
        assert "consistency" in missing_lower
        assert "replication" in missing_lower

    def test_no_gaps_when_query_has_no_domain_trigger(self):
        detector = KnowledgeGapDetector()
        result = detector.detect("Hello there, how are you?", [])
        assert result["missing_topics"] == []

    def test_covered_topics_excluded_from_missing(self):
        memories = [
            make_memory(content="User understands consistency models and replication strategies in distributed caches"),
        ]
        detector = KnowledgeGapDetector()
        result = detector.detect("Design a distributed cache.", memories)
        missing_lower = [t.lower() for t in result["missing_topics"]]
        assert "consistency" not in missing_lower
        assert "replication" not in missing_lower


class TestContextCompressionEngine:
    """Test compression: dedup, merge, token budgeting"""

    def test_deduplicates_near_identical_memories(self):
        mem_a = make_memory(content="User prefers concise technical answers always", importance_score=0.9)
        mem_b = make_memory(content="User prefers concise technical answers always please", importance_score=0.3)
        scored = [make_scored(mem_a, utility_score=0.9), make_scored(mem_b, utility_score=0.3)]
        memory_by_id = {mem_a.id: mem_a, mem_b.id: mem_b}

        engine = ContextCompressionEngine()
        result = engine.compress(scored, memory_by_id, token_budget=1000)

        assert result["duplicate_count"] == 1
        assert len(result["memories"]) == 1

    def test_merges_overlapping_concepts(self):
        mem_a = make_memory(memory_type=MemoryTypeEnum.CONCEPT, content="distributed systems caching replication concept")
        mem_b = make_memory(memory_type=MemoryTypeEnum.CONCEPT, content="distributed systems caching consistency concept")
        scored = [make_scored(mem_a), make_scored(mem_b)]
        memory_by_id = {mem_a.id: mem_a, mem_b.id: mem_b}

        engine = ContextCompressionEngine(merge_threshold=0.3)
        result = engine.compress(scored, memory_by_id, token_budget=1000)

        assert result["merged_count"] >= 1
        merged = [m for m in result["memories"] if m.merged]
        assert len(merged) == 1
        assert len(merged[0].source_ids) == 2

    def test_respects_token_budget(self):
        memories = [make_memory(content="word " * 100) for _ in range(5)]
        scored = [make_scored(m) for m in memories]
        memory_by_id = {m.id: m for m in memories}

        engine = ContextCompressionEngine()
        result = engine.compress(scored, memory_by_id, token_budget=50)

        assert result["compressed_tokens"] <= 50

    def test_compression_ratio_in_range(self):
        memories = [make_memory(content="word " * 50) for _ in range(4)]
        scored = [make_scored(m) for m in memories]
        memory_by_id = {m.id: m for m in memories}

        engine = ContextCompressionEngine()
        result = engine.compress(scored, memory_by_id, token_budget=30)

        assert 0.0 <= result["compression_ratio"] <= 1.0


class TestStateGenerator:
    """Test cognitive state synthesis"""

    def test_state_includes_goal_and_sections(self):
        compressed = [
            CompressedMemory(id="1", memory_type=MemoryTypeEnum.CONCEPT, content="Caching strategies", importance_score=0.8, utility_score=0.8, source_ids=[]),
            CompressedMemory(id="2", memory_type=MemoryTypeEnum.PROCEDURAL, content="Respond concisely", importance_score=0.7, utility_score=0.7, source_ids=[]),
        ]
        generator = StateGenerator()
        state = generator.generate("interview_preparation", [], compressed)

        assert "Interview preparation" in state["primary_goal"]
        assert len(state["relevant_expertise"]) > 0
        assert len(state["preferred_communication"]) > 0
        assert "Current User State" in state["text"]

    def test_reasoning_strategy_matches_goal(self):
        generator = StateGenerator()
        state = generator.generate("debugging", [], [])
        assert "root-cause" in state["reasoning_strategy"].lower()

    def test_fallback_communication_when_none_found(self):
        generator = StateGenerator()
        state = generator.generate("general_assistance", [], [])
        assert state["preferred_communication"] == ["Standard"]


class TestNarrativeGenerator:
    """Test narrative synthesis"""

    def test_narrative_is_nonempty_coherent_text(self):
        state = {
            "primary_goal": "Startup ideation",
            "relevant_expertise": ["AI Infrastructure", "Backend Engineering"],
            "preferred_communication": ["Concise", "Technical"],
            "reasoning_strategy": "Encourage creative, opportunity-focused thinking.",
        }
        narrative = NarrativeGenerator().generate(state)
        assert len(narrative) > 0
        assert "AI Infrastructure" in narrative or "ai infrastructure" in narrative.lower()

    def test_narrative_handles_empty_state(self):
        narrative = NarrativeGenerator().generate({})
        assert narrative == "No prior context is available for this user."


class TestContextEvaluator:
    """Test context quality scoring"""

    def test_full_coverage_when_no_required_knowledge(self):
        evaluator = ContextEvaluator()
        result = evaluator.evaluate(
            required_knowledge=[],
            compressed_memories=[],
            scored_by_id={},
            duplicate_count=0,
            original_candidate_count=1,
            contradiction_count=0,
            missing_topics=[],
            token_count=0,
        )
        assert result["coverage"] == 1.0

    def test_quality_score_in_range(self):
        cm = CompressedMemory(id="1", memory_type=MemoryTypeEnum.IDENTITY, content="backend engineering distributed systems", importance_score=0.8, utility_score=0.8, source_ids=[uuid4()])
        evaluator = ContextEvaluator()
        result = evaluator.evaluate(
            required_knowledge=["backend_engineering"],
            compressed_memories=[cm],
            scored_by_id={cm.source_ids[0]: {"identity_alignment": 0.8, "goal_alignment": 0.7}},
            duplicate_count=1,
            original_candidate_count=4,
            contradiction_count=1,
            missing_topics=["Consistency"],
            token_count=50,
        )
        assert 0.0 <= result["quality_score"] <= 1.0

    def test_contradictions_reduce_quality(self):
        evaluator = ContextEvaluator()
        clean = evaluator.evaluate(
            required_knowledge=[], compressed_memories=[], scored_by_id={},
            duplicate_count=0, original_candidate_count=1, contradiction_count=0,
            missing_topics=[], token_count=10,
        )
        conflicted = evaluator.evaluate(
            required_knowledge=[], compressed_memories=[], scored_by_id={},
            duplicate_count=0, original_candidate_count=1, contradiction_count=3,
            missing_topics=[], token_count=10,
        )
        assert conflicted["quality_score"] < clean["quality_score"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
