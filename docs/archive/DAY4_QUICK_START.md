# 🚀 DAY 4: IDENTITY GRAPH ENGINE — QUICK START

## 5-MINUTE SETUP

### 1. Apply Database Migration

```bash
cd /Users/sarves/Desktop/NextWeave

# Apply migration
alembic upgrade head

# Verify tables created
sqlite3 neuroweave.db ".tables" | grep identity
```

### 2. Start the API Server

```bash
# Terminal 1: Start FastAPI
python -m app.main

# Expected output:
# INFO:     Application startup complete
# Uvicorn running on http://127.0.0.1:8000
```

### 3. Trigger Identity Extraction

```bash
# Extract from a user's concepts/memories
curl -X POST "http://localhost:8000/identity/extract?user_id=<user_id>&use_concepts=true&num_items=50"

# Response:
# {
#   "user_id": "...",
#   "operation": "extract_identity",
#   "traits_extracted": 12,
#   "nodes_created": 8,
#   "graph_updated": true
# }
```

### 4. View User Profile

```bash
curl "http://localhost:8000/identity/profile?user_id=<user_id>"

# Response shows:
# - summary: "Working towards: Software Engineering Growth..."
# - goals: [{ value: "software_engineering_growth", confidence: 0.85 }]
# - interests: [{ value: "distributed_systems", confidence: 0.80 }]
# - communication_style: { primary: "concise", confidence: 0.75 }
```

---

## COMMON WORKFLOWS

### Extract Identity from Memories

```python
from app.db.database import get_db_session
from app.services.identity_extractor import IdentityExtractor
from app.db.models import Memory

session = get_db_session()

# Get user memories
user_id = "user_001"
memories = session.query(Memory).filter(
    Memory.user_id == user_id
).limit(50).all()

# Extract traits
extractor = IdentityExtractor(session)
traits = extractor.extract_from_memories(user_id, memories)

print(f"Extracted traits: {traits}")
```

### Reinforce a Trait

```python
from app.services.identity_reinforcement import IdentityReinforcementService

service = IdentityReinforcementService(session)

# Reinforce a specific trait
node_id = "..."
success, updated_node = service.reinforce_trait(
    user_id=user_id,
    node_id=node_id,
    confidence_boost=0.1,
    evidence_source="user_interaction"
)

print(f"New confidence: {updated_node.confidence}")
```

### Build and Analyze Graph

```python
from app.services.identity_graph import IdentityGraphService

graph_service = IdentityGraphService(session)

# Build graph
graph = graph_service.build_graph_for_user(user_id)

# Get statistics
stats = graph_service.get_graph_statistics(user_id)
print(f"Graph has {stats['nodes']} traits, {stats['edges']} relationships")

# Find related traits
trait_id = "..."
related = graph_service.find_related_traits(user_id, trait_id)
print(f"Related traits: {related}")
```

### Generate User Profile

```python
from app.services.identity_profile_generator import IdentityProfileGenerator

generator = IdentityProfileGenerator(session)

# Get full profile
profile = generator.generate_profile(user_id)
print(f"Summary: {profile['summary']}")
print(f"Goals: {profile['goals']}")
print(f"Skills: {profile['skills']}")

# Get concise profile (one-liner)
concise = generator.generate_concise_profile(user_id)
print(f"Concise: {concise}")
```

### Personalize Retrieval Context

```python
from app.services.identity_context_builder import IdentityAwareContextBuilder

builder = IdentityAwareContextBuilder(session)

# Build personalized context for a query
query = "What should I learn next?"
context = builder.build_personalized_context(
    user_id=user_id,
    query=query,
    concepts=[]  # Retrieved concepts
)

print(f"Communication style: {context['communication_style']}")
print(f"Personalization: {context['personalization_instructions']}")
```

---

## ASYNC PROCESSING (CELERY)

### Extract in Background

```python
from app.workers.tasks import extract_identity_from_memories_task

# Extract from memories asynchronously
task = extract_identity_from_memories_task.delay(
    user_id="user_001",
    num_items=100
)

print(f"Task ID: {task.id}")

# Check result later
result = task.get(timeout=300)
print(f"Extracted {result['traits_extracted']} traits")
```

### Apply Decay

```python
from app.workers.tasks import apply_identity_decay_task

# Apply decay to stale traits
task = apply_identity_decay_task.delay(user_id="user_001")
result = task.get()
print(f"Traits decayed: {result['traits_decayed']}")
```

### Rebuild Graph

```python
from app.workers.tasks import rebuild_identity_graph_task

# Full rebuild
task = rebuild_identity_graph_task.delay(user_id="user_001")
result = task.get()
print(f"Graph rebuilt: {result['nodes']} nodes, {result['edges']} edges")
```

---

## TESTING

### Run Test Suite

```bash
# All tests
pytest tests/test_identity.py -v

# Specific test class
pytest tests/test_identity.py::TestIdentityExtraction -v

# With coverage
pytest tests/test_identity.py --cov=app.services --cov-report=html
```

### Example Test

```python
def test_extract_from_memories(db_session, test_user):
    from app.services.identity_extractor import IdentityExtractor
    
    extractor = IdentityExtractor(db_session)
    extracted = extractor.extract_from_memories(test_user.id, test_memories)
    
    assert "goals" in extracted
    assert len(extracted["goals"]) > 0
```

---

## API EXAMPLES

### Complete Flow

```bash
# 1. Create user (via Day 1 ingest)
# 2. Add memories (via Day 1 ingest)
# 3. Consolidate to concepts (via Day 3)

# 4. Extract identity
curl -X POST "http://localhost:8000/identity/extract?user_id=abc123&use_concepts=true"

# 5. Get profile
curl "http://localhost:8000/identity/profile?user_id=abc123"

# 6. Get graph stats
curl "http://localhost:8000/identity/graph?user_id=abc123"

# 7. Reinforce trait
curl -X POST "http://localhost:8000/identity/reinforce?user_id=abc123&node_id=xyz" \
  -H "Content-Type: application/json" \
  -d '{
    "confidence_boost": 0.15,
    "evidence_source": "conversation",
    "source_ids": ["mem1", "mem2"]
  }'

# 8. Get history
curl "http://localhost:8000/identity/history?user_id=abc123&days=30"

# 9. Get personalized context
curl "http://localhost:8000/identity/context?user_id=abc123&query=What%20should%20I%20learn?"
```

---

## UNDERSTANDING THE OUTPUT

### Profile Example

```json
{
  "summary": "Working towards: Software Engineering Growth. Also interested in: Distributed Systems, Cloud Computing. Core traits: Analytical, Builder. Prefers Concise, Technical communication. Skilled in: Backend Engineering, System Design, Python.",
  "goals": [
    {
      "value": "software_engineering_growth",
      "confidence": 0.85,
      "importance": 0.95
    }
  ],
  "interests": [
    {
      "value": "distributed_systems",
      "confidence": 0.80,
      "importance": 0.85
    }
  ],
  "communication_style": {
    "primary": "concise",
    "preferences": ["concise", "technical"],
    "confidence": 0.75
  },
  "behavioral_traits": [
    {
      "value": "analytical",
      "confidence": 0.78,
      "importance": 0.80
    },
    {
      "value": "curious",
      "confidence": 0.72,
      "importance": 0.75
    }
  ]
}
```

### Graph Statistics Example

```json
{
  "nodes": 18,
  "edges": 24,
  "density": 0.188,
  "avg_degree_centrality": 0.22,
  "weakly_connected_components": 2
}
```

**What it means**:
- **18 nodes**: User has 18 distinct identity traits
- **24 edges**: 24 relationships between traits
- **Density 0.188**: 18.8% of possible connections exist (sparse graph is normal)
- **Avg degree 0.22**: Each trait connects to ~2-3 other traits
- **2 components**: Traits form 2 separate clusters (possibly: career cluster + personal cluster)

---

## CONFIGURATION

### Environment Variables

```bash
# .env file
IDENTITY_MIN_CONFIDENCE=0.50
IDENTITY_DECAY_RATE=0.02
IDENTITY_EMA_ALPHA=0.70
IDENTITY_MAX_PROPAGATION_DEPTH=3
```

### Code Configuration

```python
# In services:
MIN_EXTRACTION_CONFIDENCE = 0.60
DAILY_DECAY_RATE = 0.02
EMA_ALPHA = 0.7
MAX_PROPAGATION_DEPTH = 3
```

---

## TROUBLESHOOTING

### Problem: No traits extracted

```bash
# Check 1: User has concepts/memories
curl "http://localhost:8000/identity/status?user_id=abc123"

# Check 2: Run extraction with debugging
curl -X POST "http://localhost:8000/identity/extract?user_id=abc123" -v

# Check 3: Verify LLM connection
# OpenAI API key set? export OPENAI_API_KEY=sk-...
```

### Problem: Traits losing confidence too fast

```python
# Adjust decay rate
# In identity_reinforcement.py:
self.decay_rate_daily = 0.01  # Lower from 0.02
```

### Problem: Graph not updating

```bash
# Rebuild graph from scratch
curl -X POST "http://localhost:8000/identity/rebuild?user_id=abc123&force_rebuild=true"
```

---

## NEXT STEPS

### Day 5+ Features

1. **Goal-based Planning**: Use goals to plan user growth
2. **Inference Engine**: Infer new traits from relationships
3. **Multi-hop Reasoning**: Connect seemingly unrelated interests
4. **Value Alignment**: Check for conflicting values
5. **Predictive Modeling**: Predict future interests

---

## KEY CONCEPTS

### Node Types

| Type | Examples | Purpose |
|------|----------|---------|
| **goal** | Staff Engineer, Build Startup | Long-term aspirations |
| **interest** | AI, Distributed Systems | Areas of focus |
| **communication** | Concise, Technical, Visual | Preference style |
| **behavior** | Curious, Ambitious, Analytical | Personality traits |
| **value** | Learning, Speed, Excellence | Core principles |
| **skill** | Python, System Design | Technical expertise |

### Relationship Types

| Type | Meaning | Example |
|------|---------|---------|
| **related_to** | Traits often co-occur | Python → Backend Engineering |
| **reinforces** | One strengthens the other | Goal → Interest alignment |
| **derived_from** | One comes from another | Interest → Skill path |
| **influences** | One affects the other | Value → Goal direction |
| **conflicts** | One opposes another | Independence → Collaboration |

---

**Status**: ✅ Ready to Use

**Next**: Review DAY4_ARCHITECTURE.md for system design details

