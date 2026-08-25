"""Hybrid cognitive scoring engine - LLM + heuristics"""
import logging
from typing import Dict, Optional, Tuple
from neurowave_engine.services.cognitive_analyzer import CognitiveAnalyzer
from neurowave_engine.db.models import MemoryTypeEnum, CognitiveMemoryStateEnum

logger = logging.getLogger(__name__)

# Keywords that indicate high future utility
HIGH_UTILITY_KEYWORDS = {
    "goal", "plan", "objective", "target", "strategy",
    "building", "creating", "developing", "learning",
    "skill", "expertise", "knowledge", "career",
    "project", "initiative", "startup", "company",
    "investment", "growth", "scale", "optimize"
}

# Keywords indicating identity
IDENTITY_KEYWORDS = {
    "i am", "i'm", "my personality", "i believe",
    "my values", "my passion", "my dream",
    "prefer", "love", "hate", "always",
    "never", "characteristic", "trait"
}

# Emotional intensity keywords
EMOTIONAL_KEYWORDS = {
    "excited", "frustrated", "angry", "sad",
    "happy", "devastated", "thrilled", "worried",
    "anxious", "proud", "ashamed", "motivated",
    "love", "hate", "fear", "hope",
    "accomplish", "achievement", "success", "failure"
}

# Keywords indicating long-term persistence
PERSISTENCE_KEYWORDS = {
    "always", "never", "forever", "permanent",
    "fundamental", "core", "essential", "critical",
    "permanent", "long-term", "forever", "always",
    "architecture", "foundation", "base"
}

# Low importance keywords
LOW_IMPORTANCE_KEYWORDS = {
    "maybe", "could", "might", "probably",
    "hello", "thanks", "bye", "ok", "sure",
    "weather", "today", "now", "currently"
}


class HybridScoringEngine:
    """Hybrid scoring combining LLM analysis with heuristic fallback"""
    
    def __init__(self, use_llm: bool = True, llm_model: str = "gpt-4"):
        """Initialize hybrid scoring engine"""
        self.use_llm = use_llm
        self.llm_model = llm_model
        self.cognitive_analyzer = CognitiveAnalyzer(model=llm_model) if use_llm else None
    
    def score_memory(
        self,
        memory_content: str,
        memory_type: MemoryTypeEnum,
        use_llm: bool = True
    ) -> Dict:
        """
        Score a memory using hybrid approach
        
        Args:
            memory_content: The memory text
            memory_type: Type of memory
            use_llm: Whether to use LLM analysis
            
        Returns:
            Dict with all cognitive scores and state
        """
        # Try LLM analysis first if enabled
        if use_llm and self.use_llm and self.cognitive_analyzer:
            try:
                llm_scores = self.cognitive_analyzer.analyze_memory(
                    memory_content,
                    str(memory_type),
                    None
                )
                # Blend LLM scores with heuristics
                return self._blend_scores(memory_content, memory_type, llm_scores, use_llm=True)
            except Exception as e:
                logger.warning(f"LLM scoring failed, falling back to heuristics: {e}")
        
        # Fallback to heuristic scoring
        heuristic_scores = self._heuristic_score(memory_content, memory_type)
        return self._blend_scores(memory_content, memory_type, heuristic_scores, use_llm=False)
    
    def _heuristic_score(
        self,
        memory_content: str,
        memory_type: MemoryTypeEnum
    ) -> Dict:
        """Score memory using pure heuristics (no LLM)"""
        content_lower = memory_content.lower()
        
        # Base scores by memory type
        type_base_scores = {
            MemoryTypeEnum.PROCEDURAL: {"base": 0.85, "persistence": 0.90},
            MemoryTypeEnum.IDENTITY: {"base": 0.80, "identity_impact": 0.85},
            MemoryTypeEnum.SEMANTIC: {"base": 0.70, "persistence": 0.75},
            MemoryTypeEnum.EPISODIC: {"base": 0.50, "salience": 0.65}
        }
        
        base = type_base_scores.get(memory_type, {})
        
        # Calculate dimension scores
        future_utility = self._score_future_utility(content_lower, base.get("base", 0.50))
        identity_impact = self._score_identity_impact(content_lower, base.get("base", 0.50))
        emotional_salience = self._score_emotional_salience(content_lower, base.get("base", 0.50))
        reinforcement = self._score_reinforcement(content_lower, base.get("base", 0.50))
        temporal_persistence = self._score_temporal_persistence(content_lower, base.get("base", 0.50))
        
        # Calculate importance
        importance = (
            future_utility * 0.30 +
            identity_impact * 0.25 +
            emotional_salience * 0.15 +
            reinforcement * 0.15 +
            temporal_persistence * 0.15
        )
        
        return {
            "future_utility": future_utility,
            "identity_impact": identity_impact,
            "emotional_salience": emotional_salience,
            "reinforcement": reinforcement,
            "temporal_persistence": temporal_persistence,
            "importance_score": min(1.0, max(0.0, importance)),
            "reasoning": "Heuristic scoring based on keyword and content analysis"
        }
    
    def _score_future_utility(self, content: str, base: float) -> float:
        """Score likelihood this memory will matter in future"""
        score = base
        
        # Check for high utility keywords
        high_utility_count = sum(1 for kw in HIGH_UTILITY_KEYWORDS if kw in content)
        score += min(0.3, high_utility_count * 0.05)
        
        # Check for low utility keywords
        low_util_count = sum(1 for kw in LOW_IMPORTANCE_KEYWORDS if kw in content)
        score -= min(0.2, low_util_count * 0.03)
        
        # Length heuristic - longer, specific memories have higher utility
        if len(content) > 200:
            score += 0.1
        elif len(content) < 20:
            score -= 0.1
        
        return min(1.0, max(0.0, score))
    
    def _score_identity_impact(self, content: str, base: float) -> float:
        """Score whether memory defines user identity"""
        score = base
        
        # Identity keywords
        identity_count = sum(1 for kw in IDENTITY_KEYWORDS if kw in content)
        score += min(0.35, identity_count * 0.07)
        
        # Personal pronouns indicate identity
        pronouns = content.count(" i ") + content.count("i'm") + content.count("i'm")
        score += min(0.15, pronouns * 0.03)
        
        return min(1.0, max(0.0, score))
    
    def _score_emotional_salience(self, content: str, base: float) -> float:
        """Score emotional significance of memory"""
        score = base
        
        # Emotional keywords
        emotional_count = sum(1 for kw in EMOTIONAL_KEYWORDS if kw in content)
        score += min(0.4, emotional_count * 0.08)
        
        # Exclamation marks and caps indicate emotion
        exclamations = content.count("!")
        caps_words = sum(1 for word in content.split() if word.isupper() and len(word) > 1)
        score += min(0.2, (exclamations + caps_words) * 0.05)
        
        return min(1.0, max(0.0, score))
    
    def _score_reinforcement(self, content: str, base: float) -> float:
        """Score reinforcement potential (likelihood of repetition)"""
        score = base
        
        # Specific, detailed content more likely to recur
        words_count = len(content.split())
        if words_count > 100:
            score += 0.15
        elif words_count < 15:
            score -= 0.10
        
        # Repeated patterns or emphatic language
        emphatic_words = ["definitely", "always", "never", "absolutely", "must", "essential"]
        emphatic_count = sum(1 for word in emphatic_words if word in content)
        score += min(0.15, emphatic_count * 0.05)
        
        return min(1.0, max(0.0, score))
    
    def _score_temporal_persistence(self, content: str, base: float) -> float:
        """Score how long this memory will remain useful"""
        score = base
        
        # Temporal keywords
        persistence_count = sum(1 for kw in PERSISTENCE_KEYWORDS if kw in content)
        score += min(0.3, persistence_count * 0.06)
        
        # General/abstract content persists longer
        if len(content) > 100 and len(content.split()) > 20:
            score += 0.1
        
        return min(1.0, max(0.0, score))
    
    def _blend_scores(
        self,
        memory_content: str,
        memory_type: MemoryTypeEnum,
        primary_scores: Dict,
        use_llm: bool = True
    ) -> Dict:
        """Blend primary scores with heuristic validation"""
        if use_llm:
            # LLM scores are primary, but validate with heuristics
            heuristic_scores = self._heuristic_score(memory_content, memory_type)
            # Blend: 70% LLM, 30% heuristic for validation
            blended = {
                "future_utility": primary_scores.get("future_utility", 0.5) * 0.7 + heuristic_scores.get("future_utility", 0.5) * 0.3,
                "identity_impact": primary_scores.get("identity_impact", 0.5) * 0.7 + heuristic_scores.get("identity_impact", 0.5) * 0.3,
                "emotional_salience": primary_scores.get("emotional_salience", 0.5) * 0.7 + heuristic_scores.get("emotional_salience", 0.5) * 0.3,
                "reinforcement": primary_scores.get("reinforcement", 0.5) * 0.7 + heuristic_scores.get("reinforcement", 0.5) * 0.3,
                "temporal_persistence": primary_scores.get("temporal_persistence", 0.5) * 0.7 + heuristic_scores.get("temporal_persistence", 0.5) * 0.3,
            }
        else:
            # Pure heuristic
            blended = primary_scores.copy()
        
        # Recalculate importance score
        importance = (
            blended["future_utility"] * 0.30 +
            blended["identity_impact"] * 0.25 +
            blended["emotional_salience"] * 0.15 +
            blended["reinforcement"] * 0.15 +
            blended["temporal_persistence"] * 0.15
        )
        
        # Determine cognitive state based on importance
        cognitive_state = self._determine_state(importance)
        
        # Calculate memory strength and decay rate
        memory_strength = importance
        decay_rate = self._calculate_decay_rate(importance, memory_type)
        
        return {
            "future_utility_score": min(1.0, max(0.0, blended["future_utility"])),
            "identity_impact_score": min(1.0, max(0.0, blended["identity_impact"])),
            "emotional_salience_score": min(1.0, max(0.0, blended["emotional_salience"])),
            "reinforcement_score": min(1.0, max(0.0, blended["reinforcement"])),
            "temporal_persistence_score": min(1.0, max(0.0, blended["temporal_persistence"])),
            "importance_score": min(1.0, max(0.0, importance)),
            "cognitive_state": cognitive_state,
            "memory_strength": memory_strength,
            "decay_rate": decay_rate,
            "reasoning": primary_scores.get("reasoning", "Hybrid scoring applied")
        }
    
    @staticmethod
    def _determine_state(importance_score: float) -> CognitiveMemoryStateEnum:
        """Determine initial cognitive state based on importance"""
        if importance_score >= 0.80:
            return CognitiveMemoryStateEnum.ACTIVE
        elif importance_score >= 0.60:
            return CognitiveMemoryStateEnum.REINFORCED
        elif importance_score >= 0.40:
            return CognitiveMemoryStateEnum.SEMANTIC_CANDIDATE
        elif importance_score >= 0.20:
            return CognitiveMemoryStateEnum.DORMANT
        else:
            return CognitiveMemoryStateEnum.DECAYING
    
    @staticmethod
    def _calculate_decay_rate(importance_score: float, memory_type: MemoryTypeEnum) -> float:
        """Calculate exponential decay rate for memory"""
        # Base decay rates by type
        type_decay = {
            MemoryTypeEnum.PROCEDURAL: 0.02,     # Decay slowly - skills persist
            MemoryTypeEnum.IDENTITY: 0.01,       # Decay very slowly - identity persists
            MemoryTypeEnum.SEMANTIC: 0.05,       # Moderate decay - facts can change
            MemoryTypeEnum.EPISODIC: 0.15,       # Faster decay - events fade
        }
        
        base_decay = type_decay.get(memory_type, 0.05)
        
        # Adjust by importance - important memories decay slower
        importance_factor = 1.0 - (importance_score * 0.5)  # 0.5 to 1.0
        
        return base_decay * importance_factor


def score_memory(
    memory_content: str,
    memory_type: MemoryTypeEnum,
    use_llm: bool = True
) -> Dict:
    """Convenience function for memory scoring"""
    engine = HybridScoringEngine(use_llm=use_llm)
    return engine.score_memory(memory_content, memory_type, use_llm=use_llm)
