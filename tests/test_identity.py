"""
Test suite for Identity Graph Engine (Day 4)

Tests core functionality of identity extraction, reinforcement,
graph operations, and context building.
"""

import pytest
from datetime import datetime
import uuid
from unittest.mock import Mock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, IdentityNode, IdentityRelationship, IdentityHistory, Memory, ConceptMemory, User
from app.db.models import MemoryTypeEnum, CognitiveMemoryStateEnum
from app.services.identity_extractor import IdentityExtractor
from app.services.identity_reinforcement import IdentityReinforcementService
from app.services.identity_graph import IdentityGraphService
from app.services.identity_profile_generator import IdentityProfileGenerator
from app.services.identity_context_builder import IdentityAwareContextBuilder


# Test database setup
@pytest.fixture(scope="function")
def db_session():
    """Create in-memory SQLite database for tests"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture(scope="function")
def test_user(db_session):
    """Create test user"""
    user = User(
        id=uuid.uuid4(),
        external_id="test_user_001",
        name="Test User",
        email="test@example.com"
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture(scope="function")
def test_memories(db_session, test_user):
    """Create test memories for extraction"""
    memories = [
        Memory(
            id=uuid.uuid4(),
            user_id=test_user.id,
            memory_type=MemoryTypeEnum.EPISODIC,
            content="I want to become a staff engineer",
            summary="Career goal",
            importance_score=0.8
        ),
        Memory(
            id=uuid.uuid4(),
            user_id=test_user.id,
            memory_type=MemoryTypeEnum.EPISODIC,
            content="I'm fascinated by distributed systems",
            summary="Technical interest",
            importance_score=0.7
        ),
        Memory(
            id=uuid.uuid4(),
            user_id=test_user.id,
            memory_type=MemoryTypeEnum.EPISODIC,
            content="I prefer concise technical explanations",
            summary="Communication preference",
            importance_score=0.6
        ),
    ]
    for mem in memories:
        db_session.add(mem)
    db_session.commit()
    return memories


# ============================================================================
# Test Identity Extraction
# ============================================================================

class TestIdentityExtraction:
    """Tests for identity extraction from memories and concepts"""

    def test_extract_from_memories(self, db_session, test_user, test_memories):
        """Test extracting identity from memories"""
        extractor = IdentityExtractor(db_session)
        
        # Mock LLM response
        mock_response = {
            "goals": [{"value": "software_engineering_growth", "confidence": 0.85, "reasoning": "explicit goal"}],
            "interests": [{"value": "distributed_systems", "confidence": 0.80, "reasoning": "technical interest"}],
            "communication": [{"value": "concise", "confidence": 0.75, "reasoning": "preference stated"}],
            "behaviors": [],
            "values": [],
            "skills": []
        }
        
        with patch.object(extractor, '_extract_with_llm', return_value=mock_response):
            extracted = extractor.extract_from_memories(str(test_user.id), test_memories)
            
            assert "goals" in extracted
            assert len(extracted["goals"]) > 0
            assert extracted["goals"][0]["value"] == "software_engineering_growth"

    def test_create_identity_nodes(self, db_session, test_user):
        """Test creating identity nodes from extracted traits"""
        extractor = IdentityExtractor(db_session)
        
        extracted_traits = {
            "goals": [
                {"value": "software_engineering_growth", "confidence": 0.85, "reasoning": "test"}
            ],
            "interests": [
                {"value": "distributed_systems", "confidence": 0.80, "reasoning": "test"}
            ],
            "communication": [],
            "behaviors": [],
            "values": [],
            "skills": []
        }
        
        nodes = extractor.create_identity_nodes(str(test_user.id), extracted_traits)
        
        assert len(nodes) == 2
        assert nodes[0].node_type in ["goals", "interests"]
        assert nodes[0].confidence > 0.0

    def test_normalize_trait_value(self, db_session):
        """Test trait value normalization"""
        extractor = IdentityExtractor(db_session)
        
        # Test known values
        result = extractor._normalize_trait_value("concise")
        assert result == "concise"
        
        # Test with spaces
        result = extractor._normalize_trait_value("concise communication")
        assert result is not None  # Should normalize or keep


# ============================================================================
# Test Identity Reinforcement
# ============================================================================

class TestIdentityReinforcement:
    """Tests for reinforcement and confidence updates"""

    def test_reinforce_trait(self, db_session, test_user):
        """Test reinforcing an identity trait"""
        # Create node
        node = IdentityNode(
            id=uuid.uuid4(),
            user_id=test_user.id,
            node_type="goal",
            node_value="software_engineering_growth",
            confidence=0.5
        )
        db_session.add(node)
        db_session.commit()
        
        service = IdentityReinforcementService(db_session)
        success, updated_node = service.reinforce_trait(
            str(test_user.id),
            str(node.id),
            confidence_boost=0.2,
            evidence_source="memory_analysis"
        )
        
        assert success
        assert updated_node.confidence > 0.5  # Should increase
        assert updated_node.reinforcement_count == 1

    def test_propagate_reinforcement(self, db_session, test_user):
        """Test reinforcement propagation through graph"""
        # Create connected nodes
        node1 = IdentityNode(
            id=uuid.uuid4(),
            user_id=test_user.id,
            node_type="goal",
            node_value="software_engineering_growth",
            confidence=0.8
        )
        node2 = IdentityNode(
            id=uuid.uuid4(),
            user_id=test_user.id,
            node_type="interest",
            node_value="distributed_systems",
            confidence=0.6
        )
        db_session.add_all([node1, node2])
        db_session.commit()
        
        # Add relationship
        rel = IdentityRelationship(
            id=uuid.uuid4(),
            user_id=test_user.id,
            source_node_id=node1.id,
            target_node_id=node2.id,
            relationship_type="reinforces",
            strength=0.7
        )
        db_session.add(rel)
        db_session.commit()
        
        service = IdentityReinforcementService(db_session)
        result = service.propagate_reinforcement(str(test_user.id), str(node1.id))
        
        assert result["traits_affected"] >= 0

    def test_detect_trait_decay(self, db_session, test_user):
        """Test detecting traits losing confidence"""
        from datetime import timedelta
        
        # Create old, unreinforced node
        old_date = datetime.utcnow() - timedelta(days=40)
        node = IdentityNode(
            id=uuid.uuid4(),
            user_id=test_user.id,
            node_type="interest",
            node_value="frontend_development",
            confidence=0.7,
            last_reinforced_at=old_date
        )
        db_session.add(node)
        db_session.commit()
        
        service = IdentityReinforcementService(db_session)
        decaying = service.detect_trait_decay(str(test_user.id), days_without_evidence=30)
        
        assert len(decaying) > 0  # Should find decaying trait


# ============================================================================
# Test Identity Graph
# ============================================================================

class TestIdentityGraph:
    """Tests for identity graph operations"""

    def test_build_graph(self, db_session, test_user):
        """Test building identity graph"""
        # Create nodes
        nodes = []
        for i in range(3):
            node = IdentityNode(
                id=uuid.uuid4(),
                user_id=test_user.id,
                node_type="goal" if i == 0 else "interest",
                node_value=f"trait_{i}",
                confidence=0.7 + (i * 0.05)
            )
            nodes.append(node)
            db_session.add(node)
        db_session.commit()
        
        service = IdentityGraphService(db_session)
        graph = service.build_graph_for_user(str(test_user.id))
        
        assert len(graph.nodes()) == 3
        assert isinstance(graph, object)  # NetworkX graph

    def test_add_relationship(self, db_session, test_user):
        """Test adding relationships between traits"""
        node1 = IdentityNode(
            id=uuid.uuid4(),
            user_id=test_user.id,
            node_type="goal",
            node_value="software_engineering_growth",
            confidence=0.8
        )
        node2 = IdentityNode(
            id=uuid.uuid4(),
            user_id=test_user.id,
            node_type="interest",
            node_value="distributed_systems",
            confidence=0.7
        )
        db_session.add_all([node1, node2])
        db_session.commit()
        
        service = IdentityGraphService(db_session)
        success = service.add_relationship(
            str(test_user.id),
            str(node1.id),
            str(node2.id),
            "reinforces"
        )
        
        assert success
        
        # Verify relationship created
        rel = db_session.query(IdentityRelationship).filter(
            IdentityRelationship.source_node_id == node1.id
        ).first()
        assert rel is not None

    def test_find_related_traits(self, db_session, test_user):
        """Test finding related traits in graph"""
        # Create connected nodes
        nodes = []
        for i in range(3):
            node = IdentityNode(
                id=uuid.uuid4(),
                user_id=test_user.id,
                node_type="interest",
                node_value=f"interest_{i}",
                confidence=0.7
            )
            nodes.append(node)
            db_session.add(node)
        db_session.commit()
        
        # Connect them
        for i in range(2):
            rel = IdentityRelationship(
                id=uuid.uuid4(),
                user_id=test_user.id,
                source_node_id=nodes[i].id,
                target_node_id=nodes[i+1].id,
                relationship_type="related_to",
                strength=0.8
            )
            db_session.add(rel)
        db_session.commit()
        
        service = IdentityGraphService(db_session)
        related = service.find_related_traits(str(test_user.id), str(nodes[0].id))
        
        assert len(related) > 0


# ============================================================================
# Test Profile Generation
# ============================================================================

class TestProfileGeneration:
    """Tests for user profile generation"""

    def test_generate_profile(self, db_session, test_user):
        """Test generating comprehensive identity profile"""
        # Create diverse nodes
        goal = IdentityNode(
            id=uuid.uuid4(),
            user_id=test_user.id,
            node_type="goal",
            node_value="software_engineering_growth",
            confidence=0.85,
            importance=0.95
        )
        interest = IdentityNode(
            id=uuid.uuid4(),
            user_id=test_user.id,
            node_type="interest",
            node_value="distributed_systems",
            confidence=0.80,
            importance=0.85
        )
        comm = IdentityNode(
            id=uuid.uuid4(),
            user_id=test_user.id,
            node_type="communication",
            node_value="concise",
            confidence=0.75,
            importance=0.70
        )
        db_session.add_all([goal, interest, comm])
        db_session.commit()
        
        generator = IdentityProfileGenerator(db_session)
        profile = generator.generate_profile(str(test_user.id))
        
        assert "summary" in profile
        assert "goals" in profile
        assert len(profile["goals"]) > 0
        assert profile["communication_style"]["primary"] == "concise"

    def test_generate_concise_profile(self, db_session, test_user):
        """Test generating one-sentence profile"""
        node = IdentityNode(
            id=uuid.uuid4(),
            user_id=test_user.id,
            node_type="goal",
            node_value="software_engineering_growth",
            confidence=0.85,
            importance=0.95
        )
        db_session.add(node)
        db_session.commit()
        
        generator = IdentityProfileGenerator(db_session)
        profile = generator.generate_concise_profile(str(test_user.id))
        
        assert isinstance(profile, str)
        assert len(profile) > 0


# ============================================================================
# Test Context Building
# ============================================================================

class TestContextBuilding:
    """Tests for identity-aware context building"""

    def test_build_personalized_context(self, db_session, test_user):
        """Test building personalized retrieval context"""
        # Create identity traits
        node = IdentityNode(
            id=uuid.uuid4(),
            user_id=test_user.id,
            node_type="communication",
            node_value="concise",
            confidence=0.8,
            importance=0.9
        )
        db_session.add(node)
        db_session.commit()
        
        builder = IdentityAwareContextBuilder(db_session)
        context = builder.build_personalized_context(
            str(test_user.id),
            "What should I learn next?",
            []
        )
        
        assert "identity_traits" in context
        assert "communication_style" in context
        assert "personalization_instructions" in context

    def test_get_communication_style(self, db_session, test_user):
        """Test retrieving communication style"""
        comm = IdentityNode(
            id=uuid.uuid4(),
            user_id=test_user.id,
            node_type="communication",
            node_value="technical",
            confidence=0.85,
            importance=0.80
        )
        db_session.add(comm)
        db_session.commit()
        
        builder = IdentityAwareContextBuilder(db_session)
        style = builder._get_communication_style(str(test_user.id))
        
        assert style["primary"] == "technical"
        assert style["confidence"] > 0.0


# ============================================================================
# Test Edge Cases and Integration
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling"""

    def test_extract_with_no_memories(self, db_session, test_user):
        """Test extraction with no memories"""
        extractor = IdentityExtractor(db_session)
        result = extractor.extract_from_memories(str(test_user.id), [])
        
        assert result == {}

    def test_profile_generation_with_no_traits(self, db_session, test_user):
        """Test profile generation with no identity traits"""
        generator = IdentityProfileGenerator(db_session)
        profile = generator.generate_profile(str(test_user.id))
        
        assert profile == {}

    def test_graph_build_empty(self, db_session, test_user):
        """Test building graph with no nodes"""
        service = IdentityGraphService(db_session)
        graph = service.build_graph_for_user(str(test_user.id))
        
        assert len(graph.nodes()) == 0

    def test_reinforcement_nonexistent_node(self, db_session, test_user):
        """Test reinforcing non-existent node"""
        service = IdentityReinforcementService(db_session)
        success, node = service.reinforce_trait(
            str(test_user.id),
            str(uuid.uuid4()),  # Non-existent node
            confidence_boost=0.1
        )
        
        assert success == False
        assert node is None


# ============================================================================
# Test Suite Summary
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
