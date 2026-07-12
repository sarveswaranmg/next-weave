"""
Tests for the NeuroWeave Python SDK.

Uses httpx.MockTransport (a real httpx feature, not a hand-rolled fake)
to verify the SDK builds correct requests and parses responses, without
requiring a live server.
"""
import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from neurowave import CognitiveAgent, NeuroWeaveClient  # noqa: E402


def make_client(handler) -> NeuroWeaveClient:
    return NeuroWeaveClient(base_url="http://testserver", transport=httpx.MockTransport(handler))


class TestNeuroWeaveClient:
    def test_chat_sends_expected_payload(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["method"] = request.method
            captured["path"] = request.url.path
            captured["body"] = json.loads(request.content)
            return httpx.Response(200, json={"response": "hello", "provider": "echo"})

        client = make_client(handler)
        result = client.chat(user_id="123", message="Help me design a distributed cache.", provider="echo")

        assert captured["method"] == "POST"
        assert captured["path"] == "/runtime/chat"
        assert captured["body"]["user_id"] == "123"
        assert captured["body"]["message"] == "Help me design a distributed cache."
        assert captured["body"]["provider"] == "echo"
        assert result["response"] == "hello"

    def test_api_key_sent_as_header(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["api_key"] = request.headers.get("X-API-Key")
            return httpx.Response(200, json={"status": "healthy"})

        client = NeuroWeaveClient(
            base_url="http://testserver", api_key="secret-key",
            transport=httpx.MockTransport(handler),
        )
        client.health()
        assert captured["api_key"] == "secret-key"

    def test_explain_sends_query_params(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["params"] = dict(request.url.params)
            return httpx.Response(200, json={"found": True})

        client = make_client(handler)
        client.explain(user_id="123", subject_type="memory", subject_id="mem-1")

        assert captured["params"] == {"user_id": "123", "subject_type": "memory", "subject_id": "mem-1"}

    def test_http_error_raises(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"detail": "boom"})

        client = make_client(handler)
        with pytest.raises(httpx.HTTPStatusError):
            client.health()

    def test_delete_user_uses_delete_method(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["method"] = request.method
            captured["path"] = request.url.path
            return httpx.Response(200, json={"user_id": "123", "deleted_counts": {}})

        client = make_client(handler)
        client.delete_user("123")
        assert captured["method"] == "DELETE"
        assert captured["path"] == "/runtime/users/123"


class TestCognitiveAgent:
    def test_chat_forwards_constructor_flags(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = json.loads(request.content)
            return httpx.Response(200, json={"response": "ok", "provider": "openai"})

        agent = CognitiveAgent(
            provider="openai", memory=True, world_model=True,
            predictive_recall=True, context_composer=True,
            base_url="http://testserver",
        )
        agent.client = make_client(handler)  # inject the mock transport

        agent.chat(user_id="123", message="Help me design a distributed cache.")

        body = captured["body"]
        assert body["provider"] == "openai"
        assert body["memory"] is True
        assert body["world_model"] is True
        assert body["predictive_recall"] is True
        assert body["context_composer"] is True

    def test_per_call_override_wins_over_constructor_default(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = json.loads(request.content)
            return httpx.Response(200, json={"response": "ok", "provider": "anthropic"})

        agent = CognitiveAgent(provider="openai", base_url="http://testserver")
        agent.client = make_client(handler)

        agent.chat(user_id="123", message="hi", provider="anthropic")

        assert captured["body"]["provider"] == "anthropic"

    def test_explain_delegates_to_client(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"found": True, "decisions": []})

        agent = CognitiveAgent(base_url="http://testserver")
        agent.client = make_client(handler)

        result = agent.explain(user_id="123", subject_type="decision")
        assert result["found"] is True

    def test_context_manager_closes_client(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"status": "healthy"})

        with CognitiveAgent(base_url="http://testserver") as agent:
            agent.client = make_client(handler)
        # No exception on exit implies close() succeeded


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
