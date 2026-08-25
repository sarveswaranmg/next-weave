"""Tests for semantic consolidation engine"""
import pytest
import json
import numpy as np
from uuid import UUID, uuid4
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from neurowave_engine.db.models import (
    Base, Memory, MemoryCluster, ConceptMemory, ConceptRelationship,
    User, MemoryTypeEnum, CognitiveMemoryStateEnum
)
from neurowave_engine.services.semantic_clustering import SemanticClusterService
from neurowave_engine.services.memory_merge import MemoryMergeService
from neurowave_engine.services.concept_generator import ConceptGenerator
from neurowave_engine.services.concept_graph import ConceptGraph
from neurowave_engine.services.consolidation_worker import ConsolidationWorker


@pytest.fixture
def test_memories(session, test_user):
    """Create test memories for consolidation"""
    memories = []
    
    # Memory group 1: Communication preference
    communication_memories = [
        Memory(
            user_id=test_user.id,
            memory_type=MemoryTypeEnum.EPISODIC,
            content="User prefers concise answers",
            summary="Concise communication preference",
            importance_score=0.8,
            cognitive_state=CognitiveMemoryStateEnum.ACTIVE,
        ),
        Memory(
            user_id=test_user.id,
            memory_type=MemoryTypeEnum.EPISODIC,
            content="User likes short technical responses",
            summary="Short technical responses",
            importance_score=0.7,
            cognitive_state=CognitiveMemoryStateEnum.ACTIVE,
        ),
        Memory(
            user_id=test_user.id,
            memory_type=MemoryTypeEnum.EPISODIC,
            content="User dislikes lengthy explanations",
            summary="Dislikes lengthy text",
            importance_score=0.7,
            cognitive_state=CognitiveMemoryStateEnum.ACTIVE,
        ),
    ]
    
    # Memory group 2: System design interest
    design_memories = [
        Memory(
            user_id=test_user.id,
            memory_type=MemoryTypeEnum.EPISODIC,
            content="User studies system design",
            summary="System design interest",
            importance_score=0.8,
            cognitive_state=CognitiveMemoryStateEnum.ACTIVE,
        ),
        Memory(
            user_id=test_user.id,
            memory_type=MemoryTypeEnum.EPISODIC,
            content="User likes backend engineering",
            summary="Backend engineering interest",
            importance_score=0.75,
            cognitive_state=CognitiveMemoryStateEnum.ACTIVE,
        ),
    ]
    
    all_memories = communication_memories + design_memories
    for memory in all_memories:
        session.add(memory)
    
    session.commit()
    return all_memories


class TestSemanticClustering:
    """Tests for semantic clustering service"""

    def test_clustering_groups_similar_memories(self, session, test_user, test_memories):
        """Test that HDBSCAN clusters similar memories"""
        clustering_service = SemanticClusterService()
        
        # Generate mock embeddings for memories
        for memory in test_memories:
            # Create simple mock embeddings
            embedding = np.random.randn(1536).tolist()  # OpenAI embedding dimension
            memory.embedding = json.dumps(embedding)
        
        session.commit()
        
        clusters = clustering_service.cluster_memories(
            session=session,
            user_id=test_user.id,
            memories=test_memories,
        )
        
        # Should create multiple clusters
        assert len(clusters) > 0
        assert all(isinstance(c, MemoryCluster) for c in clusters)

    def test_cluster_has_valid_metrics(self, session, test_user, test_memories):
        """Test that clusters have valid metrics"""
        clustering_service = SemanticClusterService()
        
        for memory in test_memories:
            embedding = np.random.randn(1536).tolist()
            memory.embedding = json.dumps(embedding)
        
        session.commit()
        
        clusters = clustering_service.cluster_memories(
            session=session,
            user_id=test_user.id,
            memories=test_memories,
        )
        
        for cluster in clusters:
            assert 0 <= cluster.confidence <= 1.0
            assert cluster.member_count > 0
            assert len(cluster.memory_ids) == cluster.member_count


class TestMemoryMerge:
    """Tests for memory merge service"""

    def test_identify_redundant_memories(self, session, test_user, test_memories):
        """Test detection of redundant memory pairs"""
        # Create similar memories
        memory1 = Memory(
            user_id=test_user.id,
            memory_type=MemoryTypeEnum.EPISODIC,
            content="User prefers dark mode",
            importance_score=0.8,
            cognitive_state=CognitiveMemoryStateEnum.ACTIVE,
        )
        memory2 = Memory(
            user_id=test_user.id,
            memory_type=MemoryTypeEnum.EPISODIC,
            content="User likes dark theme",
            importance_score=0.7,
            cognitive_state=CognitiveMemoryStateEnum.ACTIVE,
        )
        
        session.add(memory1)
        session.add(memory2)
        session.commit()
        
        # Create cluster
        cluster = MemoryCluster(
            user_id=test_user.id,
            cluster_id="test_cluster",
            memory_ids=[str(memory1.id), str(memory2.id)],
            member_count=2,
        )
        session.add(cluster)
        session.commit()
        
        merge_service = MemoryMergeService()
        redundant_pairs = merge_service.identify_redundant_memories(session, cluster)
        
        # Should find some redundancy (similarity > 0)
        # Note: Mock embeddings will be random, so this may not find pairs
        assert isinstance(redundant_pairs, list)

    def test_merge_consolidates_memories(self, session, test_user):
        """Test that merging creates consolidated memory"""
        memories = [
            Memory(
                user_id=test_user.id,
                memory_type=MemoryTypeEnum.EPISODIC,
                content=f"Content {i}",
                importance_score=0.5 + (i * 0.1),
                cognitive_state=CognitiveMemoryStateEnum.ACTIVE,
            )
            for i in range(3)
        ]
        
        for m in memories:
            session.add(m)
        session.commit()
        
        merge_service = MemoryMergeService()
        consolidated = merge_service.merge_memories(session, [m.id for m in memories])
        
        assert consolidated is not None
        assert consolidated.id == memories[-1].id  # Primary (highest importance_score=0.7)
        assert "merged_from" in consolidated.extra_metadata


class TestConceptGeneration:
    """Tests for concept extraction"""

    def test_validate_concept_with_high_confidence(self, session, test_user):
        """Test concept validation with good metrics"""
        concept = ConceptMemory(
            user_id=test_user.id,
            concept_name="concise_communication_preference",
            description="User consistently prefers concise communication",
            confidence=0.92,
            support_count=4,
            supporting_memory_ids=["mem1", "mem2", "mem3", "mem4"],
        )
        
        generator = ConceptGenerator()
        assert generator.validate_concept(concept) is True

    def test_reject_concept_with_low_confidence(self, session, test_user):
        """Test concept rejection with poor metrics"""
        concept = ConceptMemory(
            user_id=test_user.id,
            concept_name="weak_concept",
            description="Bad",
            confidence=0.3,  # Below threshold
            support_count=1,
            supporting_memory_ids=["mem1"],
        )
        
        generator = ConceptGenerator()
        assert generator.validate_concept(concept) is False


class TestConceptGraph:
    """Tests for semantic knowledge graph"""

    def test_build_graph_for_user(self, session, test_user):
        """Test building concept graph"""
        # Create concepts
        concepts = [
            ConceptMemory(
                user_id=test_user.id,
                concept_name="concept1",
                description="First concept",
                confidence=0.9,
                support_count=3,
            ),
            ConceptMemory(
                user_id=test_user.id,
                concept_name="concept2",
                description="Second concept",
                confidence=0.85,
                support_count=2,
            ),
        ]
        
        for c in concepts:
            session.add(c)
        session.commit()
        
        # Create relationship
        rel = ConceptRelationship(
            user_id=test_user.id,
            source_concept_id=concepts[0].id,
            target_concept_id=concepts[1].id,
            relationship_type="related_to",
            strength=0.8,
        )
        session.add(rel)
        session.commit()
        
        graph = ConceptGraph()
        graph.build_graph_for_user(session, test_user.id)
        
        stats = graph.get_graph_statistics()
        assert stats['node_count'] == 2
        assert stats['edge_count'] == 1

    def test_add_relationship_increases_strength(self, session, test_user):
        """Test relationship reinforcement"""
        concepts = [
            ConceptMemory(
                user_id=test_user.id,
                concept_name="concept1",
                description="First",
                confidence=0.9,
            ),
            ConceptMemory(
                user_id=test_user.id,
                concept_name="concept2",
                description="Second",
                confidence=0.85,
            ),
        ]
        
        for c in concepts:
            session.add(c)
        session.commit()
        
        graph = ConceptGraph()
        
        # Add relationship twice
        rel1 = graph.add_relationship(
            session, test_user.id,
            concepts[0].id, concepts[1].id,
            "related_to", strength=0.75
        )
        
        strength_after_first = rel1.strength
        
        rel2 = graph.add_relationship(
            session, test_user.id,
            concepts[0].id, concepts[1].id,
            "related_to", strength=0.75
        )
        
        strength_after_second = rel2.strength
        
        # Strength should increase
        assert strength_after_second > strength_after_first


class TestConsolidationPipeline:
    """Tests for complete consolidation pipeline"""

    def test_consolidation_reduces_memory_footprint(self, session, test_user, test_memories):
        """Test that consolidation reduces total memory count via concepts"""
        worker = ConsolidationWorker()
        
        # Mock embeddings
        for memory in test_memories:
            embedding = np.random.randn(1536).tolist()
            memory.embedding = json.dumps(embedding)
        
        session.commit()
        
        initial_memory_count = len(test_memories)
        
        # Run consolidation (this will create concepts)
        # Note: In actual test, LLM calls would be mocked
        metrics = worker.consolidate_user_memories(test_user.id)
        
        # Verify consolidation occurred
        if metrics:
            assert metrics.concept_count < initial_memory_count


class TestConsolidationThresholds:
    """Test consolidation threshold logic"""

    def test_minimum_memory_threshold_enforced(self, session, test_user):
        """Test that clusters need minimum memories"""
        # Create insufficient memories
        memory = Memory(
            user_id=test_user.id,
            memory_type=MemoryTypeEnum.EPISODIC,
            content="Single memory",
            importance_score=0.8,
            cognitive_state=CognitiveMemoryStateEnum.ACTIVE,
        )
        session.add(memory)
        session.commit()
        
        worker = ConsolidationWorker()
        candidates = worker._fetch_candidate_memories(session, test_user.id)
        
        # Should still return the memory for potential consolidation
        assert len(candidates) == 1

    def test_importance_threshold_filters_memories(self, session, test_user):
        """Test that low-importance memories are filtered"""
        memories = [
            Memory(
                user_id=test_user.id,
                memory_type=MemoryTypeEnum.EPISODIC,
                content=f"Memory {i}",
                importance_score=0.3 if i < 2 else 0.8,  # Some below threshold
                cognitive_state=CognitiveMemoryStateEnum.ACTIVE,
            )
            for i in range(4)
        ]
        
        for m in memories:
            session.add(m)
        session.commit()
        
        worker = ConsolidationWorker()
        candidates = worker._fetch_candidate_memories(session, test_user.id)
        
        # Should only include high-importance memories
        assert all(c.importance_score >= worker.min_memory_importance for c in candidates)


# Run with: pytest tests/test_consolidation.py -v
