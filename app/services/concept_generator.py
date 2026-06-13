"""Concept extraction and generation service"""
import logging
import json
from typing import List, Optional, Dict
from uuid import UUID
from sqlalchemy.orm import Session
from openai import OpenAI

from app.db.models import Memory, MemoryCluster, ConceptMemory
from app.memory.embeddings import embedding_service
from app.core.config import settings

logger = logging.getLogger(__name__)


class ConceptGenerator:
    """
    Extracts semantic concepts from memory clusters using LLM assistance.
    
    Provides:
    - Pattern analysis and interpretation
    - Concept naming and description
    - Confidence scoring
    - Canonical representation generation
    """

    def __init__(self):
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.embedding_service = embedding_service
        self.model = "gpt-4"  # Use best model for concept extraction
        self.confidence_threshold = 0.7

    def generate_concept_from_cluster(
        self,
        session: Session,
        user_id: UUID,
        cluster: MemoryCluster,
    ) -> Optional[ConceptMemory]:
        """
        Generate a semantic concept from a memory cluster.
        
        Args:
            session: Database session
            user_id: User ID
            cluster: MemoryCluster to analyze
            
        Returns:
            Generated ConceptMemory object
        """
        try:
            # Get cluster memories
            memory_ids = [UUID(mid) for mid in cluster.memory_ids]
            memories = session.query(Memory).filter(Memory.id.in_(memory_ids)).all()

            if not memories:
                logger.warning("No memories found for cluster")
                return None

            # Extract concept using LLM
            concept_info = self._extract_concept_with_llm(memories, cluster)

            if not concept_info:
                logger.warning("Failed to extract concept from cluster")
                return None

            # Generate embedding for concept
            concept_embedding = self.embedding_service.embed_text(concept_info['description'])

            # Create ConceptMemory
            concept = ConceptMemory(
                user_id=user_id,
                concept_name=concept_info['name'],
                description=concept_info['description'],
                confidence=float(concept_info.get('confidence', 0.85)),
                support_count=len(memories),
                supporting_memory_ids=[str(m.id) for m in memories],
                embedding=str(concept_embedding),
                metadata={
                    'cluster_id': cluster.cluster_id,
                    'extraction_method': 'llm_assisted',
                    'theme': cluster.theme,
                }
            )

            session.add(concept)
            session.commit()

            logger.info(f"Generated concept: {concept.concept_name} (confidence: {concept.confidence})")
            return concept

        except Exception as e:
            logger.error(f"Error generating concept: {e}")
            session.rollback()
            return None

    def _extract_concept_with_llm(
        self,
        memories: List[Memory],
        cluster: MemoryCluster,
    ) -> Optional[Dict]:
        """
        Use LLM to extract concept from memories.
        
        Returns: Dict with keys: name, description, confidence
        """
        try:
            # Prepare memory summaries
            memory_texts = [
                f"- {m.summary or m.content[:200]}"
                for m in memories[:10]  # Limit to 10 for token budget
            ]

            prompt = f"""Analyze these related memories and extract a semantic concept.

Related Memories:
{chr(10).join(memory_texts)}

Your task:
1. Identify the underlying pattern or theme
2. Generate a canonical concept name (snake_case)
3. Write a clear description
4. Assess confidence (0.0-1.0)

Respond in JSON format:
{{
  "name": "concept_name",
  "description": "Clear description of the generalized concept",
  "confidence": 0.85,
  "pattern": "What pattern ties these memories together?"
}}"""

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert cognitive scientist and knowledge engineer. Extract semantic concepts from memories."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=500,
            )

            # Parse response
            content = response.choices[0].message.content
            
            # Extract JSON from response
            try:
                # Try direct JSON parsing
                result = json.loads(content)
            except json.JSONDecodeError:
                # Try to extract JSON from markdown
                import re
                match = re.search(r'\{.*\}', content, re.DOTALL)
                if match:
                    result = json.loads(match.group())
                else:
                    logger.warning(f"Failed to parse LLM response: {content}")
                    return None

            # Validate result
            if not all(k in result for k in ['name', 'description', 'confidence']):
                logger.warning("Missing required fields in concept extraction")
                return None

            # Ensure valid confidence
            result['confidence'] = max(0.0, min(1.0, float(result['confidence'])))

            return result

        except Exception as e:
            logger.error(f"LLM extraction error: {e}")
            return None

    def generate_multiple_concepts(
        self,
        session: Session,
        user_id: UUID,
        clusters: List[MemoryCluster],
    ) -> List[ConceptMemory]:
        """
        Generate concepts for multiple clusters.
        
        Args:
            session: Database session
            user_id: User ID
            clusters: List of MemoryCluster objects
            
        Returns:
            List of generated ConceptMemory objects
        """
        concepts = []

        for cluster in clusters:
            concept = self.generate_concept_from_cluster(session, user_id, cluster)
            if concept:
                concepts.append(concept)

        logger.info(f"Generated {len(concepts)} concepts")
        return concepts

    def refine_concept(
        self,
        session: Session,
        concept: ConceptMemory,
        new_supporting_memories: List[Memory],
    ) -> Optional[ConceptMemory]:
        """
        Refine existing concept with new supporting evidence.
        
        Increases confidence and updates description if warranted.
        """
        try:
            # Combine old and new supporting memories
            existing_ids = set(UUID(mid) for mid in concept.supporting_memory_ids)
            new_ids = [m.id for m in new_supporting_memories if m.id not in existing_ids]

            if not new_ids:
                return concept

            # Get all memories
            all_memory_ids = list(existing_ids) + new_ids
            all_memories = session.query(Memory).filter(Memory.id.in_(all_memory_ids)).all()

            # Re-extract concept with additional evidence
            refined_info = self._extract_concept_with_llm(all_memories, None)

            if refined_info:
                # Update concept
                concept.description = refined_info['description']
                
                # Increase confidence (capped at 1.0)
                old_conf = concept.confidence
                new_conf = refined_info.get('confidence', 0.85)
                concept.confidence = min(1.0, (old_conf + new_conf) / 2)

                # Update support
                concept.support_count = len(all_memories)
                concept.supporting_memory_ids = [str(m.id) for m in all_memories]
                concept.reinforcement_count += 1

                session.commit()
                logger.info(f"Refined concept {concept.concept_name}: confidence {old_conf:.2f} → {concept.confidence:.2f}")

            return concept

        except Exception as e:
            logger.error(f"Error refining concept: {e}")
            session.rollback()
            return None

    def validate_concept(
        self,
        concept: ConceptMemory,
    ) -> bool:
        """
        Validate that a concept meets quality thresholds.
        """
        checks = [
            concept.confidence >= self.confidence_threshold,
            concept.support_count >= 2,
            len(concept.concept_name) >= 3,
            len(concept.description) >= 20,
        ]

        return all(checks)
