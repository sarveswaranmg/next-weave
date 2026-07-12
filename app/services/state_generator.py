"""
Cognitive State Generator

Generates the internal state describing what the LLM should know before
reasoning — a synthesized profile (goal, expertise, communication style,
reasoning strategy), not a bag of retrieved facts.
"""
import logging
from typing import Dict, List

from app.db.models import MemoryTypeEnum
from app.services.context_compression import CompressedMemory

logger = logging.getLogger(__name__)

GOAL_REASONING_STRATEGY: Dict[str, str] = {
    "system_design": "Emphasize trade-offs, scalability, and architectural clarity.",
    "interview_preparation": "Focus on interview-oriented explanations that demonstrate depth quickly.",
    "debugging": "Focus on root-cause analysis and precise, actionable fixes.",
    "learning": "Build understanding incrementally, connecting new concepts to what the user already knows.",
    "career_planning": "Ground advice in the user's demonstrated goals and track record.",
    "startup_ideation": "Encourage creative, opportunity-focused thinking grounded in the user's technical strengths.",
    "research": "Present balanced trade-offs and cite the reasoning behind conclusions.",
    "code_review": "Be direct about issues while explaining the reasoning behind each suggestion.",
    "optimization": "Quantify trade-offs and prioritize the highest-impact change first.",
    "purchase_decision": "Weigh cost against the user's stated priorities.",
    "summarization": "Prioritize brevity and the most decision-relevant points.",
    "general_assistance": "Provide clear, directly useful reasoning toward the user's goal.",
}


class StateGenerator:
    """Synthesizes the compact 'Current User State' block."""

    def generate(
        self,
        goal: str,
        identity_traits: List[Dict],
        memories: List[CompressedMemory],
    ) -> Dict:
        """
        Args:
            goal: Detected goal string
            identity_traits: From ContextAnalyzer.analyze()
            memories: Post-compression CompressedMemory list

        Returns:
            Dict with primary_goal, relevant_expertise, preferred_communication,
            reasoning_strategy, and a formatted `text` block.
        """
        expertise = self._extract_expertise(identity_traits, memories)
        communication = self._extract_communication(identity_traits, memories)
        reasoning_strategy = GOAL_REASONING_STRATEGY.get(goal, GOAL_REASONING_STRATEGY["general_assistance"])

        state = {
            "primary_goal": self._humanize(goal),
            "relevant_expertise": expertise,
            "preferred_communication": communication,
            "reasoning_strategy": reasoning_strategy,
        }
        state["text"] = self._format(state)
        return state

    def _extract_expertise(self, identity_traits: List[Dict], memories: List[CompressedMemory]) -> List[str]:
        items: List[str] = []
        for trait in identity_traits:
            if trait.get("type") in ("interest", "skill") and trait.get("confidence", 0) >= 0.4:
                items.append(trait["value"].replace("_", " ").title())
        for m in memories:
            if m.memory_type in (MemoryTypeEnum.CONCEPT, MemoryTypeEnum.SEMANTIC):
                label = self._shorten(m.content)
                if label:
                    items.append(label)
        return self._dedup(items)[:6]

    def _extract_communication(self, identity_traits: List[Dict], memories: List[CompressedMemory]) -> List[str]:
        items: List[str] = []
        for trait in identity_traits:
            if trait.get("type") == "communication" and trait.get("confidence", 0) >= 0.3:
                items.append(trait["value"].replace("_", " ").title())
        for m in memories:
            if m.memory_type == MemoryTypeEnum.PROCEDURAL:
                label = self._shorten(m.content)
                if label:
                    items.append(label)
        deduped = self._dedup(items)[:4]
        return deduped if deduped else ["Standard"]

    @staticmethod
    def _dedup(items: List[str]) -> List[str]:
        seen: List[str] = []
        for item in items:
            if item and item not in seen:
                seen.append(item)
        return seen

    @staticmethod
    def _shorten(content: str, max_words: int = 6) -> str:
        words = (content or "").strip().split()
        short = " ".join(words[:max_words])
        return (short[0].upper() + short[1:]) if short else ""

    @staticmethod
    def _humanize(goal: str) -> str:
        return goal.replace("_", " ").capitalize() if goal else "General assistance"

    @staticmethod
    def _format(state: Dict) -> str:
        lines = ["Current User State", "", "Primary Goal", state["primary_goal"], ""]

        if state["relevant_expertise"]:
            lines.append("Relevant Expertise")
            lines.extend(state["relevant_expertise"])
            lines.append("")

        if state["preferred_communication"]:
            lines.append("Preferred Communication")
            lines.extend(state["preferred_communication"])
            lines.append("")

        lines.append("Reasoning Strategy")
        lines.append(state["reasoning_strategy"])

        return "\n".join(lines).strip()


# Singleton instance
state_generator = StateGenerator()
