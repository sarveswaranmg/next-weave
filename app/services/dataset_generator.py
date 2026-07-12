"""
Benchmark Dataset Generator

Automatically generates synthetic users, long conversations, changing
preferences, project evolution, contradictory information, identity
shifts, and large world models — deterministic (seeded) so the same
dataset can be regenerated for regression testing across code changes,
without needing an LLM to produce it.
"""
import logging
import random
from dataclasses import dataclass, field
from typing import List

logger = logging.getLogger(__name__)


@dataclass
class SyntheticTurn:
    role: str
    content: str
    turn_index: int


@dataclass
class SyntheticUser:
    external_id: str
    persona: str
    turns: List[SyntheticTurn] = field(default_factory=list)


PERSONAS = ["backend_engineer", "frontend_engineer", "data_scientist", "founder", "researcher"]

PREFERENCE_STATEMENTS = {
    "backend_engineer": ["User prefers Python for backend services", "User likes Rust for systems programming"],
    "frontend_engineer": ["User prefers React for frontend work", "User likes TypeScript over JavaScript"],
    "data_scientist": ["User prefers PyTorch for modeling", "User likes clean, reproducible notebooks"],
    "founder": ["User prefers moving fast over perfect architecture", "User likes lean MVPs"],
    "researcher": ["User prefers rigorous benchmarking", "User likes reproducible experiments"],
}

CONTRADICTION_PAIRS = [
    ("User prefers Vue for frontend development", "User now builds everything in React"),
    ("User prefers Angular for frontend work", "User prefers React for frontend work"),
    ("User prefers monolith architecture", "User now prefers microservices architecture"),
]

PROJECT_EVOLUTION_STEPS = [
    "I started building {project}.",
    "I'm using {tech} for {project}.",
    "I'm currently implementing the {phase} phase of {project}.",
    "I'll migrate {project}'s retrieval layer to Rust later.",
    "Deploy {tech} for {project}. Connect the database. Benchmark retrieval.",
]

IDENTITY_SHIFT_STEPS = [
    "I'm really into {old_interest} lately.",
    "I've been studying {new_interest_a} in depth.",
    "I keep coming back to {new_interest_b} in my free time.",
    "I spend most of my time now working on {new_interest_a} and {new_interest_b}.",
]


class DatasetGenerator:
    """Generates deterministic synthetic benchmark datasets."""

    def __init__(self, seed: int = 42):
        self.seed = seed
        self._rng = random.Random(seed)

    def generate_users(self, count: int = 5) -> List[SyntheticUser]:
        """Generate `count` synthetic users, each with preferences,
        a contradiction, project evolution, and an identity shift baked
        into their turn sequence."""
        return [self._generate_user(i) for i in range(count)]

    def _generate_user(self, index: int) -> SyntheticUser:
        persona = PERSONAS[index % len(PERSONAS)]
        user = SyntheticUser(external_id=f"synthetic-user-{self.seed}-{index}", persona=persona)

        turn_index = 0
        for statement in PREFERENCE_STATEMENTS.get(persona, []):
            user.turns.append(SyntheticTurn("user", statement, turn_index))
            turn_index += 1

        contradiction = CONTRADICTION_PAIRS[index % len(CONTRADICTION_PAIRS)]
        for statement in contradiction:
            user.turns.append(SyntheticTurn("user", statement, turn_index))
            turn_index += 1

        project = f"Project{index}"
        tech_options = ["FastAPI", "PostgreSQL", "Redis", "Docker"]
        for template in PROJECT_EVOLUTION_STEPS:
            content = template.format(
                project=project, tech=self._rng.choice(tech_options), phase=f"Day {index + 1}",
            )
            user.turns.append(SyntheticTurn("user", content, turn_index))
            turn_index += 1

        old_interest, new_a, new_b = self._rng.sample(
            ["React", "Rust", "distributed systems", "databases", "machine learning", "Kubernetes"], 3
        )
        for template in IDENTITY_SHIFT_STEPS:
            content = template.format(old_interest=old_interest, new_interest_a=new_a, new_interest_b=new_b)
            user.turns.append(SyntheticTurn("user", content, turn_index))
            turn_index += 1

        return user

    def generate_long_conversation(self, base_topic: str, length: int = 50) -> List[SyntheticTurn]:
        """Generate a long, evolving conversation for stress-testing
        performance after 10/100/1000/10000 interactions."""
        topics = ["FastAPI", "PostgreSQL", "Redis", "caching", "scalability", "Rust", "testing"]
        return [
            SyntheticTurn(
                "user",
                f"[{base_topic} turn {i}] Let's talk more about {topics[i % len(topics)]} in the context of {base_topic}.",
                i,
            )
            for i in range(length)
        ]
