"""
Cognitive Context Analyzer

Fuses the current query with everything NeuroWeave already knows about the
user — identity traits, semantic concepts — into a single structured
"what does the AI need to know right now" representation. This is what the
Memory Utility Predictor scores candidate memories against, instead of
scoring them against the raw query string alone.
"""
import logging
import re
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.db.models import IdentityNode, ConceptMemory

logger = logging.getLogger(__name__)


STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "i", "me", "my", "we", "our", "you", "your", "it", "its", "this", "that",
    "to", "of", "in", "on", "for", "with", "and", "or", "but", "so", "if",
    "do", "does", "did", "can", "could", "should", "would", "will", "shall",
    "help", "please", "about", "how", "what", "why", "when", "where", "who",
    # "user"/"users" is near-universal boilerplate in this app's memory
    # content (almost every memory is phrased "User prefers/likes/...") -
    # left in, it dominates word-frequency naming and inflates word-overlap
    # similarity/contradiction checks without carrying real topical signal.
    "user", "users",
}

# Maps a detected goal to the categories of knowledge that satisfy it.
# Used to bias which concepts/identity traits count as "relevant" beyond
# raw keyword overlap. Extend freely as new goals are added to GoalDetector.
GOAL_KNOWLEDGE_MAP: Dict[str, List[str]] = {
    "system_design": ["architecture", "scalability", "databases", "distributed_systems", "backend_engineering"],
    "interview_preparation": ["technical_fundamentals", "communication_style", "past_experience", "backend_engineering"],
    "debugging": ["technical_fundamentals", "past_experience", "tooling"],
    "learning": ["technical_fundamentals", "communication_style"],
    "career_planning": ["goals", "values", "past_experience"],
    "startup_ideation": ["goals", "interests", "builder_mindset"],
    "research": ["technical_fundamentals", "interests"],
    "code_review": ["technical_fundamentals", "communication_style"],
    "optimization": ["technical_fundamentals", "backend_engineering"],
    "purchase_decision": ["values", "interests"],
    "summarization": ["communication_style"],
    "general_assistance": ["communication_style"],
}


class ContextAnalyzer:
    """
    Builds the structured "required knowledge" representation for a query.
    """

    def __init__(self, session: Session):
        self.session = session

    def analyze(
        self,
        user_id: UUID,
        query: str,
        goal: str,
        intents: List[str],
    ) -> Dict:
        """
        Analyze current situation and produce structured context needs.

        Args:
            user_id: User ID
            query: Current query text
            goal: Detected goal (from GoalDetector)
            intents: List of classified intent names

        Returns:
            Structured dict consumed by MemoryUtilityPredictor
        """
        keywords = self._extract_keywords(query)
        identity_traits = self._get_identity_traits(user_id)
        concepts = self._get_concepts(user_id)
        required_knowledge = GOAL_KNOWLEDGE_MAP.get(goal, GOAL_KNOWLEDGE_MAP["general_assistance"])

        return {
            "query": query,
            "goal": goal,
            "intents": intents,
            "keywords": keywords,
            "identity_traits": identity_traits,
            "concepts": concepts,
            "required_knowledge": required_knowledge,
        }

    def _extract_keywords(self, query: str) -> List[str]:
        """Tokenize the query into lowercase content words (stopwords removed)"""
        tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9\-]{2,}", query.lower())
        seen = []
        for token in tokens:
            if token not in STOPWORDS and token not in seen:
                seen.append(token)
        return seen

    def _get_identity_traits(self, user_id: UUID, limit: int = 30) -> List[Dict]:
        """Fetch the user's higher-confidence identity traits"""
        try:
            traits = self.session.query(IdentityNode).filter(
                and_(
                    IdentityNode.user_id == user_id,
                    IdentityNode.confidence >= 0.3,
                )
            ).order_by(IdentityNode.importance.desc()).limit(limit).all()

            return [
                {
                    "id": str(trait.id),
                    "type": trait.node_type,
                    "value": trait.node_value,
                    "confidence": trait.confidence,
                    "importance": trait.importance,
                }
                for trait in traits
            ]
        except Exception as e:
            logger.warning(f"ContextAnalyzer: failed to load identity traits: {e}")
            return []

    def _get_concepts(self, user_id: UUID, limit: int = 50) -> List[Dict]:
        """Fetch the user's consolidated semantic concepts"""
        try:
            concepts = self.session.query(ConceptMemory).filter(
                ConceptMemory.user_id == user_id
            ).order_by(ConceptMemory.confidence.desc()).limit(limit).all()

            return [
                {
                    "id": str(concept.id),
                    "name": concept.concept_name,
                    "description": concept.description or "",
                    "confidence": concept.confidence,
                    "support_count": concept.support_count,
                }
                for concept in concepts
            ]
        except Exception as e:
            logger.warning(f"ContextAnalyzer: failed to load concepts: {e}")
            return []
