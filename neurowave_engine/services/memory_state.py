"""Memory state machine for cognitive lifecycle management"""
import logging
from typing import Optional, Dict, Tuple
from datetime import datetime, timedelta
from neurowave_engine.db.models import Memory, CognitiveMemoryStateEnum

logger = logging.getLogger(__name__)


class MemoryStateMachine:
    """Manages cognitive state transitions for memories"""
    
    # Valid state transitions
    VALID_TRANSITIONS = {
        CognitiveMemoryStateEnum.ACTIVE: [
            CognitiveMemoryStateEnum.REINFORCED,
            CognitiveMemoryStateEnum.DORMANT,
            CognitiveMemoryStateEnum.DECAYING,
        ],
        CognitiveMemoryStateEnum.REINFORCED: [
            CognitiveMemoryStateEnum.ACTIVE,
            CognitiveMemoryStateEnum.SEMANTIC_CANDIDATE,
            CognitiveMemoryStateEnum.DORMANT,
            CognitiveMemoryStateEnum.DECAYING,
        ],
        CognitiveMemoryStateEnum.SEMANTIC_CANDIDATE: [
            CognitiveMemoryStateEnum.ARCHIVED,
            CognitiveMemoryStateEnum.ACTIVE,
            CognitiveMemoryStateEnum.DECAYING,
        ],
        CognitiveMemoryStateEnum.DORMANT: [
            CognitiveMemoryStateEnum.ACTIVE,
            CognitiveMemoryStateEnum.DECAYING,
            CognitiveMemoryStateEnum.ARCHIVED,
        ],
        CognitiveMemoryStateEnum.DECAYING: [
            CognitiveMemoryStateEnum.ARCHIVED,
            CognitiveMemoryStateEnum.ACTIVE,  # Can be revived by access
        ],
        CognitiveMemoryStateEnum.ARCHIVED: [
            CognitiveMemoryStateEnum.ACTIVE,     # Can be retrieved (revival)
            CognitiveMemoryStateEnum.FORGOTTEN,  # Day 7: soft-forgotten after prolonged archival
        ],
        # Day 7: FORGOTTEN is a terminal soft-delete state - never hard
        # deleted, but revival is still possible (mirrors ARCHIVED -> ACTIVE)
        # for memories that become relevant again (see ReinforcementRecovery).
        CognitiveMemoryStateEnum.FORGOTTEN: [
            CognitiveMemoryStateEnum.ACTIVE,
        ],
    }

    # Time thresholds for state transitions (in days)
    TIME_THRESHOLDS = {
        "active_to_dormant": 30,        # No access for 30 days
        "dormant_to_decay": 60,         # No access for 60 days
        "decay_to_archive": 90,         # No access for 90 days
        "archive_to_forgotten": 180,    # No access for 180 days (Day 7)
    }
    
    def __init__(self, memory: Memory):
        """Initialize state machine with memory"""
        self.memory = memory
        self.current_state = memory.cognitive_state
    
    def update_state_on_access(self) -> Tuple[bool, str]:
        """
        Update memory state when it's accessed/retrieved
        
        Returns:
            Tuple of (state_changed, reason)
        """
        old_state = self.memory.cognitive_state
        
        # Accessing revives dormant/decaying memories
        if self.memory.cognitive_state in [
            CognitiveMemoryStateEnum.DORMANT,
            CognitiveMemoryStateEnum.DECAYING,
            CognitiveMemoryStateEnum.ARCHIVED
        ]:
            # Move back to active
            if self.memory.memory_strength >= 0.70:
                new_state = CognitiveMemoryStateEnum.ACTIVE
            elif self.memory.memory_strength >= 0.50:
                new_state = CognitiveMemoryStateEnum.REINFORCED
            else:
                new_state = CognitiveMemoryStateEnum.DORMANT
            
            self.memory.cognitive_state = new_state
            self.memory.memory_strength = min(1.0, self.memory.memory_strength + 0.1)
            self.memory.last_accessed = datetime.utcnow()
            
            return True, f"Revived from {old_state} to {new_state}"
        
        # Active memories with access remain active
        self.memory.last_accessed = datetime.utcnow()
        return False, "Already active"
    
    def update_state_on_reinforcement(self, reinforcement_count: int) -> Tuple[bool, str]:
        """
        Update state based on reinforcement count
        
        Returns:
            Tuple of (state_changed, reason)
        """
        old_state = self.memory.cognitive_state
        new_state = old_state
        
        # Map reinforcement count to state
        if reinforcement_count >= 5 and self.memory.memory_strength >= 0.70:
            new_state = CognitiveMemoryStateEnum.SEMANTIC_CANDIDATE
        elif reinforcement_count >= 3 and self.memory.memory_strength >= 0.75:
            new_state = CognitiveMemoryStateEnum.ACTIVE
        elif reinforcement_count >= 2 and self.memory.memory_strength >= 0.65:
            new_state = CognitiveMemoryStateEnum.REINFORCED
        
        state_changed = new_state != old_state
        if state_changed:
            self.memory.cognitive_state = new_state
            self.memory.last_reinforced_at = datetime.utcnow()
        
        return state_changed, f"{'Promoted' if state_changed else 'Maintained'} {old_state} → {new_state}"
    
    def update_state_by_time_decay(self) -> Tuple[bool, str]:
        """
        Update state based on time elapsed since last access
        
        Returns:
            Tuple of (state_changed, reason)
        """
        if not self.memory.last_accessed:
            last_access = self.memory.created_at
        else:
            last_access = self.memory.last_accessed
        
        days_since_access = (datetime.utcnow() - last_access).days
        old_state = self.memory.cognitive_state
        new_state = old_state
        
        # Time-based transitions
        if old_state == CognitiveMemoryStateEnum.ACTIVE:
            if days_since_access > self.TIME_THRESHOLDS["active_to_dormant"]:
                new_state = CognitiveMemoryStateEnum.DORMANT
                self.memory.memory_strength *= 0.9
        
        elif old_state == CognitiveMemoryStateEnum.REINFORCED:
            if days_since_access > self.TIME_THRESHOLDS["active_to_dormant"]:
                new_state = CognitiveMemoryStateEnum.DORMANT
                self.memory.memory_strength *= 0.85
        
        elif old_state == CognitiveMemoryStateEnum.DORMANT:
            if days_since_access > self.TIME_THRESHOLDS["dormant_to_decay"]:
                new_state = CognitiveMemoryStateEnum.DECAYING
                self.memory.memory_strength *= 0.8
        
        elif old_state == CognitiveMemoryStateEnum.DECAYING:
            if days_since_access > self.TIME_THRESHOLDS["decay_to_archive"]:
                new_state = CognitiveMemoryStateEnum.ARCHIVED
                self.memory.memory_strength *= 0.7
        
        # Apply exponential decay
        if new_state == old_state:
            self.memory.memory_strength = max(
                0.0,
                self.memory.memory_strength * (1.0 - self.memory.decay_rate)
            )
        
        state_changed = new_state != old_state
        if state_changed:
            self.memory.cognitive_state = new_state
        
        reason = f"{old_state} ({days_since_access} days idle)"
        if state_changed:
            reason = f"Transitioned {old_state} → {new_state} ({days_since_access} days idle)"
        
        return state_changed, reason
    
    def apply_strength_decay(self, decay_steps: int = 1) -> float:
        """
        Apply exponential decay to memory strength
        
        Args:
            decay_steps: Number of decay periods to apply
            
        Returns:
            New memory strength
        """
        for _ in range(decay_steps):
            self.memory.memory_strength = max(
                0.0,
                self.memory.memory_strength * (1.0 - self.memory.decay_rate)
            )
        
        return self.memory.memory_strength
    
    def can_transition(self, target_state: CognitiveMemoryStateEnum) -> bool:
        """Check if transition is valid"""
        current = self.memory.cognitive_state
        valid_targets = self.VALID_TRANSITIONS.get(current, [])
        return target_state in valid_targets
    
    def force_transition(
        self,
        target_state: CognitiveMemoryStateEnum,
        reason: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Force transition to target state (with validation)
        
        Returns:
            Tuple of (success, message)
        """
        if not self.can_transition(target_state):
            return False, f"Invalid transition: {self.memory.cognitive_state} → {target_state}"
        
        old_state = self.memory.cognitive_state
        self.memory.cognitive_state = target_state
        
        # Update strength based on transition
        strength_adjustment = self._get_strength_adjustment(old_state, target_state)
        self.memory.memory_strength = min(
            1.0,
            max(0.0, self.memory.memory_strength + strength_adjustment)
        )
        
        msg = f"Transitioned {old_state} → {target_state}"
        if reason:
            msg += f": {reason}"
        
        logger.info(msg)
        return True, msg
    
    @staticmethod
    def _get_strength_adjustment(
        old_state: CognitiveMemoryStateEnum,
        new_state: CognitiveMemoryStateEnum
    ) -> float:
        """Get strength adjustment for state transition"""
        # Promotion increases strength
        if new_state == CognitiveMemoryStateEnum.ACTIVE:
            return 0.2
        elif new_state == CognitiveMemoryStateEnum.REINFORCED:
            return 0.1
        elif new_state == CognitiveMemoryStateEnum.SEMANTIC_CANDIDATE:
            return 0.05
        # Demotion decreases strength
        elif new_state == CognitiveMemoryStateEnum.DORMANT:
            return -0.1
        elif new_state == CognitiveMemoryStateEnum.DECAYING:
            return -0.2
        elif new_state == CognitiveMemoryStateEnum.ARCHIVED:
            return -0.05
        elif new_state == CognitiveMemoryStateEnum.FORGOTTEN:
            return -0.15
        else:
            return 0.0
    
    def get_state_info(self) -> Dict:
        """Get detailed state information"""
        return {
            "current_state": self.memory.cognitive_state,
            "memory_strength": self.memory.memory_strength,
            "decay_rate": self.memory.decay_rate,
            "reinforcement_count": self.memory.reinforcement_count,
            "retrieval_count": self.memory.retrieval_count,
            "last_accessed": self.memory.last_accessed,
            "last_reinforced_at": self.memory.last_reinforced_at,
            "days_since_access": (
                (datetime.utcnow() - (self.memory.last_accessed or self.memory.created_at)).days
            )
        }


def transition_memory(
    memory: Memory,
    target_state: CognitiveMemoryStateEnum,
    reason: Optional[str] = None
) -> Tuple[bool, str]:
    """Convenience function to transition a memory"""
    state_machine = MemoryStateMachine(memory)
    return state_machine.force_transition(target_state, reason)
