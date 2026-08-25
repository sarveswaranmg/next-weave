"""
Contradiction Healing Engine (ConsistencyEngine)

Detects and resolves contradictions, outdated beliefs, conflicting
preferences, and duplicate identity traits — automatically, without ever
overwriting history. Memory-level conflict detection and resolution is
delegated to Day 7's `ObsoleteMemoryDetector` (durable, store-mutating);
this engine adds the identity-graph-level counterpart: duplicate
`IdentityNode`s (e.g. "backend_engineering" and "backend engineer" recorded
as two separate nodes) get merged, keeping the stronger one and softly
retiring the rest.
"""
import logging
import re
from typing import Dict, List
from uuid import UUID

from sqlalchemy.orm import Session

from neurowave_engine.db.models import Memory, IdentityNode, CognitiveMemoryStateEnum
from neurowave_engine.services.obsolete_memory_detector import ObsoleteMemoryDetector
from neurowave_engine.services.context_analyzer import STOPWORDS

logger = logging.getLogger(__name__)

# Short identity labels ("backend_engineering" vs "backend engineer") often
# share only their core word once a near-synonym ("engineering" vs
# "engineer") is counted as a literal mismatch (no stemming here) - 0.6
# would miss exactly this case, so the bar is calibrated against it rather
# than an arbitrary "looks strict enough" number.
DUPLICATE_IDENTITY_SIMILARITY_THRESHOLD = 0.5


class ConsistencyEngine:
    """Heals contradictions across memories and the identity graph."""

    def __init__(self, session: Session):
        self.session = session
        self.obsolete_detector = ObsoleteMemoryDetector(session)

    def heal(self, user_id: UUID) -> Dict:
        """Run one full consistency pass: memory conflicts + duplicate identities."""
        memory_decisions = self._heal_memory_conflicts(user_id)
        identity_decisions = self._heal_duplicate_identities(user_id)
        return {
            "memory_conflicts_resolved": memory_decisions,
            "duplicate_identities_merged": identity_decisions,
        }

    def _heal_memory_conflicts(self, user_id: UUID) -> List[Dict]:
        memories = self.session.query(Memory).filter(
            Memory.user_id == user_id,
            Memory.cognitive_state.notin_([CognitiveMemoryStateEnum.ARCHIVED, CognitiveMemoryStateEnum.FORGOTTEN]),
        ).all()
        return self.obsolete_detector.detect_and_resolve(user_id, memories)

    def _heal_duplicate_identities(self, user_id: UUID) -> List[Dict]:
        """Merge IdentityNodes that describe the same trait in different
        wording (same node_type, near-identical node_value)."""
        nodes = self.session.query(IdentityNode).filter(IdentityNode.user_id == user_id).all()
        nodes = [n for n in nodes if not (n.extra_metadata or {}).get("retired")]

        by_type: Dict[str, List[IdentityNode]] = {}
        for node in nodes:
            by_type.setdefault(node.node_type, []).append(node)

        decisions = []
        for node_type, group in by_type.items():
            clusters: List[List[IdentityNode]] = []
            cluster_words: List[set] = []
            for node in group:
                words = set(re.findall(r"\w+", (node.node_value or "").replace("_", " ").lower())) - STOPWORDS
                placed = False
                for idx, cwords in enumerate(cluster_words):
                    if not words or not cwords:
                        continue
                    overlap = len(words & cwords) / max(1, min(len(words), len(cwords)))
                    if overlap >= DUPLICATE_IDENTITY_SIMILARITY_THRESHOLD:
                        clusters[idx].append(node)
                        cluster_words[idx] |= words
                        placed = True
                        break
                if not placed:
                    clusters.append([node])
                    cluster_words.append(words)

            for cluster in clusters:
                if len(cluster) < 2:
                    continue
                decisions.append(self._merge_identity_cluster(node_type, cluster))

        if decisions:
            self.session.commit()
        return decisions

    def _merge_identity_cluster(self, node_type: str, cluster: List[IdentityNode]) -> Dict:
        primary = max(cluster, key=lambda n: (n.confidence or 0) * (n.importance or 0))
        others = [n for n in cluster if n.id != primary.id]

        primary.evidence_count = (primary.evidence_count or 1) + sum((o.evidence_count or 1) for o in others)
        primary.supporting_memory_ids = list(set(
            (primary.supporting_memory_ids or []) + sum([(o.supporting_memory_ids or []) for o in others], [])
        ))
        primary.confidence = min(1.0, (primary.confidence or 0.5) + 0.05 * len(others))

        for other in others:
            other.extra_metadata = {**(other.extra_metadata or {}), "duplicate_of": str(primary.id), "retired": True}
            other.confidence = max(0.0, (other.confidence or 0.5) * 0.3)

        return {
            "node_type": node_type,
            "primary_node_id": primary.id,
            "primary_value": primary.node_value,
            "merged_node_ids": [o.id for o in others],
            "merged_values": [o.node_value for o in others],
        }
