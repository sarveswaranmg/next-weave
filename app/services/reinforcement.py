"""Memory reinforcement engine - strengthens memories on repetition"""
import logging
from typing import Dict, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.db.models import Memory, CognitiveMemoryStateEnum

logger = logging.getLogger(__name__)


class MemoryReinforcementEngine:
    """Handles memory reinforcement when concepts repeat"""
    
    # Concept similarity keywords for detection
    CONCEPT_GROUPS = {
        "ai_ml": ["artificial intelligence", "machine learning", "ai", "ml", "neural", "deep learning", "gpt"],
        "systems": ["system design", "systems", "architecture", "scalability", "distributed"],
        "infrastructure": ["kubernetes", "docker", "cloud", "infrastructure", "deployment", "devops"],
        "startup": ["startup", "founder", "venture", "capital", "funding", "vc", "entrepreneur"],
        "optimization": ["optimize", "performance", "speed", "latency", "throughput", "efficient"],
        "learning": ["learn", "study", "education", "course", "skill", "improve"],
        "career": ["career", "job", "role", "position", "promotion", "advancement"],
    }
    
    def __init__(self, session: Session):
        """Initialize reinforcement engine with DB session"""
        self.session = session
    
    def reinforce_memory(
        self,
        memory_id: str,
        reinforcement_context: Optional[str] = None,
        strength_increase: float = 0.1
    ) -> Dict:
        """
        Reinforce a memory and update its properties
        
        Args:
            memory_id: UUID of memory to reinforce
            reinforcement_context: Optional context for reinforcement
            strength_increase: How much to increase memory strength (0.0-1.0)
            
        Returns:
            Dict with reinforcement results
        """
        memory = self.session.query(Memory).filter(Memory.id == memory_id).first()
        
        if not memory:
            logger.warning(f"Memory {memory_id} not found for reinforcement")
            return {"error": "Memory not found", "success": False}
        
        # Store previous state
        previous_strength = memory.memory_strength
        previous_state = memory.cognitive_state
        previous_count = memory.reinforcement_count
        
        # Increase reinforcement count
        memory.reinforcement_count += 1
        memory.retrieval_count += 1
        
        # Increase memory strength
        new_strength = min(1.0, memory.memory_strength + strength_increase)
        memory.memory_strength = new_strength
        
        # Update last reinforced timestamp
        memory.last_reinforced_at = datetime.utcnow()
        
        # Update cognitive state based on reinforcement count and strength
        new_state = self._determine_new_state(
            memory,
            memory.reinforcement_count,
            new_strength
        )
        memory.cognitive_state = new_state
        
        # Reduce decay rate - reinforced memories decay slower
        memory.decay_rate = max(0.0, memory.decay_rate * 0.8)
        
        # Log reinforcement
        logger.info(
            f"Memory reinforced: {memory_id}, "
            f"strength {previous_strength:.2f} → {new_strength:.2f}, "
            f"state {previous_state} → {new_state}, "
            f"count {previous_count} → {memory.reinforcement_count}"
        )
        
        self.session.commit()
        
        return {
            "memory_id": str(memory_id),
            "success": True,
            "previous_strength": previous_strength,
            "new_strength": new_strength,
            "previous_state": previous_state,
            "new_state": new_state,
            "reinforcement_count": memory.reinforcement_count,
            "decay_rate": memory.decay_rate,
            "last_reinforced_at": memory.last_reinforced_at
        }
    
    def detect_and_reinforce_concepts(
        self,
        user_id: str,
        new_content: str
    ) -> Dict:
        """
        Detect concept matches and reinforce related memories
        
        Args:
            user_id: User ID to reinforce memories for
            new_content: New content containing concepts
            
        Returns:
            Dict with reinforcement results
        """
        content_lower = new_content.lower()
        reinforced_memories = []
        
        # Get user's memories
        memories = self.session.query(Memory).filter(
            Memory.user_id == user_id
        ).all()
        
        # Check each memory for concept matches
        for memory in memories:
            matched_concepts = self._detect_concept_match(content_lower, memory.content)
            
            if matched_concepts:
                # Reinforce this memory
                result = self.reinforce_memory(
                    str(memory.id),
                    reinforcement_context=f"Concept match: {matched_concepts}",
                    strength_increase=0.05 * len(matched_concepts)
                )
                reinforced_memories.append(result)
        
        logger.info(f"Reinforced {len(reinforced_memories)} memories for user {user_id}")
        
        return {
            "reinforced_count": len(reinforced_memories),
            "reinforced_memories": reinforced_memories,
            "concepts_detected": self._get_concepts_in_content(content_lower)
        }
    
    @staticmethod
    def _detect_concept_match(new_content: str, existing_content: str) -> list:
        """Detect which concepts appear in both contents"""
        matched = []
        existing_lower = existing_content.lower()
        
        for concept_group, keywords in MemoryReinforcementEngine.CONCEPT_GROUPS.items():
            for keyword in keywords:
                if keyword in new_content and keyword in existing_lower:
                    matched.append(concept_group)
                    break
        
        return list(set(matched))  # Remove duplicates
    
    @staticmethod
    def _get_concepts_in_content(content: str) -> list:
        """Extract which concept groups are mentioned in content"""
        concepts = []
        for concept_group, keywords in MemoryReinforcementEngine.CONCEPT_GROUPS.items():
            for keyword in keywords:
                if keyword in content:
                    concepts.append(concept_group)
                    break
        
        return list(set(concepts))  # Remove duplicates
    
    @staticmethod
    def _determine_new_state(
        memory: Memory,
        reinforcement_count: int,
        strength: float
    ) -> CognitiveMemoryStateEnum:
        """Determine new cognitive state based on reinforcement"""
        
        # Strong, well-reinforced memories
        if strength >= 0.85 and reinforcement_count >= 3:
            return CognitiveMemoryStateEnum.ACTIVE
        
        # Moderately reinforced memories
        elif strength >= 0.70 and reinforcement_count >= 2:
            return CognitiveMemoryStateEnum.REINFORCED
        
        # Candidates for semantic consolidation
        elif reinforcement_count >= 5 and strength >= 0.60:
            return CognitiveMemoryStateEnum.SEMANTIC_CANDIDATE
        
        # Weak memories
        elif strength < 0.30:
            return CognitiveMemoryStateEnum.DECAYING
        
        # Default to semantic candidate if many reinforcements
        elif reinforcement_count >= 4:
            return CognitiveMemoryStateEnum.SEMANTIC_CANDIDATE
        
        # Otherwise maintain current state or move to reinforced
        else:
            return CognitiveMemoryStateEnum.REINFORCED
    
    def schedule_memory_decay(self, user_id: str, days_threshold: int = 30) -> Dict:
        """
        Schedule memories for decay based on age and non-access
        
        Args:
            user_id: User ID to process
            days_threshold: Days without access before decay consideration
            
        Returns:
            Dict with decay scheduling results
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days_threshold)
        
        # Find dormant memories that haven't been accessed
        dormant_memories = self.session.query(Memory).filter(
            Memory.user_id == user_id,
            Memory.cognitive_state == CognitiveMemoryStateEnum.DORMANT,
            (Memory.last_accessed < cutoff_date) | (Memory.last_accessed.is_(None))
        ).all()
        
        decayed_count = 0
        for memory in dormant_memories:
            # Move to decaying state
            memory.cognitive_state = CognitiveMemoryStateEnum.DECAYING
            memory.memory_strength *= 0.8  # Reduce strength
            memory.decay_rate *= 1.2       # Increase decay
            decayed_count += 1
        
        self.session.commit()
        
        logger.info(f"Scheduled {decayed_count} memories for decay")
        
        return {
            "decayed_count": decayed_count,
            "threshold_days": days_threshold,
            "cutoff_date": cutoff_date
        }
    
    def consolidate_semantic_candidates(self, user_id: str) -> Dict:
        """
        Process memories ready for semantic consolidation
        
        Args:
            user_id: User ID to consolidate
            
        Returns:
            Dict with consolidation results
        """
        # Find semantic candidates
        candidates = self.session.query(Memory).filter(
            Memory.user_id == user_id,
            Memory.cognitive_state == CognitiveMemoryStateEnum.SEMANTIC_CANDIDATE
        ).all()
        
        consolidated_count = 0
        for memory in candidates:
            # Move to archived state for consolidation
            memory.cognitive_state = CognitiveMemoryStateEnum.ARCHIVED
            memory.memory_strength = min(1.0, memory.memory_strength * 1.2)  # Preserve strength
            consolidated_count += 1
        
        self.session.commit()
        
        logger.info(f"Consolidated {consolidated_count} semantic candidates")
        
        return {
            "consolidated_count": consolidated_count,
            "candidates_processed": len(candidates)
        }


def reinforce_memory(
    session: Session,
    memory_id: str,
    reinforcement_context: Optional[str] = None
) -> Dict:
    """Convenience function to reinforce a memory"""
    engine = MemoryReinforcementEngine(session)
    return engine.reinforce_memory(memory_id, reinforcement_context)


def detect_and_reinforce(
    session: Session,
    user_id: str,
    content: str
) -> Dict:
    """Convenience function to detect and reinforce concepts"""
    engine = MemoryReinforcementEngine(session)
    return engine.detect_and_reinforce_concepts(user_id, content)
