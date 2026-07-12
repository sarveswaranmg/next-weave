# NeuroWeave — Day 7: Cognitive Forgetting & Memory Evolution Engine

## Overview

Days 1-6 built increasingly sophisticated ways to *use* memory — score it,
predict its utility, reconstruct it into cognitive state. All of it assumed
the memory store itself only grows. Day 7 makes the store itself alive:
memories strengthen, weaken, merge, get superseded, archive, and — softly,
reversibly — get forgotten, based on their ongoing value rather than just
their existence.

```
Current systems: continuously accumulate memories
NeuroWeave:       continuously evolves memories
```

Nothing is ever hard-deleted. "Forgotten" is a lifecycle state
(`CognitiveMemoryStateEnum.FORGOTTEN`), not a DELETE statement — memories
are retained, excluded from retrieval, and still revivable.

## Lifecycle

```
ACTIVE -> REINFORCED -> SEMANTIC_CANDIDATE ("SEMANTIC") -> DORMANT -> ARCHIVED -> FORGOTTEN
                                    ^                                    |
                                    |____________ revival ______________|
```

`DECAYING` (introduced in Day 2) remains as an intermediate weakening state
reachable from several points — kept rather than collapsed into the
spec's simpler 6-state list, since Day 2-4 code and tests already depend
on it. `FORGOTTEN` is new in Day 7, added additively to the existing
`CognitiveMemoryStateEnum` (a native Postgres enum — migration `007` uses
`ALTER TYPE ... ADD VALUE`, not a table rewrite).

## Pipeline

```
New Memory
   |
   v
Importance (Day 2)  -> Concept Formation (Day 3)  -> Identity Integration (Day 4)
   |
   v
[Ongoing, run by MemoryEvolutionWorker hourly/daily or POST /memory/evolve]
   |
   v
Decay Evaluation        MemoryDecayEngine + AdaptiveDecayStrategy
   |
   v
Duplicate Resolution     DuplicateResolver
   |
   v
Conflict Resolution      ObsoleteMemoryDetector
   |
   v
Forgetting Decision      ForgettingEngine (+ MemoryLifecycleManager)
   |
   v
Entropy Recalculation    MemoryEntropyCalculator -> MemoryHealthService
```

Retrieval (Day 1's `MemoryRetrievalEngine`, Day 5's `PredictiveMemoryRanker`)
now excludes `ARCHIVED`/`FORGOTTEN`, low-strength (< `retrieval_min_strength`),
and high-entropy (> `retrieval_max_entropy`) memories at the query level —
a living system retrieves only healthy, current knowledge.

## Components

| Component | File | Responsibility |
|---|---|---|
| `AdaptiveDecayStrategy` | `app/services/memory_decay_engine.py` | Per-type base decay rate (identity slowest, low-importance episodic fastest) |
| `MemoryDecayEngine` | `app/services/memory_decay_engine.py` | Multi-factor decay: age, retrieval frequency, reinforcement, concept/identity membership, importance, emotional salience |
| `DuplicateResolver` | `app/services/duplicate_resolver.py` | Clusters near-duplicate memories, merges into a `ConceptMemory`, archives originals |
| `ObsoleteMemoryDetector` | `app/services/obsolete_memory_detector.py` | Durably archives superseded memories, strengthens the current one, preserves history |
| `MemoryEntropyCalculator` | `app/services/memory_entropy.py` | Redundancy, conflicts, fragmentation, obsolescence -> a single entropy score |
| `ReinforcementRecoveryService` | `app/services/reinforcement_recovery.py` | Revives decayed/archived/forgotten memories that become relevant again |
| `MemoryLifecycleManager` | `app/services/memory_lifecycle_manager.py` | Validated, event-logged state transitions (wraps Day 2's `MemoryStateMachine`) |
| `ForgettingEngine` | `app/services/forgetting_engine.py` | Remain / weaken / archive / forget decisions, always explainable |
| `MemoryHealthService` | `app/services/memory_health_monitor.py` | Aggregates everything into a 0-100 Cognitive Health Score |
| `MemoryEvolutionPipeline` | `app/services/memory_evolution_pipeline.py` | Orchestrates one full evolution pass; what the worker and `/memory/evolve` call |

## Decay Formula

```python
effective_decay_rate = (
    base_rate(type)        # identity 0.002 .. episodic 0.05, "random conversation" 0.12
    * age_factor           # 1.0 .. 2.0, older+untouched decays faster
    * retrieval_factor      # 1 / (1 + log1p(retrieval_count)) - frequently retrieved decays slower
    * reinforcement_factor # 1.0 - reinforcement*0.6
    * membership_factor    # x0.5 if identity-linked, x0.7 if concept-linked
    * importance_factor    # 1.0 - importance*0.5
    * emotional_factor     # 1.0 - emotional_salience*0.3
)
```

Every factor is independently inspectable via `POST /memory/decay`'s
per-memory breakdown — not just a final number.

## Contradiction Detection: One Shared Engine, Two Consumers

Day 6's `ContradictionResolver` (transient, per-context-composition) and
Day 7's `ObsoleteMemoryDetector` (durable, store-mutating) share the exact
same detection primitives (`find_conflicting_pairs`, `_is_contradiction`,
`_resolution_score`) rather than duplicating the heuristic. `DuplicateResolver`
also calls into this: a candidate is refused entry into a duplicate cluster
if it *contradicts* an existing member, so "prefers Angular" and "prefers
React" (75%+ word overlap) can never be blended into one nonsensical merged
concept — a real failure mode this project's own test suite caught (see
*Bugs Found* below).

## Database Changes

`memories` gains (migration `007_memory_evolution_engine.py`):
```
entropy_score FLOAT, last_decay_at TIMESTAMP, archive_reason TEXT,
forget_reason TEXT, revival_count INTEGER
```
(`memory_strength`, `decay_rate`, `reinforcement_count`, `last_reinforced_at`
already existed from Day 2 and are reused — not duplicated into a separate
`memory_lifecycle` table, since these participate in every retrieval's
WHERE clause and a join would cost more than it's worth.)

New table `memory_events` (audit trail, mirrors Day 4's `IdentityHistory`):
```
id, memory_id, user_id, event_type, old_state, new_state,
old_strength, new_strength, reason, confidence, metadata, timestamp
```

## Background Worker

`MemoryEvolutionWorker` extends the existing Celery infrastructure
(`app/workers/celery_app.py`, `app/workers/tasks.py` — which had a
`enforce_memory_retention_policy` stub since Day 1 that was never
implemented; it now runs `MemoryEvolutionPipeline`):

- **Hourly** (`hourly_memory_evolution`): users with activity in the last
  hour — keeps evolution close to real-time for active users.
- **Daily** (`daily_memory_evolution_sweep`, 03:00 UTC): every user with
  non-forgotten memories — catches everyone else.
- **Manual**: `POST /memory/evolve`.

Both periodic tasks fan out per-user work via `enforce_memory_retention_policy.delay(user_id)`
rather than processing inline, so the beat scheduler stays fast and actual
evolution work is parallelized across Celery workers.

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/memory/evolve` | Full evolution pass for a user (manual trigger) |
| POST | `/memory/decay` | Apply decay evaluation only |
| POST | `/memory/archive` | Manually archive a specific memory with a reason |
| POST | `/memory/revive` | Revive by `memory_id` (direct) or `query` (automatic relevance-based) |
| GET | `/memory/lifecycle` | Full lifecycle status for one memory |
| GET | `/memory/health` | Cognitive Health Score + contributing metrics |
| GET | `/memory/events` | Lifecycle audit trail (filterable by memory/event type) |
| GET | `/memory/entropy` | Store-wide entropy breakdown |

Every forgetting/archival decision is explainable, matching the spec's
format exactly:
```json
{"memory": "User prefers Vue for frontend development", "decision": "Archived",
 "reason": "Superseded by 'preference' statement: \"User builds everything in React\"",
 "confidence": 0.94}
```

## Test Cases (validated in `tests/test_memory_evolution.py`, 22/22 passing)

- **Repeated preference**: "likes Rust" / "enjoys Rust" / "learns Rust" /
  "writes Rust code" collapse into one `ConceptMemory` (`Rust Interest`,
  `support_count >= 3`) via `DuplicateResolver`, sources archived not deleted.
- **Obsolete preference**: "prefers Angular" (400 days idle, weak
  reinforcement) vs. "prefers React" (1 day idle, strong reinforcement) —
  React strengthens, Angular archives with `archive_reason` set and a
  `MemoryEvent` logged, Angular's original content is untouched (history
  preserved).
- **Revival**: a `DORMANT` "User is learning React" memory (strength 0.25,
  365 days idle) revives when the query "Help me optimize React rendering
  performance" arrives — strength increases, state returns to
  `ACTIVE`/`REINFORCED`, `revival_count` increments, retrieval eligibility
  restored.
- Full `MemoryEvolutionPipeline.run()` end-to-end over a mixed store
  (duplicate cluster + obsolete pair + a weak decaying memory) correctly
  merges, resolves, and archives in one pass, and produces a valid
  Cognitive Health Score.

Also verified live end-to-end (not just unit tests) via direct
`MemoryEvolutionPipeline` execution against SQLite, confirming the pipeline
stages interoperate correctly — this is what surfaced the bugs below.

## Bugs Found and Fixed During This Build

Real defects caught by testing the spec's actual examples end-to-end,
not by inspection:

1. **"user" dominating concept naming**: `DuplicateResolver` named merged
   clusters by most-frequent word, but "user" appears in nearly every
   memory ("User prefers...") and isn't a generic English stopword — every
   merge was named "User Interest" instead of e.g. "Rust Interest". Fixed
   by adding "user"/"users" to the shared `STOPWORDS` set (Day 5's
   `context_analyzer.py`), which also improves Day 5 keyword-extraction
   precision as a side benefit.
2. **Same-verb-bucket requirement blocked the spec's own example**:
   `ContradictionResolver` (Day 6) required both memories to use the exact
   same verb ("prefers" vs "prefers") to even be compared — so "prefers
   Vue" vs. "builds everything in React" (different verbs) was never
   checked, missing this exact scenario from the Day 7 spec. Fixed by
   flattening to a pairwise scan across all stance-bearing memories
   (`find_conflicting_pairs`), relying on the stricter word-overlap test
   to prevent false positives instead of bucket identity.
3. **Duplicates-vs-contradictions collision**: with the same word-overlap
   machinery, "prefers Angular for frontend work" and "prefers React for
   frontend work" score 75% similar — high enough that `DuplicateResolver`
   was merging them into one blended (nonsensical) concept *before*
   `ObsoleteMemoryDetector` ever got to see them as a genuine conflict.
   Fixed by having cluster placement refuse any candidate that
   contradicts an existing cluster member.
4. **Miscalibrated default threshold**: `duplicate_similarity_threshold`
   defaulted to 0.75 — but short paraphrased memories sharing only a topic
   word (the spec's actual "Likes Rust" / "Enjoys Rust" example) can't
   reach 75% overlap. Recalibrated to 0.40 against the real example rather
   than an arbitrary "looks strict enough" number.

## Known Limitation

Duplicate clustering is pure lexical word-overlap (no embeddings) —
consistent with this project's dependency-free heuristic approach — so it
won't catch every possible paraphrase (a memory with several unique words
can dip just under threshold against an already-larger cluster union). A
3-of-4 merge on a loosely-worded cluster is expected, not a bug. Memories
already carry embeddings (`app/memory/embeddings.py`); swapping the
similarity function for cosine similarity over embeddings is a natural,
localized upgrade (`DuplicateResolver.find_clusters` and
`ContradictionResolver._is_contradiction` are the only two call sites)
without touching the surrounding pipeline.

## Scalability Notes

- **Incremental, not full-scan**: `hourly_memory_evolution` only touches
  users active in the last hour; the daily sweep is the full-coverage
  fallback. Per-user work is bounded by that user's memory count, not the
  global store, so this scales horizontally with user count via Celery
  worker concurrency — the path to 100M+ memories is more Celery workers,
  not a different algorithm.
- **Retrieval-time filtering is a single indexed WHERE clause** (`cognitive_state`,
  `memory_strength`, `entropy_score` are all indexed) — excluding
  archived/forgotten/weak/high-entropy memories costs an index scan, not a
  full-table scan.
- **Contradiction/duplicate detection is O(n²) within one user's stance-bearing
  memories**, not the whole store — bounded by how many preference-type
  memories a single user accumulates, which stays small in practice.
- **Pure Python heuristics throughout** (no LLM round-trip in the decay/
  merge/archive hot path), keeping per-user evolution passes fast enough
  for hourly scheduling even at scale.
- **Future Rust migration**: the decay formula, entropy scoring, and
  word-overlap contradiction test are pure functions over primitive types
  — the same property that makes Days 5-6's utility/knapsack logic
  portable applies here.

## Future Extensibility

- **Sleep consolidation / replay simulation**: `MemoryEvolutionPipeline.run()`
  is already the "offline maintenance pass" shape — an overnight batch job
  is a scheduling change, not an architecture change.
- **Curiosity-driven retention**: `MemoryDecayEngine`'s factors are all
  named, independent multipliers; a novelty/curiosity factor is another
  multiplier, not a rewrite.
- **Reinforcement learning**: `MemoryEvent` already logs every decision
  with a `confidence` score — the reward signal for an RL loop tuning
  decay/forgetting thresholds is already being captured.
- **Multi-agent shared memory**: `DuplicateResolver`/`ObsoleteMemoryDetector`
  operate on `(user_id, memories)` as plain arguments, not implicit
  single-user state — a shared-pool variant changes the candidate query,
  not these engines.
- **Autonomous self-reflection**: `GET /memory/events` and
  `GET /memory/health` already give an agent a queryable view of its own
  memory evolution history to reason about.
