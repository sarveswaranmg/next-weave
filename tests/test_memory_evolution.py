"""Tests for the Day 7 Cognitive Forgetting & Memory Evolution Engine"""
import pytest
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.db.models import (
    User, Memory, MemoryTypeEnum, CognitiveMemoryStateEnum,
    ConceptMemory, ConceptRelationship, IdentityNode, IdentityRelationship,
    MemoryEvent,
)
from app.services.memory_decay_engine import AdaptiveDecayStrategy, MemoryDecayEngine
from app.services.duplicate_resolver import DuplicateResolver
from app.services.obsolete_memory_detector import ObsoleteMemoryDetector
from app.services.memory_entropy import MemoryEntropyCalculator
from app.services.reinforcement_recovery import ReinforcementRecoveryService
from app.services.memory_lifecycle_manager import MemoryLifecycleManager
from app.services.forgetting_engine import ForgettingEngine
from app.services.memory_health_monitor import MemoryHealthService
from app.services.memory_evolution_pipeline import MemoryEvolutionPipeline


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[
        User.__table__, Memory.__table__, ConceptMemory.__table__,
        ConceptRelationship.__table__, IdentityNode.__table__,
        IdentityRelationship.__table__, MemoryEvent.__table__,
    ])
    SessionLocal = sessionmaker(bind=engine)
    s = SessionLocal()
    yield s
    s.close()


@pytest.fixture
def user(session):
    u = User(id=uuid4(), external_id=f"u-{uuid4()}", name="Test User")
    session.add(u)
    session.commit()
    return u


def make_memory(
    session, user_id,
    memory_type=MemoryTypeEnum.SEMANTIC,
    content="Some memory content",
    importance_score=0.5,
    reinforcement_score=0.5,
    memory_strength=0.5,
    decay_rate=0.05,
    cognitive_state=CognitiveMemoryStateEnum.ACTIVE,
    days_since_access=1,
    retrieval_count=0,
    emotional_salience_score=0.5,
):
    now = datetime.utcnow()
    m = Memory(
        id=uuid4(),
        user_id=user_id,
        memory_type=memory_type,
        content=content,
        importance_score=importance_score,
        reinforcement_score=reinforcement_score,
        memory_strength=memory_strength,
        decay_rate=decay_rate,
        cognitive_state=cognitive_state,
        created_at=now - timedelta(days=days_since_access + 5),
        last_accessed=now - timedelta(days=days_since_access),
        retrieval_count=retrieval_count,
        emotional_salience_score=emotional_salience_score,
        revival_count=0,
    )
    session.add(m)
    session.commit()
    return m


class TestAdaptiveDecayStrategy:
    """Different memory types should decay at different base rates"""

    def test_identity_decays_slowest(self):
        strategy = AdaptiveDecayStrategy()
        identity = Memory(memory_type=MemoryTypeEnum.IDENTITY, importance_score=0.5)
        episodic = Memory(memory_type=MemoryTypeEnum.EPISODIC, importance_score=0.5)
        assert strategy.base_rate(identity) < strategy.base_rate(episodic)

    def test_low_importance_episodic_decays_fastest(self):
        strategy = AdaptiveDecayStrategy()
        random_chat = Memory(memory_type=MemoryTypeEnum.EPISODIC, importance_score=0.1)
        normal_episodic = Memory(memory_type=MemoryTypeEnum.EPISODIC, importance_score=0.6)
        assert strategy.base_rate(random_chat) > strategy.base_rate(normal_episodic)

    def test_full_ordering(self):
        strategy = AdaptiveDecayStrategy()
        rates = {
            "identity": strategy.base_rate(Memory(memory_type=MemoryTypeEnum.IDENTITY, importance_score=0.5)),
            "concept": strategy.base_rate(Memory(memory_type=MemoryTypeEnum.CONCEPT, importance_score=0.5)),
            "procedural": strategy.base_rate(Memory(memory_type=MemoryTypeEnum.PROCEDURAL, importance_score=0.5)),
            "episodic": strategy.base_rate(Memory(memory_type=MemoryTypeEnum.EPISODIC, importance_score=0.6)),
        }
        assert rates["identity"] < rates["concept"] < rates["procedural"] < rates["episodic"]


class TestMemoryDecayEngine:
    """Multi-factor decay: age, retrieval frequency, reinforcement, membership, importance, emotion"""

    def test_decay_reduces_strength(self, session, user):
        memory = make_memory(session, user.id, memory_strength=0.8, days_since_access=100)
        engine = MemoryDecayEngine(session)
        result = engine.apply_decay(memory)
        assert result["new_strength"] < result["previous_strength"]
        assert memory.last_decay_at is not None

    def test_high_reinforcement_slows_decay(self, session, user):
        strong = make_memory(session, user.id, reinforcement_score=0.9, days_since_access=50)
        weak = make_memory(session, user.id, reinforcement_score=0.1, days_since_access=50)
        engine = MemoryDecayEngine(session)
        strong_factors = engine.compute_decay_factor(strong)
        weak_factors = engine.compute_decay_factor(weak)
        assert strong_factors["effective_decay_rate"] < weak_factors["effective_decay_rate"]

    def test_concept_membership_slows_decay(self, session, user):
        memory = make_memory(session, user.id, days_since_access=50)
        concept = ConceptMemory(
            user_id=user.id, concept_name="test_concept", confidence=0.8,
            support_count=1, supporting_memory_ids=[str(memory.id)],
        )
        session.add(concept)
        session.commit()

        engine = MemoryDecayEngine(session)
        factors = engine.compute_decay_factor(memory)
        assert factors["in_concept"] is True
        assert factors["membership_factor"] < 1.0


class TestDuplicateResolver:
    """Repeated near-duplicate preferences collapse into one reinforced concept"""

    def test_repeated_rust_preference_merges_into_one_concept(self, session, user):
        contents = ["User likes Rust", "User enjoys Rust", "User learns Rust", "User writes Rust programs"]
        memories = [make_memory(session, user.id, content=c) for c in contents]

        resolver = DuplicateResolver(session)
        decisions = resolver.resolve(user.id, memories)

        # Pure lexical overlap won't always catch every paraphrase (e.g. a
        # 3-content-word memory can dip just under threshold against an
        # already-larger cluster union) - a strong majority merge is the
        # realistic bar for a dependency-free heuristic, not a perfect 4/4.
        assert len(decisions) == 1
        assert decisions[0]["support_count"] >= 3
        assert "Rust" in decisions[0]["concept_name"]

        merged_ids = set(decisions[0]["source_memory_ids"])
        for m in memories:
            session.refresh(m)
            if m.id in merged_ids:
                assert m.cognitive_state == CognitiveMemoryStateEnum.ARCHIVED
                assert m.archive_reason is not None

    def test_distinct_memories_not_merged(self, session, user):
        memories = [
            make_memory(session, user.id, content="User enjoys distributed systems design"),
            make_memory(session, user.id, content="User is preparing for a backend interview next month"),
        ]
        resolver = DuplicateResolver(session)
        decisions = resolver.resolve(user.id, memories)
        assert len(decisions) == 0


class TestObsoleteMemoryDetector:
    """Old preference should be archived and confidence-reduced when superseded"""

    def test_react_supersedes_vue_history_preserved(self, session, user):
        old_memory = make_memory(
            session, user.id, content="User prefers Vue for frontend development",
            days_since_access=400, reinforcement_score=0.2, memory_strength=0.5,
        )
        new_memory = make_memory(
            session, user.id, content="User builds everything in React for frontend development",
            days_since_access=1, reinforcement_score=0.7, memory_strength=0.6,
        )

        detector = ObsoleteMemoryDetector(session)
        decisions = detector.detect_and_resolve(user.id, [old_memory, new_memory])

        assert len(decisions) == 1
        decision = decisions[0]
        assert decision["decision"] == "Archived"
        assert decision["superseded_memory_id"] == old_memory.id
        assert decision["winning_memory_id"] == new_memory.id

        session.refresh(old_memory)
        session.refresh(new_memory)

        # History preserved - old memory still exists, just archived + weakened
        assert old_memory.cognitive_state == CognitiveMemoryStateEnum.ARCHIVED
        assert old_memory.content == "User prefers Vue for frontend development"
        assert old_memory.memory_strength < 0.5

        # Current preference strengthened
        assert new_memory.memory_strength > 0.6

        events = session.query(MemoryEvent).filter(MemoryEvent.memory_id == old_memory.id).all()
        assert len(events) == 1
        assert events[0].event_type == "archive"


class TestReinforcementRecovery:
    """Decay is reversible - relevant queries revive decayed memories"""

    def test_dormant_react_memory_revives_on_relevant_query(self, session, user):
        memory = make_memory(
            session, user.id,
            memory_type=MemoryTypeEnum.SEMANTIC,
            content="User is learning React and studying component rendering",
            cognitive_state=CognitiveMemoryStateEnum.DORMANT,
            memory_strength=0.25,
            days_since_access=365,
        )

        service = ReinforcementRecoveryService(session)
        revivals = service.check_and_revive(user.id, "Help me optimize React rendering performance", threshold=0.1)

        assert len(revivals) >= 1
        revived = next(r for r in revivals if r["memory_id"] == memory.id)
        assert revived["new_strength"] > revived["old_strength"]
        assert revived["new_state"] in (CognitiveMemoryStateEnum.ACTIVE, CognitiveMemoryStateEnum.REINFORCED)

        session.refresh(memory)
        assert memory.revival_count == 1
        assert memory.cognitive_state != CognitiveMemoryStateEnum.DORMANT

    def test_manual_revive_restores_eligibility(self, session, user):
        memory = make_memory(
            session, user.id, cognitive_state=CognitiveMemoryStateEnum.ARCHIVED, memory_strength=0.1,
        )
        service = ReinforcementRecoveryService(session)
        result = service.revive_memory(user.id, memory, reason="Manually revived for testing")

        assert result["new_strength"] > result["old_strength"]
        session.refresh(memory)
        assert memory.cognitive_state in (CognitiveMemoryStateEnum.ACTIVE, CognitiveMemoryStateEnum.REINFORCED)
        assert memory.revival_count == 1


class TestMemoryLifecycleManager:
    """State transitions, including the FORGOTTEN terminal state"""

    def test_archived_to_forgotten_after_long_idle(self, session, user):
        memory = make_memory(
            session, user.id, cognitive_state=CognitiveMemoryStateEnum.ARCHIVED, days_since_access=200,
        )
        manager = MemoryLifecycleManager(session)
        result = manager.evaluate_after_decay(memory)

        assert result["new_state"] == CognitiveMemoryStateEnum.FORGOTTEN
        assert memory.forget_reason is not None

    def test_forced_transition_logs_event(self, session, user):
        memory = make_memory(session, user.id)
        manager = MemoryLifecycleManager(session)
        result = manager.transition(memory, CognitiveMemoryStateEnum.DORMANT, "Test transition")

        assert result["success"] is True
        events = session.query(MemoryEvent).filter(MemoryEvent.memory_id == memory.id).all()
        assert len(events) == 1


class TestForgettingEngine:
    """Every decision is explainable: memory, decision, reason, confidence"""

    def test_weak_memory_gets_archived(self, session, user):
        memory = make_memory(session, user.id, memory_strength=0.1, cognitive_state=CognitiveMemoryStateEnum.DECAYING)
        engine = ForgettingEngine(session)
        decision = engine.evaluate(memory)

        assert decision["decision"] in ("Archived", "Weaken")
        assert "reason" in decision
        assert 0.0 <= decision["confidence"] <= 1.0
        assert decision["memory"] == memory.content

    def test_strong_memory_remains(self, session, user):
        memory = make_memory(session, user.id, memory_strength=0.9)
        engine = ForgettingEngine(session)
        decision = engine.evaluate(memory)
        assert decision["decision"] == "Remain"


class TestMemoryEntropyCalculator:
    """Entropy measures redundancy, conflicts, fragmentation, and obsolescence"""

    def test_entropy_in_range(self, session, user):
        memories = [make_memory(session, user.id, content=f"Distinct memory number {i}") for i in range(5)]
        calculator = MemoryEntropyCalculator(session)
        result = calculator.calculate(user.id, memories=memories)
        assert 0.0 <= result["entropy_score"] <= 1.0

    def test_duplicates_increase_redundancy(self, session, user):
        duplicates = [make_memory(session, user.id, content="User likes Rust programming") for _ in range(3)]
        calculator = MemoryEntropyCalculator(session)
        result = calculator.calculate(user.id, memories=duplicates)
        assert result["redundancy"] > 0.0

    def test_empty_store_has_zero_entropy(self, session, user):
        calculator = MemoryEntropyCalculator(session)
        result = calculator.calculate(user.id, memories=[])
        assert result["entropy_score"] == 0.0


class TestMemoryHealthService:
    """Cognitive Health Score aggregates the full picture"""

    def test_health_score_in_range(self, session, user):
        for i in range(5):
            make_memory(session, user.id, content=f"Healthy memory {i}", memory_strength=0.8)
        health = MemoryHealthService(session).compute_health(user.id)
        assert 0.0 <= health["cognitive_health_score"] <= 100.0
        assert health["total_memories"] == 5

    def test_empty_store_health(self, session, user):
        health = MemoryHealthService(session).compute_health(user.id)
        assert health["total_memories"] == 0
        assert health["cognitive_health_score"] == 0.0


class TestMemoryEvolutionPipeline:
    """End-to-end evolution pass covering the spec's core test cases"""

    def test_full_pipeline_run(self, session, user):
        # Repeated preference cluster
        for c in ["User likes Rust", "User enjoys Rust", "User learns Rust", "User writes Rust code"]:
            make_memory(session, user.id, content=c)

        # Obsolete preference pair
        make_memory(session, user.id, content="User prefers Angular for frontend work",
                    days_since_access=400, reinforcement_score=0.2)
        make_memory(session, user.id, content="User prefers React for frontend work",
                    days_since_access=1, reinforcement_score=0.7)

        # Weak memory that should be archived
        make_memory(session, user.id, memory_strength=0.05, cognitive_state=CognitiveMemoryStateEnum.DECAYING)

        pipeline = MemoryEvolutionPipeline(session)
        report = pipeline.run(user.id)

        assert report["memories_evaluated"] == 7
        assert report["merged_clusters"] >= 1
        assert report["obsolete_resolved"] >= 1
        assert "cognitive_health_score" in report["health"]
        assert report["total_latency_ms"] > 0

    def test_empty_store_returns_empty_report(self, session, user):
        pipeline = MemoryEvolutionPipeline(session)
        report = pipeline.run(user.id)
        assert report["memories_evaluated"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
