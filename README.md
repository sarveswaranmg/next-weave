# NeuroWeave

**A cognitive memory engine and runtime platform for AI agents.**

NeuroWeave gives your AI agent structured, evolving, long-term memory instead of raw chat
history or flat vector RAG. It extracts what matters from a conversation, consolidates related
facts into concepts, builds a model of who the user is and what they're working on, forgets what
stops mattering, and assembles a token-budgeted context on demand — all behind a single
`chat()` call.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)

```python
from neurowave import Memory

m = Memory()  # local SQLite file, no server/Docker/Postgres/Redis required
m.chat(user_id="alice", message="I'm building a Rust backend for a startup called Nexus.")
m.chat(user_id="alice", message="What language am I using again?")
# -> remembers, without you re-sending any history
```

## Why

Most LLM "memory" is either the full chat log pasted back into every prompt (unbounded token
cost) or flat vector retrieval over raw messages (no structure, nothing ever consolidates or
gets forgotten). NeuroWeave instead gives memory a real lifecycle: extraction → scoring →
consolidation → decay/forgetting → predictive, budget-aware recall — the same shape human
memory actually has. See [**docs/DOCUMENTATION.md**](docs/DOCUMENTATION.md#why-neuroweave) for
the full rationale.

## Features

- **Structured memory extraction** — episodic / semantic / identity / procedural, scored and
  typed, not raw text blobs.
- **Semantic consolidation** — related memories cluster into higher-level concepts over time.
- **Identity graph** — an explicit, evolving model of who the user is.
- **World model** — tracks projects, technologies, entities, and decisions from conversation.
- **Predictive, budget-aware recall** — assembles a token-budgeted context, not just top-K nearest
  neighbors.
- **Memory evolution & forgetting** — decay, archival, and revival instead of unbounded growth;
  soft-delete by default.
- **Dream mode** — offline consolidation during idle periods (pattern discovery, contradiction
  resolution, knowledge synthesis).
- **Runtime platform** — one `RuntimeOrchestrator.chat()` pipeline wiring all of the above behind
  REST, WebSocket, and SDK entry points, model-agnostic across 9 LLM providers.
- **NeuroBench** — a built-in benchmark suite comparing memory strategies (no-memory vs.
  raw-history vs. NeuroWeave) on real, measured metrics.
- **Python & TypeScript SDKs**, plus a LangChain memory adapter.
- **Production scaffolding** — Prometheus metrics, GDPR-compliant hard-deletion, API-key auth,
  Docker Compose, Kubernetes manifests, CI with a continuous-evaluation benchmark job.

## Quick Start (embedded — no server)

The fastest way to try NeuroWeave: it runs in-process against a local SQLite file — no Docker,
Postgres, Redis, or Celery.

```bash
pip install -e .                          # from a NeuroWeave checkout - the engine (lean core)
pip install -e "sdk/python[embedded]"      # the SDK's embedded Memory() entry point
export OPENAI_API_KEY=sk-...               # embeddings (search) - always required
export GOOGLE_API_KEY=...                  # free-tier Gemini, the default chat provider
```

```python
from neurowave import Memory

m = Memory()  # creates ./neurowave.db on first use
m.chat(user_id="alice", message="I'm building a Rust backend for a startup called Nexus.")
result = m.chat(user_id="alice", message="What language am I using again?")
print(result["response"])

m.add(user_id="alice", content="Alice prefers concise answers.")   # store without an LLM call
m.search(query="Rust backend", user_id="alice")                    # ranked recall
m.forget_user(user_id="alice")                                     # GDPR/CCPA erasure
```

`user_id` can be any string (`"alice"`, an internal user PK, etc.) — it's mapped to a stable
UUID internally, so you don't need to generate one yourself. This runs the exact same
`RuntimeOrchestrator` cognitive pipeline as the hosted server, just in-process and single-tenant.
For a real multi-tenant, horizontally-scaled deployment, see **Self-Hosted / Production** below.

**Known limitation:** embeddings (used by `search()`/`chat()`'s recall step) always go through
OpenAI today — there's no offline/local embedding model yet. A local embedding option is a
natural follow-up.

## Self-Hosted / Production

For a real multi-tenant deployment (horizontal scaling, a shared Postgres+pgvector store,
background consolidation via Celery):

**Prerequisites:** Docker + Docker Compose (or Python 3.11+ with a local Postgres+pgvector and
Redis).

```bash
git clone <this-repo-url>
cd NextWeave
cp .env.example .env            # set OPENAI_API_KEY (embeddings) and GOOGLE_API_KEY (free chat provider) at minimum
docker compose up -d            # postgres, redis, api, celery-worker, celery-beat
docker compose exec neuroweave alembic -c migrations/alembic.ini upgrade head
```

NeuroWeave is multi-tenant: every `/runtime/*` request authenticates with an `X-API-Key`
belonging to a tenant (see [Multi-Tenancy & Auth](docs/DOCUMENTATION.md#multi-tenancy--auth)).
Bootstrap your first tenant + key:

```bash
docker compose exec neuroweave python scripts/bootstrap_tenant.py --name "My Company" --email me@example.com
# prints: Tenant (tenant_id): ...  API key (shown once, store it now): nw_live_...
```

That's the admin-run path for tenants you create yourself. To let other people create their own
tenant without you running anything, point them at `http://localhost:8000/signup` — a public
signup page (email verification, one free-tier API key per account, capped at
`FREE_TIER_MONTHLY_CHAT_LIMIT` calls/month, no billing yet). See
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md#letting-others-self-serve-sign-up) for the production
setup (SMTP, rate limiting).

The API is now live at `http://localhost:8000` — try `/docs` for interactive Swagger, or:

```bash
curl -X POST localhost:8000/runtime/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: nw_live_..." \
  -d '{"user_id": "00000000-0000-0000-0000-000000000001", "message": "I prefer concise answers and I work with FastAPI and PostgreSQL.", "provider": "echo"}'
```

Without Docker:
```bash
pip install -e ".[server]"
alembic -c migrations/alembic.ini upgrade head
uvicorn neurowave_engine.main:app --reload
```

### Using the REST client SDK

```bash
pip install -e sdk/python[dev]
```
```python
from neurowave import CognitiveAgent

agent = CognitiveAgent(provider="google", base_url="http://localhost:8000")
result = agent.chat(user_id="...", message="...")
agent.explain(user_id="...", subject_type="decision")   # why did it respond this way?
agent.forget_user(user_id="...")                          # GDPR erasure
```

TypeScript:
```bash
cd sdk/typescript && npm install && npm run build
```
```ts
import { CognitiveAgent } from "neurowave";
const agent = new CognitiveAgent({ provider: "google", baseUrl: "http://localhost:8000" });
await agent.chat(userId, "...");
```

## Deploying to Production

**[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)** — step-by-step guide for a single-server Docker
Compose deploy with automatic HTTPS (Caddy) and an optional GitHub Actions CI/CD trigger. For a
Kubernetes cluster instead, see **[k8s/README.md](k8s/README.md)**.

## Documentation

**[docs/DOCUMENTATION.md](docs/DOCUMENTATION.md)** is the complete reference: architecture, the
full memory pipeline, database schema, every API endpoint, SDK usage, configuration reference,
deployment (Docker/K8s/CI), observability, security & privacy, testing, and the NeuroBench
benchmark methodology — plus an honest list of known limitations and the roadmap.

This project was originally built incrementally across ten milestones; the detailed build logs
(what was built, what was tested, and real bugs found and fixed at each stage) are preserved in
[`docs/archive/`](docs/archive/) for anyone who wants the implementation history.

## Testing

```bash
pytest tests/ -v                                          # backend suite
pytest sdk/python/tests/ -v                                # Python SDK
cd sdk/typescript && npx tsc -p tsconfig.json --noEmit     # TypeScript typecheck
```

## Contributing

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for setup, the project's
design philosophy, and PR expectations.

## License

[MIT](LICENSE)
