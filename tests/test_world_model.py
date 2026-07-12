"""Tests for the Day 9 World Model Engine"""
import pytest
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.db.models import (
    User, WorldEntity, WorldEntityTypeEnum, WorldRelationship,
    Project, ProjectStatusEnum, ArchitecturalDecision,
)
from app.services.entity_extractor import EntityExtractor
from app.services.relationship_builder import RelationshipBuilder
from app.services.world_graph import WorldGraph
from app.services.project_engine import ProjectMemoryEngine
from app.services.decision_engine import DecisionMemoryEngine
from app.services.active_context_engine import ActiveContextEngine
from app.services.timeline_engine import TimelineEngine
from app.services.environmental_context_engine import EnvironmentalContextEngine
from app.services.predictive_project_intelligence import PredictiveProjectIntelligence
from app.services.world_traversal import WorldTraversalService
from app.services.world_model_pipeline import WorldModelPipeline


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[
        User.__table__, WorldEntity.__table__, WorldRelationship.__table__,
        Project.__table__, ArchitecturalDecision.__table__,
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


class TestEntityExtractor:
    """Detects real-world entities from text"""

    def test_extracts_technology_keywords(self, session, user):
        extractor = EntityExtractor(session)
        entities = extractor.extract(user.id, "I'm using FastAPI and PostgreSQL for the backend")
        names = {e.entity_name for e in entities}
        assert "FastAPI" in names
        assert "PostgreSQL" in names
        assert all(e.entity_type == WorldEntityTypeEnum.TECHNOLOGY for e in entities if e.entity_name in ("FastAPI", "PostgreSQL"))

    def test_extracts_project_from_building_pattern(self, session, user):
        extractor = EntityExtractor(session)
        entities = extractor.extract(user.id, "I started building NeuroWeave last month")
        project_entities = [e for e in entities if e.entity_type == WorldEntityTypeEnum.PROJECT]
        assert any(e.entity_name == "NeuroWeave" for e in project_entities)

    def test_repeated_mentions_reinforce_confidence(self, session, user):
        extractor = EntityExtractor(session)
        extractor.extract(user.id, "I'm using Redis for caching")
        entities_second = extractor.extract(user.id, "Redis is working well")

        redis_entities = [e for e in entities_second if e.entity_name == "Redis"]
        assert len(redis_entities) == 1
        assert redis_entities[0].mention_count == 2

    def test_empty_text_returns_no_entities(self, session, user):
        extractor = EntityExtractor(session)
        assert extractor.extract(user.id, "") == []


class TestRelationshipBuilder:
    """Infers typed, weighted relationships between co-occurring entities"""

    def test_infers_uses_relationship(self, session, user):
        extractor = EntityExtractor(session)
        entities = extractor.extract(user.id, "NeuroWeave uses PostgreSQL for storage")

        builder = RelationshipBuilder(session)
        relationships = builder.build(user.id, entities, "NeuroWeave uses PostgreSQL for storage")

        uses_rels = [r for r in relationships if r.relationship_type == "uses"]
        assert len(uses_rels) >= 1

    def test_single_entity_produces_no_relationships(self, session, user):
        extractor = EntityExtractor(session)
        entities = extractor.extract(user.id, "I'm using FastAPI")
        builder = RelationshipBuilder(session)
        assert builder.build(user.id, entities, "I'm using FastAPI") == []


class TestWorldGraph:
    """Builds the World Model Graph from entities and relationships"""

    def test_graph_contains_entities_and_relationships(self, session, user):
        extractor = EntityExtractor(session)
        entities = extractor.extract(user.id, "NeuroWeave uses PostgreSQL and Redis")
        builder = RelationshipBuilder(session)
        builder.build(user.id, entities, "NeuroWeave uses PostgreSQL and Redis")

        world_graph = WorldGraph()
        graph = world_graph.build_graph_for_user(session, user.id)
        stats = world_graph.get_graph_statistics()

        assert stats["node_count"] == len(entities)
        assert graph.number_of_nodes() == len(entities)


class TestProjectMemoryEngine:
    """Projects are first-class citizens with phase, next step, and tech stack"""

    def test_creates_and_updates_project(self, session, user):
        extractor = EntityExtractor(session)
        text = "I started building NeuroWeave. I'm currently implementing Day 9."
        entities = extractor.extract(user.id, text)
        project_entities = [e for e in entities if e.entity_type == WorldEntityTypeEnum.PROJECT]

        engine = ProjectMemoryEngine(session)
        projects = engine.update_from_text(user.id, project_entities, text)

        assert len(projects) == 1
        assert projects[0].project_name == "NeuroWeave"
        assert "Day 9" in projects[0].current_phase
        assert projects[0].status == ProjectStatusEnum.ACTIVE

    def test_tech_stack_recorded(self, session, user):
        extractor = EntityExtractor(session)
        text = "Building NeuroWeave with FastAPI and PostgreSQL"
        entities = extractor.extract(user.id, text)
        project_entities = [e for e in entities if e.entity_type == WorldEntityTypeEnum.PROJECT]
        tech_entities = [e for e in entities if e.entity_type == WorldEntityTypeEnum.TECHNOLOGY]

        engine = ProjectMemoryEngine(session)
        projects = engine.update_from_text(user.id, project_entities, text, tech_entities)

        assert "FastAPI" in projects[0].tech_stack
        assert "PostgreSQL" in projects[0].tech_stack


class TestDecisionMemoryEngine:
    """Tracks architectural decisions with reasons, never overwriting history"""

    def test_detects_migration_decision(self, session, user):
        engine = DecisionMemoryEngine(session)
        decisions = engine.detect_and_record(user.id, "I'll migrate retrieval to Rust later.")
        assert len(decisions) >= 1
        assert "rust" in decisions[0].decision.lower()

    def test_detects_postponed_decision_with_reason(self, session, user):
        engine = DecisionMemoryEngine(session)
        text = "Rust migration postponed because rapid iteration in Python is more valuable right now."
        decisions = engine.detect_and_record(user.id, text)
        assert len(decisions) >= 1
        postponed = [d for d in decisions if d.status == "postponed"]
        assert len(postponed) == 1
        assert postponed[0].reason is not None

    def test_manual_record_never_overwrites(self, session, user):
        engine = DecisionMemoryEngine(session)
        d1 = engine.record(user.id, "Use PostgreSQL", reason="Strong ecosystem")
        d2 = engine.record(user.id, "Use PostgreSQL with pgvector", reason="Need vector search", status="superseded")

        history = session.query(ArchitecturalDecision).filter(ArchitecturalDecision.user_id == user.id).all()
        assert len(history) == 2
        assert d1.id != d2.id


class TestActiveContextEngine:
    """The world model always knows the current project, milestone, and stack"""

    def test_returns_active_project_context(self, session, user):
        project = Project(
            id=uuid4(), user_id=user.id, project_name="NeuroWeave",
            status=ProjectStatusEnum.ACTIVE, current_phase="Day 9",
            next_step="Day 10", tech_stack=["FastAPI", "PostgreSQL"],
        )
        session.add(project)
        session.commit()

        engine = ActiveContextEngine(session)
        context = engine.get_active_context(user.id)

        assert context["current_project"]["name"] == "NeuroWeave"
        assert context["current_milestone"] == "Day 9"
        assert "Day 10" in context["current_priorities"]


class TestTimelineEngine:
    """Represents past, present, and future for tracked projects"""

    def test_timeline_has_past_present_future(self, session, user):
        project = Project(
            id=uuid4(), user_id=user.id, project_name="NeuroWeave",
            status=ProjectStatusEnum.ACTIVE, current_phase="Day 9", next_step="Day 10",
        )
        session.add(project)
        session.commit()

        DecisionMemoryEngine(session).record(user.id, "Use FastAPI", project_id=project.id)

        timeline = TimelineEngine(session).get_timeline(user.id)
        assert len(timeline["past"]) >= 1
        assert len(timeline["present"]) == 1
        assert any(f["label"] == "Day 10" for f in timeline["future"])


class TestEnvironmentalContextEngine:
    """Represents the user's actual development environment"""

    def test_categorizes_environment_entities(self, session, user):
        extractor = EntityExtractor(session)
        extractor.extract(user.id, "I develop on macOS using VS Code, deploy to AWS, and use GitHub")

        engine = EnvironmentalContextEngine(session)
        env = engine.get_environment(user.id)

        assert "macOS" in env["operating_system"]
        assert "VS Code" in env["ide"]
        assert "AWS" in env["cloud_providers"]
        assert "GitHub" in env["integrations"]


class TestPredictiveProjectIntelligence:
    """Proactively predicts next steps, blockers, and missing knowledge"""

    def test_predicts_missing_knowledge_from_stack(self, session, user):
        project = Project(
            id=uuid4(), user_id=user.id, project_name="NeuroWeave",
            status=ProjectStatusEnum.ACTIVE, tech_stack=["FastAPI", "PostgreSQL"],
        )
        session.add(project)
        session.commit()

        intelligence = PredictiveProjectIntelligence(session)
        result = intelligence.predict(user.id, project.id)

        assert result["project_name"] == "NeuroWeave"
        assert len(result["likely_missing_knowledge"]) > 0
        assert 0.0 <= result["confidence"] <= 1.0

    def test_next_task_from_next_step(self, session, user):
        project = Project(
            id=uuid4(), user_id=user.id, project_name="NeuroWeave",
            status=ProjectStatusEnum.ACTIVE, next_step="Build the SDK",
        )
        session.add(project)
        session.commit()

        result = PredictiveProjectIntelligence(session).predict(user.id, project.id)
        assert result["likely_next_task"] == "Build the SDK"

    def test_no_project_returns_empty_prediction(self, session, user):
        result = PredictiveProjectIntelligence(session).predict(user.id)
        assert result["likely_next_task"] is None
        assert result["confidence"] == 0.0


class TestWorldTraversalService:
    """Graph traversal: dependencies, affected systems, explained paths"""

    def test_find_dependencies_follows_dependency_edges_only(self, session, user):
        extractor = EntityExtractor(session)
        text = "NeuroWeave uses PostgreSQL. NeuroWeave uses Redis."
        entities = extractor.extract(user.id, text)
        RelationshipBuilder(session).build(user.id, entities, text)

        neuroweave = next(e for e in entities if e.entity_name == "NeuroWeave")
        traversal = WorldTraversalService(session, user.id)
        deps = traversal.find_dependencies(neuroweave.id)

        dep_names = {d["name"] for d in deps}
        assert "PostgreSQL" in dep_names or "Redis" in dep_names

    def test_explain_path_between_entities(self, session, user):
        extractor = EntityExtractor(session)
        text = "NeuroWeave uses PostgreSQL for storage"
        entities = extractor.extract(user.id, text)
        RelationshipBuilder(session).build(user.id, entities, text)

        neuroweave = next(e for e in entities if e.entity_name == "NeuroWeave" or e.entity_type == WorldEntityTypeEnum.PROJECT)
        postgres = next(e for e in entities if e.entity_name == "PostgreSQL")

        traversal = WorldTraversalService(session, user.id)
        explanation = traversal.explain_path(neuroweave.id, postgres.id)

        assert explanation is not None
        assert explanation["length"] >= 1


class TestWorldModelPipeline:
    """End-to-end pipeline covering the spec's exact test case"""

    def test_neuroweave_conversation_builds_expected_world_model(self, session, user):
        conversation = (
            "I started building NeuroWeave. "
            "I'm using FastAPI. "
            "I'll migrate retrieval to Rust later. "
            "I'm currently implementing Day 9."
        )

        pipeline = WorldModelPipeline(session)
        result = pipeline.update(user.id, conversation)

        assert result["entities_extracted"] > 0
        assert result["projects_touched"] == 1
        assert result["decisions_recorded"] >= 1

        project = result["projects"][0]
        assert project.project_name == "NeuroWeave"
        assert project.status == ProjectStatusEnum.ACTIVE
        assert "Day 9" in project.current_phase
        assert "FastAPI" in project.tech_stack

        decision = result["decisions"][0]
        assert "rust" in decision.decision.lower()

        assert result["active_context"]["current_project"]["name"] == "NeuroWeave"
        assert result["total_latency_ms"] > 0

    def test_infrastructure_conversation(self, session, user):
        text = "Deploy Redis. Connect PostgreSQL. Benchmark retrieval."
        pipeline = WorldModelPipeline(session)
        result = pipeline.update(user.id, text)

        entity_names = {e.entity_name for e in result["entities"]}
        assert "Redis" in entity_names
        assert "PostgreSQL" in entity_names

    def test_empty_text_completes_without_error(self, session, user):
        pipeline = WorldModelPipeline(session)
        result = pipeline.update(user.id, "")
        assert result["entities_extracted"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
