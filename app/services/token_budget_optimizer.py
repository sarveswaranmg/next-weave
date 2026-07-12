"""
Token Budget Optimizer

Naive retrieval takes the top-N memories and stops. NeuroWeave instead
treats context selection as a constrained optimization problem: choose the
subset of scored candidates that maximizes total predicted utility without
exceeding a token budget. This is a classic 0/1 knapsack (value = utility
score, weight = estimated token cost).

For small candidate pools this solves optimally via dynamic programming.
Above `max_dp_candidates` (DP is O(n * capacity), which stops being cheap
at scale) it falls back to a greedy utility-per-token ratio heuristic, which
is the standard sub-linear approximation for large-N knapsack problems and
keeps latency bounded as the memory store grows toward millions of rows.
"""
import logging
from typing import Dict, List

from app.core.config import settings

logger = logging.getLogger(__name__)


class TokenBudgetOptimizer:
    """Selects the utility-maximizing subset of candidates under a token budget."""

    def __init__(self, max_dp_candidates: int = None):
        self.max_dp_candidates = max_dp_candidates or settings.predictive_recall_knapsack_max_candidates

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Rough token estimation (1 token ~= 4 characters), matching the
        convention used elsewhere in the retrieval engine."""
        return max(1, len(text or "") // 4)

    def optimize(
        self,
        candidates: List[Dict],
        token_budget: int,
        text_key: str = "content_preview",
    ) -> List[Dict]:
        """
        Select the subset of candidates that maximizes total utility_score
        subject to sum(token_cost) <= token_budget.

        Args:
            candidates: List of dicts each with at least `utility_score`
                and a text field (`text_key`) used to estimate token cost.
            token_budget: Max tokens allowed for the selected set.
            text_key: Which key in each candidate dict holds representative text.

        Returns:
            Selected subset (unordered relative to input; caller re-ranks).
        """
        if not candidates or token_budget <= 0:
            return []

        for c in candidates:
            if "token_cost" not in c:
                c["token_cost"] = self.estimate_tokens(c.get(text_key, ""))

        # Drop anything that alone can't fit — never worth considering.
        feasible = [c for c in candidates if c["token_cost"] <= token_budget]
        if not feasible:
            return []

        if len(feasible) <= self.max_dp_candidates:
            selected = self._knapsack_dp(feasible, token_budget)
        else:
            logger.info(
                f"TokenBudgetOptimizer: {len(feasible)} candidates exceeds DP threshold "
                f"({self.max_dp_candidates}), falling back to greedy ratio selection"
            )
            selected = self._greedy_fill(feasible, token_budget)

        selected.sort(key=lambda c: c["utility_score"], reverse=True)
        return selected

    def _knapsack_dp(self, candidates: List[Dict], token_budget: int) -> List[Dict]:
        """Exact 0/1 knapsack via dynamic programming. O(n * budget)."""
        n = len(candidates)
        capacity = int(token_budget)

        dp = [[0.0] * (capacity + 1) for _ in range(n + 1)]
        for i in range(1, n + 1):
            cost = candidates[i - 1]["token_cost"]
            value = candidates[i - 1]["utility_score"]
            for cap in range(capacity + 1):
                dp[i][cap] = dp[i - 1][cap]
                if cost <= cap:
                    alt = dp[i - 1][cap - cost] + value
                    if alt > dp[i][cap]:
                        dp[i][cap] = alt

        selected = []
        cap = capacity
        for i in range(n, 0, -1):
            if dp[i][cap] != dp[i - 1][cap]:
                selected.append(candidates[i - 1])
                cap -= candidates[i - 1]["token_cost"]

        return selected

    def _greedy_fill(self, candidates: List[Dict], token_budget: int) -> List[Dict]:
        """Greedy utility-per-token ratio fill. Approximate but O(n log n)."""
        remaining = token_budget
        ranked = sorted(
            candidates,
            key=lambda c: c["utility_score"] / max(1, c["token_cost"]),
            reverse=True,
        )
        selected = []
        for c in ranked:
            if c["token_cost"] <= remaining:
                selected.append(c)
                remaining -= c["token_cost"]
        return selected


# Singleton instance
token_budget_optimizer = TokenBudgetOptimizer()
