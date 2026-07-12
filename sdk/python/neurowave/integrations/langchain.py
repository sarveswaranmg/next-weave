"""
LangChain Integration (flagship framework adapter)

Implements LangChain's memory-provider interface shape so NeuroWeave can
replace an existing LangChain memory module with minimal configuration.
Duck-typed against LangChain's documented interface
(`load_memory_variables`, `save_context`, `clear`, `memory_variables`)
rather than importing `langchain` directly, so this file has no hard
dependency on the langchain package being installed — if a project has
langchain installed, this class satisfies `BaseMemory`'s contract; if
not, it's still a fully usable object with the same three methods.

Other frameworks named in the Day 10 spec (LlamaIndex, CrewAI, AutoGen,
OpenAI Agents SDK, Haystack, Semantic Kernel) follow the same adapter
pattern — wrap `NeuroWeaveClient` behind that framework's memory/tool
interface — and are documented, not yet implemented; see
`DAY10_RUNTIME_PLATFORM.md`'s "Framework Integrations" section for the
concrete shape each one would take.
"""
from typing import Any, Dict, List, Optional

from ..client import NeuroWeaveClient


class NeuroWeaveMemory:
    """
    Drop-in replacement for a LangChain memory module.

    Usage (with langchain installed)::

        from neurowave.integrations.langchain import NeuroWeaveMemory
        memory = NeuroWeaveMemory(user_id="123", base_url="http://localhost:8000")
        chain = ConversationChain(llm=llm, memory=memory)
    """

    def __init__(
        self,
        user_id: str,
        base_url: str = "http://localhost:8000",
        api_key: Optional[str] = None,
        memory_key: str = "history",
    ):
        self.user_id = user_id
        self.memory_key = memory_key
        self.client = NeuroWeaveClient(base_url=base_url, api_key=api_key)

    @property
    def memory_variables(self) -> List[str]:
        return [self.memory_key]

    def load_memory_variables(self, inputs: Dict[str, Any]) -> Dict[str, str]:
        """Called by LangChain before each LLM call - returns NeuroWeave's
        composed cognitive context in place of raw chat history."""
        query = inputs.get("input") or next(iter(inputs.values()), "")
        result = self.client.compose_context(self.user_id, str(query))
        return {self.memory_key: result.get("final_context", "")}

    def save_context(self, inputs: Dict[str, Any], outputs: Dict[str, Any]) -> None:
        """Called by LangChain after each LLM call - stores the turn as memory."""
        user_message = inputs.get("input") or next(iter(inputs.values()), "")
        ai_message = outputs.get("output") or next(iter(outputs.values()), "")
        conversation = f"User: {user_message}\nAssistant: {ai_message}"
        self.client.ingest_memory(self.user_id, conversation)

    def clear(self) -> None:
        """LangChain's memory-reset hook. NeuroWeave memories are durable
        by design (soft-forgotten, never hard-deleted per-turn) - clear()
        is intentionally a no-op here; use `NeuroWeaveClient.delete_user`
        for actual erasure (GDPR/CCPA right to be forgotten)."""
        pass
