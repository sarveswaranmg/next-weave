# NeuroWeave — Day 8: Offline Cognitive Consolidation Engine ("Dream Mode")

## Overview

Days 1-7 built a memory system that responds to interaction — every
improvement (scoring, decay, forgetting) happened as a side effect of a
live request. Day 8 makes NeuroWeave improve itself while idle, the way
sleep consolidates memory in a biological brain: replaying salient
experiences, discovering patterns that were never explicitly stored,
refining and merging concepts, evolving identity, healing contradictions,
optimizing graph structure, synthesizing new knowledge, and compressing
storage — all without a new conversation.

```
Current systems: only learn when users interact
NeuroWeave:       continues improving when idle
```

Dream Mode is largely a **new orchestration layer over existing engines**:
contradiction detection/healing reuses Day 7's `ObsoleteMemoryDetector`,
health scoring reuses Day 7's `MemoryHealthService`, utility simulation
reuses Day 5's `MemoryUtilityPredictor`, and heuristic re-scoring reuses
Day 2's `HybridScoringEngine` (previously wired into ingest only — Dream
Mode is the first place it runs periodically). The genuinely new pieces
are pattern discovery, concept refinement, identity evolution, graph
optimization, and knowledge synthesis.

## Pipeline

```
Idle Trigger / Scheduler
        |
        v
Replay                    ReplayEngine (select) + HybridScoringEngine (rebuild)
        |
        v
Pattern Discovery         PatternDiscoveryEngine -> new IdentityNode traits
        |
        v
Concept Refinement        ConceptRefiner: merge -> generalize -> strengthen -> retire
        |
        v
Consistency Healing       ConsistencyEngine: memory conflicts (Day 7 reuse) +
        |                                     duplicate identity traits (new)
        v
Identity Evolution        IdentityEvolutionEngine -> IdentityEvolutionEvent
        |
        v
Graph Optimization        GraphOptimizationEngine: dead nodes, edge strength
        |
        v
Knowledge Synthesis       KnowledgeSynthesizer -> KnowledgeSynthesis + new ConceptMemory
        |
        v
Replay Simulation         MemoryReplaySimulator (predictive maintenance)
        |
        v
Compression                CompressionOptimizer: reclaim embeddings, report ratio
        |
        v
Memory Health Evaluation   MemoryHealthService (Day 7 reuse) - before/after score
```

Every stage updates and commits a `DreamSession` row; a concurrent
`POST /dream/stop` flips its status to `CANCELLED`, checked cooperatively
between stages (not a hard interrupt) — this is why every stage commits
before checking, not just at the end.

## Components

| Component | File | Responsibility |
|---|---|---|
| `DreamScheduler` | `app/services/dream_scheduler.py` | Which users are eligible right now (cooldown, idle detection, growth-based prioritization, compute budget) |
| `ReplayEngine` | `app/services/replay_engine.py` | Selects high-value memories (importance, uncertainty, identity recency, conflict, reinforcement) and rebuilds their cognitive scores |
| `PatternDiscoveryEngine` | `app/services/pattern_discovery.py` | Infers higher-order traits from accumulated evidence (e.g. "systems_engineering_interest") |
| `ConceptRefiner` | `app/services/concept_refiner.py` | Merges duplicates, generalizes related clusters, strengthens well-supported concepts, retires stale ones |
| `ConsistencyEngine` | `app/services/consistency_engine.py` | Heals memory conflicts (delegates to Day 7) + merges duplicate identity traits (new) |
| `IdentityEvolutionEngine` | `app/services/identity_evolution.py` | Detects identity shifts from recent vs. established evidence, logs (never overwrites) |
| `GraphOptimizationEngine` | `app/services/graph_optimizer.py` | Retires dead concept/identity nodes, strengthens reinforced edges |
| `KnowledgeSynthesizer` | `app/services/knowledge_synthesizer.py` | Generates a genuinely new composite concept from several existing ones |
| `MemoryReplaySimulator` | `app/services/replay_simulator.py` | Predictive maintenance: scores memories against synthetic future contexts, weakens poor performers |
| `CompressionOptimizer` | `app/services/compression_optimizer.py` | Reclaims embeddings for inactive memories, reports storage compression |
| `DreamPipeline` | `app/services/dream_pipeline.py` | Orchestrates all of the above; `run()` / `stop()` |

## Database Changes

`dream_sessions` (migration `008_dream_mode.py`): status (native Postgres
enum, `RUNNING`/`COMPLETED`/`CANCELLED`/`FAILED`), trigger, timestamps, and
one counter per pipeline stage (`memories_replayed`, `patterns_discovered`,
`concepts_created`, `concepts_refined`, `identity_updates`,
`contradictions_resolved`, `graph_nodes_removed`,
`graph_edges_strengthened`, `knowledge_synthesized`, `compression_ratio`,
`health_score_before/after`), plus `stage_latency_ms` (per-stage timing)
and `metadata` (full decision detail — merges, shifts, discoveries).

`knowledge_synthesis`: `source_concept_ids`, `new_concept`, `confidence`,
linked to the `dream_session_id` that produced it.

`identity_evolution_events`: `old_identity`, `new_identity`, `reason`,
`confidence` — append-only, the old `IdentityNode` is never modified.

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/dream/start` | Run a full dream session for a user |
| POST | `/dream/stop` | Cooperatively cancel a running session |
| GET | `/dream/status` | Status of a session (defaults to most recent) |
| GET | `/dream/history` | Past sessions for a user |
| POST | `/dream/replay` | Standalone replay pass |
| POST | `/dream/refine` | Standalone concept refinement pass |
| POST | `/dream/synthesize` | Standalone knowledge synthesis pass |
| GET | `/dream/statistics` | Aggregated observability metrics |

## Background Workers

`DreamWorker`, `ReplayWorker`, `ConceptWorker`, `GraphWorker`, and
`CompressionWorker` are separate Celery tasks (`app/workers/tasks.py`) so
each can be routed to its own queue for distributed execution, even though
`DreamWorker` (`dream_worker_task`) typically runs the full pipeline
in-process via `DreamPipeline`. `DreamScheduler` ticks are also Celery
tasks (`hourly_dream_tick`, `daily_dream_tick`, `weekly_dream_tick`,
`idle_triggered_dream_tick`), scheduled via Celery beat and fanning out
per-user `dream_worker_task.delay(...)` calls — the beat scheduler itself
stays fast; the actual consolidation work is parallelized across workers
and never runs in a live request's path.

## Test Cases (validated in `tests/test_dream_mode.py`, 22/22 passing)

- **Case 1 (backend memories -> higher-level concepts)**: verified both
  as a unit test and live end-to-end — 15 backend-related memories
  produced a `systems_engineering_interest` trait at **0.978 confidence**
  via `PatternDiscoveryEngine`, matching the spec's own example almost
  exactly.
- **Case 2 (contradictory preferences -> identity evolution, history
  preserved)**: "prefers Vue" (300 days idle) vs. "builds everything in
  React" (1 day idle, reinforced) — React wins, Vue's original content is
  untouched (only archived), and the identity shift from `react` to the
  newly-discovered `systems_engineering_interest` trait was logged with
  the old `IdentityNode` left exactly as-is.
- **Case 3 (large duplicate graph -> reduced complexity)**: 5 paraphrased
  "likes/enjoys/learns/writes/codes in Rust" memories merged into one
  `ConceptMemory`; `GraphOptimizationEngine` retires dead nodes and
  strengthens reinforced edges.
- Full `DreamPipeline.run()` end-to-end (not just unit tests) over a
  combined scenario (15 backend memories + 5 concepts + contradictory
  identity/preference pair + a 5-memory duplicate cluster) completed in
  **42ms**, correctly executing every stage and improving the Cognitive
  Health Score (81.47 -> 82.1) in one pass — this is what caught two of
  the four bugs below.

## Bugs Found and Fixed During This Build

Following the pattern from Days 6-7: real defects caught by running actual
scenarios end-to-end, not by inspection.

1. **`_cancelled()` silently discarding stage results**: the cancellation
   check called `session.refresh()` to pick up a concurrent `POST
   /dream/stop`, but `refresh()` reloads *all* attributes from the
   database — including the current stage's just-set-but-not-yet-committed
   stats (e.g. `memories_replayed`). Every session showed 0 memories
   replayed despite replay genuinely running. Fixed by committing before
   refreshing in `_cancelled()`.
2. **`float.hex()` colliding with UUID detection**: `_jsonable_list` used
   `hasattr(v, "hex")` to detect UUIDs for JSON serialization — but Python
   floats also define `.hex()` (`(1.0).hex()` is a real method). Every
   `confidence` score in stored decision metadata was being silently
   stringified (`1.0` -> `"1.0"`). Fixed with an explicit `isinstance(v, UUID)` check.
3. **Identity-shift detection comparing a node against itself**: computing
   "current dominant trait" as `max()` over *all* nodes (old and new
   together) meant recently-reinforced nodes — which score highest by
   construction — were picked as both the "current" and "recent" dominant
   trait, so `recent_dominant.id == current_dominant.id` was always true
   and no shift was ever detected. Fixed by computing "current dominant"
   from *established* (non-recent) evidence only, so there's something
   genuine to compare the new evidence against.
4. **Miscalibrated similarity thresholds** (same class of bug as Day 7):
   the duplicate-identity merge threshold (0.6) was higher than
   "backend_engineering" vs. "backend engineer" can ever reach with a
   no-stemming word-overlap heuristic (0.5, since "engineering"/"engineer"
   are different tokens) — recalibrated to 0.5. Separately, `ConceptRefiner
   ._generalize` used Jaccard-over-union, which dilutes every time a
   cluster grows (the same effect that hit Day 7's `DuplicateResolver`),
   so a third genuinely-related concept could fail to join a
   two-member cluster; switched to overlap-coefficient (shared / smaller
   set), consistent with `_merge_duplicates`.

## Known Limitations

- **Lexical heuristics, not embeddings**: concept merging/generalization
  and contradiction detection are pure word-overlap (no LLM, no cosine
  similarity over embeddings) — consistent with this project's
  dependency-free approach through Days 5-8, but it means concepts that
  are thematically related without *any* shared vocabulary (e.g. "Backend"
  and "Infrastructure" with completely disjoint wording) won't be
  recognized as related. Memories already carry embeddings
  (`app/memory/embeddings.py`); swapping in cosine similarity is a
  localized upgrade to `ConceptRefiner`/`ContradictionResolver`, not an
  architecture change.
- **Knowledge synthesis labels are compositional, not fluent**: `KnowledgeSynthesizer`
  produces labels like "Distributed Systems Caching Scalability" (one
  distinctive word per source concept) rather than natural-language
  synthesis ("High Performance Distributed Backend Engineering"). An
  LLM-optional path (mirroring `HybridScoringEngine`'s dual heuristic/LLM
  design) is the natural upgrade for more fluent labels without changing
  the pipeline's contract.

## Scalability Notes

- **Never in the request path**: every Dream Mode component takes a
  `session` and `user_id` and runs standalone — `DreamPipeline` is only
  ever invoked from a Celery task or a manual API call, never from a live
  retrieval/composition endpoint, so it structurally cannot add latency to
  user-facing inference.
- **Idle-triggered scheduling avoids wasted work**: `DreamScheduler
  ._is_idle()` checks for recent `PredictiveRecallLog`/`ContextSnapshot`
  activity before considering a user for an idle-triggered dream tick, so
  consolidation never runs concurrently with a user who's actively engaged.
- **Bounded, prioritized batches**: `dream_max_users_per_scheduler_tick`
  caps each scheduler tick; users are prioritized by memory growth since
  their last completed session, so the highest-value consolidation happens
  first as the store scales toward 100M+ memories.
- **Per-user cooldown** (`dream_min_hours_between_sessions`) prevents
  redundant back-to-back sessions for the same user.
- **Distributed by construction**: `DreamWorker`/`ReplayWorker`/
  `ConceptWorker`/`GraphWorker`/`CompressionWorker` are independent Celery
  tasks — horizontal scaling is adding worker processes/queues, not
  redesigning the pipeline.
- **Future Rust migration**: pattern matching, word-overlap scoring, and
  the decay/health formulas reused from Days 5-7 are pure functions over
  primitive types — the same portability property carried through every
  prior day applies here too.

## Future Extensibility

- **Reinforcement learning from replay**: `ReplayEngine`'s priority
  formula and `MemoryReplaySimulator`'s simulated-utility scores are
  already logged per dream session (`DreamSession.stage_latency_ms` /
  `metadata`) — an RL loop optimizing replay selection has a ready reward
  signal without new instrumentation.
- **Autonomous curiosity / self-generated hypotheses**: `PatternDiscoveryEngine`'s
  `HIGHER_ORDER_PATTERNS` is data, not logic — a curiosity-driven variant
  that proposes and tests its *own* candidate patterns (rather than
  matching a fixed list) plugs into the same `discover()` contract.
- **World model construction**: `KnowledgeSynthesizer` already builds new
  `ConceptMemory` nodes from combinations of existing ones with
  `is_derived_from` provenance — a world-model builder is a variant that
  synthesizes relationships between concepts, not just new concept nodes.
- **Multi-agent shared dreaming**: every engine takes `(session, user_id)`
  as plain arguments, not implicit single-user state — a shared-pool
  consolidation pass changes the candidate query in each engine, not the
  engines themselves.
- **Continual learning**: `IdentityEvolutionEvent` and `KnowledgeSynthesis`
  are already append-only logs of everything NeuroWeave has learned about
  itself over time — the substrate a continual-learning loop would read
  from already exists.
