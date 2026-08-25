"""
Identity-Aware Context Builder

Builds retrieval context that incorporates user identity.
Personalizes response generation based on identity traits.
"""

from typing import List, Dict, Optional, Tuple
import logging
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import and_

from neurowave_engine.db.models import (
    IdentityNode, ConceptMemory, Memory, RetrievalLog
)
from neurowave_engine.services.identity_graph import IdentityGraphService
from neurowave_engine.services.identity_profile_generator import IdentityProfileGenerator


logger = logging.getLogger(__name__)


class IdentityAwareContextBuilder:
    """
    Builds retrieval context that respects user identity.
    
    Incorporates:
    - Communication style preferences
    - Relevant goals and interests
    - Behavioral traits (curious, analytical, etc.)
    - Technical skill level
    - Past interactions
    """

    def __init__(self, db: Session):
        """Initialize with database session."""
        self.db = db
        self.graph_service = IdentityGraphService(db)
        self.profile_generator = IdentityProfileGenerator(db)

    def build_personalized_context(
        self,
        user_id: str,
        query: str,
        concepts: List[ConceptMemory],
        num_identity_elements: int = 5
    ) -> Dict:
        """
        Build context that combines concepts with identity information.
        
        Args:
            user_id: User ID
            query: User's query/question
            concepts: Retrieved concepts
            num_identity_elements: How many identity elements to include
            
        Returns:
            Personalized context dict
        """
        logger.info(f"Building personalized context for user {user_id}, query: {query}")

        # Get user identity
        identity_traits = self._get_relevant_identity_traits(
            user_id,
            query,
            num_identity_elements
        )

        # Filter concepts based on identity
        filtered_concepts = self._filter_concepts_by_identity(
            concepts,
            identity_traits
        )

        # Get communication preferences
        comm_style = self._get_communication_style(user_id)

        # Build context
        context = {
            "query": query,
            "concepts": filtered_concepts,
            "identity_traits": identity_traits,
            "communication_style": comm_style,
            "personalization_instructions": self._generate_personalization_instructions(
                comm_style,
                identity_traits
            ),
            "confidence_level": self._calculate_context_confidence(
                identity_traits,
                filtered_concepts
            )
        }

        return context

    def _get_relevant_identity_traits(
        self,
        user_id: str,
        query: str,
        limit: int = 5
    ) -> List[Dict]:
        """
        Get identity traits relevant to current query.
        
        Args:
            user_id: User ID
            query: Query text
            limit: Maximum traits to return
            
        Returns:
            Relevant identity traits
        """
        # Get all high-confidence traits
        traits = self.db.query(IdentityNode).filter(
            and_(
                IdentityNode.user_id == user_id,
                IdentityNode.confidence >= 0.5
            )
        ).order_by(
            IdentityNode.importance.desc()
        ).all()

        # Score traits for relevance to query
        scored_traits = []
        for trait in traits[:20]:  # Look at top 20 traits
            relevance = self._score_trait_relevance(trait, query)
            if relevance > 0.0:
                scored_traits.append((trait, relevance))

        # Sort by relevance
        scored_traits.sort(key=lambda x: x[1], reverse=True)

        # Format results
        result = []
        for trait, relevance in scored_traits[:limit]:
            result.append({
                "type": trait.node_type,
                "value": trait.node_value,
                "confidence": trait.confidence,
                "relevance": relevance
            })

        return result

    def _score_trait_relevance(self, trait: IdentityNode, query: str) -> float:
        """
        Score how relevant a trait is to a query.
        
        Args:
            trait: Identity trait
            query: Query text
            
        Returns:
            Relevance score (0.0-1.0)
        """
        # Keywords by trait type
        type_keywords = {
            "goal": ["help", "build", "improve", "learn", "achieve"],
            "interest": ["interested", "curious", "about", "topic"],
            "skill": ["can", "know", "expertise", "use", "implement"],
            "behavior": ["usually", "typically", "tend", "prefer"],
            "communication": ["explain", "describe", "tell", "ask", "understand"],
            "value": ["important", "matter", "believe", "value"]
        }

        keywords = type_keywords.get(trait.node_type, [])
        query_lower = query.lower()
        trait_value_lower = trait.node_value.lower()

        # Check for trait value in query
        if trait_value_lower in query_lower:
            base_score = 0.7
        elif any(kw in query_lower for kw in keywords):
            base_score = 0.3
        else:
            base_score = 0.0

        # Factor in trait confidence
        return base_score * trait.confidence

    def _filter_concepts_by_identity(
        self,
        concepts: List[ConceptMemory],
        identity_traits: List[Dict]
    ) -> List[Dict]:
        """
        Filter and rerank concepts based on identity traits.
        
        Args:
            concepts: Retrieved concepts
            identity_traits: User identity traits
            
        Returns:
            Filtered and reranked concepts
        """
        trait_values = set([t["value"] for t in identity_traits])

        scored_concepts = []
        for concept in concepts:
            # Base score is confidence
            score = concept.confidence

            # Boost if related to identity traits
            for trait_val in trait_values:
                if trait_val.lower() in concept.concept_name.lower():
                    score *= 1.2
                elif trait_val.lower() in (concept.description or "").lower():
                    score *= 1.1

            scored_concepts.append((concept, score))

        # Sort by score
        scored_concepts.sort(key=lambda x: x[1], reverse=True)

        # Return as dicts
        result = []
        for concept, score in scored_concepts:
            result.append({
                "name": concept.concept_name,
                "description": concept.description,
                "confidence": concept.confidence,
                "relevance_to_identity": score,
                "support_count": concept.support_count
            })

        return result

    def _get_communication_style(self, user_id: str) -> Dict:
        """
        Get user's preferred communication style.
        
        Args:
            user_id: User ID
            
        Returns:
            Communication style preferences
        """
        comm_traits = self.db.query(IdentityNode).filter(
            and_(
                IdentityNode.user_id == user_id,
                IdentityNode.node_type == "communication",
                IdentityNode.confidence >= 0.4
            )
        ).order_by(
            IdentityNode.confidence.desc()
        ).all()

        if not comm_traits:
            return {
                "primary": "standard",
                "traits": [],
                "confidence": 0.0
            }

        primary = comm_traits[0]
        return {
            "primary": primary.node_value,
            "traits": [t.node_value for t in comm_traits],
            "confidence": primary.confidence
        }

    def _generate_personalization_instructions(
        self,
        comm_style: Dict,
        identity_traits: List[Dict]
    ) -> str:
        """
        Generate instructions for personalizing response.
        
        Args:
            comm_style: Communication style
            identity_traits: Identity traits
            
        Returns:
            Personalization instructions
        """
        instructions = []

        # Communication style instructions
        if comm_style["primary"] == "concise":
            instructions.append("Keep response concise and direct.")
        elif comm_style["primary"] == "detailed":
            instructions.append("Provide comprehensive details and examples.")
        elif comm_style["primary"] == "technical":
            instructions.append("Use technical terminology and system-level details.")
        elif comm_style["primary"] == "visual":
            instructions.append("Include diagrams or visual representations if possible.")
        elif comm_style["primary"] == "exploratory":
            instructions.append("Encourage exploration and open-ended thinking.")

        # Trait-based instructions
        trait_instructions = {
            "high_curiosity": "Satisfy curiosity with deeper explanations.",
            "analytical": "Focus on logical reasoning and analysis.",
            "experimental": "Include novel approaches and experiments.",
            "practical": "Focus on practical implementation.",
            "ambitious": "Challenge assumptions and aim high."
        }

        for trait in identity_traits:
            if trait["type"] == "behavior":
                if trait["value"] in trait_instructions:
                    instructions.append(trait_instructions[trait["value"]])

        return " ".join(instructions) if instructions else "Provide helpful context-appropriate response."

    def _calculate_context_confidence(
        self,
        identity_traits: List[Dict],
        concepts: List[Dict]
    ) -> float:
        """
        Calculate confidence in the built context.
        
        Args:
            identity_traits: Used identity traits
            concepts: Used concepts
            
        Returns:
            Confidence score (0.0-1.0)
        """
        if not identity_traits or not concepts:
            return 0.0

        # Average trait confidence
        avg_trait_conf = sum(t["confidence"] for t in identity_traits) / len(identity_traits)

        # Average concept confidence
        avg_concept_conf = sum(c["confidence"] for c in concepts) / len(concepts)

        # Combine
        return (avg_trait_conf + avg_concept_conf) / 2

    def get_response_guidance(self, user_id: str) -> Dict:
        """
        Get guidance for response generation.
        
        Includes context about user's preferences, goals, and style.
        
        Args:
            user_id: User ID
            
        Returns:
            Response guidance
        """
        profile = self.profile_generator.generate_profile(user_id, include_evolution=False)
        comm_style = self._get_communication_style(user_id)

        # Build guidance
        guidance = {
            "communication_style": comm_style,
            "user_context": profile.get("summary", ""),
            "key_interests": [i["value"] for i in profile.get("interests", [])[:3]],
            "skill_level": self._estimate_skill_level(profile),
            "goals": [g["value"] for g in profile.get("goals", [])],
            "values": [v["value"] for v in profile.get("values", [])]
        }

        return guidance

    def _estimate_skill_level(self, profile: Dict) -> str:
        """
        Estimate overall technical skill level.
        
        Args:
            profile: User profile
            
        Returns:
            Skill level (novice, intermediate, advanced, expert)
        """
        skills = profile.get("skills", [])
        if not skills:
            return "unknown"

        avg_confidence = sum(s["confidence"] for s in skills) / len(skills)

        if avg_confidence >= 0.8:
            return "expert"
        elif avg_confidence >= 0.6:
            return "advanced"
        elif avg_confidence >= 0.4:
            return "intermediate"
        else:
            return "novice"

    def extract_and_apply_context(
        self,
        user_id: str,
        query: str,
        retrieved_concepts: List[ConceptMemory]
    ) -> Dict:
        """
        End-to-end context extraction and application.
        
        Args:
            user_id: User ID
            query: User query
            retrieved_concepts: Retrieved concepts
            
        Returns:
            Complete context with personalization
        """
        # Build personalized context
        context = self.build_personalized_context(
            user_id,
            query,
            retrieved_concepts
        )

        # Get response guidance
        guidance = self.get_response_guidance(user_id)
        context["response_guidance"] = guidance

        # Log retrieval
        self._log_retrieval(user_id, query, context)

        return context

    def _log_retrieval(self, user_id: str, query: str, context: Dict):
        """
        Log retrieval for analytics.
        
        Args:
            user_id: User ID
            query: Query text
            context: Generated context
        """
        try:
            log = RetrievalLog(
                user_id=user_id,
                query=query,
                retrieved_memory_ids=[],
                retrieval_latency_ms=0,
                context_token_count=len(str(context).split()),
                created_at=datetime.utcnow()
            )
            self.db.add(log)
            self.db.commit()
        except Exception as e:
            logger.error(f"Failed to log retrieval: {e}")

    def get_query_routing_hint(self, user_id: str, query: str) -> str:
        """
        Suggest how to route/handle query based on identity.
        
        Args:
            user_id: User ID
            query: Query text
            
        Returns:
            Routing hint
        """
        traits = self._get_relevant_identity_traits(user_id, query, limit=3)

        if not traits:
            return "general"

        # Determine routing based on traits
        trait_types = set([t["type"] for t in traits])

        if "goal" in trait_types:
            return "goal_aligned"
        elif "interest" in trait_types:
            return "interest_relevant"
        elif "skill" in trait_types:
            return "skill_development"
        else:
            return "general"
