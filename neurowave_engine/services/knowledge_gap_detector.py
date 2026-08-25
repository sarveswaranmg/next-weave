"""
Missing Knowledge Detector

After assembling context, a human recognizes what they *don't* know before
reasoning — "I know Redis and scaling, but not how consistency models or
replication work here." NeuroWeave should do the same: detect the subtopics
a query's domain implies that aren't backed by any retained memory, so a
future retrieval/RAG pass can be triggered *only when actually needed*
instead of always over-fetching.
"""
import logging
import re
from typing import Dict, List

from neurowave_engine.db.models import Memory

logger = logging.getLogger(__name__)


# Maps a trigger pattern found in the query to the subtopics a competent
# answer in that domain would be expected to touch. Extend freely — this is
# data, not logic, so new domains don't require pipeline changes.
TOPIC_EXPECTATIONS: List[tuple] = [
    (re.compile(r"\bcach(e|ing)\b", re.IGNORECASE),
     ["consistency", "replication", "partition tolerance", "cap theorem", "eviction policy", "ttl"]),
    (re.compile(r"\bdistributed system(s)?\b|\bdistributed\b", re.IGNORECASE),
     ["consistency", "replication", "partition tolerance", "cap theorem", "consensus"]),
    (re.compile(r"\bdatabase(s)?\b|\bdb\b", re.IGNORECASE),
     ["indexing", "normalization", "sharding", "replication", "acid"]),
    (re.compile(r"\binterview(s|ing)?\b", re.IGNORECASE),
     ["data structures", "algorithms", "system design", "behavioral questions"]),
    (re.compile(r"\bownership\b|\brust\b", re.IGNORECASE),
     ["ownership", "borrowing", "lifetimes", "traits", "memory safety"]),
    (re.compile(r"\bmicroservices?\b", re.IGNORECASE),
     ["service discovery", "api gateway", "circuit breaker", "observability"]),
    (re.compile(r"\bauth(entication|orization)?\b", re.IGNORECASE),
     ["oauth", "jwt", "session management", "rbac"]),
    (re.compile(r"\bqueue(s|ing)?\b|\bmessag(e|ing) (broker|queue)\b", re.IGNORECASE),
     ["delivery guarantees", "ordering", "backpressure", "dead letter queue"]),
    (re.compile(r"\bload balanc\w*\b", re.IGNORECASE),
     ["health checks", "routing algorithms", "sticky sessions"]),
]

MAX_MISSING_TOPICS = 5


class KnowledgeGapDetector:
    """Detects subtopics implied by the query/goal that aren't in memory."""

    def __init__(self, topic_expectations: List[tuple] = None):
        self.topic_expectations = topic_expectations or TOPIC_EXPECTATIONS

    def detect(self, query: str, memories: List[Memory]) -> Dict:
        """
        Args:
            query: The user's query text
            memories: The memories retained for context (post-compression
                ideally, so gaps reflect what will *actually* be sent)

        Returns:
            Dict with `missing_topics`, `triggered_topics`, `covered_topics`
        """
        triggered: List[str] = []
        for pattern, topics in self.topic_expectations:
            if pattern.search(query):
                for topic in topics:
                    if topic not in triggered:
                        triggered.append(topic)

        if not triggered:
            return {"missing_topics": [], "triggered_topics": [], "covered_topics": []}

        combined_text = " ".join((m.content or "") + " " + (m.summary or "") for m in memories).lower()

        covered = [topic for topic in triggered if self._is_covered(topic, combined_text)]
        missing = [topic for topic in triggered if topic not in covered]

        return {
            "missing_topics": [t.title() for t in missing[:MAX_MISSING_TOPICS]],
            "triggered_topics": [t.title() for t in triggered],
            "covered_topics": [t.title() for t in covered],
        }

    @staticmethod
    def _is_covered(topic: str, combined_text: str) -> bool:
        if topic in combined_text:
            return True
        # Multi-word topics count as covered if all significant words appear
        # (handles "cap theorem" being phrased differently across memories)
        words = [w for w in topic.split() if len(w) > 3]
        return bool(words) and all(w in combined_text for w in words)


# Singleton instance
knowledge_gap_detector = KnowledgeGapDetector()
