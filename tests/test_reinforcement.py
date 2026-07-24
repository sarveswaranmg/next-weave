"""Tests for memory reinforcement engine"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
from app.services.reinforcement import MemoryReinforcementEngine


class TestMemoryReinforcementEngine:
    """Test memory reinforcement system"""
    
    def test_reinforce_memory_increases_strength(self):
        """Test that reinforcing a memory increases its strength"""
        mock_session = MagicMock()
        mock_memory = MagicMock()
        mock_memory.id = "test-id"
        mock_memory.memory_strength = 0.5
        mock_memory.reinforcement_count = 0
        mock_memory.retrieval_count = 0
        mock_memory.decay_rate = 0.05
        
        mock_session.query.return_value.filter.return_value.first.return_value = mock_memory
        
        engine = MemoryReinforcementEngine(mock_session)
        result = engine.reinforce_memory("test-id", strength_increase=0.1)
        
        # Should be successful
        assert result["success"] == True
        assert result["new_strength"] == pytest.approx(0.6)  # 0.5 + 0.1
    
    def test_reinforce_capped_at_1_0(self):
        """Test that memory strength is capped at 1.0"""
        mock_session = MagicMock()
        mock_memory = MagicMock()
        mock_memory.id = "test-id"
        mock_memory.memory_strength = 0.95
        mock_memory.reinforcement_count = 0
        mock_memory.retrieval_count = 0
        mock_memory.decay_rate = 0.05
        
        mock_session.query.return_value.filter.return_value.first.return_value = mock_memory
        
        engine = MemoryReinforcementEngine(mock_session)
        result = engine.reinforce_memory("test-id", strength_increase=0.1)
        
        # Should not exceed 1.0
        assert result["new_strength"] == pytest.approx(1.0)
    
    def test_reinforcement_increases_count(self):
        """Test that reinforcement increments the count"""
        mock_session = MagicMock()
        mock_memory = MagicMock()
        mock_memory.id = "test-id"
        mock_memory.memory_strength = 0.5
        mock_memory.reinforcement_count = 3
        mock_memory.retrieval_count = 5
        mock_memory.decay_rate = 0.05
        
        mock_session.query.return_value.filter.return_value.first.return_value = mock_memory
        
        engine = MemoryReinforcementEngine(mock_session)
        result = engine.reinforce_memory("test-id")
        
        assert result["reinforcement_count"] == 4  # 3 + 1
    
    def test_reinforcement_updates_timestamp(self):
        """Test that reinforcement updates last_reinforced_at"""
        mock_session = MagicMock()
        mock_memory = MagicMock()
        mock_memory.id = "test-id"
        mock_memory.memory_strength = 0.5
        mock_memory.reinforcement_count = 0
        mock_memory.retrieval_count = 0
        mock_memory.decay_rate = 0.05
        
        mock_session.query.return_value.filter.return_value.first.return_value = mock_memory
        
        engine = MemoryReinforcementEngine(mock_session)
        result = engine.reinforce_memory("test-id")
        
        # Timestamp should be set
        assert result["last_reinforced_at"] is not None
    
    def test_reinforcement_reduces_decay_rate(self):
        """Test that reinforcement slows decay"""
        mock_session = MagicMock()
        mock_memory = MagicMock()
        mock_memory.id = "test-id"
        mock_memory.memory_strength = 0.5
        mock_memory.reinforcement_count = 0
        mock_memory.retrieval_count = 0
        mock_memory.decay_rate = 0.10
        
        mock_session.query.return_value.filter.return_value.first.return_value = mock_memory
        
        engine = MemoryReinforcementEngine(mock_session)
        result = engine.reinforce_memory("test-id")
        
        # Decay should be reduced (0.10 * 0.8 = 0.08)
        assert result["decay_rate"] == pytest.approx(0.08)
    
    def test_concept_detection(self):
        """Test that concepts are correctly detected"""
        engine = MemoryReinforcementEngine(MagicMock())
        
        content1 = "I work with AI and machine learning"
        content2 = "Neural networks are fascinating"
        
        matched = engine._detect_concept_match(content1, content2)
        
        # Should detect AI/ML concept match
        assert "ai_ml" in matched
    
    def test_multiple_concept_detection(self):
        """Test detection of multiple concepts"""
        engine = MemoryReinforcementEngine(MagicMock())
        
        content1 = "I build AI systems using Kubernetes and Docker"
        content2 = "Infrastructure and ML optimization are key"
        
        matched = engine._detect_concept_match(content1, content2)
        
        # Should detect multiple concepts
        assert len(matched) >= 2
        assert "ai_ml" in matched or "infrastructure" in matched
    
    def test_memory_not_found(self):
        """Test handling of non-existent memory"""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        
        engine = MemoryReinforcementEngine(mock_session)
        result = engine.reinforce_memory("nonexistent-id")
        
        assert result["success"] == False
        assert "error" in result


class TestMemoryStateTransitions:
    """Test memory state transitions during reinforcement"""
    
    def test_state_promotion_on_reinforcement(self):
        """Test that memories are promoted when reinforced enough"""
        mock_session = MagicMock()
        mock_memory = MagicMock()
        mock_memory.id = "test-id"
        mock_memory.memory_strength = 0.80
        mock_memory.reinforcement_count = 2
        mock_memory.retrieval_count = 0
        mock_memory.decay_rate = 0.05
        from app.db.models import CognitiveMemoryStateEnum
        mock_memory.cognitive_state = CognitiveMemoryStateEnum.DORMANT
        
        mock_session.query.return_value.filter.return_value.first.return_value = mock_memory
        
        engine = MemoryReinforcementEngine(mock_session)
        result = engine.reinforce_memory("test-id", strength_increase=0.05)
        
        # Should transition to REINFORCED state
        assert result["new_state"] != result["previous_state"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
