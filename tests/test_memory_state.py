"""Tests for memory state machine"""
import pytest
from unittest.mock import MagicMock
from datetime import datetime, timedelta
from app.services.memory_state import MemoryStateMachine
from app.db.models import CognitiveMemoryStateEnum


class TestMemoryStateMachine:
    """Test memory state transitions"""
    
    def test_access_revives_dormant_memory(self):
        """Test that accessing dormant memory revives it"""
        mock_memory = MagicMock()
        mock_memory.cognitive_state = CognitiveMemoryStateEnum.DORMANT
        mock_memory.memory_strength = 0.6
        
        state_machine = MemoryStateMachine(mock_memory)
        changed, reason = state_machine.update_state_on_access()
        
        # Should transition to REINFORCED
        assert changed == True
        assert mock_memory.cognitive_state == CognitiveMemoryStateEnum.REINFORCED
    
    def test_access_updates_last_accessed(self):
        """Test that access updates timestamp"""
        mock_memory = MagicMock()
        mock_memory.cognitive_state = CognitiveMemoryStateEnum.ACTIVE
        mock_memory.last_accessed = datetime(2020, 1, 1)
        
        state_machine = MemoryStateMachine(mock_memory)
        state_machine.update_state_on_access()
        
        # Should update timestamp to recently (not exactly utcnow due to mocking)
        assert mock_memory.last_accessed != datetime(2020, 1, 1)
    
    def test_time_decay_active_to_dormant(self):
        """Test transition from ACTIVE to DORMANT after 30 days"""
        mock_memory = MagicMock()
        mock_memory.cognitive_state = CognitiveMemoryStateEnum.ACTIVE
        mock_memory.memory_strength = 0.8
        mock_memory.decay_rate = 0.05
        mock_memory.last_accessed = datetime.utcnow() - timedelta(days=31)
        mock_memory.created_at = datetime.utcnow() - timedelta(days=40)
        
        state_machine = MemoryStateMachine(mock_memory)
        changed, reason = state_machine.update_state_by_time_decay()
        
        # Should transition to DORMANT
        assert changed == True
        assert mock_memory.cognitive_state == CognitiveMemoryStateEnum.DORMANT
    
    def test_time_decay_dormant_to_decaying(self):
        """Test transition from DORMANT to DECAYING after 60 days"""
        mock_memory = MagicMock()
        mock_memory.cognitive_state = CognitiveMemoryStateEnum.DORMANT
        mock_memory.memory_strength = 0.5
        mock_memory.decay_rate = 0.05
        mock_memory.last_accessed = datetime.utcnow() - timedelta(days=61)
        
        state_machine = MemoryStateMachine(mock_memory)
        changed, reason = state_machine.update_state_by_time_decay()
        
        # Should transition to DECAYING
        assert changed == True
        assert mock_memory.cognitive_state == CognitiveMemoryStateEnum.DECAYING
    
    def test_no_transition_when_recent(self):
        """Test that recent memories don't decay"""
        mock_memory = MagicMock()
        mock_memory.cognitive_state = CognitiveMemoryStateEnum.ACTIVE
        mock_memory.memory_strength = 0.8
        mock_memory.decay_rate = 0.05
        mock_memory.last_accessed = datetime.utcnow() - timedelta(days=5)
        
        state_machine = MemoryStateMachine(mock_memory)
        changed, reason = state_machine.update_state_by_time_decay()
        
        # Should not transition
        assert changed == False
        assert mock_memory.cognitive_state == CognitiveMemoryStateEnum.ACTIVE
    
    def test_reinforcement_promotes_to_active(self):
        """Test that sufficient reinforcement promotes to ACTIVE"""
        mock_memory = MagicMock()
        mock_memory.cognitive_state = CognitiveMemoryStateEnum.DORMANT
        mock_memory.memory_strength = 0.80
        
        state_machine = MemoryStateMachine(mock_memory)
        changed, reason = state_machine.update_state_on_reinforcement(reinforcement_count=3)
        
        # Should transition to ACTIVE
        assert changed == True
        assert mock_memory.cognitive_state == CognitiveMemoryStateEnum.ACTIVE
    
    def test_reinforcement_promotes_to_semantic_candidate(self):
        """Test promotion to SEMANTIC_CANDIDATE with high reinforcement"""
        mock_memory = MagicMock()
        mock_memory.cognitive_state = CognitiveMemoryStateEnum.REINFORCED
        mock_memory.memory_strength = 0.75
        
        state_machine = MemoryStateMachine(mock_memory)
        changed, reason = state_machine.update_state_on_reinforcement(reinforcement_count=5)
        
        # Should transition to SEMANTIC_CANDIDATE
        assert changed == True
        assert mock_memory.cognitive_state == CognitiveMemoryStateEnum.SEMANTIC_CANDIDATE
    
    def test_valid_transitions(self):
        """Test that valid transitions are allowed"""
        mock_memory = MagicMock()
        mock_memory.cognitive_state = CognitiveMemoryStateEnum.ACTIVE
        
        state_machine = MemoryStateMachine(mock_memory)
        
        # These should be valid
        assert state_machine.can_transition(CognitiveMemoryStateEnum.DORMANT)
        assert state_machine.can_transition(CognitiveMemoryStateEnum.REINFORCED)
        
        # This should be invalid
        assert not state_machine.can_transition(CognitiveMemoryStateEnum.ARCHIVED)
    
    def test_invalid_transitions_blocked(self):
        """Test that invalid transitions are blocked"""
        mock_memory = MagicMock()
        mock_memory.cognitive_state = CognitiveMemoryStateEnum.ACTIVE
        
        state_machine = MemoryStateMachine(mock_memory)
        success, msg = state_machine.force_transition(CognitiveMemoryStateEnum.ARCHIVED)
        
        # Should fail
        assert success == False
        assert "Invalid transition" in msg
    
    def test_exponential_decay_application(self):
        """Test exponential decay reduces memory strength"""
        mock_memory = MagicMock()
        mock_memory.memory_strength = 1.0
        mock_memory.decay_rate = 0.1
        
        state_machine = MemoryStateMachine(mock_memory)
        
        # Apply one decay step
        new_strength = state_machine.apply_strength_decay(decay_steps=1)
        
        # Should be reduced
        assert new_strength == 0.9
    
    def test_multiple_decay_steps(self):
        """Test multiple decay steps"""
        mock_memory = MagicMock()
        mock_memory.memory_strength = 1.0
        mock_memory.decay_rate = 0.1
        
        state_machine = MemoryStateMachine(mock_memory)
        
        # Apply multiple decay steps
        new_strength = state_machine.apply_strength_decay(decay_steps=3)
        
        # Should compound: 1.0 * 0.9 * 0.9 * 0.9 = 0.729
        assert abs(new_strength - 0.729) < 0.001
    
    def test_decay_floor_at_zero(self):
        """Test that strength doesn't go below 0"""
        mock_memory = MagicMock()
        mock_memory.memory_strength = 0.05
        mock_memory.decay_rate = 0.5  # High decay
        
        state_machine = MemoryStateMachine(mock_memory)
        
        # Apply many decay steps
        new_strength = state_machine.apply_strength_decay(decay_steps=20)
        
        # Should be clamped at 0.0
        assert new_strength >= 0.0


class TestStateTransitionWeights:
    """Test state transition strength adjustments"""
    
    def test_promotion_increases_strength(self):
        """Test that promotions increase memory strength"""
        mock_memory = MagicMock()
        mock_memory.cognitive_state = CognitiveMemoryStateEnum.DORMANT
        mock_memory.memory_strength = 0.5
        
        state_machine = MemoryStateMachine(mock_memory)
        success, msg = state_machine.force_transition(
            CognitiveMemoryStateEnum.ACTIVE,
            reason="Revived by access"
        )
        
        # Should increase strength
        assert success == True
        assert mock_memory.memory_strength == 0.7  # 0.5 + 0.2
    
    def test_demotion_decreases_strength(self):
        """Test that demotions decrease memory strength"""
        mock_memory = MagicMock()
        mock_memory.cognitive_state = CognitiveMemoryStateEnum.ACTIVE
        mock_memory.memory_strength = 0.8
        
        state_machine = MemoryStateMachine(mock_memory)
        success, msg = state_machine.force_transition(
            CognitiveMemoryStateEnum.DORMANT,
            reason="Aged without access"
        )
        
        # Should decrease strength
        assert success == True
        assert mock_memory.memory_strength == 0.7  # 0.8 - 0.1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
