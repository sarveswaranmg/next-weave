"""
NeuroBench: Cognitive Benchmark Suite

Compares memory strategies on identical evaluation tasks: no memory, raw
chat history, and NeuroWeave's full predictive-recall + context-composition
pipeline. Metrics are computed from real pipeline output wherever possible
(token counts, latency, compression ratio, utility/alignment scores);
metrics that would normally require an LLM judge (reasoning quality,
hallucination rate) are heuristic proxies here, not model-graded scores —
see `DAY10_RUNTIME_PLATFORM.md` for exactly what's measured vs. proxied.

Mem0 and Zep are modeled as pluggable `BenchmarkStrategy` slots (same
interface as every real strategy) but not implemented, since those are
external services not installed in this environment — `MissingStrategy`
records that a comparison was requested rather than fabricating results.
"""
import logging
import time
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from neurowave_engine.db.models import BenchmarkRun, Tenant, User, Memory, MemoryTypeEnum
from neurowave_engine.services.token_budget_optimizer import TokenBudgetOptimizer
from neurowave_engine.services.context_composer import ContextComposer
from neurowave_engine.services.cognitive_scoring import score_memory
from neurowave_engine.services.dataset_generator import DatasetGenerator, SyntheticUser

logger = logging.getLogger(__name__)


class BenchmarkStrategy(ABC):
    """A pluggable memory strategy NeuroBench can evaluate."""

    name: str = "base"

    @abstractmethod
    def build_context(self, session: Session, user_id: UUID, query: str, history: List[str]) -> Dict:
        """Returns a dict with `context_text` (str sent to the LLM) and `estimated_tokens` (int)."""
        raise NotImplementedError


class NoMemoryStrategy(BenchmarkStrategy):
    name = "no_memory"

    def build_context(self, session: Session, user_id: UUID, query: str, history: List[str]) -> Dict:
        return {"context_text": "", "estimated_tokens": 0}


class RawHistoryStrategy(BenchmarkStrategy):
    """The naive baseline every prior day's docs compare against: dump
    the entire raw conversation history into the prompt."""
    name = "raw_history"

    def build_context(self, session: Session, user_id: UUID, query: str, history: List[str]) -> Dict:
        context_text = "\n".join(history)
        return {"context_text": context_text, "estimated_tokens": TokenBudgetOptimizer.estimate_tokens(context_text)}


class NeuroWeaveStrategy(BenchmarkStrategy):
    """NeuroWeave's full Cognitive Context Composer pipeline (Day 6),
    built on Day 5's predictive recall."""
    name = "neuroweave"

    def build_context(self, session: Session, user_id: UUID, query: str, history: List[str]) -> Dict:
        composed = ContextComposer(session).compose(user_id=user_id, query=query)
        return {
            "context_text": composed["final_context"],
            "estimated_tokens": composed["compression"]["compressed_tokens"],
            "quality_score": composed["evaluation"]["quality_score"],
            "identity_alignment": composed["evaluation"]["identity_alignment"],
            "goal_alignment": composed["evaluation"]["goal_alignment"],
        }


class MissingStrategy(BenchmarkStrategy):
    """Placeholder for external services (Mem0, Zep, ...) not installed
    in this environment. Raises rather than fabricating results."""

    def __init__(self, name: str):
        self.name = name

    def build_context(self, session: Session, user_id: UUID, query: str, history: List[str]) -> Dict:
        raise NotImplementedError(f"'{self.name}' is not installed in this environment - see DAY10_RUNTIME_PLATFORM.md")


STRATEGY_REGISTRY: Dict[str, BenchmarkStrategy] = {
    "no_memory": NoMemoryStrategy(),
    "raw_history": RawHistoryStrategy(),
    "neuroweave": NeuroWeaveStrategy(),
    "mem0": MissingStrategy("mem0"),
    "zep": MissingStrategy("zep"),
}


class NeuroBench:
    """Runs comparative benchmarks across memory strategies."""

    def __init__(self, session: Session):
        self.session = session

    def run(
        self, user_id: UUID, query: str, history: Optional[List[str]] = None,
        strategies: Optional[List[str]] = None, dataset: str = "manual",
    ) -> List[BenchmarkRun]:
        """Run one query through each requested strategy and record a
        BenchmarkRun per strategy."""
        strategies = strategies or ["no_memory", "raw_history", "neuroweave"]
        history = history or []

        results = []
        for strategy_name in strategies:
            strategy = STRATEGY_REGISTRY.get(strategy_name)
            if not strategy:
                logger.warning(f"Unknown benchmark strategy '{strategy_name}', skipping")
                continue

            start = time.time()
            try:
                built = strategy.build_context(self.session, user_id, query, history)
            except NotImplementedError as e:
                logger.info(str(e))
                continue
            latency_ms = (time.time() - start) * 1000

            raw_tokens = (
                TokenBudgetOptimizer.estimate_tokens("\n".join(history)) if history else built["estimated_tokens"]
            )
            reduction_percent = (
                max(0.0, (raw_tokens - built["estimated_tokens"]) / raw_tokens * 100) if raw_tokens > 0 else 0.0
            )

            run = BenchmarkRun(
                user_id=user_id, strategy=strategy_name, dataset=dataset,
                latency_ms=latency_ms, token_usage=built["estimated_tokens"],
                prompt_token_reduction_percent=reduction_percent,
                personalization_score=built.get("identity_alignment", 0.0),
                reasoning_score=built.get("quality_score", 0.0),
                compression_ratio=(1 - built["estimated_tokens"] / raw_tokens) if raw_tokens > 0 else 0.0,
                interaction_count=len(history),
                extra_metadata={"context_preview": (built["context_text"] or "")[:500]},
            )
            self.session.add(run)
            results.append(run)

        self.session.commit()
        for r in results:
            self.session.refresh(r)
        return results

    # Well-known tenant for synthetic benchmark data - NeuroBench/the
    # continuous-evaluation pipeline runs independently of any specific
    # real customer, so synthetic users are grouped under one dedicated
    # internal tenant rather than requiring every caller to supply one.
    _BENCHMARK_TENANT_EMAIL = "benchmark@internal.neuroweave"

    def run_dataset(
        self, dataset_name: str = "synthetic", user_count: int = 3, seed: int = 42,
        tenant_id: Optional[UUID] = None,
    ) -> List[BenchmarkRun]:
        """Generate a synthetic dataset and benchmark every strategy
        against every synthetic user's accumulated context — the
        continuous-evaluation entry point (see 'Continuous Evaluation
        Pipeline' in DAY10_RUNTIME_PLATFORM.md)."""
        generator = DatasetGenerator(seed=seed)
        synthetic_users = generator.generate_users(count=user_count)
        effective_tenant_id = tenant_id or self._get_or_create_benchmark_tenant().id

        all_results = []
        for synthetic_user in synthetic_users:
            user = self._materialize_user(synthetic_user, effective_tenant_id)
            history = []
            for turn in synthetic_user.turns:
                history.append(turn.content)
                self._ingest_turn(user.id, turn.content)

            query = synthetic_user.turns[-1].content if synthetic_user.turns else "Help me with my project."
            all_results.extend(self.run(user.id, query, history=history, dataset=dataset_name))

        return all_results

    def _get_or_create_benchmark_tenant(self) -> Tenant:
        tenant = self.session.query(Tenant).filter(Tenant.email == self._BENCHMARK_TENANT_EMAIL).first()
        if not tenant:
            tenant = Tenant(name="NeuroBench synthetic data", email=self._BENCHMARK_TENANT_EMAIL)
            self.session.add(tenant)
            self.session.commit()
            self.session.refresh(tenant)
        return tenant

    def _materialize_user(self, synthetic_user: SyntheticUser, tenant_id: UUID) -> User:
        user = self.session.query(User).filter(User.external_id == synthetic_user.external_id).first()
        if not user:
            user = User(external_id=synthetic_user.external_id, name=synthetic_user.persona, tenant_id=tenant_id)
            self.session.add(user)
            self.session.commit()
            self.session.refresh(user)
        return user

    def _ingest_turn(self, user_id: UUID, content: str) -> None:
        scores = score_memory(content, MemoryTypeEnum.SEMANTIC, use_llm=False)
        memory = Memory(
            user_id=user_id, memory_type=MemoryTypeEnum.SEMANTIC, content=content,
            importance_score=scores.get("importance_score", 0.5),
            reinforcement_score=scores.get("reinforcement_score", 0.5),
            memory_strength=scores.get("memory_strength", 0.5),
            decay_rate=scores.get("decay_rate", 0.05),
        )
        self.session.add(memory)
        self.session.commit()
