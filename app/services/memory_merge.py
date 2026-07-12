"""Memory merge service for deduplication and consolidation"""
import logging
from typing import List, Tuple, Optional, Dict
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.db.models import Memory, MemoryCluster, ConceptMemory
from app.memory.embeddings import embedding_service

logger = logging.getLogger(__name__)


class MemoryMergeService:
    """
    Merges and deduplicates similar memories.
    
    Provides:
    - Redundancy detection
    - Memory consolidation
    - Importance-weighted merging
    - Semantic summary generation
    """

    def __init__(self):
        self.embedding_service = embedding_service
        self.similarity_threshold = 0.85

    def identify_redundant_memories(
        self,
        session: Session,
        cluster: MemoryCluster,
    ) -> List[Tuple[UUID, UUID, float]]:
        """
        Identify redundant memory pairs within a cluster.
        
        Args:
            session: Database session
            cluster: MemoryCluster to analyze
            
        Returns:
            List of (memory_id_1, memory_id_2, similarity) tuples
        """
        from sklearn.metrics.pairwise import cosine_similarity
        import numpy as np

        try:
            # Get memories for this cluster
            memory_ids = [UUID(mid) for mid in cluster.memory_ids]
            memories = session.query(Memory).filter(Memory.id.in_(memory_ids)).all()

            if len(memories) < 2:
                return []

            # Get embeddings
            embeddings = []
            valid_memories = []

            for memory in memories:
                try:
                    if memory.embedding:
                        embedding = self._parse_embedding(memory.embedding)
                        embeddings.append(embedding)
                        valid_memories.append(memory)
                except:
                    pass

            if len(embeddings) < 2:
                return []

            # Calculate similarities
            embeddings_array = np.array(embeddings)
            similarity_matrix = cosine_similarity(embeddings_array)

            # Find redundant pairs
            redundant_pairs = []
            n = len(valid_memories)

            for i in range(n):
                for j in range(i + 1, n):
                    similarity = similarity_matrix[i, j]

                    if similarity >= self.similarity_threshold:
                        redundant_pairs.append((
                            valid_memories[i].id,
                            valid_memories[j].id,
                            float(similarity),
                        ))

            logger.info(f"Identified {len(redundant_pairs)} redundant pairs")
            return redundant_pairs

        except Exception as e:
            logger.error(f"Error identifying redundant memories: {e}")
            return []

    def merge_memories(
        self,
        session: Session,
        memory_ids: List[UUID],
    ) -> Optional[Memory]:
        """
        Merge multiple memories into a single consolidated memory.
        
        Args:
            session: Database session
            memory_ids: List of memory IDs to merge
            
        Returns:
            Consolidated Memory object
        """
        if len(memory_ids) < 2:
            return None

        try:
            # Get memories
            memories = session.query(Memory).filter(Memory.id.in_(memory_ids)).all()

            if not memories:
                return None

            # Sort by importance to pick primary memory
            memories.sort(key=lambda m: m.importance_score, reverse=True)
            primary = memories[0]

            # Merge metadata
            merged_metadata = {}
            for memory in memories:
                if memory.extra_metadata:
                    merged_metadata.update(memory.extra_metadata)

            # Update primary memory
            primary.summary = self._generate_merged_summary(memories)
            primary.extra_metadata = merged_metadata
            primary.extra_metadata['merged_from'] = [str(m.id) for m in memories[1:]]
            primary.importance_score = min(1.0, max(m.importance_score for m in memories))
            
            # Update cognitive scores (average)
            primary.future_utility_score = sum(m.future_utility_score for m in memories) / len(memories)
            primary.identity_impact_score = sum(m.identity_impact_score for m in memories) / len(memories)
            primary.emotional_salience_score = sum(m.emotional_salience_score for m in memories) / len(memories)
            primary.reinforcement_score = sum(m.reinforcement_score for m in memories) / len(memories)
            primary.temporal_persistence_score = sum(m.temporal_persistence_score for m in memories) / len(memories)

            # Delete secondary memories
            for memory in memories[1:]:
                session.delete(memory)

            session.commit()
            logger.info(f"Merged {len(memories)} memories into {primary.id}")
            return primary

        except Exception as e:
            logger.error(f"Error merging memories: {e}")
            session.rollback()
            return None

    def consolidate_cluster(
        self,
        session: Session,
        cluster: MemoryCluster,
    ) -> Optional[Memory]:
        """
        Consolidate all memories in a cluster into a single semantic memory.
        
        Args:
            session: Database session
            cluster: MemoryCluster to consolidate
            
        Returns:
            Consolidated Memory object
        """
        try:
            memory_ids = [UUID(mid) for mid in cluster.memory_ids]
            consolidated = self.merge_memories(session, memory_ids)

            if consolidated:
                # Update cluster status
                cluster.consolidation_status = "completed"
                session.commit()

            return consolidated

        except Exception as e:
            logger.error(f"Error consolidating cluster: {e}")
            session.rollback()
            return None

    def _generate_merged_summary(self, memories: List[Memory]) -> str:
        """
        Generate summary for merged memories.
        
        Combines summaries/contents of multiple memories.
        """
        summaries = [m.summary or m.content for m in memories]
        
        # Truncate if too long
        combined = " ".join(summaries)
        if len(combined) > 1000:
            combined = combined[:1000] + "..."

        return combined

    def _parse_embedding(self, embedding_str: str):
        """Parse embedding string to numpy array"""
        import json
        import numpy as np
        
        try:
            data = json.loads(embedding_str)
            return np.array(data)
        except:
            values = [float(x.strip()) for x in embedding_str.strip('[]').split(',')]
            return np.array(values)

    def calculate_merge_confidence(
        self,
        memories: List[Memory],
        similarities: List[float],
    ) -> float:
        """
        Calculate confidence score for merging memories.
        
        Factors:
        - Average similarity
        - Memory importance
        - Thematic consistency
        """
        if not similarities:
            return 0.0

        avg_similarity = sum(similarities) / len(similarities)
        avg_importance = sum(m.importance_score for m in memories) / len(memories)

        # Combined confidence
        confidence = (avg_similarity * 0.7) + (avg_importance * 0.3)

        return min(1.0, max(0.0, confidence))
