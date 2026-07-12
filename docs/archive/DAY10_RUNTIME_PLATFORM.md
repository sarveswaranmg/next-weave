# NeuroWeave — Day 10: Cognitive Runtime Platform, SDK & Benchmark Suite

## Overview

Day 10 turns the nine days of cognitive-memory pipeline work (extraction,
consolidation, identity, predictive recall, context composition, memory
evolution, dream mode, world modeling) into a **product**: a single
`RuntimeOrchestrator.chat()` entry point that runs the whole pipeline behind
one call, a REST + WebSocket API to reach it from outside the process, a
Python and TypeScript SDK to reach it from application code, an
explainability layer to answer "why did the system respond this way," a
benchmark suite (NeuroBench) that quantifies what memory actually buys over
no-memory/raw-history baselines, and the observability/security/deployment
scaffolding a real service needs (Prometheus metrics, API-key auth, GDPR
hard-deletion, K8s manifests, CI).

This is the capstone day of the arc, so the scope drawn here is explicit
about what's genuinely built-and-verified in this sandbox versus what's a
real, usable artifact that hasn't been executed against live infrastructure
versus what's out-of-scope guidance. See **Honest Scope Boundary** below —
read that section before assuming anything in this doc is "deployed."

## Pipeline

```
Client (Python/TS SDK, curl, LangChain memory adapter)
        │
        ▼
POST /runtime/chat  (or WS /runtime/chat/stream)
        │  [API-key auth via verify_api_key, Prometheus record_chat]
        ▼
RuntimeOrchestrator.chat(user_id, message, provider, model, ...)
        │
        ├─ _ensure_user()                         (create User row if missing)
        ├─ _ingest(message, ...)                    heuristic score_memory() → Memory row
        ├─ WorldModelPipeline.update(...)            (Day 9)   — entities/relationships
        ├─ ContextComposer.compose(...)   OR
        │  PredictiveRecallPipeline.run(...)          (Day 6 / Day 5) — assembled context
        ├─ get_provider(provider).complete(system_prompt, message, model)
        │       └─ EchoProvider / OpenAIProvider / AnthropicProvider /
        │          OpenAICompatibleProvider(google/mistral/deepseek/llama/qwen/vllm/ollama)
        │          — any provider failure silently falls back to EchoProvider
        ├─ _ingest(response, PROCEDURAL)             store assistant turn too
        └─ _schedule_background()                    Celery: consolidation + retention
                (never raises — broker absence can't fail the chat request)
        │
        ▼
ChatResponse {response, provider, model, usage, memory_stored,
              world_model, context, background_scheduled,
              stage_latency_ms, total_latency_ms}
```

`ExplainabilityEngine`, `NeuroBench`, `RuntimeMetricsService`, and
`DataDeletionService` sit alongside the orchestrator as independent
read/analysis/lifecycle services — none of them are in the hot chat path.

## Components

| Component | File | Responsibility |
|---|---|---|
| `LLMProvider` abstraction | `app/services/llm_providers.py` | Model-agnostic completion across 9 providers via one `OpenAICompatibleProvider` adapter + dedicated OpenAI/Anthropic clients; `EchoProvider` fallback on any failure |
| `RuntimeOrchestrator` | `app/services/runtime_orchestrator.py` | The core `chat()` pipeline wiring memory, world model, context composition, provider call, and background scheduling |
| `ExplainabilityEngine` | `app/services/explainability_engine.py` | Answers "why" for a memory, retrieval, identity shift, dream session, or decision |
| `PluginRegistry` / `CognitivePlugin` | `app/services/plugin_system.py` | ABC + registry for `on_message`/`on_memory_created`/`on_response` hooks; per-plugin exception isolation |
| `DatasetGenerator` | `app/services/dataset_generator.py` | Deterministic (seeded) synthetic users/conversations with contradictions and identity shifts, for benchmarking |
| `NeuroBench` | `app/services/benchmark_suite.py` | `BenchmarkStrategy` comparison (no-memory / raw-history / NeuroWeave; Mem0/Zep explicitly stubbed as `MissingStrategy`, not faked) |
| Prometheus metrics | `app/utils/prometheus_metrics.py` | Real counters/histograms for chat requests, latency, memory ingestion, benchmark runs, dream sessions |
| `RuntimeMetricsService` | `app/services/runtime_metrics_service.py` | Rolls up memory/concept/identity/world counts + compression ratio + cognitive health into a persisted snapshot |
| `security.py` | `app/core/security.py` | `Role`/`ROLE_PERMISSIONS` RBAC scaffold + `verify_api_key` dependency (no-op if unconfigured) |
| `DataDeletionService` | `app/services/data_deletion_service.py` | GDPR "right to be forgotten" — real cross-table cascading hard-delete in FK-safe order |
| Runtime API | `app/api/runtime.py` | REST + WebSocket surface: chat, streaming chat, benchmark, evaluate, metrics, health, version, explain, plugins, dashboard, user deletion |
| Python SDK | `sdk/python/` | `NeuroWeaveClient` (httpx, testable via `transport=`), `CognitiveAgent` (matches the spec's exact example), LangChain memory adapter |
| TypeScript SDK | `sdk/typescript/` | Mirrors the Python SDK's shape using native `fetch`, zero runtime deps |

## Database Changes

Migration `010_runtime_platform.py` (`down_revision='009'`) adds:

- **`benchmark_runs`** — one row per `(strategy, user, dataset)` comparison: latency, token usage,
  prompt-token-reduction %, precision/recall/task-completion/personalization/reasoning/hallucination
  scores, long-term-consistency & identity-continuity & world-model-accuracy scores, storage growth,
  compression ratio, cost, interaction count, `extra_metadata`.
- **`runtime_metrics`** — periodic rollup snapshots (global when `user_id IS NULL`, else per-user):
  memory/concept/identity-node/world-node/relationship/project counts, compression ratio, cognitive
  health score, latency, `extra_metadata`.

Both follow the established `extra_metadata = Column("metadata", ...)` pattern to avoid the
SQLAlchemy `Base.metadata` collision (root-caused Day 5).

## API

All `/runtime/*` routes require `verify_api_key` (no-op unless `RUNTIME_API_KEY` is set); `/metrics`
is unauthenticated (standard Prometheus scrape convention).

| Endpoint | Method | Purpose |
|---|---|---|
| `/runtime/chat` | POST | Run the full orchestrator pipeline once, synchronously |
| `/runtime/chat/stream` | WS | Same pipeline; response chunked into 40-char frames + a final `done` frame (see limitation below) |
| `/runtime/benchmark` | POST | Run `NeuroBench` against a single query/history for one user |
| `/runtime/evaluate` | POST | Run `NeuroBench.run_dataset` and return a per-strategy averaged summary |
| `/runtime/metrics` | GET | `RuntimeMetricsService` snapshot (global or per-user) |
| `/runtime/health` | GET | `SELECT 1` liveness check |
| `/runtime/version` | GET | `settings.runtime_version` |
| `/runtime/explain` | GET | `ExplainabilityEngine.explain(user_id, subject_type, subject_id)` |
| `/runtime/plugins` | POST | `list`/`unregister` against the default plugin registry (`register` returns 400 — requires a Python import, can't be done over HTTP) |
| `/runtime/dashboard` | GET | Combined metrics + health snapshot for a lightweight ops view |
| `/runtime/users/{user_id}` | DELETE | `DataDeletionService.delete_user` — hard delete, GDPR |
| `/metrics` | GET | Prometheus text exposition (`prometheus_client.generate_latest`) |

## Test Cases (validated in `tests/test_runtime_platform.py` + `sdk/python/tests/test_sdk.py`, 35/35 passing, and live end-to-end)

- **Providers (4 tests):** echo works with no network; unknown provider name falls back to echo;
  `openai` with no API key falls back to echo (test isolates the ambient `OPENAI_API_KEY` env var via
  `monkeypatch` — see Bugs section); all 9 documented provider names resolve to *some* `LLMProvider`.
- **Orchestrator (4 tests):** full pipeline stores both the user and assistant turns as memories;
  auto-creates the user if missing; `memory=False` stores nothing; background Celery scheduling never
  raises even with no broker configured.
- **Explainability (3 tests):** memory explanation includes lifecycle info; unknown subject type
  returns a structured "not found" rather than raising; identity-shift explanation returns an empty
  list (not an error) when there are no shifts yet.
- **Plugins (4 tests):** default registry ships with `CuriosityPlugin` pre-registered; a custom
  registry correctly invokes registered plugins; one plugin raising doesn't stop others from running;
  unregister works.
- **Dataset generator (3 tests):** same seed → identical output; generated users include both
  contradictions and identity shifts; long-conversation generator produces the requested length.
- **NeuroBench (3 tests):** strategies are genuinely compared against each other; a missing strategy
  (`mem0`/`zep`) is skipped and logged, never faked with synthetic numbers; `run_dataset` generates
  real `User`/`Memory` rows and benchmarks them.
- **Runtime metrics (3 tests):** counts memories correctly; persists a row by default; can skip
  persistence.
- **Data deletion (2 tests):** full deletion removes every row across every table; deleting a
  nonexistent user is a safe no-op.
- **Python SDK (9 tests, `httpx.MockTransport`, no live server needed):** chat payload correctness,
  API-key header propagation, explain query params, HTTP errors surface as `httpx.HTTPStatusError`,
  delete uses the DELETE verb; `CognitiveAgent` forwards constructor flags into the chat body,
  per-call kwargs override constructor defaults, `explain()` delegates correctly, context-manager
  `__exit__` closes the underlying client.
- **Live end-to-end smoke test** (fresh SQLite DB, no mocks): ran two real `orchestrator.chat()` turns
  end-to-end (world model update + memory storage + echo provider response), `ExplainabilityEngine`,
  `RuntimeMetricsService`, `NeuroBench.run()` across all three real strategies, `NeuroBench.run_dataset()`
  generating and benchmarking synthetic users, and a full `DataDeletionService.delete_user()` cascade —
  all completed without error.
- **Full cross-day regression:** `pytest tests/ --ignore=tests/test_identity.py -q` → **172 passed**.
  The remaining 6 failures + 11 errors are the pre-existing, already-documented (Day 5 doc, "Known
  Pre-Existing Issues") `test_consolidation.py` missing-`db_session`-fixture issue and a handful of
  Day 2/3 `str(enum_member)`/float-equality assertions in `test_cognitive_scoring.py`,
  `test_memory_state.py`, `test_reinforcement.py` — confirmed via `git diff` that none of those files
  were touched by Day 10 work, so these are not regressions.
- **App boot / route registration:** `app.openapi()` lists all 10 new REST paths under `/runtime/*`
  plus `/metrics`; the WebSocket route `/runtime/chat/stream` is present in the router tree (confirmed
  by walking `original_router.routes` — this FastAPI version wraps included routers in a lazy
  `_IncludedRouter`, so `app.routes` alone doesn't show sub-router contents).
- **TypeScript SDK:** `tsc -p tsconfig.json --noEmit` → zero errors, `strict: true`.

## Bugs Found and Fixed During This Build

Unlike every previous day, end-to-end verification here did **not** surface a source-code bug in the
new Day 10 components themselves. Two issues did surface during verification, both correctly
attributable elsewhere:

1. **Test isolation gap, not a source bug** — `test_openai_without_key_falls_back_to_echo` initially
   failed because it asserted `get_provider("openai", api_key=None)` returns `EchoProvider`, but got a
   real `OpenAIProvider` back. Root cause: the test run command's ambient `OPENAI_API_KEY=sk-test-...`
   environment variable (required since Day 5 because `MemoryExtractionService` eagerly instantiates
   an OpenAI client at import time) was picked up by `settings.openai_api_key`, which `OpenAIProvider`
   correctly falls back to when no explicit key is passed — that fallback is the intended behavior, not
   a bug. Fixed by isolating the test with
   `monkeypatch.setattr("app.services.llm_providers.settings.openai_api_key", "")` rather than touching
   source.
2. **My own smoke-test script bug** — an ad hoc verification script passed `str(uuid.uuid4())` as
   `user_id` directly to `RuntimeOrchestrator.chat()`, which queries `User.id` (a UUID column) with a
   plain Python `str`; SQLite's GUID type processor expects a real `uuid.UUID` object and raised
   `AttributeError: 'str' object has no attribute 'hex'`. The REST layer never hits this because
   `ChatRequest.user_id: UUID` in `app/schemas/runtime.py` already parses incoming JSON strings into
   `UUID` objects via Pydantic before the orchestrator ever sees them — confirmed correct by checking
   every `user_id` field in `app/schemas/runtime.py`. Fixed the smoke script, not the source.

## Known Limitations

- **WebSocket streaming is turn-complete, not token-streamed.** `/runtime/chat/stream` runs the full
  orchestrator pipeline synchronously per frame, then chunks the *already-complete* response into
  40-character pieces before sending. True token-by-token streaming would require every `LLMProvider`
  to support a streaming completion API (most of the OpenAI-compatible vendors do via SSE) — that
  plumbing is real future work, not implemented here.
- **gRPC is a `.proto` file, not a server.** `proto/neuroweave.proto` defines a real, valid proto3
  service mirroring the REST surface, with an in-file comment giving the exact 3-step path
  (`grpc_tools.protoc` codegen → a servicer that reuses the same service classes `app/api/runtime.py`
  already calls → serve via `grpc.aio` alongside uvicorn) — but no server actually runs in this build.
- **6 of 7 requested framework integrations are not implemented.** Only LangChain
  (`sdk/python/neurowave/integrations/langchain.py`) is real code. LlamaIndex, CrewAI, AutoGen, OpenAI
  Agents SDK, Haystack, and Semantic Kernel would each follow the same shape (wrap `NeuroWeaveClient`
  behind that framework's memory/tool interface) but weren't built — implementing and testing six
  more framework adapters honestly wasn't feasible in this session alongside everything else.
- **`clear()` on the LangChain memory adapter is an intentional no-op.** NeuroWeave memories are
  durable by design (soft-delete/never-hard-delete, established Day 2); the adapter's docstring directs
  callers to `client.delete_user()` for actual erasure rather than silently discarding history.
- **NeuroBench's `mem0`/`zep` strategies are explicitly unimplemented, not faked.** `MissingStrategy`
  raises `NotImplementedError`, which `NeuroBench.run()` catches and skips with a log line — there was
  no attempt to synthesize plausible-looking comparison numbers for competitor products without
  actually running them.
- **Personalization/reasoning/hallucination-rate scores in `BenchmarkRun` are heuristic proxies**,
  not LLM-graded evaluations — no evaluator model is called. They're derived from context
  quality/identity/goal alignment signals already computed by `ContextComposer` (Day 6), not an
  independent judgment of the actual generated response's quality.
- **K8s manifests, the Grafana dashboard JSON, and the GitHub Actions CI workflow are real, valid
  artifacts that were not executed against live infrastructure** in this sandbox (no cluster, no
  Grafana instance, no GitHub Actions runner available here). The CI workflow's `benchmark` job was
  sanity-checked by manually running the equivalent Python inline in this environment (see the Test
  Cases section — this is exactly the `run_dataset` call the CI job would make).
- **Security/compliance requirements from the spec (SOC2, HIPAA, GDPR/CCPA certification, encryption
  at rest, multi-region DR) are documented guidance, not code**, except for the two pieces that are
  genuinely implementable as code without external infrastructure: API-key auth
  (`verify_api_key`) + an RBAC role/permission scaffold (`Role`, `ROLE_PERMISSIONS`), and the GDPR
  "right to be forgotten" hard-delete (`DataDeletionService`, verified end-to-end above).
- **RuntimeOrchestrator uses heuristic memory scoring (`score_memory(..., use_llm=False)`), not the
  full LLM-based extraction service**, in the chat hot path — an explicit latency tradeoff documented
  inline in the source, consistent with the dependency-free-hot-path philosophy established Day 2.

## Scalability Notes

- `RuntimeOrchestrator._schedule_background()` wraps every `.delay()` call in its own try/except so a
  missing or overloaded Celery broker degrades to "chat works, background consolidation doesn't run
  this cycle" rather than failing the user-facing request — the same fail-open pattern used for
  provider fallback.
- The `k8s/worker-deployment.yaml` HPA scales Celery workers 2→30 replicas on CPU; the API deployment
  scales 3→20. Celery beat is pinned to `replicas: 1` with an explicit in-file comment — running more
  than one beat scheduler double-fires every scheduled task (memory evolution ticks, dream-mode
  scheduling, retention enforcement), a correctness constraint, not a preference.
- `RuntimeMetricsService` and `NeuroBench` are both read/analysis-only relative to the hot chat path —
  neither is called synchronously from `/runtime/chat`, so benchmark or metrics load never adds
  latency to a live chat request.
- `DataDeletionService` deletes in explicit FK-dependency order (embeddings → events → snapshots →
  ... → the `User` row last) using bulk `.filter(...).delete(synchronize_session=False)` per table
  rather than loading and deleting ORM objects one at a time — this keeps a full-user deletion to one
  query per table regardless of row count.
- `OpenAICompatibleProvider` means adding a 10th, 11th, ... LLM vendor is a one-line addition to
  `_PROVIDER_FACTORIES` (a `base_url` + `provider_name`), not a new class, as long as the vendor
  exposes an OpenAI-compatible `/chat/completions` endpoint (true for most current OSS-model hosts).

## Future Extensibility

- **Token-streamed chat:** extend `LLMProvider.complete()` with a `stream()` variant, have
  `/runtime/chat/stream` call it and forward chunks directly instead of chunking a completed response.
- **gRPC server:** implement the `CognitiveRuntimeServicer` described in `proto/neuroweave.proto`'s
  header comment, sharing the exact same service-layer classes the REST router already calls, so REST
  and gRPC never diverge in pipeline logic.
- **Remaining framework integrations:** LlamaIndex/CrewAI/AutoGen/OpenAI Agents SDK/Haystack/Semantic
  Kernel adapters can all follow `sdk/python/neurowave/integrations/langchain.py`'s shape — wrap
  `NeuroWeaveClient`, translate that framework's memory/tool-call interface into
  `compose_context`/`ingest_memory`/`chat` calls.
- **Real Mem0/Zep benchmark strategies:** once those SDKs are an approved dependency,
  `BenchmarkStrategy` subclasses replacing the `MissingStrategy` stubs in `STRATEGY_REGISTRY` slot in
  without touching `NeuroBench.run()`'s comparison logic.
- **OpenTelemetry tracing:** the Prometheus metrics module already isolates a custom `registry`
  (`app/utils/prometheus_metrics.py`); a parallel `app/utils/tracing.py` wrapping
  `RuntimeOrchestrator.chat()`'s stages in OTel spans would slot into the same per-stage
  `stage_latency_ms` breakdown the orchestrator already computes.
- **Multi-tenant RBAC enforcement:** `Role`/`ROLE_PERMISSIONS` in `app/core/security.py` currently
  defines the permission model but nothing in `app/api/runtime.py` checks a caller's role against a
  specific permission yet (`verify_api_key` only checks that *a* valid key was presented) — wiring
  `has_permission()` into each route's dependency chain is the natural next step.

## Honest Scope Boundary

Given this was, by a wide margin, the largest single-day prompt of the ten-day arc, here's exactly
what's real versus what's guidance:

**Real, tested, working code:** `LLMProvider` abstraction (9 providers, verified fallback-to-echo
behavior), `RuntimeOrchestrator` (full pipeline, live end-to-end tested), `ExplainabilityEngine`,
`PluginRegistry`, `DatasetGenerator`, `NeuroBench` (verified against real synthetic data, no faked
competitor numbers), Prometheus metrics + `RuntimeMetricsService`, `DataDeletionService` (verified
full cascading deletion), the full `/runtime/*` REST API + WebSocket route, the Python SDK (client +
agent + LangChain adapter, 9/9 tests passing against `httpx.MockTransport`), the TypeScript SDK
(typechecks clean, `strict: true`).

**Real artifacts, not executed against live infrastructure here:** the 5 K8s manifests, the GitHub
Actions CI workflow (its logic was manually sanity-checked by running the equivalent Python inline —
see Test Cases — but no actual GitHub Actions runner executed it), the Grafana dashboard JSON
(references real Prometheus metric names, never rendered against a live Grafana), the gRPC `.proto`
(valid proto3, no server implements it).

**Explicitly out of scope, documented as guidance only:** actual SOC2/HIPAA/GDPR certification
(GDPR's core mechanical requirement — user data deletion — *is* implemented and tested;
certification itself is a legal/audit process, not code), live multi-region deployment, encryption at
rest (an infra/KMS concern, not application code), 6 of 7 requested framework integrations beyond
LangChain.

This mirrors the scoping approach stated at the start of Day 10's build and held consistent
throughout: build everything genuinely real and verify it the same way every prior day was verified,
and be explicit in-repo about the boundary rather than presenting an unexecuted artifact as a tested
one.
