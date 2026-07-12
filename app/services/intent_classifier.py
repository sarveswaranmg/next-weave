"""
Intent Classification Engine

Classifies the query's intent(s) — what action the user wants performed —
independently from the goal (what they're trying to achieve overall). A
query can carry multiple simultaneous intents (e.g. "compare Redis and
Memcached for my caching layer" is both `compare` and `optimize`), so this
returns an independent probability per intent rather than a single softmax
label.
"""
import logging
import re
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


INTENTS = [
    "learn", "build", "debug", "compare", "brainstorm", "plan",
    "purchase", "summarize", "explain", "create", "optimize",
    "research", "evaluate",
]

INTENT_SIGNALS: Dict[str, List[Tuple[str, float]]] = {
    "learn": [(r"\blearn\b", 1.0), (r"\bunderstand\b", 0.7), (r"\bhow does .* work\b", 0.8), (r"\bteach me\b", 0.9)],
    "build": [(r"\bbuild\b", 1.0), (r"\bimplement\b", 0.8), (r"\bset up\b", 0.5), (r"\bdevelop\b", 0.6), (r"\bwrite (a|the) code\b", 0.6)],
    "debug": [(r"\bdebug\b", 1.0), (r"\bfix\b", 0.8), (r"\berror\b", 0.6), (r"\bbug\b", 0.7), (r"\bnot working\b", 0.6), (r"\bcrash\w*\b", 0.6)],
    "compare": [(r"\bcompare\b", 1.0), (r"\bvs\.?\b", 0.8), (r"\bversus\b", 0.8), (r"\bdifference between\b", 0.8), (r"\bwhich is better\b", 0.7)],
    "brainstorm": [(r"\bbrainstorm\b", 1.0), (r"\bideas?\b", 0.5), (r"\bwhat if\b", 0.4), (r"\bcome up with\b", 0.5)],
    "plan": [(r"\bplan\b", 1.0), (r"\broadmap\b", 0.7), (r"\bstrategy\b", 0.6), (r"\bnext steps?\b", 0.5), (r"\bschedule\b", 0.4)],
    "purchase": [(r"\bbuy\b", 1.0), (r"\bpurchase\b", 1.0), (r"\bpricing\b", 0.6), (r"\bsubscri\w*\b", 0.5)],
    "summarize": [(r"\bsummari[sz]e\b", 1.0), (r"\btl;?dr\b", 0.9), (r"\bkey points\b", 0.6), (r"\bshorten\b", 0.5)],
    "explain": [(r"\bexplain\b", 1.0), (r"\bwhat is\b", 0.5), (r"\bwhy\b", 0.4), (r"\bclarify\b", 0.6)],
    "create": [(r"\bcreate\b", 1.0), (r"\bgenerate\b", 0.7), (r"\bwrite (a|an)\b", 0.6), (r"\bdraft\b", 0.5)],
    "optimize": [(r"\boptimi[sz]e\b", 1.0), (r"\bimprove\b", 0.6), (r"\bfaster\b", 0.5), (r"\breduce\b", 0.4), (r"\bperformance\b", 0.5)],
    "research": [(r"\bresearch\b", 1.0), (r"\binvestigate\b", 0.7), (r"\bfind out\b", 0.5), (r"\blook into\b", 0.5)],
    "evaluate": [(r"\bevaluate\b", 1.0), (r"\bassess\b", 0.7), (r"\breview\b", 0.5), (r"\bworth (it|doing)\b", 0.5), (r"\bpros and cons\b", 0.6)],
}


class IntentClassifier:
    """
    Multi-label intent classifier over a fixed intent vocabulary.

    Each intent gets an independent probability in [0, 1] (not a softmax
    distribution) since a query can express several intents at once.
    """

    def __init__(self, signals: Dict[str, List[Tuple[str, float]]] = None):
        self.signals = signals or INTENT_SIGNALS
        self._compiled = {
            intent: [(re.compile(pattern, re.IGNORECASE), weight) for pattern, weight in patterns]
            for intent, patterns in self.signals.items()
        }

    def _score_intent(self, query: str, intent: str) -> float:
        patterns = self._compiled.get(intent, [])
        raw = sum(weight for pattern, weight in patterns if pattern.search(query))
        # Squash to (0, 1) without forcing a cross-intent sum of 1, so
        # multiple intents can each score high independently.
        return raw / (raw + 1.0)

    def classify(self, query: str, top_k: int = 3) -> Dict:
        """
        Classify intents present in a query.

        Returns:
            Dict with `intents` (all scored intents sorted desc) and `primary_intent`
        """
        if not query or not query.strip():
            return {
                "intents": [{"intent": "explain", "probability": 0.0}],
                "primary_intent": "explain",
            }

        scored = [
            {"intent": intent, "probability": round(self._score_intent(query, intent), 3)}
            for intent in self._compiled
        ]
        scored.sort(key=lambda x: x["probability"], reverse=True)

        # Keep only intents with a non-trivial signal, but always return at
        # least one so downstream stages have something to condition on.
        significant = [s for s in scored if s["probability"] > 0.05]
        if not significant:
            significant = [scored[0]] if scored else [{"intent": "explain", "probability": 0.0}]

        primary = significant[0]["intent"]

        return {
            "intents": significant[:max(top_k, 1)],
            "primary_intent": primary,
        }


# Singleton instance
intent_classifier = IntentClassifier()


def classify_intent(query: str, top_k: int = 3) -> Dict:
    """Convenience function for intent classification"""
    return intent_classifier.classify(query, top_k=top_k)
