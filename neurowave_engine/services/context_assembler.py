"""
Context Assembly Engine

Merges the utility-ranked, token-budgeted memory set into one compact
reasoning context for LLM injection — identity, semantic concepts,
procedural preferences, and (only when nothing else is available) episodic
evidence. Raw chat history never appears; only structured, distilled
memories do.
"""
import logging
from typing import Dict, List, Tuple
from uuid import UUID

from neurowave_engine.db.models import Memory, MemoryTypeEnum
from neurowave_engine.services.token_budget_optimizer import TokenBudgetOptimizer

logger = logging.getLogger(__name__)


class ContextAssembler:
    """Assembles selected memories into a single compact context block."""

    def assemble(
        self,
        query: str,
        goal: str,
        selected: List[Dict],
        memory_by_id: Dict[UUID, Memory],
        token_limit: int = None,
    ) -> Dict:
        """
        Assemble selected memories into a structured, compact context.

        Args:
            query: Original user query
            goal: Detected goal string
            selected: Ranked/budgeted score dicts from PredictiveMemoryRanker
            memory_by_id: memory_id -> Memory ORM object
            token_limit: Optional hard cap; trims context_text if exceeded

        Returns:
            Dict with context_text, estimated_tokens, sections
        """
        by_type: Dict[MemoryTypeEnum, List[Tuple[Memory, Dict]]] = {mt: [] for mt in MemoryTypeEnum}
        for score in selected:
            memory = memory_by_id.get(score["memory_id"])
            if memory:
                by_type[memory.memory_type].append((memory, score))

        # Preserve utility rank ordering within each section
        for mt in by_type:
            by_type[mt].sort(key=lambda pair: pair[1]["utility_score"], reverse=True)

        identity_items = [self._text(m) for m, _ in by_type[MemoryTypeEnum.IDENTITY]]
        procedural_items = [self._text(m) for m, _ in by_type[MemoryTypeEnum.PROCEDURAL]]
        concept_items = [self._text(m) for m, _ in by_type[MemoryTypeEnum.CONCEPT]]
        semantic_items = [self._text(m) for m, _ in by_type[MemoryTypeEnum.SEMANTIC]]
        combined_concepts = concept_items + semantic_items
        episodic_items = [self._text(m) for m, _ in by_type[MemoryTypeEnum.EPISODIC]]

        # Episodic (raw event) evidence only appears when it's all we have —
        # per spec, no raw history unless absolutely necessary.
        include_episodic = bool(episodic_items) and not (identity_items or procedural_items or combined_concepts)

        lines: List[str] = ["User Profile", ""]

        lines.append("Current Goal:")
        lines.append(self._humanize(goal))
        lines.append("")

        if identity_items:
            lines.append("Relevant Interests & Identity:")
            lines.extend(f"- {item}" for item in identity_items)
            lines.append("")

        if procedural_items:
            lines.append("Communication Style:")
            lines.extend(f"- {item}" for item in procedural_items)
            lines.append("")

        if combined_concepts:
            lines.append("Relevant Concepts:")
            lines.extend(f"- {item}" for item in combined_concepts)
            lines.append("")

        if include_episodic:
            lines.append("Supporting Evidence:")
            lines.extend(f"- {item}" for item in episodic_items)
            lines.append("")

        context_text = "\n".join(lines).strip()
        estimated_tokens = TokenBudgetOptimizer.estimate_tokens(context_text)

        if token_limit and estimated_tokens > token_limit:
            context_text = self._trim_to_budget(context_text, token_limit)
            estimated_tokens = TokenBudgetOptimizer.estimate_tokens(context_text)

        sections = {
            "current_goal": [self._humanize(goal)],
            "identity": identity_items,
            "communication_style": procedural_items,
            "concepts": combined_concepts,
            "episodic_evidence": episodic_items if include_episodic else [],
        }

        return {
            "context_text": context_text,
            "estimated_tokens": estimated_tokens,
            "sections": sections,
        }

    @staticmethod
    def _text(memory: Memory) -> str:
        return memory.summary or memory.content or ""

    @staticmethod
    def _humanize(goal: str) -> str:
        return goal.replace("_", " ").capitalize() if goal else "General assistance"

    @staticmethod
    def _trim_to_budget(context_text: str, token_limit: int) -> str:
        """Trim context to fit a hard token budget, cutting at a line boundary."""
        char_limit = max(0, token_limit * 4)
        if len(context_text) <= char_limit:
            return context_text
        truncated = context_text[:char_limit]
        last_newline = truncated.rfind("\n")
        return truncated[:last_newline] if last_newline > 0 else truncated


# Singleton instance
context_assembler = ContextAssembler()
