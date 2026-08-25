"""Tests for the Day 10 Cognitive Runtime Platform"""
import pytest
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from neurowave_engine.db.database import Base
from neurowave_engine.db.models import User, Memory, MemoryTypeEnum, IdentityNode, DreamSession, ArchitecturalDecision
from neurowave_engine.services.llm_providers import get_provider, EchoProvider, LLMProvider
from neurowave_engine.services.runtime_orchestrator import RuntimeOrchestrator
from neurowave_engine.services.explainability_engine import ExplainabilityEngine
from neurowave_engine.services.plugin_system import PluginRegistry, CognitivePlugin, CuriosityPlugin, default_registry
from neurowave_engine.services.dataset_generator import DatasetGenerator
from neurowave_engine.services.benchmark_suite import NeuroBench, STRATEGY_REGISTRY
from neurowave_engine.services.runtime_metrics_service import RuntimeMetricsService
from neurowave_engine.services.data_deletion_service import DataDeletionService


class TestLLMProviders:
    """Model-agnostic memory: every provider implements the same interface"""

    def test_echo_provider_completes_without_network(self):
        provider = get_provider("echo")
        result = provider.complete("system", "hello world")
        assert result["content"] == "[echo] hello world"
        assert "prompt_tokens" in result["usage"]

    def test_unknown_provider_falls_back_to_echo(self):
        provider = get_provider("totally-unknown-vendor")
        assert isinstance(provider, EchoProvider)

    def test_openai_without_key_falls_back_to_echo(self, monkeypatch):
        # Isolate from the test environment's global OPENAI_API_KEY (set
        # for unrelated reasons since Day 5) to actually exercise "no key
        # configured anywhere" rather than "key came from settings".
        monkeypatch.setattr("neurowave_engine.services.llm_providers.settings.openai_api_key", "")
        provider = get_provider("openai", api_key=None)
        assert isinstance(provider, EchoProvider)

    def test_all_documented_providers_resolve_to_a_provider(self):
        for name in ["openai", "anthropic", "google", "mistral", "deepseek", "llama", "qwen", "vllm", "ollama"]:
            provider = get_provider(name, api_key=None)
            assert isinstance(provider, LLMProvider)


class TestRuntimeOrchestrator:
    """The full cognitive runtime chat pipeline"""

    def test_chat_runs_full_pipeline_and_stores_memory(self, session, user):
        orchestrator = RuntimeOrchestrator(session)
        result = orchestrator.chat(
            user_id=user.id, tenant_id=user.tenant_id, message="Help me design a distributed cache.",
            provider="echo", schedule_background=False,
        )

        assert result["response"] == "[echo] Help me design a distributed cache."
        assert result["provider"] == "echo"
        assert result["memory_stored"] is not None
        assert result["total_latency_ms"] > 0

        memories = session.query(Memory).filter(Memory.user_id == user.id).all()
        # user message + assistant response both stored
        assert len(memories) == 2

    def test_chat_creates_user_if_missing(self, session, tenant):
        new_user_id = uuid4()
        orchestrator = RuntimeOrchestrator(session)
        result = orchestrator.chat(
            user_id=new_user_id, tenant_id=tenant.id, message="Hello", provider="echo", schedule_background=False,
        )
        assert result["user_id"] == new_user_id
        assert session.query(User).filter(User.id == new_user_id).first() is not None

    def test_chat_rejects_user_id_owned_by_another_tenant(self, session, user, tenant):
        from neurowave_engine.db.models import Tenant
        from fastapi import HTTPException
        other_tenant = Tenant(name="Other Tenant", email="other@example.com")
        session.add(other_tenant)
        session.commit()

        orchestrator = RuntimeOrchestrator(session)
        with pytest.raises(HTTPException) as exc_info:
            orchestrator.chat(
                user_id=user.id, tenant_id=other_tenant.id, message="Hello",
                provider="echo", schedule_background=False,
            )
        assert exc_info.value.status_code == 403

    def test_chat_without_memory_stores_nothing(self, session, user):
        orchestrator = RuntimeOrchestrator(session)
        orchestrator.chat(
            user_id=user.id, tenant_id=user.tenant_id, message="Hello",
            provider="echo", memory=False, schedule_background=False,
        )
        assert session.query(Memory).filter(Memory.user_id == user.id).count() == 0

    def test_background_scheduling_never_fails_the_chat(self, session, user):
        """No Celery broker is running in tests - scheduling must degrade
        gracefully, not raise."""
        orchestrator = RuntimeOrchestrator(session)
        result = orchestrator.chat(
            user_id=user.id, tenant_id=user.tenant_id, message="Hello",
            provider="echo", schedule_background=True,
        )
        assert result["response"] is not None


class TestExplainabilityEngine:
    """Every decision NeuroWeave makes should be explainable"""

    def test_explain_memory_includes_lifecycle(self, session, user):
        memory = Memory(
            user_id=user.id, memory_type=MemoryTypeEnum.SEMANTIC, content="User likes concise answers",
            importance_score=0.8, utility_score=0.9, selection_reason="Matches communication profile",
        )
        session.add(memory)
        session.commit()

        engine = ExplainabilityEngine(session)
        result = engine.explain(user.id, "memory", memory.id)

        assert result["found"] is True
        assert result["selection_reason"] == "Matches communication profile"

    def test_explain_unknown_subject_type(self, session, user):
        engine = ExplainabilityEngine(session)
        result = engine.explain(user.id, "nonsense")
        assert result["found"] is False

    def test_explain_identity_returns_empty_list_when_no_shifts(self, session, user):
        engine = ExplainabilityEngine(session)
        result = engine.explain(user.id, "identity")
        assert result["found"] is True
        assert result["events"] == []


class TestPluginSystem:
    """New cognitive modules plug in without changing the core runtime"""

    def test_default_registry_has_curiosity_plugin(self):
        names = [p["name"] for p in default_registry.list()]
        assert "curiosity" in names

    def test_custom_registry_invokes_registered_plugins(self):
        registry = PluginRegistry()
        registry.register(CuriosityPlugin())

        results = registry.invoke_on_message("user-1", "What should I build next for this project?", {})
        assert len(results) == 1
        assert results[0]["plugin"] == "curiosity"

    def test_plugin_failure_does_not_break_others(self):
        class BrokenPlugin(CognitivePlugin):
            name = "broken"

            def on_message(self, user_id, message, context):
                raise RuntimeError("boom")

        registry = PluginRegistry()
        registry.register(BrokenPlugin())
        registry.register(CuriosityPlugin())

        results = registry.invoke_on_message("user-1", "What should I build next for this project?", {})
        assert len(results) == 1  # broken plugin's failure didn't stop curiosity from running

    def test_unregister_removes_plugin(self):
        registry = PluginRegistry()
        registry.register(CuriosityPlugin())
        assert registry.unregister("curiosity") is True
        assert registry.get("curiosity") is None


class TestDatasetGenerator:
    """Deterministic synthetic datasets for regression testing"""

    def test_deterministic_with_same_seed(self):
        gen_a = DatasetGenerator(seed=7)
        gen_b = DatasetGenerator(seed=7)
        users_a = gen_a.generate_users(count=3)
        users_b = gen_b.generate_users(count=3)

        contents_a = [t.content for u in users_a for t in u.turns]
        contents_b = [t.content for u in users_b for t in u.turns]
        assert contents_a == contents_b

    def test_users_include_contradictions_and_identity_shifts(self):
        gen = DatasetGenerator(seed=1)
        users = gen.generate_users(count=2)
        for u in users:
            contents = " ".join(t.content for t in u.turns).lower()
            assert "prefers" in contents
            assert len(u.turns) > 5

    def test_long_conversation_has_requested_length(self):
        gen = DatasetGenerator(seed=1)
        turns = gen.generate_long_conversation("stress-test", length=25)
        assert len(turns) == 25


class TestNeuroBench:
    """Compares memory strategies on identical evaluation tasks"""

    def test_run_compares_strategies(self, session, user):
        bench = NeuroBench(session)
        history = ["User likes Rust", "User works on distributed systems"]
        runs = bench.run(user.id, "Help me design a system", history=history, strategies=["no_memory", "raw_history"])

        strategies = {r.strategy for r in runs}
        assert strategies == {"no_memory", "raw_history"}

        no_memory_run = next(r for r in runs if r.strategy == "no_memory")
        raw_history_run = next(r for r in runs if r.strategy == "raw_history")
        assert no_memory_run.token_usage == 0
        assert raw_history_run.token_usage > 0

    def test_missing_strategy_is_skipped_not_faked(self, session, user):
        bench = NeuroBench(session)
        runs = bench.run(user.id, "test query", strategies=["mem0"])
        assert runs == []  # not implemented, not fabricated

    def test_run_dataset_generates_and_benchmarks(self, session):
        bench = NeuroBench(session)
        runs = bench.run_dataset(dataset_name="test-dataset", user_count=1, seed=99)
        assert len(runs) > 0
        assert all(r.dataset == "test-dataset" for r in runs)


class TestRuntimeMetricsService:
    """Point-in-time rollup of the runtime's scale and health"""

    def test_compute_counts_memories(self, session, user):
        session.add(Memory(user_id=user.id, memory_type=MemoryTypeEnum.SEMANTIC, content="test", importance_score=0.5, memory_strength=0.5))
        session.commit()

        metrics = RuntimeMetricsService(session).compute(user_id=user.id)
        assert metrics["memory_count"] == 1

    def test_compute_persists_a_row_by_default(self, session, user):
        from neurowave_engine.db.models import RuntimeMetrics
        RuntimeMetricsService(session).compute(user_id=user.id)
        assert session.query(RuntimeMetrics).filter(RuntimeMetrics.user_id == user.id).count() == 1

    def test_compute_can_skip_persistence(self, session, user):
        from neurowave_engine.db.models import RuntimeMetrics
        RuntimeMetricsService(session).compute(user_id=user.id, persist=False)
        assert session.query(RuntimeMetrics).filter(RuntimeMetrics.user_id == user.id).count() == 0


class TestDataDeletionService:
    """GDPR 'right to be forgotten' - permanent, cross-table deletion"""

    def test_delete_user_removes_all_data(self, session, user):
        session.add(Memory(user_id=user.id, memory_type=MemoryTypeEnum.SEMANTIC, content="secret", importance_score=0.5, memory_strength=0.5))
        session.add(IdentityNode(user_id=user.id, node_type="interest", node_value="rust", confidence=0.7, importance=0.5))
        session.add(ArchitecturalDecision(user_id=user.id, decision="Use Postgres", reason="reliability"))
        session.commit()

        service = DataDeletionService(session)
        counts = service.delete_user(user.id)

        assert counts["memories"] == 1
        assert counts["identity_nodes"] == 1
        assert counts["architectural_decisions"] == 1
        assert counts["users"] == 1
        assert session.query(User).filter(User.id == user.id).first() is None
        assert session.query(Memory).filter(Memory.user_id == user.id).count() == 0

    def test_delete_nonexistent_user_is_safe(self, session):
        service = DataDeletionService(session)
        counts = service.delete_user(uuid4())
        assert counts["users"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
