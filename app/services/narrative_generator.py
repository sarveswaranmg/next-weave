"""
Cognitive Narrative Generator

Current systems send fragments:

    Interest: AI
    Goal: Startup
    Preference: Technical

NeuroWeave sends a coherent narrative instead — the form an LLM reasons
over far better than a bullet-fragment dump. Template-based (no LLM round
trip in the hot path), built entirely from the structured state produced
by StateGenerator so it stays consistent with what's actually in context.
"""
import logging
from typing import Dict, List

logger = logging.getLogger(__name__)


class NarrativeGenerator:
    """Turns a structured cognitive state into one coherent paragraph."""

    def generate(self, state: Dict) -> str:
        expertise = state.get("relevant_expertise", [])
        communication = state.get("preferred_communication", [])
        goal = state.get("primary_goal", "")
        strategy = state.get("reasoning_strategy", "")

        sentences: List[str] = []

        if expertise:
            expertise_phrase = self._join(expertise[:3])
            focus = goal.lower() if goal else "their current task"
            sentences.append(
                f"The user has a background in {expertise_phrase} and is currently focused on {focus}."
            )
        elif goal:
            sentences.append(f"The user is currently focused on {goal.lower()}.")

        if communication:
            comm_phrase = self._join([c.lower() for c in communication[:3]])
            sentences.append(f"They prefer {comm_phrase} explanations.")

        if strategy:
            sentences.append(strategy)

        return " ".join(sentences) if sentences else "No prior context is available for this user."

    @staticmethod
    def _join(items: List[str]) -> str:
        items = [i for i in items if i]
        if not items:
            return ""
        if len(items) == 1:
            return items[0]
        return ", ".join(items[:-1]) + f" and {items[-1]}"


# Singleton instance
narrative_generator = NarrativeGenerator()
