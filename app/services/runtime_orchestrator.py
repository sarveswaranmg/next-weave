"""
Runtime Orchestrator

Implements the full Cognitive Runtime Pipeline for one chat turn:

    User Message -> Memory Ingestion -> Importance Scoring -> World Model
    Update -> Predictive Recall -> Context Composition -> LLM -> Response
    Ingestion -> (Memory Evolution / Offline Consolidation scheduled, async)

Only the stages that must happen before the LLM call run synchronously;
expensive batch stages (semantic consolidation, memory evolution, dream
mode) are scheduled via the existing Celery tasks from Days 3/7/8 rather
than run inline, so a chat turn's latency never depends on them
completing — a live request must never wait on offline consolidation.
"""
import logging
import time
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import Memory, MemoryTypeEnum, User
from app.core.config import settings
from app.services.cognitive_scoring import score_memory
from app.services.context_composer import ContextComposer
from app.services.predictive_recall_pipeline import PredictiveRecallPipeline
from app.services.world_model_pipeline import WorldModelPipeline
from app.services.llm_providers import get_provider

logger = logging.getLogger(__name__)


class RuntimeOrchestrator:
    """Runs one full cognitive runtime chat turn — the engine behind
    `CognitiveAgent.chat()` in the SDK and `POST /runtime/chat`."""

    def __init__(self, session: Session):
        self.session = session

    def chat(
        self,
        user_id: UUID,
        message: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        memory: bool = True,
        world_model: bool = True,
        predictive_recall: bool = True,
        context_composer: bool = True,
        token_budget: Optional[int] = None,
        schedule_background: bool = True,
    ) -> Dict:
        """Run one chat turn through the full cognitive pipeline."""
        start = time.time()
        stage_latency: Dict[str, float] = {}
        provider_name = provider or settings.runtime_default_provider
        model_name = model or settings.runtime_default_model
        token_budget = token_budget or settings.runtime_default_token_budget

        self._ensure_user(user_id)

        stored_memory = None
        if memory:
            t0 = time.time()
            stored_memory = self._ingest(user_id, message)
            stage_latency["memory_ingestion"] = (time.time() - t0) * 1000

        world_result = None
        if world_model:
            t0 = time.time()
            world_result = WorldModelPipeline(self.session).update(
                user_id, message, source_memory_id=stored_memory.id if stored_memory else None,
            )
            stage_latency["world_model_update"] = (time.time() - t0) * 1000

        system_prompt = "You are a helpful, thoughtful assistant."
        context_summary = None
        if context_composer:
            t0 = time.time()
            composed = ContextComposer(self.session).compose(user_id=user_id, query=message, token_budget=token_budget)
            system_prompt = composed["final_context"] or system_prompt
            context_summary = {
                "narrative": composed["narrative"],
                "estimated_tokens": composed["compression"]["compressed_tokens"],
                "compression_ratio": composed["compression"]["compression_ratio"],
            }
            stage_latency["context_composition"] = (time.time() - t0) * 1000
        elif predictive_recall:
            t0 = time.time()
            recalled = PredictiveRecallPipeline(self.session).run(user_id=user_id, query=message, token_budget=token_budget)
            system_prompt = recalled["assembled_context"]["context_text"] or system_prompt
            context_summary = {
                "narrative": None,
                "estimated_tokens": recalled["assembled_context"]["estimated_tokens"],
                "compression_ratio": None,
            }
            stage_latency["predictive_recall"] = (time.time() - t0) * 1000

        t0 = time.time()
        llm_provider = get_provider(provider_name)
        completion = llm_provider.complete(system_prompt, message, model=model_name)
        stage_latency["llm_completion"] = (time.time() - t0) * 1000

        if memory:
            t0 = time.time()
            self._ingest(user_id, completion["content"], memory_type=MemoryTypeEnum.PROCEDURAL)
            stage_latency["response_ingestion"] = (time.time() - t0) * 1000

        background_scheduled = self._schedule_background(user_id) if schedule_background else []

        total_latency_ms = (time.time() - start) * 1000

        return {
            "user_id": user_id,
            "response": completion["content"],
            "provider": llm_provider.name,
            "model": completion["model"],
            "usage": completion["usage"],
            "memory_stored": stored_memory.id if stored_memory else None,
            "world_model": {
                "entities_extracted": world_result["entities_extracted"],
                "relationships_built": world_result["relationships_built"],
                "projects_touched": world_result["projects_touched"],
            } if world_result else None,
            "context": context_summary,
            "background_scheduled": background_scheduled,
            "stage_latency_ms": stage_latency,
            "total_latency_ms": total_latency_ms,
        }

    def _ensure_user(self, user_id: UUID) -> User:
        user = self.session.query(User).filter(User.id == user_id).first()
        if not user:
            user = User(id=user_id, external_id=str(user_id))
            self.session.add(user)
            self.session.commit()
        return user

    def _ingest(
        self, user_id: UUID, content: str, memory_type: MemoryTypeEnum = MemoryTypeEnum.EPISODIC
    ) -> Memory:
        """
        Lightweight, heuristic-scored direct storage — not the full
        LLM-based multi-memory extraction pipeline (`POST /memory/ingest`
        / `MemoryExtractionService`). A chat turn's latency shouldn't
        depend on an LLM extraction call; richer batch extraction remains
        available separately for callers who want it.
        """
        scores = score_memory(content, memory_type, use_llm=False)
        memory = Memory(
            user_id=user_id, memory_type=memory_type, content=content,
            importance_score=scores.get("importance_score", 0.5),
            future_utility_score=scores.get("future_utility_score", 0.5),
            identity_impact_score=scores.get("identity_impact_score", 0.5),
            emotional_salience_score=scores.get("emotional_salience_score", 0.5),
            reinforcement_score=scores.get("reinforcement_score", 0.5),
            temporal_persistence_score=scores.get("temporal_persistence_score", 0.5),
            memory_strength=scores.get("memory_strength", 0.5),
            decay_rate=scores.get("decay_rate", 0.05),
        )
        self.session.add(memory)
        self.session.commit()
        self.session.refresh(memory)
        return memory

    def _schedule_background(self, user_id: UUID) -> List[str]:
        """Schedule the expensive batch stages (semantic consolidation,
        memory evolution) via Celery rather than running them inline.
        Failures here (e.g. no broker configured) never fail the chat
        request itself — background scheduling is best-effort."""
        scheduled = []
        try:
            from app.workers.tasks import consolidate_user_memories_task
            consolidate_user_memories_task.delay(str(user_id))
            scheduled.append("semantic_consolidation")
        except Exception as e:
            logger.debug(f"Could not schedule consolidation: {e}")

        try:
            from app.workers.tasks import enforce_memory_retention_policy
            enforce_memory_retention_policy.delay(str(user_id))
            scheduled.append("memory_evolution")
        except Exception as e:
            logger.debug(f"Could not schedule memory evolution: {e}")

        return scheduled
