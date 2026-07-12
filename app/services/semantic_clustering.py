"""Semantic clustering service for grouping similar memories"""
import logging
import numpy as np
from typing import List, Tuple, Dict, Optional
from uuid import UUID
from sqlalchemy.orm import Session
from sklearn.metrics.pairwise import cosine_similarity
from hdbscan import HDBSCAN

from app.db.models import Memory, MemoryCluster, ConceptMemory
from app.memory.embeddings import embedding_service

logger = logging.getLogger(__name__)


class SemanticClusterService:
    """
    Groups similar memories using HDBSCAN clustering.
    
    Provides:
    - Embedding-based similarity analysis
    - Hierarchical density-based clustering
    - Cluster theme identification
    - Pattern detection for concept extraction
    """

    def __init__(self):
        self.embedding_service = embedding_service
        self.min_cluster_size = 3  # Minimum memories per cluster
        self.min_samples = 2  # Sensitivity to noise
        self.similarity_threshold = 0.75  # For merging small clusters

    def cluster_memories(
        self,
        session: Session,
        user_id: UUID,
        memories: List[Memory],
        min_similarity: float = 0.75,
    ) -> List[MemoryCluster]:
        """
        Cluster memories using HDBSCAN algorithm.
        
        Args:
            session: Database session
            user_id: User ID
            memories: List of memories to cluster
            min_similarity: Minimum similarity threshold
            
        Returns:
            List of MemoryCluster objects
        """
        if len(memories) < self.min_cluster_size:
            logger.info(f"Insufficient memories for clustering: {len(memories)}")
            return []

        try:
            # Generate embeddings for memories
            embeddings = self._get_embeddings(memories)
            
            if embeddings is None or len(embeddings) < self.min_cluster_size:
                logger.warning("Insufficient embeddings for clustering")
                return []

            # Compute similarity matrix
            similarity_matrix = cosine_similarity(embeddings)

            # Convert similarity to distance for HDBSCAN
            distance_matrix = 1 - similarity_matrix

            # Run HDBSCAN clustering
            clusterer = HDBSCAN(
                min_cluster_size=self.min_cluster_size,
                min_samples=self.min_samples,
                metric='precomputed',
                allow_single_cluster=True,
            )
            labels = clusterer.fit_predict(distance_matrix)

            # Create cluster objects
            clusters = self._create_clusters(
                session=session,
                user_id=user_id,
                memories=memories,
                embeddings=embeddings,
                labels=labels,
                similarity_matrix=similarity_matrix,
            )

            logger.info(f"Created {len(clusters)} clusters for user {user_id}")
            return clusters

        except Exception as e:
            logger.error(f"Clustering error: {e}")
            raise

    def _get_embeddings(self, memories: List[Memory]) -> Optional[np.ndarray]:
        """Extract embeddings from memories"""
        embeddings = []
        
        for memory in memories:
            if memory.embedding:
                # Parse stored embedding
                try:
                    embedding = self._parse_embedding(memory.embedding)
                    embeddings.append(embedding)
                except Exception as e:
                    logger.warning(f"Failed to parse embedding: {e}")
                    # Generate new embedding
                    content = memory.summary or memory.content
                    embedding = self.embedding_service.embed_text(content)
                    embeddings.append(embedding)
            else:
                # Generate embedding if not present
                content = memory.summary or memory.content
                embedding = self.embedding_service.embed_text(content)
                embeddings.append(embedding)

        return np.array(embeddings) if embeddings else None

    def _parse_embedding(self, embedding_str: str) -> np.ndarray:
        """Parse embedding string to numpy array"""
        import json
        # Try to parse as JSON
        try:
            data = json.loads(embedding_str)
            return np.array(data)
        except:
            # Fallback: split by comma
            values = [float(x.strip()) for x in embedding_str.strip('[]').split(',')]
            return np.array(values)

    def _create_clusters(
        self,
        session: Session,
        user_id: UUID,
        memories: List[Memory],
        embeddings: np.ndarray,
        labels: np.ndarray,
        similarity_matrix: np.ndarray,
    ) -> List[MemoryCluster]:
        """Create MemoryCluster objects from clustering results"""
        clusters = []
        
        # Group memories by cluster label
        unique_labels = set(labels)
        
        for cluster_label in unique_labels:
            # Get indices for this cluster
            indices = np.where(labels == cluster_label)[0]
            
            if len(indices) < 2:  # Skip noise points
                continue

            cluster_memories = [memories[i] for i in indices]
            cluster_embeddings = embeddings[indices]
            
            # Calculate metrics
            avg_similarity = self._calculate_avg_similarity(
                similarity_matrix[np.ix_(indices, indices)]
            )
            
            # Generate cluster centroid
            centroid = np.mean(cluster_embeddings, axis=0)
            centroid_str = str(centroid.tolist())
            
            # Create MemoryCluster
            cluster = MemoryCluster(
                user_id=user_id,
                cluster_id=f"cluster_{cluster_label}_{len(clusters)}",
                theme=None,  # Will be set by concept generator
                memory_ids=[str(m.id) for m in cluster_memories],
                member_count=len(cluster_memories),
                avg_similarity=float(avg_similarity),
                confidence=float(avg_similarity),  # Use similarity as confidence
                centroid_embedding=centroid_str,
                consolidation_status="pending",
            )
            
            session.add(cluster)
            clusters.append(cluster)
        
        session.commit()
        return clusters

    def _calculate_avg_similarity(self, similarity_submatrix: np.ndarray) -> float:
        """Calculate average pairwise similarity in cluster"""
        if similarity_submatrix.shape[0] < 2:
            return 0.0

        # Get upper triangle (excluding diagonal)
        upper_triangle = np.triu_indices(similarity_submatrix.shape[0], k=1)
        similarities = similarity_submatrix[upper_triangle]

        if len(similarities) == 0:
            return 0.0

        # cosine_similarity ranges [-1, 1]; clamp to [0, 1] since this value is
        # also used directly as a cluster confidence score
        return max(0.0, float(np.mean(similarities)))

    def merge_similar_clusters(
        self,
        session: Session,
        clusters: List[MemoryCluster],
        similarity_threshold: float = 0.85,
    ) -> List[MemoryCluster]:
        """
        Merge clusters that are too similar.
        
        Reduces fragmentation by combining highly similar clusters.
        """
        if len(clusters) < 2:
            return clusters

        try:
            # Build cluster centroids
            centroids = []
            for cluster in clusters:
                try:
                    centroid = self._parse_embedding(cluster.centroid_embedding)
                    centroids.append(centroid)
                except:
                    centroids.append(None)

            # Find similar cluster pairs
            merged_clusters = clusters.copy()
            merged_indices = set()

            for i, centroid_i in enumerate(centroids):
                if i in merged_indices or centroid_i is None:
                    continue

                for j in range(i + 1, len(centroids)):
                    if j in merged_indices or centroids[j] is None:
                        continue

                    # Calculate similarity
                    similarity = cosine_similarity(
                        [centroid_i],
                        [centroids[j]]
                    )[0, 0]

                    if similarity >= similarity_threshold:
                        # Merge cluster j into cluster i
                        clusters[i].memory_ids.extend(clusters[j].memory_ids)
                        clusters[i].member_count += clusters[j].member_count
                        clusters[i].confidence = max(
                            clusters[i].confidence,
                            clusters[j].confidence
                        )
                        session.delete(clusters[j])
                        merged_indices.add(j)

            if merged_indices:
                session.commit()
                merged_clusters = [c for i, c in enumerate(clusters) if i not in merged_indices]
                logger.info(f"Merged {len(merged_indices)} similar clusters")

            return merged_clusters

        except Exception as e:
            logger.error(f"Error merging clusters: {e}")
            return clusters
