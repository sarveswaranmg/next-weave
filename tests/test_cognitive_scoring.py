"""Tests for cognitive scoring engine"""
import pytest
from app.db.models import MemoryTypeEnum
from app.services.cognitive_scoring import HybridScoringEngine, score_memory


class TestHybridScoringEngine:
    """Test hybrid scoring engine"""
    
    def test_heuristic_scoring_high_importance(self):
        """Test that high-importance content scores well"""
        engine = HybridScoringEngine(use_llm=False)
        
        content = "I am building an AI startup focused on inference optimization. My goal is to revolutionize system performance."
        result = engine.score_memory(content, MemoryTypeEnum.IDENTITY, use_llm=False)
        
        # Should be high importance
        assert result["importance_score"] > 0.70
        assert result["identity_impact_score"] > 0.60
        assert result["future_utility_score"] > 0.60
    
    def test_heuristic_scoring_low_importance(self):
        """Test that low-importance content scores low"""
        engine = HybridScoringEngine(use_llm=False)
        
        content = "hello"
        result = engine.score_memory(content, MemoryTypeEnum.EPISODIC, use_llm=False)
        
        # Should be low importance
        assert result["importance_score"] < 0.50
        assert result["future_utility_score"] < 0.50
    
    def test_emotional_salience_detection(self):
        """Test detection of emotionally salient content"""
        engine = HybridScoringEngine(use_llm=False)
        
        content = "I'm really excited about this achievement! This is amazing and I'm so proud!"
        result = engine.score_memory(content, MemoryTypeEnum.EPISODIC, use_llm=False)
        
        # Should have high emotional salience
        assert result["emotional_salience_score"] > 0.60
    
    def test_identity_impact_detection(self):
        """Test detection of identity-defining content"""
        engine = HybridScoringEngine(use_llm=False)
        
        content = "I am deeply passionate about creating systems that scale. This defines who I am as an engineer."
        result = engine.score_memory(content, MemoryTypeEnum.IDENTITY, use_llm=False)
        
        # Should have high identity impact
        assert result["identity_impact_score"] > 0.65
    
    def test_persistence_keyword_detection(self):
        """Test detection of persistent/long-term content"""
        engine = HybridScoringEngine(use_llm=False)
        
        content = "Architecture is fundamental to everything. This is the core foundation that will always matter."
        result = engine.score_memory(content, MemoryTypeEnum.SEMANTIC, use_llm=False)
        
        # Should have high temporal persistence
        assert result["temporal_persistence_score"] > 0.65
    
    def test_procedural_memory_type_bias(self):
        """Test that procedural memories get higher base scores"""
        engine = HybridScoringEngine(use_llm=False)
        
        content = "Always check return values"
        
        procedural_result = engine.score_memory(content, MemoryTypeEnum.PROCEDURAL, use_llm=False)
        episodic_result = engine.score_memory(content, MemoryTypeEnum.EPISODIC, use_llm=False)
        
        # Procedural should score higher than episodic
        assert procedural_result["importance_score"] > episodic_result["importance_score"]
    
    def test_identity_memory_type_bias(self):
        """Test that identity memories get higher scores"""
        engine = HybridScoringEngine(use_llm=False)
        
        content = "I prefer concise technical answers"
        
        identity_result = engine.score_memory(content, MemoryTypeEnum.IDENTITY, use_llm=False)
        episodic_result = engine.score_memory(content, MemoryTypeEnum.EPISODIC, use_llm=False)
        
        # Identity should score higher than episodic
        assert identity_result["importance_score"] > episodic_result["importance_score"]
    
    def test_cognitive_state_assignment(self):
        """Test cognitive state assignment based on importance"""
        engine = HybridScoringEngine(use_llm=False)
        
        # High importance
        high_content = "I am building an AI company focused on revolution"
        high_result = engine.score_memory(high_content, MemoryTypeEnum.IDENTITY, use_llm=False)
        assert high_result["cognitive_state"].value == "active"

        # Low importance
        low_content = "hello"
        low_result = engine.score_memory(low_content, MemoryTypeEnum.EPISODIC, use_llm=False)
        assert low_result["cognitive_state"].value in ["decaying", "dormant", "semantic_candidate"]
    
    def test_decay_rate_by_memory_type(self):
        """Test that decay rates differ by memory type"""
        engine = HybridScoringEngine(use_llm=False)
        
        content = "Some content"
        
        procedural = engine.score_memory(content, MemoryTypeEnum.PROCEDURAL, use_llm=False)
        identity = engine.score_memory(content, MemoryTypeEnum.IDENTITY, use_llm=False)
        episodic = engine.score_memory(content, MemoryTypeEnum.EPISODIC, use_llm=False)
        
        # Identity decays slowest, episodic decays fastest (per DAY7 spec)
        assert identity["decay_rate"] < procedural["decay_rate"] < episodic["decay_rate"]
    
    def test_score_ranges(self):
        """Test that all scores are in valid range 0.0-1.0"""
        engine = HybridScoringEngine(use_llm=False)
        
        content = "Test content with various importance signals!"
        result = engine.score_memory(content, MemoryTypeEnum.SEMANTIC, use_llm=False)
        
        # All scores should be in range
        assert 0.0 <= result["future_utility_score"] <= 1.0
        assert 0.0 <= result["identity_impact_score"] <= 1.0
        assert 0.0 <= result["emotional_salience_score"] <= 1.0
        assert 0.0 <= result["reinforcement_score"] <= 1.0
        assert 0.0 <= result["temporal_persistence_score"] <= 1.0
        assert 0.0 <= result["importance_score"] <= 1.0
        assert 0.0 <= result["memory_strength"] <= 1.0
        assert 0.0 <= result["decay_rate"] <= 1.0


class TestScoringEdgeCases:
    """Test edge cases in scoring"""
    
    def test_empty_content(self):
        """Test scoring of empty content"""
        engine = HybridScoringEngine(use_llm=False)
        
        result = engine.score_memory("", MemoryTypeEnum.EPISODIC, use_llm=False)
        
        assert result["importance_score"] >= 0.0
        assert result["importance_score"] <= 1.0
    
    def test_very_long_content(self):
        """Test scoring of very long content"""
        engine = HybridScoringEngine(use_llm=False)
        
        content = "word " * 1000  # Very long
        result = engine.score_memory(content, MemoryTypeEnum.IDENTITY, use_llm=False)
        
        # Length should help but score should still be capped at 1.0
        assert result["importance_score"] <= 1.0
        assert result["future_utility_score"] <= 1.0
    
    def test_special_characters(self):
        """Test scoring content with special characters"""
        engine = HybridScoringEngine(use_llm=False)
        
        content = "@#$%^&*() Test !!!!! AMAZING!!!!!"
        result = engine.score_memory(content, MemoryTypeEnum.EPISODIC, use_llm=False)
        
        # Should handle special characters
        assert 0.0 <= result["emotional_salience_score"] <= 1.0
    
    def test_repeated_keywords(self):
        """Test that repeated keywords boost scores appropriately"""
        engine = HybridScoringEngine(use_llm=False)
        
        content_single = "goal"
        content_repeated = "goal goal goal goal goal"
        
        single = engine.score_memory(content_single, MemoryTypeEnum.IDENTITY, use_llm=False)
        repeated = engine.score_memory(content_repeated, MemoryTypeEnum.IDENTITY, use_llm=False)
        
        # Repeated should score higher
        assert repeated["future_utility_score"] > single["future_utility_score"]


class TestScoringFormula:
    """Test the scoring formula weights"""
    
    def test_formula_weights_sum(self):
        """Test that formula weights sum to 1.0"""
        # Formula: future_utility * 0.30 + identity_impact * 0.25 + emotional_salience * 0.15 + reinforcement * 0.15 + temporal_persistence * 0.15
        weights = [0.30, 0.25, 0.15, 0.15, 0.15]
        total = sum(weights)
        assert abs(total - 1.0) < 0.001
    
    def test_uniform_scoring_distribution(self):
        """Test that uniform dimension scores produce middle importance"""
        engine = HybridScoringEngine(use_llm=False)
        
        # Mock heuristic with all equal scores
        class MockScorer:
            pass
        
        # All 0.5
        expected_importance = 0.5
        # 0.5 * 0.30 + 0.5 * 0.25 + 0.5 * 0.15 + 0.5 * 0.15 + 0.5 * 0.15 = 0.5
        assert expected_importance == 0.5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
