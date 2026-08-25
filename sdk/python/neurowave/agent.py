"""
CognitiveAgent — the five-minute integration surface.

    from neurowave import CognitiveAgent

    agent = CognitiveAgent(
        provider="google",
        memory=True,
        world_model=True,
        predictive_recall=True,
        context_composer=True,
    )

    response = agent.chat(
        user_id="123",
        message="Help me design a distributed cache.",
    )
"""
from typing import Any, Dict, Optional

from .client import NeuroWeaveClient


class CognitiveAgent:
    """High-level cognitive agent wrapping the NeuroWeave Runtime API."""

    def __init__(
        self,
        provider: str = "google",
        model: Optional[str] = None,
        memory: bool = True,
        world_model: bool = True,
        predictive_recall: bool = True,
        context_composer: bool = True,
        base_url: str = "http://localhost:8000",
        api_key: Optional[str] = None,
        token_budget: Optional[int] = None,
    ):
        self.provider = provider
        self.model = model
        self.memory = memory
        self.world_model = world_model
        self.predictive_recall = predictive_recall
        self.context_composer = context_composer
        self.token_budget = token_budget
        self.client = NeuroWeaveClient(base_url=base_url, api_key=api_key)

    def chat(self, user_id: str, message: str, **overrides: Any) -> Dict[str, Any]:
        """Send one message through the full cognitive pipeline and get a response."""
        return self.client.chat(
            user_id=user_id,
            message=message,
            provider=overrides.pop("provider", self.provider),
            model=overrides.pop("model", self.model),
            memory=overrides.pop("memory", self.memory),
            world_model=overrides.pop("world_model", self.world_model),
            predictive_recall=overrides.pop("predictive_recall", self.predictive_recall),
            context_composer=overrides.pop("context_composer", self.context_composer),
            token_budget=overrides.pop("token_budget", self.token_budget),
            **overrides,
        )

    def explain(self, user_id: str, subject_type: str, subject_id: Optional[str] = None) -> Dict[str, Any]:
        """Ask why NeuroWeave made a specific cognitive decision."""
        return self.client.explain(user_id, subject_type, subject_id)

    def metrics(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """Current memory/concept/identity/world-graph scale and health."""
        return self.client.metrics(user_id)

    def world_model_snapshot(self, user_id: str) -> Dict[str, Any]:
        return self.client.get_world_model(user_id)

    def forget_user(self, user_id: str) -> Dict[str, Any]:
        """GDPR/CCPA right-to-be-forgotten: permanently delete all of this user's data."""
        return self.client.delete_user(user_id)

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "CognitiveAgent":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
