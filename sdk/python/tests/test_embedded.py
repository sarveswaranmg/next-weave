"""
Tests for the embedded, zero-server `Memory` entry point.

Uses the `echo` LLM provider (no API key/network call needed for chat) and
monkeypatches `EmbeddingService.embed_text` to a deterministic fake vector
(no real OpenAI call needed for search) - this suite never touches the
network, mirroring how `test_sdk.py` avoids a live server via MockTransport.
"""
import sys
from pathlib import Path

import pytest

# sdk/python (for `neurowave`) and the repo root (for `neurowave_engine`,
# the embedded core `Memory` runs in-process).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from neurowave.embedded import Memory  # noqa: E402
from neurowave_engine.memory.embeddings import embedding_service  # noqa: E402


def _fake_embed_text(text: str):
    # Deterministic, content-sensitive fake vector: same text -> same
    # vector, so cosine similarity in MemoryRetrievalEngine still ranks
    # "relevant" content above unrelated content without a real API call.
    import hashlib

    digest = hashlib.sha256(text.encode()).digest()
    return [b / 255.0 for b in digest[:16]]


@pytest.fixture(autouse=True)
def fake_embeddings(monkeypatch):
    monkeypatch.setattr(embedding_service, "embed_text", _fake_embed_text)


@pytest.fixture
def db_path(tmp_path) -> str:
    return str(tmp_path / "neurowave.db")


class TestMemoryChat:
    def test_chat_returns_response_and_stores_memory(self, db_path):
        m = Memory(db_path=db_path, provider="echo")
        result = m.chat(user_id="alice", message="I'm building a Rust backend for Nexus.")

        assert "Rust backend" in result["response"]
        assert result["memory_stored"] is not None
        assert result["user_id"] == "alice"

    def test_arbitrary_string_user_id_is_stable_across_calls(self, db_path):
        m = Memory(db_path=db_path, provider="echo")
        m.chat(user_id="alice", message="I use FastAPI and PostgreSQL.")
        m.chat(user_id="alice", message="What do I use?")

        results = m.search(query="FastAPI", user_id="alice")
        assert any("FastAPI" in r["content"] for r in results)


class TestMemoryAdd:
    def test_add_stores_content_without_llm_call(self, db_path):
        m = Memory(db_path=db_path, provider="echo")
        stored = m.add(user_id="bob", content="Bob prefers concise answers.")

        assert stored["content"] == "Bob prefers concise answers."
        assert stored["memory_type"] == "episodic"


class TestMemorySearch:
    def test_search_ranks_relevant_content_first(self, db_path):
        m = Memory(db_path=db_path, provider="echo")
        m.add(user_id="carol", content="Carol is building a distributed cache in Rust.")
        m.add(user_id="carol", content="Carol likes hiking on weekends.")

        results = m.search(query="Carol's distributed cache in Rust", user_id="carol")
        assert len(results) == 2
        assert "cache" in results[0]["content"]


class TestMemoryPersistence:
    def test_second_instance_sees_prior_data(self, db_path):
        m1 = Memory(db_path=db_path, provider="echo")
        m1.add(user_id="dave", content="Dave's startup is called Nexus.")

        m2 = Memory(db_path=db_path, provider="echo")
        results = m2.search(query="Nexus", user_id="dave")

        assert any("Nexus" in r["content"] for r in results)


class TestMemoryForgetUser:
    def test_forget_user_deletes_stored_memories(self, db_path):
        m = Memory(db_path=db_path, provider="echo")
        m.add(user_id="erin", content="Erin's favorite language is Go.")

        result = m.forget_user(user_id="erin")
        assert result["deleted_counts"]["memories"] >= 1

        results = m.search(query="Go", user_id="erin")
        assert results == []


class TestMemoryContextManager:
    def test_context_manager_closes_cleanly(self, db_path):
        with Memory(db_path=db_path, provider="echo") as m:
            m.chat(user_id="frank", message="hi")
        # No exception on exit implies close() succeeded


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
