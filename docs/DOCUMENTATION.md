# NeuroWeave — Complete Documentation

**NeuroWeave** is a cognitive memory engine and runtime platform for AI agents. It replaces
"paste the whole chat history into the prompt" with a structured memory system that extracts,
scores, consolidates, forgets, and recalls what actually matters — so an agent built on it
remembers who a user is and what they care about without re-reading the entire conversation
every time.

This is the single reference document for the whole system: what it does, how it's built, how
to run it, and how to extend it. If a docs website is ever built for this project, this file is
the source of truth it should be generated from.

> Looking for the fast version? See the [README](../README.md) for a 5-minute quickstart.
> Historical day-by-day build logs (this project was built incrementally over 10 milestones)
> live in [`docs/archive/`](archive/) if you want the blow-by-blow implementation history,
> including bugs found and fixed along the way.

---

## Table of Contents

1. [Why NeuroWeave](#why-neuroweave)
2. [Core Concepts](#core-concepts)
3. [System Architecture](#system-architecture)
4. [The Full Pipeline](#the-full-pipeline)
5. [Database Schema](#database-schema)
6. [API Reference](#api-reference)
7. [SDKs](#sdks)
8. [Framework Integrations](#framework-integrations)
9. [Configuration Reference](#configuration-reference)
10. [Running Locally](#running-locally)
11. [Production Deployment](#production-deployment)
12. [Observability](#observability)
13. [Security & Privacy](#security--privacy)
14. [Testing](#testing)
15. [Benchmarking (NeuroBench)](#benchmarking-neurobench)
16. [Known Limitations](#known-limitations)
17. [Roadmap](#roadmap)
18. [Contributing](#contributing)

---

## Why NeuroWeave

Most "memory" for LLM agents is one of:

- **Raw history** — dump the whole conversation back into the prompt every time. Simple, but
  token cost grows unbounded and signal drowns in noise.
- **Vector RAG over chat logs** — embed and retrieve raw messages. Better than nothing, but
  retrieval quality is capped by how well a raw message embeds, and nothing ever gets
  consolidated, contradicted, or forgotten.

NeuroWeave instead treats memory as something with structure and a lifecycle:

- Conversations are **extracted** into typed, scored memory objects (not stored verbatim).
- Related memories get **consolidated** into higher-level concepts over time, the same way a
  human generalizes "mentioned Rust three times" into "is a Rust developer."
- Memories that stop being reinforced **decay and get archived** — old, unused, low-importance
  information doesn't clutter retrieval forever, but nothing is ever hard-deleted except on
  explicit user request (GDPR).
- The system builds an explicit model of **who the user is** (identity graph) and **what they're
  working on** (world model: projects, entities, decisions), not just a bag of facts.
- Retrieval is **predictive and budget-aware** — it estimates what the user is about to need and
  assembles a token-budgeted context, not just "top-K nearest neighbors."
- There's an offline **consolidation/"dream" cycle** that runs when the user is idle, the same
  way biological memory consolidation happens during sleep — clustering, refining, and resolving
  contradictions without blocking any live request.

The result, measured by the built-in benchmark suite (see [NeuroBench](#benchmarking-neurobench)):
significantly fewer prompt tokens than raw history for equivalent or better personalization and
task-relevant context.

## Core Concepts

**Memory types** (`MemoryTypeEnum`): `episodic` (a specific event/exchange), `semantic` (a
general fact), `identity` (a trait about who the user is), `procedural` (a behavioral rule /
preference for how to respond).

**Cognitive memory state** (`CognitiveMemoryStateEnum`): every memory moves through a lifecycle —
`active` → `reinforced` (used repeatedly) or → `dormant` → `archived` → `forgotten` (soft-delete;
excluded from retrieval, never physically removed except via GDPR deletion) — with a
`revival` path back to active if a decayed memory becomes relevant again.

**Memory strength**: a 0–1 score that decays over time (rate depends on memory type — identity
decays slowest, episodic fastest) and increases on reinforcement (the memory being used in a
retrieval that mattered). Drives both ranking and lifecycle transitions.

**Concepts**: clusters of semantically related memories, generalized into a single higher-level
node (e.g., several "likes Rust" / "used Rust for X" memories → one `rust_developer` concept)
with its own confidence score and relationships to other concepts.

**Identity graph**: nodes representing traits/interests/roles about the user, built from
reinforced concepts, with confidence scores and an evolution history (when and why a trait
changed).

**World model**: entities (projects, technologies, people, organizations) and relationships
extracted from conversation, plus architectural decisions and a project timeline — this is what
lets the system answer "what tech stack is the user using for project X."

**Context composition**: the step that takes retrieved memories + identity + world model and
assembles them into a token-budgeted prompt context, deduplicating, resolving contradictions, and
scoring the result for coverage/alignment/quality before it's used.

## System Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                              CLIENTS                                     │
│   Python SDK (CognitiveAgent) · TypeScript SDK · LangChain adapter ·     │
│   curl / any HTTP client · WebSocket client                             │
└───────────────────────────────┬────────────────────────────────────────┘
                                 │ REST / WebSocket
                                 ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                  FastAPI Application (neurowave_engine/main.py)          │
│  ┌────────────┐ ┌───────────┐ ┌───────────┐ ┌────────────┐ ┌──────────┐ │
│  │  ingest /  │ │ cognitive │ │ semantic  │ │  identity  │ │predictive│ │
│  │  retrieval │ │  scoring  │ │consolidate│ │   graph    │ │  recall  │ │
│  └────────────┘ └───────────┘ └───────────┘ └────────────┘ └──────────┘ │
│  ┌────────────┐ ┌───────────┐ ┌───────────┐ ┌────────────┐ ┌──────────┐ │
│  │  context   │ │  memory   │ │   dream   │ │   world    │ │ runtime  │ │
│  │  composer  │ │ evolution │ │   mode    │ │   model    │ │ platform │ │
│  └────────────┘ └───────────┘ └───────────┘ └────────────┘ └──────────┘ │
└───────────────────────────────┬──────────────────┬──────────────────────┘
                                 │                   │
                     ┌───────────▼──────────┐   ┌────▼─────────────────┐
                     │  PostgreSQL+pgvector  │   │   Redis (broker +    │
                     │  (all structured data,│   │   Celery result      │
                     │   embeddings)         │   │   backend/cache)     │
                     └───────────────────────┘   └────┬──────────────────┘
                                                       │
                                          ┌─────────────▼──────────────┐
                                          │  Celery worker + beat      │
                                          │  (consolidation, retention │
                                          │   enforcement, dream-mode  │
                                          │   scheduling, background   │
                                          │   memory evolution ticks)  │
                                          └─────────────────────────────┘
```

Everything above the database line is one FastAPI app (`neurowave_engine/main.py`) with routers registered
per subsystem — there's no microservice split; the "runtime platform" is a orchestration layer
on top of the same service classes every other router calls, not a separate system.

## The Full Pipeline

This is what happens end-to-end when a message comes in through the highest-level entry point,
`RuntimeOrchestrator.chat()` (used by `POST /runtime/chat`, the WebSocket route, and both SDKs):

```
1. Ensure the user exists (auto-create on first contact)
2. Ingest the incoming message
     → HybridScoringEngine.score_memory() classifies + scores it (heuristic, no LLM call
       in this hot path — an explicit latency/cost tradeoff) → stored as a Memory row
3. Update the world model
     → EntityExtractor + ProjectMemoryEngine + relationship extraction
4. Assemble context for the LLM call, in priority order:
     a. ContextComposer.compose() — the full pipeline: predictive recall → dedup →
        contradiction resolution → concept merging → narrative generation →
        quality/coverage/identity-alignment/goal-alignment scoring, OR (if disabled)
     b. PredictiveRecallPipeline.run() — goal detection → intent classification →
        utility scoring → knapsack-style budget-constrained memory selection
5. Call the LLM provider (OpenAI / Anthropic / any OpenAI-compatible endpoint / echo)
     → any provider failure or misconfiguration silently falls back to a deterministic
       echo provider rather than hard-failing the request
6. Ingest the assistant's response as a procedural memory too
7. Schedule background work (non-blocking, best-effort):
     → consolidate_user_memories_task, enforce_memory_retention_policy via Celery
       (each wrapped so a missing/down broker never fails the chat request itself)
```

Independent of the live chat path, background/offline processes handle the rest of the
lifecycle:

- **Semantic consolidation** clusters related memories and generates/refines concepts.
- **Memory evolution** applies daily decay, promotes/demotes cognitive state, archives or
  soft-forgets low-utility memories, and revives ones that become relevant again.
- **Dream mode** runs during user idle periods (or on a schedule): replays and re-scores recent
  memories, discovers higher-order patterns, resolves contradictions, retires stale concepts,
  and synthesizes new knowledge from concept clusters.
- **Identity evolution** detects and logs shifts in who the user appears to be, once enough
  supporting evidence accumulates.

## Database Schema

PostgreSQL + the `pgvector` extension (for memory embeddings). Schema is managed via Alembic;
migrations `001`–`010` are additive, one per major subsystem:

| Migration | Adds |
|---|---|
| `001_initial` | `users`, `memories`, `sessions` — the foundational tables |
| `002_add_cognitive_scoring` | Cognitive state/strength columns on `memories` |
| `003_semantic_consolidation` | `memory_clusters`, `concept_memories`, `concept_relationships` |
| `004_identity_graph_engine` | `identity_nodes`, `identity_relationships`, `identity_history` |
| `005_predictive_recall_engine` | `predictive_recall_logs` |
| `006_cognitive_context_composer` | `context_snapshots`, `context_metrics` |
| `007_memory_evolution_engine` | `memory_events`, `memory_consolidations`, `consolidation_metrics`, `retrieval_logs` |
| `008_dream_mode` | `dream_sessions` |
| `009_world_model_engine` | `world_entities`, `world_relationships`, `projects`, `architectural_decisions` |
| `010_runtime_platform` | `benchmark_runs`, `runtime_metrics` |

Every table with a JSON metadata column maps it as `extra_metadata = Column("metadata", ...)` —
the Python attribute is renamed but the DB column stays `metadata`; this works around SQLAlchemy
reserving `Base.metadata` on every declarative model (a real bug hit and fixed early in the
project — see `docs/archive/DAY5_PREDICTIVE_RECALL.md` for the root-cause writeup).

Apply migrations with:
```bash
alembic upgrade head
```

## API Reference

All endpoints are served from one FastAPI app. Interactive docs are always available at
`/docs` (Swagger) and `/redoc` when the app is running.

### Memory ingestion & retrieval (`/memory/*`)
| Method | Path | Purpose |
|---|---|---|
| POST | `/memory/ingest` | Extract and store memories from a conversation |
| POST | `/memory/retrieve` | Semantic retrieval of relevant memories |
| POST | `/memory/reconstruct` | Build a compressed context string from retrieved memories |

### Cognitive scoring (`/cognitive/*`)
| Method | Path | Purpose |
|---|---|---|
| POST | `/cognitive/score` | Score a piece of content for importance/decay/type |
| POST | `/cognitive/reinforce` | Reinforce a memory (increases strength, resets decay) |
| GET | `/cognitive/importance/{memory_id}` | Get a memory's current importance breakdown |
| GET | `/cognitive/stats` | Aggregate cognitive-state stats for a user |

### Semantic consolidation (`/semantic/*`)
| Method | Path | Purpose |
|---|---|---|
| POST | `/semantic/consolidate` | Run clustering + concept generation for a user |
| GET | `/semantic/concepts` | List a user's concepts |
| GET | `/semantic/concepts/{concept_id}` | Get one concept |
| POST | `/semantic/concepts/{concept_id}/reinforce` | Reinforce a concept |
| GET | `/semantic/concepts/{concept_id}/related` | Related concepts |
| POST | `/semantic/concepts/search` | Search concepts by text |
| GET | `/semantic/graph` / `/semantic/graph/{concept_id}` | Concept relationship graph |
| GET | `/semantic/clusters` | List memory clusters |
| POST | `/semantic/clusters/create` | Force cluster creation |
| GET | `/semantic/metrics` / `/semantic/status` | Consolidation health metrics |

### Identity graph (`/identity/*`)
| Method | Path | Purpose |
|---|---|---|
| POST | `/identity/extract` | Extract identity traits from memories/concepts |
| GET | `/identity/profile` | Full user profile |
| GET | `/identity/graph` | Identity node/relationship graph |
| POST | `/identity/reinforce` | Reinforce an identity node |
| GET | `/identity/history` | Identity evolution history |
| POST | `/identity/rebuild` | Rebuild identity from scratch |
| GET | `/identity/context` | Identity summary formatted for prompt injection |
| GET | `/identity/status` | Identity subsystem health |

### Predictive recall (top-level, no prefix)
| Method | Path | Purpose |
|---|---|---|
| POST | `/goal-detect` | Detect the user's likely current goal |
| POST | `/intent-classify` | Classify message intent |
| POST | `/utility-score` | Score a memory's utility for the current context |
| POST | `/context/assemble` | Budget-constrained context assembly |
| POST | `/predictive-recall` | Full predictive recall pipeline |
| GET | `/retrieval/explanation` | Why a given retrieval returned what it did |

### Cognitive Context Composer (`/context/*`)
| Method | Path | Purpose |
|---|---|---|
| POST | `/context/compose` | Full context composition pipeline |
| POST | `/context/evaluate` | Score an assembled context's quality |
| POST | `/context/compress` | Compress context text to a token budget |
| POST | `/context/narrative` | Generate a narrative summary from memories |
| POST | `/context/gaps` | Detect missing/needed context |
| GET | `/context/history` / `/context/metrics` | Past compositions and aggregate metrics |

### Memory evolution (`/memory/*`)
| Method | Path | Purpose |
|---|---|---|
| POST | `/memory/evolve` | Run one evolution pass (decay + lifecycle transitions) |
| POST | `/memory/decay` | Apply decay only |
| POST | `/memory/archive` | Force-archive a memory |
| POST | `/memory/revive` | Revive an archived/dormant memory |
| GET | `/memory/lifecycle` | Lifecycle state distribution |
| GET | `/memory/health` | Cognitive health score |
| GET | `/memory/events` | Memory lifecycle event log |
| GET | `/memory/entropy` | Memory entropy metrics |

### Dream mode (`/dream/*`)
| Method | Path | Purpose |
|---|---|---|
| POST | `/dream/start` / `/dream/stop` | Manually start/stop a dream session |
| GET | `/dream/status` | Current session status |
| GET | `/dream/history` | Past dream sessions |
| POST | `/dream/replay` | Trigger memory replay |
| POST | `/dream/refine` | Trigger concept refinement |
| POST | `/dream/synthesize` | Trigger knowledge synthesis |
| GET | `/dream/statistics` | Aggregate dream-mode stats |

### World model (top-level, no prefix)
| Method | Path | Purpose |
|---|---|---|
| POST | `/world/update` | Update the world model from new content |
| GET | `/world/model` | Full world model snapshot |
| GET | `/projects` / `/projects/{project_id}` | Project list / detail |
| POST | `/decision` | Log an architectural decision |
| GET | `/timeline` | Project/decision timeline |
| GET | `/dependencies` | Entity dependency graph |
| POST | `/world/predict` | Predict likely next entity/action |

### Runtime platform (`/runtime/*`, requires `X-API-Key` if `RUNTIME_API_KEY` is set)
| Method | Path | Purpose |
|---|---|---|
| POST | `/runtime/chat` | Run the full orchestrator pipeline once |
| WS | `/runtime/chat/stream` | Same pipeline, response sent back in chunks |
| POST | `/runtime/benchmark` | Run NeuroBench for one user/query |
| POST | `/runtime/evaluate` | Run NeuroBench across a synthetic dataset |
| GET | `/runtime/metrics` | Runtime metrics snapshot |
| GET | `/runtime/health` | Liveness check (`SELECT 1`) |
| GET | `/runtime/version` | Version string |
| GET | `/runtime/explain` | Explainability query |
| POST | `/runtime/plugins` | List/unregister plugins |
| GET | `/runtime/dashboard` | Combined metrics + health |
| DELETE | `/runtime/users/{user_id}` | GDPR hard-delete of all user data |

### Observability & health
| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | App liveness |
| GET | `/readiness` | Readiness (DB reachable) |
| GET | `/metrics` | Prometheus scrape endpoint (unauthenticated, standard convention) |

## SDKs

### Python

```bash
pip install -e sdk/python[dev]   # local install; adjust once published to PyPI
```

```python
from neurowave import CognitiveAgent

agent = CognitiveAgent(
    provider="openai",       # or "anthropic", "echo", or any OpenAI-compatible vendor
    memory=True,
    world_model=True,
    predictive_recall=True,
    context_composer=True,
    base_url="http://localhost:8000",
)

response = agent.chat(user_id="...", message="What tech stack am I using for my project?")
print(response["response"])

agent.explain(user_id="...", subject_type="decision")
agent.metrics(user_id="...")
agent.forget_user(user_id="...")   # GDPR erasure
```

Lower-level access via `NeuroWeaveClient` (thin `httpx` wrapper, every SDK call goes through it —
also directly usable, and swappable with `httpx.MockTransport` for testing without a live server).

### TypeScript

```bash
cd sdk/typescript && npm install && npm run build
```

```ts
import { CognitiveAgent } from "neurowave";

const agent = new CognitiveAgent({ provider: "openai", baseUrl: "http://localhost:8000" });
const response = await agent.chat(userId, "What tech stack am I using?");
```

Zero runtime dependencies — built on native `fetch`.

## Framework Integrations

| Framework | Status |
|---|---|
| LangChain | Implemented — `sdk/python/neurowave/integrations/langchain.py`, a `NeuroWeaveMemory` class implementing LangChain's memory interface (`load_memory_variables`/`save_context`). `clear()` is an intentional no-op (memories are durable by design); use `agent.forget_user()` for real erasure. |
| LlamaIndex, CrewAI, AutoGen, OpenAI Agents SDK, Haystack, Semantic Kernel | Not implemented. Each would follow the same shape as the LangChain adapter — wrap `NeuroWeaveClient` behind that framework's memory/tool interface. Contributions welcome; see [Contributing](#contributing). |

## Configuration Reference

All settings live in `neurowave_engine/core/config.py` (Pydantic `BaseSettings`, overridable via `.env` or
environment variables — see `.env.example` for the ones you're actually likely to need to
change). The essentials:

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql://neuroweave:neuroweave@localhost:5432/neuroweave` | Postgres connection (needs pgvector) |
| `REDIS_URL` | `redis://localhost:6379/0` | Celery broker/backend + cache |
| `OPENAI_API_KEY` | _(required)_ | Embeddings + default chat provider |
| `ANTHROPIC_API_KEY` | _(optional)_ | Only needed for `provider="anthropic"` |
| `RUNTIME_API_KEY` | _(unset = no auth)_ | If set, gates every `/runtime/*` endpoint behind `X-API-Key` |
| `RUNTIME_DEFAULT_PROVIDER` / `RUNTIME_DEFAULT_MODEL` | `openai` / `gpt-4` | Default LLM for `/runtime/chat` when not specified per-call |
| `MEMORY_RETRIEVAL_TOP_K` | `10` | Default candidate pool size for retrieval |
| `MEMORY_CONTEXT_TOKEN_LIMIT` | `2000` | Default token budget for reconstructed context |

Beyond that, `neurowave_engine/core/config.py` has ~60 more tunables covering per-memory-type decay rates,
forgetting/archival thresholds, context-composer quality-score weights, dream-mode scheduling,
identity-shift evidence thresholds, and world-model merge/staleness thresholds — each documented
inline with a comment explaining the tradeoff it controls. Override only if you've read the
relevant service and know what you're changing.

## Running Locally

**Prerequisites:** Docker + Docker Compose, or Python 3.11+ and a local Postgres (with
`pgvector`) + Redis.

```bash
cp .env.example .env        # then set OPENAI_API_KEY at minimum
docker compose up -d        # postgres, redis, api, celery-worker, celery-beat
docker compose exec neuroweave alembic upgrade head
```

The API is now at `http://localhost:8000` (`/docs` for interactive Swagger, `/health` for
liveness). `./docker-start.sh` and `./quickstart.sh` automate the same steps.

**Without Docker:**
```bash
pip install -r requirements.txt
alembic upgrade head
uvicorn neurowave_engine.main:app --reload
# in separate terminals:
celery -A neurowave_engine.workers.celery_app worker --loglevel=info
celery -A neurowave_engine.workers.celery_app beat --loglevel=info
```

A `Makefile` wraps the common commands (`make install`, `make dev`, `make test`, `make
docker-up`).

## Production Deployment

Real, valid deployment artifacts ship in the repo. Note their actual verification status honestly:

- **`k8s/`** — namespace, configmap, secret template, API Deployment+Service+HPA (3→20 replicas),
  Celery worker Deployment+HPA (2→30 replicas) and Celery beat Deployment (pinned to exactly 1
  replica — a second beat process double-fires every scheduled task), and an nginx Ingress with
  WebSocket support for `/runtime/chat/stream`. **Not deployed against a live cluster in this
  project's development — validate against your own cluster before trusting it in production.**
- **`.github/workflows/ci.yml`** — runs the full test suite + SDK tests on every push/PR, builds
  the TypeScript SDK, and (on PRs) runs a "continuous evaluation" job that executes NeuroBench
  against a fresh synthetic dataset and uploads the results as a build artifact.
- **`grafana/neuroweave-dashboard.json`** — a real dashboard definition wired to the actual
  Prometheus metric names this app emits. Import it into a Grafana instance pointed at your
  `/metrics` endpoint.
- **`proto/neuroweave.proto`** — a valid gRPC service definition mirroring the REST surface. No
  gRPC server actually runs yet; the file's header comment gives the exact steps to stand one up
  (codegen → a servicer that reuses the same service classes the REST router calls → serve via
  `grpc.aio` alongside uvicorn).

## Observability

- **Prometheus** (`neurowave_engine/utils/prometheus_metrics.py`, scraped at `GET /metrics`): chat request
  counts by provider/status, chat latency histogram, memories-ingested counter by type,
  benchmark-run counter by strategy, dream-session counter by status.
- **`RuntimeMetricsService`** (`GET /runtime/metrics`, `GET /runtime/dashboard`): point-in-time
  rollups of memory/concept/identity/world counts, compression ratio, and cognitive health score
  — either global or per-user.
- **Structured logging** via the standard `logging` module throughout every service.
- **OpenTelemetry / distributed tracing is not implemented** — see [Roadmap](#roadmap).

## Security & Privacy

- **API-key auth**: `verify_api_key` (`neurowave_engine/core/security.py`) gates all `/runtime/*` routes when
  `RUNTIME_API_KEY` is set; it's a no-op when unset, which is intentional for local development
  but means you must set it before exposing this publicly.
- **RBAC scaffold**: `Role` (`ADMIN`/`DEVELOPER`/`READONLY`) and `ROLE_PERMISSIONS` exist in
  `neurowave_engine/core/security.py` but nothing currently checks a caller's role against a specific
  permission — only that *a* valid key was presented. Wiring `has_permission()` into individual
  routes is a natural next contribution.
- **GDPR "right to be forgotten"**: `DataDeletionService.delete_user()` performs a real,
  verified, cascading hard-delete of every row belonging to a user across all ~25 tables, in
  foreign-key-safe order. This is the one place in the codebase hard deletion is correct — every
  other memory-lifecycle operation is soft-delete/archive by design.
- **Everything else** (encryption at rest, SOC2/HIPAA/formal GDPR certification, multi-region
  disaster recovery) is infrastructure/legal/audit scope, not application code, and is not
  implemented here.

## Testing

```bash
pytest tests/ -v                                    # full backend suite
pytest sdk/python/tests/ -v                          # Python SDK (httpx.MockTransport, no live server)
cd sdk/typescript && npx tsc -p tsconfig.json --noEmit   # TypeScript typecheck
```

206 tests across the backend suite as of the last full run. One pre-existing, documented,
unrelated-to-any-subsystem issue: `tests/test_consolidation.py` references a `db_session` fixture
that no `conftest.py` currently provides (11 collection errors); a handful of Day 2/3 tests in
`test_cognitive_scoring.py`, `test_memory_state.py`, and `test_reinforcement.py` assert on
`str(enum_member)` behavior that differs across Python/SQLAlchemy versions, plus a couple of
float-equality assertions. None of these block any other subsystem — every other test file
passes clean. See `docs/archive/DAY5_PREDICTIVE_RECALL.md` for when this was first diagnosed.

Every subsystem was verified with both unit tests and a live end-to-end smoke script against a
real (SQLite, for speed) database — not just mocked unit tests — as part of its original build;
see the individual build logs in `docs/archive/` for what each smoke test actually exercised and
which real bugs it caught.

## Benchmarking (NeuroBench)

`NeuroBench` (`neurowave_engine/services/benchmark_suite.py`) compares memory strategies head-to-head on the
same query/history:

- `no_memory` — empty context (baseline floor)
- `raw_history` — dump the full conversation history, token-counted
- `neuroweave` — the real `ContextComposer` pipeline

`external_a` and `external_b` are registered as `MissingStrategy` slots for other memory
systems — calling them raises `NotImplementedError`, which `NeuroBench.run()` catches and skips
with a log line. **Their comparison numbers are never fabricated** — if you want a real
head-to-head against another product, implement a `BenchmarkStrategy` subclass for it (it slots
into `STRATEGY_REGISTRY` without touching `run()`'s logic) with the actual SDK installed.

```bash
curl -X POST localhost:8000/runtime/evaluate \
  -H "Content-Type: application/json" \
  -d '{"dataset": "synthetic", "user_count": 5, "seed": 42}'
```

Or generate a reproducible synthetic dataset directly: `DatasetGenerator(seed=42).generate_users(5)`
produces deterministic synthetic personas with realistic preference statements, contradictions,
project-evolution conversations, and identity shifts — used both by NeuroBench and by the CI
"continuous evaluation" job.

Metrics captured per run: latency, token usage, prompt-token-reduction %, and a mix of directly
measured values (latency, tokens, compression ratio) and heuristic proxies (personalization,
reasoning, hallucination-rate — derived from `ContextComposer`'s own quality/alignment scoring,
not an independent LLM-judge evaluation).

## Known Limitations

- Memory scoring in the live chat hot path is heuristic (no LLM call) by design — an explicit
  latency/cost tradeoff. The full LLM-based extraction service exists and is used by
  `/memory/ingest`, just not by `RuntimeOrchestrator.chat()`'s inline ingestion.
- WebSocket streaming (`/runtime/chat/stream`) is turn-complete, not token-streamed: the full
  response is generated, then chunked into fixed-size pieces for delivery. True token streaming
  needs each `LLMProvider` to support a streaming completion API.
- No gRPC server runs yet (proto file only — see Production Deployment).
- Only the LangChain framework integration is implemented; 6 others are documented-as-the-same-
  pattern but not built.
- `neurowave_engine/models/` contains a legacy repository-pattern module (`UserRepository`, `MemoryRepository`)
  from the very first build that predates `neurowave_engine/db/models.py` + the service-layer pattern every
  later subsystem uses. Nothing in the current codebase imports it. It's flagged here rather than
  removed so a maintainer can confirm before deleting it.
- RBAC permission checks aren't enforced yet (see Security & Privacy above).
- OpenTelemetry tracing isn't implemented (Prometheus metrics are).

## Roadmap

Roughly in order of leverage:

1. Wire `has_permission()` RBAC checks into `/runtime/*` routes.
2. True token-streamed chat (extend `LLMProvider` with a `stream()` method).
3. Implement the gRPC servicer described in `proto/neuroweave.proto`.
4. Real `BenchmarkStrategy` implementations for other memory systems, for head-to-head NeuroBench comparisons.
5. Additional framework integrations (LlamaIndex, CrewAI, AutoGen, OpenAI Agents SDK, Haystack,
   Semantic Kernel) following the LangChain adapter's pattern.
6. OpenTelemetry distributed tracing alongside the existing Prometheus metrics.
7. Remove or repurpose the dead `neurowave_engine/models/` legacy module.

## Contributing

Issues and PRs are welcome. See [CONTRIBUTING.md](../CONTRIBUTING.md) for setup and expectations.
Before opening a PR that adds a subsystem, skim [The Full Pipeline](#the-full-pipeline) and the
relevant service files under `neurowave_engine/services/` to keep the same design philosophy: heuristics in
hot paths, LLM calls only where their cost is justified, soft-delete by default, and real tests
(unit + a live end-to-end smoke check) for anything you add.
