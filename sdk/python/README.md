# NeuroWeave Python SDK

Integrate the NeuroWeave Cognitive Runtime Platform into any AI agent in
under five minutes — either embedded (no server) or against a running
NeuroWeave deployment.

## Local / embedded mode (no server)

The mem0-style zero-server path: runs in-process against a local SQLite
file, no Docker/Postgres/Redis/Celery required.

```bash
# From a NeuroWeave checkout:
pip install -e .                          # the engine (repo root)
pip install -e "sdk/python[embedded]"
```

```python
from neurowave import Memory

m = Memory()  # ./neurowave.db on first use
m.chat(user_id="alice", message="I'm building a Rust backend for a startup called Nexus.")
result = m.chat(user_id="alice", message="What language am I using again?")
print(result["response"])

m.add(user_id="alice", content="Alice prefers concise answers.")
m.search(query="Rust backend", user_id="alice")
m.forget_user(user_id="alice")  # GDPR/CCPA erasure
```

`user_id` accepts any string — it's mapped to a stable UUID internally.
Requires `OPENAI_API_KEY` (embeddings) and, for the default `google`
provider, `GOOGLE_API_KEY`.

## Against a running server

```bash
# From a NeuroWeave checkout:
pip install -e sdk/python

# With the LangChain integration:
pip install -e "sdk/python[langchain]"
```

## Quick Start

```python
from neurowave import CognitiveAgent

agent = CognitiveAgent(
    provider="google",
    memory=True,
    world_model=True,
    predictive_recall=True,
    context_composer=True,
)

response = agent.chat(
    user_id="123",
    message="Help me design a distributed cache.",
)

print(response["response"])
```

Point `base_url` at your running NeuroWeave server (defaults to
`http://localhost:8000`):

```python
agent = CognitiveAgent(base_url="https://neuroweave.your-domain.com", api_key="...")
```

## Lower-level access

For anything beyond `chat()` — explaining a decision, checking runtime
metrics, running a benchmark — use `NeuroWeaveClient` directly, or reach
through `agent.client`:

```python
from neurowave import NeuroWeaveClient

client = NeuroWeaveClient(base_url="http://localhost:8000")
print(client.metrics(user_id="123"))
print(client.explain(user_id="123", subject_type="memory", subject_id="..."))
```

## Framework Integrations

```python
from neurowave.integrations.langchain import NeuroWeaveMemory

memory = NeuroWeaveMemory(user_id="123")
chain = ConversationChain(llm=llm, memory=memory)
```

See `DAY10_RUNTIME_PLATFORM.md` in the repo root for the full list of
supported and planned framework integrations.

## Privacy

```python
agent.forget_user(user_id="123")  # GDPR/CCPA right to be forgotten
```
