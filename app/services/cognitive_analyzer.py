"""Cognitive memory analyzer using LLM for human-like importance assessment"""
import json
import logging
from typing import Dict, Optional
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

# Initialize OpenAI client
client = OpenAI()

COGNITIVE_ANALYSIS_PROMPT = """You are a cognitive memory analyzer designed to assess the long-term cognitive value of memories.

Analyze the following memory and provide a JSON response with cognitive importance scores.

Memory Content:
{memory_content}

Memory Type: {memory_type}

Your task:
1. Evaluate the future utility of this memory (how likely it is to matter later)
2. Assess identity impact (does it define who the user is)
3. Measure emotional salience (emotional significance)
4. Estimate reinforcement potential (likelihood of repetition)
5. Calculate temporal persistence (how long it will remain useful)

Return ONLY valid JSON with these exact fields (float 0.0-1.0):
{{
  "future_utility": <float>,
  "identity_impact": <float>,
  "emotional_salience": <float>,
  "reinforcement": <float>,
  "temporal_persistence": <float>,
  "reasoning": "<brief explanation>"
}}

IMPORTANT:
- All scores must be floats between 0.0 and 1.0
- Be consistent with memory importance research
- Consider long-term cognitive value, not just immediate relevance
- Return ONLY the JSON object, no additional text
"""


class CognitiveAnalyzer:
    """LLM-powered cognitive memory analyzer"""
    
    def __init__(self, model: str = "gpt-4"):
        """Initialize analyzer with OpenAI model"""
        self.model = model
        self.client = client
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    def analyze_memory(
        self,
        memory_content: str,
        memory_type: str,
        user_context: Optional[Dict] = None
    ) -> Dict[str, float]:
        """
        Analyze a memory using LLM-based cognitive assessment
        
        Args:
            memory_content: The memory text to analyze
            memory_type: Type of memory (episodic/semantic/identity/procedural)
            user_context: Optional user context for better analysis
            
        Returns:
            Dict with cognitive scores and reasoning
        """
        try:
            prompt = COGNITIVE_ANALYSIS_PROMPT.format(
                memory_content=memory_content,
                memory_type=memory_type
            )
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a cognitive memory analyzer. Respond with valid JSON only."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.3,
                max_tokens=500
            )
            
            response_text = response.choices[0].message.content.strip()
            
            # Parse JSON response
            analysis = json.loads(response_text)
            
            # Validate score ranges
            self._validate_scores(analysis)
            
            # Calculate final importance score using weighted formula
            importance_score = (
                analysis.get("future_utility", 0.5) * 0.30 +
                analysis.get("identity_impact", 0.5) * 0.25 +
                analysis.get("emotional_salience", 0.5) * 0.15 +
                analysis.get("reinforcement", 0.5) * 0.15 +
                analysis.get("temporal_persistence", 0.5) * 0.15
            )
            
            analysis["importance_score"] = min(1.0, max(0.0, importance_score))
            
            logger.info(
                f"Cognitive analysis: importance={importance_score:.2f}, "
                f"future_utility={analysis['future_utility']:.2f}, "
                f"identity_impact={analysis['identity_impact']:.2f}"
            )
            
            return analysis
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            # Return default scores on parse error
            return self._get_default_scores(memory_content, memory_type)
        except Exception as e:
            logger.error(f"Cognitive analysis error: {e}")
            # Return default scores on any error
            return self._get_default_scores(memory_content, memory_type)
    
    @staticmethod
    def _validate_scores(analysis: Dict) -> None:
        """Validate that scores are in valid range"""
        for key in ["future_utility", "identity_impact", "emotional_salience", "reinforcement", "temporal_persistence"]:
            if key in analysis:
                value = analysis[key]
                if not isinstance(value, (int, float)) or value < 0.0 or value > 1.0:
                    analysis[key] = max(0.0, min(1.0, float(value)))
    
    @staticmethod
    def _get_default_scores(memory_content: str, memory_type: str) -> Dict[str, float]:
        """
        Fallback scoring when LLM analysis fails
        Uses heuristic defaults based on memory type
        """
        type_defaults = {
            "identity": {"base": 0.75, "identity_impact": 0.85},
            "semantic": {"base": 0.65, "future_utility": 0.80},
            "procedural": {"base": 0.80, "temporal_persistence": 0.90},
            "episodic": {"base": 0.45, "emotional_salience": 0.70}
        }
        
        defaults = type_defaults.get(memory_type, {"base": 0.50})
        
        return {
            "future_utility": defaults.get("future_utility", 0.50),
            "identity_impact": defaults.get("identity_impact", 0.50),
            "emotional_salience": defaults.get("emotional_salience", 0.50),
            "reinforcement": 0.50,
            "temporal_persistence": defaults.get("temporal_persistence", 0.50),
            "importance_score": defaults.get("base", 0.50),
            "reasoning": "Fallback heuristic scoring due to LLM analysis failure"
        }


async def analyze_memory_async(
    memory_content: str,
    memory_type: str,
    user_context: Optional[Dict] = None
) -> Dict[str, float]:
    """Async wrapper for cognitive analysis"""
    analyzer = CognitiveAnalyzer()
    return analyzer.analyze_memory(memory_content, memory_type, user_context)
