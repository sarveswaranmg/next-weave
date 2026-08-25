"""Tests for the Day 8 Offline Cognitive Consolidation Engine ("Dream Mode")"""
import pytest
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from neurowave_engine.db.database import Base
from neurowave_engine.db.models import (
    User, Memory, MemoryTypeEnum, CognitiveMemoryStateEnum,
    ConceptMemory, ConceptRelationship, IdentityNode, IdentityRelationship,
    MemoryEvent, MemoryEmbedding, DreamSession, DreamSessionStatusEnum,
    KnowledgeSynthesis, IdentityEvolutionEvent, PredictiveRecallLog, ContextSnapshot,
)
from neurowave_engine.services.replay_engine import ReplayEngine
from neurowave_engine.services.pattern_discovery import PatternDiscoveryEngine
from neurowave_engine.services.concept_refiner import ConceptRefiner
from neurowave_engine.services.identity_evolution import IdentityEvolutionEngine
from neurowave_engine.services.consistency_engine import ConsistencyEngine
from neurowave_engine.services.graph_optimizer import GraphOptimizationEngine
from neurowave_engine.services.knowledge_synthesizer import KnowledgeSynthesizer
from neurowave_engine.services.compression_optimizer import CompressionOptimizer
from neurowave_engine.services.dream_scheduler import DreamScheduler
from neurowave_engine.services.dream_pipeline import DreamPipeline


def make_memory(session, user_id, content="Some memory content", memory_type=MemoryTypeEnum.SEMANTIC,
                 importance_score=0.6, reinforcement_score=0.5, memory_strength=0.6,
                 cognitive_state=CognitiveMemoryStateEnum.ACTIVE, days_since_access=1):
    now = datetime.utcnow()
    m = Memory(
        id=uuid4(), user_id=user_id, memory_type=memory_type, content=content,
        importance_score=importance_score, reinforcement_score=reinforcement_score,
        memory_strength=memory_strength, decay_rate=0.05, cognitive_state=cognitive_state,
        created_at=now - timedelta(days=days_since_access + 2),
        last_accessed=now - timedelta(days=days_since_access),
        retrieval_count=1, emotional_salience_score=0.5, revival_count=0,
    )
    session.add(m)
    session.commit()
    return m


def make_concept(session, user_id, name, description="", confidence=0.7, support_count=2, days_old=1):
    now = datetime.utcnow()
    c = ConceptMemory(
        id=uuid4(), user_id=user_id, concept_name=name, description=description,
        confidence=confidence, support_count=support_count, supporting_memory_ids=[],
        last_reinforced_at=now - timedelta(days=days_old), created_at=now - timedelta(days=days_old),
    )
    session.add(c)
    session.commit()
    return c


def make_identity_node(session, user_id, node_type, value, confidence=0.6, importance=0.5,
                        evidence_count=2, days_old=1):
    now = datetime.utcnow()
    n = IdentityNode(
        id=uuid4(), user_id=user_id, node_type=node_type, node_value=value,
        confidence=confidence, importance=importance, evidence_count=evidence_count,
        last_reinforced_at=now - timedelta(days=days_old), created_at=now - timedelta(days=days_old),
    )
    session.add(n)
    session.commit()
    return n


class TestReplayEngine:
    """Replay prioritizes importance, uncertainty, conflicts, and reinforcement"""

    def test_prioritizes_high_importance_and_uncertainty(self, session, user):
        important = make_memory(session, user.id, content="Critical goal memory", importance_score=0.95)
        important.prediction_confidence = 0.3  # high uncertainty
        trivial = make_memory(session, user.id, content="Trivial aside", importance_score=0.1)
        trivial.prediction_confidence = 0.9
        session.commit()

        engine = ReplayEngine(session)
        selected = engine.select_for_replay(user.id, batch_size=1)

        assert selected[0].id == important.id

    def test_replay_rebuilds_scores(self, session, user):
        memory = make_memory(session, user.id, content="I am building an AI startup with a strong long-term goal")
        engine = ReplayEngine(session)
        results = engine.replay([memory])

        assert len(results) == 1
        assert "delta" in results[0]


class TestPatternDiscoveryEngine:
    """Discovers higher-order traits from accumulated evidence"""

    def test_discovers_systems_engineering_interest(self, session, user):
        make_memory(session, user.id, content="User studies distributed systems in depth")
        make_memory(session, user.id, content="User likes Rust for systems programming")
        make_memory(session, user.id, content="User researches operating systems and kernel internals")
        make_memory(session, user.id, content="User builds backend services daily")

        engine = PatternDiscoveryEngine(session)
        discovered = engine.discover(user.id)

        traits = [d["new_trait"] for d in discovered]
        assert "systems_engineering_interest" in traits
        match = next(d for d in discovered if d["new_trait"] == "systems_engineering_interest")
        assert 0.0 <= match["confidence"] <= 1.0

        node = session.query(IdentityNode).filter(
            IdentityNode.user_id == user.id, IdentityNode.node_value == "systems_engineering_interest"
        ).first()
        assert node is not None

    def test_no_discovery_without_enough_evidence(self, session, user):
        make_memory(session, user.id, content="User had coffee this morning")
        engine = PatternDiscoveryEngine(session)
        discovered = engine.discover(user.id)
        assert discovered == []

    def test_does_not_rediscover_existing_trait(self, session, user):
        make_identity_node(session, user.id, "trait", "systems_engineering_interest", confidence=0.8)
        for c in ["distributed systems", "rust", "operating systems", "backend"]:
            make_memory(session, user.id, content=f"User works with {c} extensively")

        engine = PatternDiscoveryEngine(session)
        discovered = engine.discover(user.id)
        assert all(d["new_trait"] != "systems_engineering_interest" for d in discovered)


class TestConceptRefiner:
    """Merge, generalize, strengthen, retire concepts - Case: large duplicate graph"""

    def test_merges_duplicate_concepts(self, session, user):
        make_concept(session, user.id, "rust_interest", "User likes Rust programming")
        make_concept(session, user.id, "rust_enthusiasm", "User enjoys Rust programming")

        refiner = ConceptRefiner(session)
        result = refiner.refine(user.id)

        assert len(result["merged"]) >= 1

    def test_generalizes_related_concept_cluster(self, session, user):
        # Distinct names (won't trip the merge pass) that share just enough
        # thematic overlap via description to be recognized as related.
        make_concept(session, user.id, "Backend", "core backend service")
        make_concept(session, user.id, "Distributed Systems", "backend architecture patterns")
        make_concept(session, user.id, "Infrastructure", "backend operations")

        refiner = ConceptRefiner(session)
        result = refiner.refine(user.id)

        assert len(result["generalized"]) >= 1
        assert "Backend" in result["generalized"][0]["new_concept_name"]

    def test_retires_stale_low_confidence_concepts(self, session, user):
        stale = make_concept(session, user.id, "obsolete_topic", confidence=0.05, days_old=200)
        refiner = ConceptRefiner(session)
        result = refiner.refine(user.id)

        retired_ids = [d["concept_id"] for d in result["retired"]]
        assert stale.id in retired_ids

    def test_strengthens_well_supported_concepts(self, session, user):
        concept = make_concept(session, user.id, "well_supported", confidence=0.5, support_count=5)
        refiner = ConceptRefiner(session)
        result = refiner.refine(user.id)

        strengthened_ids = [d["concept_id"] for d in result["strengthened"]]
        assert concept.id in strengthened_ids


class TestIdentityEvolutionEngine:
    """Identity evolves during sleep; history is preserved, not overwritten"""

    def test_identity_shift_detected_and_history_preserved(self, session, user):
        old_dominant = make_identity_node(
            session, user.id, "interest", "react", confidence=0.5, importance=0.5, days_old=200,
        )
        for value in ["rust", "distributed_systems", "databases"]:
            make_identity_node(session, user.id, "interest", value, confidence=0.85, importance=0.4, days_old=2)

        engine = IdentityEvolutionEngine(session)
        shifts = engine.evolve(user.id)

        assert len(shifts) == 1
        assert shifts[0]["old_identity"] == "react"
        assert shifts[0]["new_identity"] in ["rust", "distributed_systems", "databases"]

        # History preserved - old node untouched
        session.refresh(old_dominant)
        assert old_dominant.node_value == "react"
        assert old_dominant.confidence == 0.5

        events = session.query(IdentityEvolutionEvent).filter(IdentityEvolutionEvent.user_id == user.id).all()
        assert len(events) == 1
        assert events[0].old_identity == "react"


class TestConsistencyEngine:
    """Heals memory conflicts and duplicate identity traits"""

    def test_merges_duplicate_identity_traits(self, session, user):
        node_a = make_identity_node(session, user.id, "skill", "backend_engineering", confidence=0.7)
        node_b = make_identity_node(session, user.id, "skill", "backend engineer", confidence=0.5)

        engine = ConsistencyEngine(session)
        result = engine.heal(user.id)

        assert len(result["duplicate_identities_merged"]) >= 1
        merge = result["duplicate_identities_merged"][0]
        assert node_a.id == merge["primary_node_id"] or node_b.id == merge["primary_node_id"]

    def test_resolves_memory_conflicts(self, session, user):
        make_memory(session, user.id, content="User prefers Vue for frontend development",
                    days_since_access=300, reinforcement_score=0.2)
        make_memory(session, user.id, content="User builds everything in React for frontend development",
                    days_since_access=1, reinforcement_score=0.8)

        engine = ConsistencyEngine(session)
        result = engine.heal(user.id)
        assert len(result["memory_conflicts_resolved"]) == 1


class TestGraphOptimizationEngine:
    """Removes dead nodes, strengthens reinforced edges"""

    def test_removes_dead_concept_nodes(self, session, user):
        dead = make_concept(session, user.id, "dead_concept", confidence=0.05, support_count=1)
        alive = make_concept(session, user.id, "alive_concept", confidence=0.8, support_count=5)

        optimizer = GraphOptimizationEngine(session)
        result = optimizer.optimize(user.id)

        assert result["nodes_removed"] >= 1
        session.refresh(dead)
        session.refresh(alive)
        assert dead.confidence == 0.0
        assert alive.confidence == 0.8


class TestKnowledgeSynthesizer:
    """Generates new knowledge from multiple concepts"""

    def test_synthesizes_new_concept_from_group(self, session, user):
        for name in ["Distributed Systems", "Rust", "Backend", "Caching", "Scalability"]:
            make_concept(session, user.id, name, confidence=0.8, support_count=3)

        synthesizer = KnowledgeSynthesizer(session)
        results = synthesizer.synthesize(user.id)

        assert len(results) == 1
        assert results[0]["confidence"] >= 0.5
        assert len(results[0]["source_concepts"]) >= 3

        record = session.query(KnowledgeSynthesis).filter(KnowledgeSynthesis.user_id == user.id).first()
        assert record is not None
        assert record.new_concept == results[0]["synthesized_concept"]

    def test_no_synthesis_with_too_few_concepts(self, session, user):
        make_concept(session, user.id, "only_one", confidence=0.9)
        synthesizer = KnowledgeSynthesizer(session)
        results = synthesizer.synthesize(user.id)
        assert results == []


class TestCompressionOptimizer:
    """Reclaims embeddings for inactive memories"""

    def test_reclaims_embeddings_for_archived_memories(self, session, user):
        archived = make_memory(session, user.id, cognitive_state=CognitiveMemoryStateEnum.ARCHIVED)
        embedding = MemoryEmbedding(id=uuid4(), memory_id=archived.id, embedding="[0.1,0.2]", model="test")
        session.add(embedding)
        session.commit()

        optimizer = CompressionOptimizer(session)
        result = optimizer.optimize(user.id)

        assert result["embeddings_reclaimed"] == 1
        assert session.query(MemoryEmbedding).filter(MemoryEmbedding.memory_id == archived.id).count() == 0


class TestDreamScheduler:
    """Determines when to run and for which users"""

    def test_new_user_is_eligible(self, session, user):
        make_memory(session, user.id)
        scheduler = DreamScheduler(session)
        eligible = scheduler.eligible_users(trigger="manual")
        assert user.id in eligible

    def test_cooldown_excludes_recently_dreamed_user(self, session, user):
        make_memory(session, user.id)
        session.add(DreamSession(
            user_id=user.id, status=DreamSessionStatusEnum.COMPLETED,
            started_at=datetime.utcnow() - timedelta(minutes=5),
            finished_at=datetime.utcnow() - timedelta(minutes=1),
        ))
        session.commit()

        scheduler = DreamScheduler(session)
        eligible = scheduler.eligible_users(trigger="manual")
        assert user.id not in eligible

    def test_running_session_blocks_new_scheduling(self, session, user):
        make_memory(session, user.id)
        dream_session = DreamSession(user_id=user.id, status=DreamSessionStatusEnum.RUNNING)
        session.add(dream_session)
        session.commit()

        scheduler = DreamScheduler(session)
        assert scheduler.is_running(user.id) is True


class TestDreamPipeline:
    """End-to-end dream session covering the spec's core test cases"""

    def test_full_dream_session_completes(self, session, user):
        # Case 1: backend-related memories -> higher-level concepts
        for i, c in enumerate([
            "User studies distributed systems", "User likes Rust", "User researches operating systems",
            "User builds backend services", "User works on caching layers",
        ]):
            make_memory(session, user.id, content=c, importance_score=0.6 + i * 0.02)
        make_concept(session, user.id, "Backend Development")
        make_concept(session, user.id, "Backend Distributed Systems")
        make_concept(session, user.id, "Backend Infrastructure")

        # Case 2: contradictory preferences
        make_memory(session, user.id, content="User prefers Angular for frontend work",
                    days_since_access=300, reinforcement_score=0.2)
        make_memory(session, user.id, content="User prefers React for frontend work",
                    days_since_access=1, reinforcement_score=0.8)

        pipeline = DreamPipeline(session)
        dream_session = pipeline.run(user.id, trigger="manual")

        assert dream_session.status == DreamSessionStatusEnum.COMPLETED
        assert dream_session.finished_at is not None
        assert dream_session.memories_replayed > 0
        assert dream_session.health_score_before is not None
        assert dream_session.health_score_after is not None
        assert dream_session.total_latency_ms > 0
        assert "identity_shifts" in dream_session.extra_metadata

    def test_dream_session_can_be_stopped(self, session, user):
        make_memory(session, user.id)
        dream_session = DreamSession(user_id=user.id, status=DreamSessionStatusEnum.RUNNING)
        session.add(dream_session)
        session.commit()

        pipeline = DreamPipeline(session)
        success = pipeline.stop(dream_session.id)

        assert success is True
        session.refresh(dream_session)
        assert dream_session.status == DreamSessionStatusEnum.CANCELLED

    def test_empty_store_still_completes(self, session, user):
        pipeline = DreamPipeline(session)
        dream_session = pipeline.run(user.id)
        assert dream_session.status == DreamSessionStatusEnum.COMPLETED


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
