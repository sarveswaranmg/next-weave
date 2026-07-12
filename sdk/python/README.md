# NeuroWeave Python SDK

Integrate the NeuroWeave Cognitive Runtime Platform into any AI agent in
under five minutes.

## Install

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
    provider="openai",
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
