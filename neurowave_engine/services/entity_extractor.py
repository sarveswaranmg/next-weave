"""
Entity Discovery Engine

Detects real-world entities in conversation/memory text — projects,
companies, technologies, repositories, documents, people, tasks, meetings,
goals — and turns them into World Model Graph nodes. Heuristic (curated
keyword vocabularies + regex capture patterns), consistent with this
codebase's dependency-free approach through Days 5-8; no LLM round trip in
the extraction hot path.
"""
import logging
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy.orm import Session

from neurowave_engine.db.models import WorldEntity, WorldEntityTypeEnum

logger = logging.getLogger(__name__)

# Curated technology/service/device vocabularies. Data, not logic - extend
# freely as new domains matter. Dict value is the canonical display name.
TECHNOLOGY_KEYWORDS: Dict[str, str] = {
    "fastapi": "FastAPI", "postgresql": "PostgreSQL", "postgres": "PostgreSQL",
    "pgvector": "pgvector", "redis": "Redis", "celery": "Celery",
    "python": "Python", "rust": "Rust", "typescript": "TypeScript",
    "javascript": "JavaScript", "react": "React", "vue": "Vue", "angular": "Angular",
    "docker": "Docker", "kubernetes": "Kubernetes", "sqlalchemy": "SQLAlchemy",
    "alembic": "Alembic", "pydantic": "Pydantic", "graphql": "GraphQL",
    "grpc": "gRPC", "kafka": "Kafka", "elasticsearch": "Elasticsearch",
    "mongodb": "MongoDB", "mysql": "MySQL", "sqlite": "SQLite",
    "nginx": "Nginx", "terraform": "Terraform", "openai": "OpenAI",
    "anthropic": "Anthropic", "langchain": "LangChain", "pytorch": "PyTorch",
    "tensorflow": "TensorFlow", "numpy": "NumPy", "networkx": "NetworkX",
    "node.js": "Node.js", "nodejs": "Node.js", "next.js": "Next.js", "django": "Django",
    "flask": "Flask", "golang": "Go", "java": "Java", "c++": "C++", "celery beat": "Celery",
}

SERVICE_KEYWORDS: Dict[str, str] = {
    "aws": "AWS", "gcp": "GCP", "azure": "Azure", "github": "GitHub",
    "gitlab": "GitLab", "vercel": "Vercel", "heroku": "Heroku",
    "cloudflare": "Cloudflare", "stripe": "Stripe", "twilio": "Twilio",
    "datadog": "Datadog", "sentry": "Sentry", "netlify": "Netlify",
}

DEVICE_KEYWORDS: Dict[str, str] = {
    "macbook": "MacBook", "iphone": "iPhone", "linux": "Linux",
    "macos": "macOS", "windows": "Windows", "ubuntu": "Ubuntu",
    "vs code": "VS Code", "vscode": "VS Code", "vim": "Vim", "neovim": "Neovim",
    "pycharm": "PyCharm", "intellij": "IntelliJ", "xcode": "Xcode", "cursor": "Cursor",
}

KEYWORD_VOCABULARIES: List[Tuple[WorldEntityTypeEnum, Dict[str, str]]] = [
    (WorldEntityTypeEnum.TECHNOLOGY, TECHNOLOGY_KEYWORDS),
    (WorldEntityTypeEnum.SERVICE, SERVICE_KEYWORDS),
    (WorldEntityTypeEnum.DEVICE, DEVICE_KEYWORDS),
]

# (entity_type, regex with one-or-more capture groups, base_confidence)
#
# Trigger words are wrapped in inline `(?i:...)` groups rather than relying
# on a blanket re.IGNORECASE flag: IGNORECASE also neutralizes `[A-Z]`
# character classes used here to mean "capitalized word" (proper-noun
# detection), which would otherwise happily capture lowercase filler words
# like "last month" as if they were part of a proper noun.
PATTERN_RULES: List[Tuple[WorldEntityTypeEnum, str, float]] = [
    (WorldEntityTypeEnum.PROJECT,
     r"\b(?i:building|started building|working on|created|creating|launched)\s+"
     r"([A-Z][\w\-]*(?:\s+[A-Z][\w\-]*){0,3})", 0.75),
    # Subject-of-relationship-verb: catches proper nouns that were never
    # introduced with "building/creating" but act as the subject of a
    # relationship (e.g. "NeuroWeave uses PostgreSQL") - the exact shape
    # of the spec's own relationship example. Lower confidence since the
    # signal is weaker than an explicit "building X" statement.
    (WorldEntityTypeEnum.PROJECT,
     r"\b([A-Z][\w\-]{2,30})\s+(?i:uses|stores|depends on|migrates to|"
     r"is built with|builds|runs on|is deployed to)\b", 0.5),
    (WorldEntityTypeEnum.TASK,
     r"\b(?i:i'?ll|i will|need to|todo:?|going to)\s+([a-zA-Z][^.!?\n]{3,60})", 0.5),
    (WorldEntityTypeEnum.MEETING,
     r"\b(?i:meeting|call)\s+(?i:with)\s+([A-Z][\w]*(?:\s+[A-Z][\w]*)?)", 0.6),
    (WorldEntityTypeEnum.PERSON,
     r"\b(?i:with|from)\s+([A-Z][a-z]+\s+[A-Z][a-z]+)\b", 0.35),
    (WorldEntityTypeEnum.REPOSITORY,
     r"\b([\w\-]+/[\w\-]+)\s+(?i:repo(?:sitory)?)\b|\b(?i:repo(?:sitory)?)\s+([\w\-]+/[\w\-]+)", 0.6),
    (WorldEntityTypeEnum.GOAL,
     r"\b(?i:goal is to|planning to|aiming to|my goal:?)\s+([a-zA-Z][^.!?\n]{3,80})", 0.55),
    (WorldEntityTypeEnum.DOCUMENT,
     r"\b([A-Z][\w\-]*\.md|(?i:README)(?:\.md)?)", 0.5),
    (WorldEntityTypeEnum.COMPANY,
     r"\b(?i:at)\s+([A-Z][\w]*(?:\s+[A-Z][\w]*)?)\s+(?i:Inc|Corp|LLC|Ltd)\b", 0.6),
]


class EntityExtractor:
    """Extracts world-model entities from text and persists them as WorldEntity nodes."""

    def __init__(self, session: Session):
        self.session = session

    def extract(
        self, user_id: UUID, text: str, source_memory_id: Optional[UUID] = None
    ) -> List[WorldEntity]:
        """
        Extract entities from text and upsert them as WorldEntity nodes —
        repeated mentions reinforce confidence rather than duplicate.

        Returns:
            List of WorldEntity rows touched by this extraction pass.
        """
        if not text or not text.strip():
            return []

        candidates = self._detect_candidates(text)
        touched = [
            self._upsert(user_id, entity_type, name, confidence, source_memory_id)
            for entity_type, name, confidence in candidates
        ]

        if touched:
            self.session.commit()
        return touched

    def _detect_candidates(self, text: str) -> List[Tuple[WorldEntityTypeEnum, str, float]]:
        candidates: List[Tuple[WorldEntityTypeEnum, str, float]] = []
        seen = set()
        matched_keyword_names = set()  # canonical names already classified via curated vocab
        lowered = text.lower()

        for entity_type, vocab in KEYWORD_VOCABULARIES:
            for keyword, canonical in vocab.items():
                if keyword in lowered:
                    key = (entity_type, canonical.lower())
                    matched_keyword_names.add(canonical.lower())
                    if key not in seen:
                        seen.add(key)
                        candidates.append((entity_type, canonical, 0.8))

        for entity_type, pattern, base_confidence in PATTERN_RULES:
            for match in re.finditer(pattern, text):
                groups = [g for g in match.groups() if g]
                if not groups:
                    continue
                name = groups[0].strip().rstrip(".,;:")
                if not name or len(name) < 2:
                    continue
                if name.lower() in matched_keyword_names:
                    # Already classified via curated vocabulary (e.g. "Redis"
                    # matched as TECHNOLOGY) - don't also relabel it via a
                    # weaker pattern rule (e.g. as the subject of "stores").
                    continue
                key = (entity_type, name.lower())
                if key not in seen:
                    seen.add(key)
                    candidates.append((entity_type, name, base_confidence))

        return candidates

    def _upsert(
        self, user_id: UUID, entity_type: WorldEntityTypeEnum, name: str,
        confidence: float, source_memory_id: Optional[UUID],
    ) -> WorldEntity:
        existing = self.session.query(WorldEntity).filter(
            WorldEntity.user_id == user_id,
            WorldEntity.entity_type == entity_type,
            WorldEntity.entity_name.ilike(name),
        ).first()

        now = datetime.utcnow()
        if existing:
            existing.mention_count = (existing.mention_count or 1) + 1
            existing.confidence = min(1.0, (existing.confidence or 0.5) + 0.05)
            existing.last_seen_at = now
            if source_memory_id and str(source_memory_id) not in (existing.supporting_memory_ids or []):
                existing.supporting_memory_ids = (existing.supporting_memory_ids or []) + [str(source_memory_id)]
            return existing

        entity = WorldEntity(
            user_id=user_id, entity_type=entity_type, entity_name=name,
            confidence=confidence, mention_count=1,
            supporting_memory_ids=[str(source_memory_id)] if source_memory_id else [],
            first_seen_at=now, last_seen_at=now,
        )
        self.session.add(entity)
        self.session.flush()
        return entity
