"""Semantic consolidation pipeline orchestrator"""
import logging
import time
from typing import Optional, Dict, List
from uuid import UUID, uuid4
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import select, and_

from neurowave_engine.db.database import get_db_session
from neurowave_engine.db.models import (
    Memory, MemoryCluster, ConceptMemory, ConceptRelationship,
    ConsolidationMetrics, CognitiveMemoryStateEnum, MemoryTypeEnum
)
from neurowave_engine.services.semantic_clustering import SemanticClusterService
from neurowave_engine.services.memory_merge import MemoryMergeService
from neurowave_engine.services.concept_generator import ConceptGenerator
from neurowave_engine.services.concept_graph import ConceptGraph

logger = logging.getLogger(__name__)


class ConsolidationWorker:
    """
    Background worker for semantic memory consolidation.
    
    Pipeline:
    1. Fetch candidate memories
    2. Generate embeddings
    3. Cluster similar memories (HDBSCAN)
    4. Identify redundant memories
    5. Extract concepts from clusters (LLM)
    6. Build concept graph
    7. Update retrieval priorities
    8. Record metrics
    """

    def __init__(self):
        self.clustering_service = SemanticClusterService()
        self.merge_service = MemoryMergeService()
        self.concept_generator = ConceptGenerator()
        self.concept_graph = ConceptGraph()
        
        # Consolidation thresholds
        self.min_memories_for_cluster = 3
        self.min_similarity_for_cluster = 0.75
        self.min_concept_confidence = 0.70
        self.min_memory_importance = 0.6

    def consolidate_user_memories(
        self,
        user_id: UUID,
        force: bool = False,
    ) -> Optional[ConsolidationMetrics]:
        """
        Run complete consolidation pipeline for a user.
        
        Args:
            user_id: User ID to consolidate
            force: Force consolidation even if recent run exists
            
        Returns:
            ConsolidationMetrics from this run
        """
        session = get_db_session()
        run_id = str(uuid4())
        start_time = time.time()

        try:
            logger.info(f"Starting consolidation for user {user_id} (run: {run_id})")

            # Step 1: Fetch candidate memories
            candidates = self._fetch_candidate_memories(session, user_id)
            
            if len(candidates) < self.min_memories_for_cluster:
                logger.info(f"Insufficient memories for consolidation: {len(candidates)}")
                return None

            logger.info(f"Found {len(candidates)} candidate memories")

            # Step 2: Cluster memories
            clusters = self._cluster_memories(session, user_id, candidates)
            
            if not clusters:
                logger.info("No clusters formed")
                return None

            logger.info(f"Formed {len(clusters)} clusters")

            # Step 3: Identify and merge redundant memories
            self._merge_redundant_memories(session, clusters)

            # Step 4: Generate concepts from clusters
            concepts = self._generate_concepts_from_clusters(session, user_id, clusters)
            logger.info(f"Generated {len(concepts)} concepts")

            # Step 5: Build semantic graph
            self._build_concept_graph(session, user_id, concepts)

            # Step 6: Update memory states
            self._update_memory_states(session, user_id, concepts)

            # Step 7: Record metrics
            elapsed = time.time() - start_time
            metrics = self._record_consolidation_metrics(
                session, user_id, run_id, candidates, clusters, concepts, elapsed
            )

            logger.info(f"Consolidation complete: {len(concepts)} concepts from {len(candidates)} memories in {elapsed:.2f}s")
            return metrics

        except Exception as e:
            logger.error(f"Consolidation error: {e}")
            session.rollback()
            return None
        finally:
            session.close()

    def _fetch_candidate_memories(
        self,
        session: Session,
        user_id: UUID,
    ) -> List[Memory]:
        """
        Fetch memories eligible for consolidation.
        
        Criteria:
        - Memory type: episodic or semantic
        - State: active or reinforced
        - Importance: > threshold
        """
        try:
            query = session.query(Memory).filter(
                and_(
                    Memory.user_id == user_id,
                    Memory.memory_type.in_([MemoryTypeEnum.EPISODIC, MemoryTypeEnum.SEMANTIC]),
                    Memory.cognitive_state.in_([
                        CognitiveMemoryStateEnum.ACTIVE,
                        CognitiveMemoryStateEnum.REINFORCED,
                        CognitiveMemoryStateEnum.SEMANTIC_CANDIDATE,
                    ]),
                    Memory.importance_score >= self.min_memory_importance,
                )
            ).order_by(Memory.created_at.desc()).limit(1000)

            memories = query.all()
            logger.info(f"Fetched {len(memories)} candidate memories for consolidation")
            return memories

        except Exception as e:
            logger.error(f"Error fetching candidates: {e}")
            return []

    def _cluster_memories(
        self,
        session: Session,
        user_id: UUID,
        memories: List[Memory],
    ) -> List[MemoryCluster]:
        """Run clustering on memories"""
        try:
            clusters = self.clustering_service.cluster_memories(
                session=session,
                user_id=user_id,
                memories=memories,
                min_similarity=self.min_similarity_for_cluster,
            )

            # Merge similar clusters
            clusters = self.clustering_service.merge_similar_clusters(
                session=session,
                clusters=clusters,
                similarity_threshold=0.85,
            )

            return clusters

        except Exception as e:
            logger.error(f"Clustering error: {e}")
            return []

    def _merge_redundant_memories(
        self,
        session: Session,
        clusters: List[MemoryCluster],
    ) -> int:
        """Identify and merge redundant memories in clusters"""
        merged_count = 0

        for cluster in clusters:
            try:
                # Identify redundant pairs
                redundant_pairs = self.merge_service.identify_redundant_memories(session, cluster)

                if not redundant_pairs:
                    continue

                # For each redundant group, merge them
                merged_groups = self._group_redundant_pairs(redundant_pairs)

                for group in merged_groups:
                    self.merge_service.merge_memories(session, group)
                    merged_count += 1

            except Exception as e:
                logger.error(f"Error merging redundant memories: {e}")

        logger.info(f"Merged {merged_count} redundant memory groups")
        return merged_count

    def _group_redundant_pairs(
        self,
        pairs: List[tuple],
    ) -> List[List[UUID]]:
        """
        Group redundant memory pairs into transitive groups.
        
        If A~B and B~C, group as [A,B,C]
        """
        # Build adjacency
        adjacency = {}
        for id1, id2, _ in pairs:
            if id1 not in adjacency:
                adjacency[id1] = []
            if id2 not in adjacency:
                adjacency[id2] = []
            adjacency[id1].append(id2)
            adjacency[id2].append(id1)

        # Find connected components
        visited = set()
        groups = []

        for node in adjacency:
            if node in visited:
                continue

            group = []
            stack = [node]

            while stack:
                current = stack.pop()
                if current in visited:
                    continue

                visited.add(current)
                group.append(current)

                for neighbor in adjacency[current]:
                    if neighbor not in visited:
                        stack.append(neighbor)

            if len(group) > 1:
                groups.append(group)

        return groups

    def _generate_concepts_from_clusters(
        self,
        session: Session,
        user_id: UUID,
        clusters: List[MemoryCluster],
    ) -> List[ConceptMemory]:
        """Extract concepts from clusters"""
        concepts = []

        for cluster in clusters:
            try:
                concept = self.concept_generator.generate_concept_from_cluster(
                    session=session,
                    user_id=user_id,
                    cluster=cluster,
                )

                if concept and self.concept_generator.validate_concept(concept):
                    concepts.append(concept)
                    cluster.concept_generated = str(concept.id)
                    session.commit()

            except Exception as e:
                logger.error(f"Error generating concept from cluster: {e}")

        return concepts

    def _build_concept_graph(
        self,
        session: Session,
        user_id: UUID,
        concepts: List[ConceptMemory],
    ) -> None:
        """Build semantic graph between concepts"""
        try:
            # Build graph
            self.concept_graph.build_graph_for_user(session, user_id)

            # Find relationships between concepts
            for i, concept1 in enumerate(concepts):
                for concept2 in concepts[i+1:]:
                    # Check similarity
                    similarity = self._compute_concept_similarity(concept1, concept2)

                    if similarity > 0.75:
                        # Add relationship
                        self.concept_graph.add_relationship(
                            session=session,
                            user_id=user_id,
                            source_concept_id=concept1.id,
                            target_concept_id=concept2.id,
                            relationship_type='related_to',
                            strength=float(similarity),
                        )

            logger.info("Built concept graph")

        except Exception as e:
            logger.error(f"Error building concept graph: {e}")

    def _compute_concept_similarity(
        self,
        concept1: ConceptMemory,
        concept2: ConceptMemory,
    ) -> float:
        """Compute similarity between two concepts"""
        try:
            from sklearn.metrics.pairwise import cosine_similarity
            import numpy as np

            if not concept1.embedding or not concept2.embedding:
                return 0.0

            emb1 = self._parse_embedding(concept1.embedding)
            emb2 = self._parse_embedding(concept2.embedding)

            similarity = cosine_similarity([emb1], [emb2])[0, 0]
            return float(similarity)

        except Exception as e:
            logger.error(f"Error computing concept similarity: {e}")
            return 0.0

    def _parse_embedding(self, embedding_str: str):
        """Parse embedding string"""
        import json
        import numpy as np

        try:
            data = json.loads(embedding_str)
            return np.array(data)
        except:
            values = [float(x.strip()) for x in embedding_str.strip('[]').split(',')]
            return np.array(values)

    def _update_memory_states(
        self,
        session: Session,
        user_id: UUID,
        concepts: List[ConceptMemory],
    ) -> None:
        """Update memory states after consolidation"""
        try:
            # Get all supporting memories
            supporting_ids = set()
            for concept in concepts:
                supporting_ids.update(UUID(mid) for mid in concept.supporting_memory_ids)

            # Mark supporting memories as consolidated
            supporting_memories = session.query(Memory).filter(
                Memory.id.in_(list(supporting_ids))
            ).all()

            for memory in supporting_memories:
                memory.cognitive_state = CognitiveMemoryStateEnum.SEMANTIC_CANDIDATE

            session.commit()
            logger.info(f"Updated state for {len(supporting_memories)} memories")

        except Exception as e:
            logger.error(f"Error updating memory states: {e}")

    def _record_consolidation_metrics(
        self,
        session: Session,
        user_id: UUID,
        run_id: str,
        candidates: List[Memory],
        clusters: List[MemoryCluster],
        concepts: List[ConceptMemory],
        elapsed: float,
    ) -> ConsolidationMetrics:
        """Record consolidation metrics"""
        try:
            # Count memory types
            memory_types = {}
            for memory in candidates:
                mtype = memory.memory_type.value
                memory_types[mtype] = memory_types.get(mtype, 0) + 1

            # Calculate metrics
            compression_ratio = len(candidates) / len(concepts) if concepts else 0.0
            memory_reduction = (1 - len(concepts) / len(candidates)) * 100 if candidates else 0.0

            # Estimate token reduction (rough)
            avg_tokens_per_memory = 150
            avg_tokens_per_concept = 200  # Concepts are more dense
            token_reduction = (len(candidates) * avg_tokens_per_memory - 
                             len(concepts) * avg_tokens_per_concept)

            # Graph metrics
            graph_stats = self.concept_graph.get_graph_statistics()

            metrics = ConsolidationMetrics(
                user_id=user_id,
                consolidation_run_id=run_id,
                consolidation_timestamp=datetime.utcnow(),
                total_memories=len(candidates),
                episodic_memories=memory_types.get('episodic', 0),
                semantic_memories=memory_types.get('semantic', 0),
                identity_memories=memory_types.get('identity', 0),
                procedural_memories=memory_types.get('procedural', 0),
                cluster_count=len(clusters),
                avg_cluster_size=len(candidates) / len(clusters) if clusters else 0.0,
                concept_count=len(concepts),
                new_concepts_created=len(concepts),
                total_relationships=graph_stats.get('edge_count', 0),
                avg_concept_degree=2 * graph_stats.get('edge_count', 0) / max(len(concepts), 1),
                memory_reduction_percentage=float(memory_reduction),
                compression_ratio=float(compression_ratio),
                token_reduction=int(token_reduction),
                processing_time_ms=elapsed * 1000,
                avg_concept_confidence=sum(c.confidence for c in concepts) / len(concepts) if concepts else 0.0,
            )

            session.add(metrics)
            session.commit()

            logger.info(f"Recorded metrics: compression_ratio={compression_ratio:.2f}, "
                       f"memory_reduction={memory_reduction:.1f}%")

            return metrics

        except Exception as e:
            logger.error(f"Error recording metrics: {e}")
            return None
