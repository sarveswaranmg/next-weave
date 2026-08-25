"""
Plugin Architecture

New cognitive modules (Curiosity Engine, Planning Engine, Reflection
Engine, Emotion Model, Vision Memory, Robotics Memory, Enterprise
Knowledge Modules, ...) can be added without changing the core runtime —
every plugin implements the same small hook interface, and
`RuntimeOrchestrator` (or any caller) invokes them through the registry
rather than importing them directly.
"""
import logging
from abc import ABC
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class CognitivePlugin(ABC):
    """Common interface every cognitive module must implement to plug
    into the runtime without the runtime knowing about it in advance."""

    name: str = "base_plugin"
    version: str = "0.1.0"
    description: str = ""

    def on_message(self, user_id: str, message: str, context: Dict) -> Optional[Dict]:
        """Called before the LLM completion. Return a dict to surface in
        the response, or None to no-op."""
        return None

    def on_memory_created(self, user_id: str, memory_id: str, content: str) -> Optional[Dict]:
        """Called after a new memory is stored."""
        return None

    def on_response(self, user_id: str, response: str) -> Optional[Dict]:
        """Called after the LLM responds."""
        return None

    def describe(self) -> Dict:
        return {"name": self.name, "version": self.version, "description": self.description}


class PluginRegistry:
    """Registers and invokes cognitive plugins."""

    def __init__(self):
        self._plugins: Dict[str, CognitivePlugin] = {}

    def register(self, plugin: CognitivePlugin) -> None:
        self._plugins[plugin.name] = plugin
        logger.info(f"Registered plugin: {plugin.name} v{plugin.version}")

    def unregister(self, name: str) -> bool:
        return self._plugins.pop(name, None) is not None

    def get(self, name: str) -> Optional[CognitivePlugin]:
        return self._plugins.get(name)

    def list(self) -> List[Dict]:
        return [p.describe() for p in self._plugins.values()]

    def invoke_on_message(self, user_id: str, message: str, context: Dict) -> List[Dict]:
        results = []
        for plugin in self._plugins.values():
            try:
                result = plugin.on_message(user_id, message, context)
                if result:
                    results.append({"plugin": plugin.name, "result": result})
            except Exception as e:
                logger.error(f"Plugin '{plugin.name}' on_message failed: {e}")
        return results

    def invoke_on_memory_created(self, user_id: str, memory_id: str, content: str) -> List[Dict]:
        results = []
        for plugin in self._plugins.values():
            try:
                result = plugin.on_memory_created(user_id, memory_id, content)
                if result:
                    results.append({"plugin": plugin.name, "result": result})
            except Exception as e:
                logger.error(f"Plugin '{plugin.name}' on_memory_created failed: {e}")
        return results


class CuriosityPlugin(CognitivePlugin):
    """
    Reference plugin implementation: flags open-ended questions in the
    user's message as candidates for future exploration. Proves the
    plugin interface works end-to-end; a real curiosity engine (see Day 8's
    "Future Extensibility" note) would replace this with genuine
    hypothesis generation without changing the interface it plugs into.
    """

    name = "curiosity"
    version = "0.1.0"
    description = "Flags open-ended questions as candidates for future exploration"

    def on_message(self, user_id: str, message: str, context: Dict) -> Optional[Dict]:
        if "?" in message and len(message.split()) > 4:
            return {"flagged_question": message.strip()}
        return None


# Default registry - the runtime's own reference plugins register here at
# import time; callers can also construct their own PluginRegistry.
default_registry = PluginRegistry()
default_registry.register(CuriosityPlugin())
