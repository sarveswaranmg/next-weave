"""
Model-Agnostic Memory: LLM Provider Abstraction

Memory must survive model replacement — changing the underlying LLM must
not destroy cognition. Every provider implements the same minimal
interface (`complete`), so `RuntimeOrchestrator` never depends on a
specific vendor's SDK shape. Concrete providers exist for OpenAI and
Anthropic; the generic `OpenAICompatibleProvider` covers vLLM, Ollama,
DeepSeek, Qwen, and Mistral, which all expose an OpenAI-compatible chat
completions endpoint — one adapter, five providers.
"""
import logging
from abc import ABC, abstractmethod
from typing import Dict, Optional

from neurowave_engine.core.config import settings

logger = logging.getLogger(__name__)


class ProviderCredentialError(Exception):
    """
    Raised (by callers, not by `get_provider()` itself) when a tenant's
    explicitly-configured BYOK credential fails to produce a working
    provider. `get_provider()` keeps its existing echo-fallback behavior
    for the "nothing configured at all" case (see
    `test_openai_without_key_falls_back_to_echo`) - a tenant whose stored
    key is invalid/expired needs a clear error instead, which
    `RuntimeOrchestrator.chat()` raises this for when `provider_kwargs`
    was supplied but initialization still silently fell back to echo.
    """
    pass


class LLMProvider(ABC):
    """Common interface every model provider must implement."""

    name: str = "base"

    @abstractmethod
    def complete(self, system_prompt: str, user_message: str, model: Optional[str] = None) -> Dict:
        """
        Returns:
            Dict with `content` (str), `model` (str), `usage`
            ({"prompt_tokens", "completion_tokens", "total_tokens"})
        """
        raise NotImplementedError


class EchoProvider(LLMProvider):
    """
    No-op provider for tests/offline use — echoes back a deterministic
    response without any network call. Also the default fallback when a
    provider can't be initialized (missing key, unknown name), so the
    runtime stays usable without one.
    """

    name = "echo"

    def complete(self, system_prompt: str, user_message: str, model: Optional[str] = None) -> Dict:
        content = f"[echo] {user_message}"
        return {
            "content": content,
            "model": model or "echo-1",
            "usage": {
                "prompt_tokens": len((system_prompt or "").split()) + len(user_message.split()),
                "completion_tokens": len(content.split()),
                "total_tokens": 0,
            },
        }


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.openai_api_key
        if not self.api_key:
            raise ValueError("OpenAI provider requires an api_key")

    def complete(self, system_prompt: str, user_message: str, model: Optional[str] = None) -> Dict:
        from openai import OpenAI
        client = OpenAI(api_key=self.api_key)
        model = model or "gpt-4"
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        )
        choice = response.choices[0]
        usage = response.usage
        return {
            "content": choice.message.content,
            "model": response.model,
            "usage": {
                "prompt_tokens": usage.prompt_tokens if usage else 0,
                "completion_tokens": usage.completion_tokens if usage else 0,
                "total_tokens": usage.total_tokens if usage else 0,
            },
        }


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, api_key: str, base_url: str = "https://api.anthropic.com/v1"):
        if not api_key:
            raise ValueError("Anthropic provider requires an api_key")
        self.api_key = api_key
        self.base_url = base_url

    def complete(self, system_prompt: str, user_message: str, model: Optional[str] = None) -> Dict:
        import httpx
        model = model or "claude-3-5-sonnet-latest"
        response = httpx.post(
            f"{self.base_url}/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model, "max_tokens": 1024, "system": system_prompt,
                "messages": [{"role": "user", "content": user_message}],
            },
            timeout=60.0,
        )
        response.raise_for_status()
        data = response.json()
        content = "".join(block.get("text", "") for block in data.get("content", []))
        usage = data.get("usage", {})
        return {
            "content": content,
            "model": data.get("model", model),
            "usage": {
                "prompt_tokens": usage.get("input_tokens", 0),
                "completion_tokens": usage.get("output_tokens", 0),
                "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
            },
        }


class OpenAICompatibleProvider(LLMProvider):
    """
    Covers vLLM, Ollama, DeepSeek, Qwen, Mistral, and any other backend
    exposing an OpenAI-compatible /chat/completions endpoint — one adapter
    instead of five near-identical ones.
    """

    def __init__(self, base_url: str, api_key: str = "not-needed", provider_name: str = "openai_compatible"):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.name = provider_name

    def complete(self, system_prompt: str, user_message: str, model: Optional[str] = None) -> Dict:
        import httpx
        model = model or "default"
        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
            },
            timeout=120.0,
        )
        response.raise_for_status()
        data = response.json()
        choice = data["choices"][0]
        usage = data.get("usage", {})
        return {
            "content": choice["message"]["content"],
            "model": data.get("model", model),
            "usage": {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            },
        }


# Provider registry: name -> factory. Adding a new model-agnostic backend
# is a new entry here, not a RuntimeOrchestrator change.
_PROVIDER_FACTORIES = {
    "echo": lambda **kw: EchoProvider(),
    "openai": lambda **kw: OpenAIProvider(api_key=kw.get("api_key")),
    "anthropic": lambda **kw: AnthropicProvider(api_key=kw.get("api_key")),
    "google": lambda **kw: OpenAICompatibleProvider(
        base_url=kw.get("base_url", "https://generativelanguage.googleapis.com/v1beta/openai"),
        api_key=kw.get("api_key") or settings.google_api_key or "not-needed", provider_name="google"),
    "mistral": lambda **kw: OpenAICompatibleProvider(
        base_url=kw.get("base_url", "https://api.mistral.ai/v1"),
        api_key=kw.get("api_key", "not-needed"), provider_name="mistral"),
    "deepseek": lambda **kw: OpenAICompatibleProvider(
        base_url=kw.get("base_url", "https://api.deepseek.com/v1"),
        api_key=kw.get("api_key", "not-needed"), provider_name="deepseek"),
    "llama": lambda **kw: OpenAICompatibleProvider(
        base_url=kw.get("base_url", "http://localhost:11434/v1"),
        api_key=kw.get("api_key", "not-needed"), provider_name="llama"),
    "qwen": lambda **kw: OpenAICompatibleProvider(
        base_url=kw.get("base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        api_key=kw.get("api_key", "not-needed"), provider_name="qwen"),
    "vllm": lambda **kw: OpenAICompatibleProvider(
        base_url=kw.get("base_url", "http://localhost:8000/v1"),
        api_key=kw.get("api_key", "not-needed"), provider_name="vllm"),
    "ollama": lambda **kw: OpenAICompatibleProvider(
        base_url=kw.get("base_url", "http://localhost:11434/v1"),
        api_key=kw.get("api_key", "not-needed"), provider_name="ollama"),
}


def get_provider(name: str, **kwargs) -> LLMProvider:
    """
    Get an LLMProvider by name. Falls back to EchoProvider for unknown
    names or when required credentials aren't supplied, so the runtime
    never hard-fails a chat request just because a provider isn't
    configured — it degrades to an echo response instead.
    """
    factory = _PROVIDER_FACTORIES.get((name or "").lower())
    if not factory:
        logger.warning(f"Unknown provider '{name}', falling back to echo")
        return EchoProvider()
    try:
        return factory(**kwargs)
    except Exception as e:
        logger.warning(f"Failed to initialize provider '{name}': {e} - falling back to echo")
        return EchoProvider()
