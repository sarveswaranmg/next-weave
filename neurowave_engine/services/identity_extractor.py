"""
Identity Extractor Service

Analyzes memories and concepts to infer user identity traits.
Extracts goals, interests, communication patterns, values, traits, and skills.

Uses LLM-assisted extraction with confidence scoring.
"""

from typing import List, Dict, Optional, Tuple
import json
import logging
from datetime import datetime
import uuid

from sqlalchemy.orm import Session
from sqlalchemy import func

import openai
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from neurowave_engine.db.models import (
    Memory, ConceptMemory, IdentityNode, IdentityHistory,
    MemoryTypeEnum, CognitiveMemoryStateEnum
)
from neurowave_engine.memory.embeddings import get_embedding_service


logger = logging.getLogger(__name__)


# Node types and valid values
NODE_TYPES = {
    "goal": [
        "become_staff_engineer", "build_startup", "learn_ai_systems",
        "improve_dsa", "software_engineering_growth", "leadership",
        "technical_excellence", "startup_creation"
    ],
    "interest": [
        "ai", "infrastructure", "startups", "backend_engineering",
        "databases", "distributed_systems", "systems_design",
        "cloud_computing", "machine_learning", "nlp"
    ],
    "communication": [
        "concise", "detailed", "technical", "visual", "exploratory",
        "storytelling", "direct", "socratic"
    ],
    "behavior": [
        "high_curiosity", "ambitious", "analytical", "experimental",
        "persistent", "risk_tolerant", "methodical", "creative",
        "builder", "learner", "explorer"
    ],
    "value": [
        "continuous_learning", "speed", "excellence", "innovation",
        "independence", "collaboration", "reliability", "simplicity"
    ],
    "skill": [
        "backend_engineering", "frontend_development", "devops",
        "data_engineering", "system_design", "python", "golang",
        "rust", "java", "distributed_systems", "databases",
        "ai_ml", "cloud_architecture"
    ]
}


class IdentityExtractor:
    """
    Extracts and manages identity traits from memories and concepts.
    
    Identity traits include:
    - Goals: Career and personal aspirations
    - Interests: Areas of fascination and focus
    - Communication: How the user prefers to communicate
    - Behaviors: Behavioral patterns and traits
    - Values: Core principles and priorities
    - Skills: Technical and domain expertise
    """

    def __init__(self, db: Session, embedding_service=None):
        """Initialize extractor with database session."""
        self.db = db
        self.embedding_service = embedding_service or get_embedding_service()
        self.llm_model = "gpt-4"
        self.temperature = 0.3  # Lower temperature for consistent extraction

    def extract_from_memories(
        self,
        user_id: str,
        memories: List[Memory],
        batch_size: int = 10
    ) -> Dict[str, List[Dict]]:
        """
        Extract identity traits from a batch of memories.
        
        Args:
            user_id: User ID
            memories: List of Memory objects to analyze
            batch_size: Memories per LLM call
            
        Returns:
            Dictionary with extracted traits by type
        """
        if not memories:
            logger.warning(f"No memories provided for identity extraction for user {user_id}")
            return {}

        logger.info(f"Extracting identity from {len(memories)} memories for user {user_id}")

        all_traits = {
            "goals": [],
            "interests": [],
            "communication": [],
            "behaviors": [],
            "values": [],
            "skills": []
        }

        # Process memories in batches
        for i in range(0, len(memories), batch_size):
            batch = memories[i:i + batch_size]
            traits = self._extract_from_batch(batch)
            
            # Merge traits
            for key in all_traits:
                if key in traits:
                    all_traits[key].extend(traits[key])

        return all_traits

    def extract_from_concepts(
        self,
        user_id: str,
        concepts: List[ConceptMemory]
    ) -> Dict[str, List[Dict]]:
        """
        Extract identity traits from semantic concepts.
        
        More efficient than memory extraction - works on consolidated concepts.
        
        Args:
            user_id: User ID
            concepts: List of ConceptMemory objects
            
        Returns:
            Dictionary with extracted traits
        """
        if not concepts:
            logger.warning(f"No concepts provided for identity extraction for user {user_id}")
            return {}

        logger.info(f"Extracting identity from {len(concepts)} concepts for user {user_id}")

        # Convert concepts to memory-like format for processing
        concept_texts = [
            f"Concept: {c.concept_name}. {c.description}. (confidence: {c.confidence})"
            for c in concepts
        ]

        return self._extract_from_texts(concept_texts)

    def _extract_from_batch(self, memories: List[Memory]) -> Dict[str, List[Dict]]:
        """
        Extract traits from a batch of memories using LLM.
        
        Args:
            memories: Batch of memories
            
        Returns:
            Extracted traits
        """
        # Build context from memories
        memory_texts = [
            f"- {m.summary or m.content[:200]}" 
            for m in memories
        ]
        context = "\n".join(memory_texts)

        # Use LLM for extraction
        traits = self._extract_with_llm(context)
        
        return traits

    def _extract_from_texts(self, texts: List[str]) -> Dict[str, List[Dict]]:
        """
        Extract traits from list of texts.
        
        Args:
            texts: List of text content
            
        Returns:
            Extracted traits
        """
        context = "\n".join(texts)
        traits = self._extract_with_llm(context)
        return traits

    def _extract_with_llm(self, context: str) -> Dict[str, List[Dict]]:
        """
        Use GPT-4 to extract identity traits from context.
        
        Args:
            context: Text to analyze
            
        Returns:
            Extracted traits with confidence scores
        """
        prompt = f"""Analyze the following user context and extract identity traits.

CONTEXT:
{context}

Extract the following types of identity traits:
1. Goals (career/personal aspirations)
2. Interests (areas of focus)
3. Communication style (how they prefer to communicate)
4. Behavioral traits (personality patterns)
5. Values (core principles)
6. Skills (technical expertise)

For each trait, provide:
- The trait value (concise)
- Confidence (0.0-1.0)
- Brief reasoning

Format as JSON:
{{
  "goals": [{{"value": "...", "confidence": 0.0, "reasoning": "..."}}],
  "interests": [{{"value": "...", "confidence": 0.0, "reasoning": "..."}}],
  "communication": [{{"value": "...", "confidence": 0.0, "reasoning": "..."}}],
  "behaviors": [{{"value": "...", "confidence": 0.0, "reasoning": "..."}}],
  "values": [{{"value": "...", "confidence": 0.0, "reasoning": "..."}}],
  "skills": [{{"value": "...", "confidence": 0.0, "reasoning": "..."}}]
}}

Focus on evidence-based traits. Only include traits mentioned or strongly implied in the context.
Confidence should reflect how strongly the context supports the trait."""

        try:
            response = openai.ChatCompletion.create(
                model=self.llm_model,
                messages=[
                    {"role": "system", "content": "You are an expert at analyzing user identity and behavior patterns."},
                    {"role": "user", "content": prompt}
                ],
                temperature=self.temperature,
                max_tokens=2000
            )

            result_text = response.choices[0].message.content.strip()
            
            # Parse JSON from response
            traits = json.loads(result_text)
            
            # Validate and normalize
            return self._validate_traits(traits)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            return {
                "goals": [], "interests": [], "communication": [],
                "behaviors": [], "values": [], "skills": []
            }
        except Exception as e:
            logger.error(f"LLM extraction failed: {e}")
            return {
                "goals": [], "interests": [], "communication": [],
                "behaviors": [], "values": [], "skills": []
            }

    def _validate_traits(self, traits: Dict) -> Dict[str, List[Dict]]:
        """
        Validate extracted traits against known values.
        
        Args:
            traits: Raw extracted traits
            
        Returns:
            Validated traits
        """
        validated = {
            "goals": [],
            "interests": [],
            "communication": [],
            "behaviors": [],
            "values": [],
            "skills": []
        }

        for trait_type, trait_list in traits.items():
            if trait_type not in validated:
                continue

            for trait in trait_list:
                if not isinstance(trait, dict):
                    continue

                value = trait.get("value", "").lower().replace(" ", "_")
                confidence = float(trait.get("confidence", 0.5))
                reasoning = trait.get("reasoning", "")

                # Validate confidence
                confidence = max(0.0, min(1.0, confidence))

                # Normalize trait value
                normalized_value = self._normalize_trait_value(value)
                
                if normalized_value:
                    validated[trait_type].append({
                        "value": normalized_value,
                        "confidence": confidence,
                        "reasoning": reasoning
                    })

        return validated

    def _normalize_trait_value(self, value: str) -> Optional[str]:
        """
        Normalize trait value to standard form.
        
        Args:
            value: Raw trait value
            
        Returns:
            Normalized value or None if invalid
        """
        value = value.lower().strip()
        
        # Direct mapping
        for node_type, valid_values in NODE_TYPES.items():
            if value in valid_values:
                return value
            
            # Fuzzy match
            for valid in valid_values:
                if value in valid or valid in value:
                    return valid
        
        # Fallback: keep as-is but mark for review
        return value

    def create_identity_nodes(
        self,
        user_id: str,
        extracted_traits: Dict[str, List[Dict]]
    ) -> List[IdentityNode]:
        """
        Create IdentityNode objects from extracted traits.
        
        Args:
            user_id: User ID (as string)
            extracted_traits: Extracted traits dictionary
            
        Returns:
            List of created IdentityNode objects
        """
        created_nodes = []

        for trait_type, traits in extracted_traits.items():
            for trait in traits:
                # Check if node already exists
                existing = self.db.query(IdentityNode).filter(
                    IdentityNode.user_id == user_id,
                    IdentityNode.node_type == trait_type,
                    IdentityNode.node_value == trait["value"]
                ).first()

                if existing:
                    # Reinforce existing node
                    self._reinforce_node(existing, trait["confidence"])
                    created_nodes.append(existing)
                else:
                    # Create new node
                    node = IdentityNode(
                        id=uuid.uuid4(),
                        user_id=user_id,
                        node_type=trait_type,
                        node_value=trait["value"],
                        confidence=trait["confidence"],
                        evidence_count=1,
                        reinforcement_count=1,
                        last_reinforced_at=datetime.utcnow(),
                        importance=self._calculate_importance(trait_type, trait["confidence"]),
                        extra_metadata={"reasoning": trait.get("reasoning", "")}
                    )
                    self.db.add(node)
                    created_nodes.append(node)

        self.db.commit()
        logger.info(f"Created {len(created_nodes)} identity nodes for user {user_id}")
        return created_nodes

    def _reinforce_node(self, node: IdentityNode, new_confidence: float):
        """
        Reinforce an existing identity node.
        
        Args:
            node: IdentityNode to reinforce
            new_confidence: New confidence evidence
        """
        old_confidence = node.confidence
        
        # Update confidence using exponential moving average
        alpha = 0.7  # Weight for new evidence
        node.confidence = alpha * new_confidence + (1 - alpha) * node.confidence
        node.confidence = max(0.0, min(1.0, node.confidence))
        
        # Update evidence
        node.reinforcement_count += 1
        node.evidence_count += 1
        node.last_reinforced_at = datetime.utcnow()
        
        # Record history
        history = IdentityHistory(
            id=uuid.uuid4(),
            user_id=node.user_id,
            node_id=node.id,
            node_type=node.node_type,
            node_value=node.node_value,
            old_confidence=old_confidence,
            new_confidence=node.confidence,
            confidence_delta=node.confidence - old_confidence,
            change_reason="reinforced",
            event_type="reinforced"
        )
        self.db.add(history)
        self.db.commit()

    def _calculate_importance(self, node_type: str, confidence: float) -> float:
        """
        Calculate node importance based on type and confidence.
        
        Args:
            node_type: Type of node
            confidence: Confidence score
            
        Returns:
            Importance score (0.0-1.0)
        """
        # Weights by type
        type_weights = {
            "goal": 1.0,
            "value": 0.9,
            "behavior": 0.8,
            "interest": 0.7,
            "communication": 0.6,
            "skill": 0.5
        }
        
        weight = type_weights.get(node_type, 0.5)
        return min(1.0, confidence * weight)

    def get_user_identity_profile(self, user_id: str) -> Dict:
        """
        Get comprehensive user identity profile from all nodes.
        
        Args:
            user_id: User ID
            
        Returns:
            Identity profile summary
        """
        nodes = self.db.query(IdentityNode).filter(
            IdentityNode.user_id == user_id,
            IdentityNode.confidence >= 0.5
        ).order_by(
            IdentityNode.importance.desc()
        ).all()

        if not nodes:
            logger.warning(f"No identity nodes found for user {user_id}")
            return {}

        profile = {
            "goals": [],
            "interests": [],
            "communication": [],
            "behaviors": [],
            "values": [],
            "skills": []
        }

        # IdentityNode.node_type is stored singular ("goal", "interest", ...);
        # profile buckets are plural category names.
        node_type_to_category = {
            "goal": "goals",
            "interest": "interests",
            "communication": "communication",
            "behavior": "behaviors",
            "value": "values",
            "skill": "skills",
        }

        for node in nodes:
            category = node_type_to_category.get(node.node_type)
            if category:
                profile[category].append({
                    "value": node.node_value,
                    "confidence": node.confidence,
                    "importance": node.importance,
                    "reinforcement_count": node.reinforcement_count
                })

        return profile

    def track_evolution(self, user_id: str, days: int = 30) -> Dict:
        """
        Track how user identity has evolved over time.
        
        Args:
            user_id: User ID
            days: Number of days to look back
            
        Returns:
            Evolution metrics
        """
        cutoff_date = datetime.utcnow().timestamp() - (days * 86400)
        
        history = self.db.query(IdentityHistory).filter(
            IdentityHistory.user_id == user_id,
            IdentityHistory.created_at >= cutoff_date
        ).all()

        if not history:
            return {"events": [], "trends": {}}

        events = len(history)
        increased = sum(1 for h in history if h.confidence_delta > 0.1)
        decreased = sum(1 for h in history if h.confidence_delta < -0.1)

        return {
            "events": events,
            "increased_confidence": increased,
            "decreased_confidence": decreased,
            "traits_changed": list(set([h.node_value for h in history])),
            "avg_delta": np.mean([h.confidence_delta for h in history if h.confidence_delta])
        }
