"""
Goal Detection Engine

Infers the user's actual underlying objective from a query, rather than
matching literal keywords. This is the first stage of the Predictive Recall
Pipeline: everything downstream (intent classification, utility prediction)
is conditioned on the detected goal.

Implemented as a transparent, extensible weighted-signal classifier so it
runs with zero external dependencies and sub-millisecond latency. Each goal
is defined by a set of (pattern, weight) signals; matched signals are
returned alongside the score so predictions stay explainable. This keeps the
door open to later replacing/augmenting scoring with an LLM or a trained
classifier without changing the pipeline contract (see `score_goal`).
"""
import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


# Each goal maps to a list of (regex_pattern, weight) signals. Patterns are
# matched case-insensitively against the raw query. Weights are additive and
# then normalized across goals to produce a confidence-like score.
GOAL_SIGNALS: Dict[str, List[Tuple[str, float]]] = {
    "system_design": [
        (r"\bsystem design\b", 1.0),
        (r"\barchitect(ure|ing)?\b", 0.8),
        (r"\bscal(e|ing|ability)\b", 0.6),
        (r"\bmicroservices?\b", 0.6),
        (r"\bload balanc\w*\b", 0.6),
        (r"\bdatabase (schema|design)\b", 0.6),
        (r"\bdesign (a|the|my) backend\b", 0.9),
        (r"\bhigh[- ]level design\b", 0.8),
        (r"\bbuild (a|an|the) (backend|api|service|platform)\b", 0.5),
    ],
    "interview_preparation": [
        (r"\binterview(s|ing)?\b", 1.0),
        (r"\bwhiteboard\b", 0.5),
        (r"\bleet ?code\b", 0.6),
        (r"\bmock interview\b", 0.9),
        (r"\bhiring (process|round)\b", 0.5),
        (r"\btomorrow\b.*\binterview\b", 0.3),
        (r"\bprep(are|aring)? for\b", 0.3),
    ],
    "debugging": [
        (r"\bdebug(ging)?\b", 1.0),
        (r"\bfix (this|the|my) (bug|error|issue)\b", 0.9),
        (r"\berror\b", 0.5),
        (r"\bexception\b", 0.5),
        (r"\bstack trace\b", 0.7),
        (r"\bnot working\b", 0.5),
        (r"\bcrash(ing|es)?\b", 0.6),
        (r"\bwhy (is|does|isn't|doesn't)\b", 0.3),
    ],
    "learning": [
        (r"\bexplain\b", 0.6),
        (r"\blearn(ing)?\b", 0.8),
        (r"\bhow does .* work\b", 0.7),
        (r"\bwhat is\b", 0.4),
        (r"\bunderstand(ing)?\b", 0.5),
        (r"\bteach me\b", 0.8),
        (r"\btutorial\b", 0.5),
    ],
    "career_planning": [
        (r"\bcareer\b", 0.9),
        (r"\bpromotion\b", 0.7),
        (r"\bjob (offer|search|hunt)\b", 0.7),
        (r"\bresume|cv\b", 0.6),
        (r"\bnegotiat\w* (salary|offer)\b", 0.7),
        (r"\bstaff engineer|principal engineer|senior engineer\b", 0.6),
    ],
    "startup_ideation": [
        (r"\bstartup\b", 1.0),
        (r"\bbrainstorm\b", 0.6),
        (r"\bbusiness idea\b", 0.8),
        (r"\bfounder\b", 0.6),
        (r"\bmvp\b", 0.5),
        (r"\bproduct idea\b", 0.7),
        (r"\braise (funding|capital)\b", 0.6),
    ],
    "research": [
        (r"\bresearch\b", 0.9),
        (r"\bcompare\b", 0.4),
        (r"\bstate of the art\b", 0.7),
        (r"\bliterature\b", 0.6),
        (r"\btrade[- ]?offs?\b", 0.5),
        (r"\bpros and cons\b", 0.5),
    ],
    "code_review": [
        (r"\bcode review\b", 1.0),
        (r"\breview (this|my) code\b", 0.9),
        (r"\brefactor\b", 0.6),
        (r"\bclean(ing)? up\b", 0.4),
        (r"\bbest practices?\b", 0.4),
    ],
    "optimization": [
        (r"\boptimi[sz]e\b", 0.9),
        (r"\bperformance\b", 0.6),
        (r"\blatency\b", 0.6),
        (r"\bfaster\b", 0.5),
        (r"\breduce (cost|memory|latency)\b", 0.6),
        (r"\bbottleneck\b", 0.6),
    ],
    "purchase_decision": [
        (r"\bbuy\b", 0.8),
        (r"\bpurchase\b", 0.8),
        (r"\bpricing\b", 0.6),
        (r"\bworth (it|the money)\b", 0.6),
        (r"\bwhich (tool|product|plan) should i\b", 0.7),
    ],
    "summarization": [
        (r"\bsummari[sz]e\b", 1.0),
        (r"\btl;?dr\b", 0.8),
        (r"\bkey (points|takeaways)\b", 0.6),
        (r"\bin short\b", 0.4),
    ],
}

DEFAULT_GOAL = "general_assistance"


@dataclass
class GoalScore:
    goal: str
    score: float
    matched_signals: List[str] = field(default_factory=list)


class GoalDetector:
    """
    Infers the user's objective from a query using weighted signal matching.

    Usage:
        detector = GoalDetector()
        result = detector.detect(query)
        # result.goal, result.confidence, result.alternative_goals
    """

    def __init__(self, signals: Dict[str, List[Tuple[str, float]]] = None):
        self.signals = signals or GOAL_SIGNALS
        self._compiled = {
            goal: [(re.compile(pattern, re.IGNORECASE), weight) for pattern, weight in patterns]
            for goal, patterns in self.signals.items()
        }

    def score_goal(self, query: str, goal: str) -> GoalScore:
        """Score a single goal against a query. Exposed separately so the
        scoring strategy (regex today) can be swapped per-goal without
        touching pipeline callers."""
        patterns = self._compiled.get(goal, [])
        total = 0.0
        matched: List[str] = []
        for pattern, weight in patterns:
            if pattern.search(query):
                total += weight
                matched.append(pattern.pattern)
        return GoalScore(goal=goal, score=total, matched_signals=matched)

    def detect(self, query: str) -> Dict:
        """
        Detect the most likely goal behind a query.

        Returns:
            Dict with goal, confidence (0-1), alternative_goals, matched_signals
        """
        if not query or not query.strip():
            return {
                "goal": DEFAULT_GOAL,
                "confidence": 0.0,
                "alternative_goals": [],
                "matched_signals": [],
            }

        scores = [self.score_goal(query, goal) for goal in self._compiled]
        scores = [s for s in scores if s.score > 0]
        scores.sort(key=lambda s: s.score, reverse=True)

        if not scores:
            return {
                "goal": DEFAULT_GOAL,
                "confidence": 0.35,  # Low but non-zero: general assistance is a valid fallback
                "alternative_goals": [],
                "matched_signals": [],
            }

        total_score = sum(s.score for s in scores)
        top = scores[0]
        confidence = min(1.0, top.score / total_score if total_score > 0 else 0.0)
        # Blend in absolute strength so a single weak match doesn't look
        # falsely confident just because it was the only one that fired
        confidence = min(1.0, confidence * min(1.0, top.score / 1.0))

        alternatives = [
            {"goal": s.goal, "score": round(s.score, 3)}
            for s in scores[1:4]
        ]

        return {
            "goal": top.goal,
            "confidence": round(max(confidence, 0.3), 3),
            "alternative_goals": alternatives,
            "matched_signals": top.matched_signals,
        }


# Singleton instance, consistent with other Day 2-4 services
goal_detector = GoalDetector()


def detect_goal(query: str) -> Dict:
    """Convenience function for goal detection"""
    return goal_detector.detect(query)
