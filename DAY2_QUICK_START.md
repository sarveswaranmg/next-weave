# NeuroWeave Day 2: Quick Start & API Guide

## 🚀 Quick Start

### 1. Run Migrations

After updating to Day 2, run the new migration:

```bash
docker-compose exec neuroweave alembic upgrade head
```

This adds cognitive scoring fields to the database.

### 2. Score a Memory

```bash
curl -X POST http://localhost:8000/cognitive/score \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "550e8400-e29b-41d4-a716-446655440000",
    "memory_id": "660e8400-e29b-41d4-a716-446655440000",
    "use_llm": true
  }'
```

### 3. Get Memory Statistics

```bash
curl http://localhost:8000/cognitive/stats?user_id=550e8400-e29b-41d4-a716-446655440000
```

### 4. Reinforce a Memory

```bash
curl -X POST http://localhost:8000/cognitive/reinforce \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "550e8400-e29b-41d4-a716-446655440000",
    "memory_id": "660e8400-e29b-41d4-a716-446655440000",
    "reinforcement_context": "User mentioned this concept again"
  }'
```

## 📊 Cognitive Dimensions

Each memory is scored on 5 dimensions (0.0-1.0):

| Dimension | What It Measures | Example High (0.9+) | Example Low (0.1-) |
|-----------|------------------|---------------------|-------------------|
| **Future Utility** | Will this matter later? | "My 5-year plan" | "The weather today" |
| **Identity Impact** | Does this define me? | "I am deeply passionate about AI" | "Random observation" |
| **Emotional Salience** | Is this emotionally significant? | "I achieved my dream!" | "I ate lunch" |
| **Reinforcement** | How often will I think about this? | Topic mentioned 5x | First time mentioned |
| **Temporal Persistence** | How long-term is this? | "Career goal" | "Current task" |

## 🧠 Memory States

Memories flow through 6 states automatically:

```
ACTIVE (High value, frequent access)
  ↓ (30 days no access)
REINFORCED (Repeated, strengthening)
  ↓ (5+ reinforcements)
SEMANTIC_CANDIDATE (Ready for consolidation)
  ↓
ARCHIVED (Consolidated, compressed)

DORMANT (Low value, unused)
  ↓ (60 days no access)
DECAYING (Rapidly losing strength)
  ↓ (90 days no access)
ARCHIVED (Eventually cleaned up)
```

## 🔄 Memory Reinforcement

When a concept repeats:

```python
# Automatic reinforcement on concept match
POST /memory/ingest with content containing repeated concepts
↓
Concept detection (AI, systems, startup, learning, etc.)
↓
Matching memories reinforced
↓
Memory strength increased
↓
Decay rate reduced
↓
Cognitive state promoted
```

## 📈 Importance Calculation

The final importance score combines all 5 dimensions:

```
importance = 
  future_utility * 0.30 +          # Most important
  identity_impact * 0.25 +         # 2nd most important
  emotional_salience * 0.15 +      
  reinforcement * 0.15 +
  temporal_persistence * 0.15      # Least weight
```

**Result**: 0.0 (not important) to 1.0 (critical)

## 🎯 Example: Scoring Flow

### Input Memory

```
User: "I want to build the best inference optimization engine in the world."
Memory Type: IDENTITY
```

### Cognitive Analysis

```json
{
  "future_utility": 0.94,           // Definitely matters later
  "identity_impact": 0.95,          // Core to who they are
  "emotional_salience": 0.68,       // Some excitement but not extreme
  "reinforcement": 0.75,            // Likely to repeat frequently
  "temporal_persistence": 0.92      // Long-term goal
}
```

### Final Scores

```
importance_score = 0.94*0.30 + 0.95*0.25 + 0.68*0.15 + 0.75*0.15 + 0.92*0.15
                 = 0.282 + 0.238 + 0.102 + 0.113 + 0.138
                 = 0.873 ✅ HIGH IMPORTANCE

cognitive_state = ACTIVE (>0.80)
memory_strength = 0.87
decay_rate = 0.01 (very slow - identity persists)
```

## 🔍 Retrieval with Cognitive Ranking

Old approach (Day 1):
```
Rank only by semantic similarity
Result: Sometimes retrieve low-value memories
```

New approach (Day 2):
```
retrieval_score = 
  semantic_similarity * 0.40 +       // Content relevance
  importance_score * 0.30 +          // Value
  recency * 0.15 +                   // Recent
  reinforcement * 0.15               // Repeated

Result: Retrieve high-value, relevant memories first
```

## 📊 Analytics Dashboard Data

Available statistics via `/cognitive/stats`:

```json
{
  "total_memories": 145,
  "average_importance": 0.62,
  "memory_states": {
    "active": 32,
    "reinforced": 28,
    "semantic_candidate": 15,
    "dormant": 52,
    "decaying": 18,
    "archived": 0
  },
  "types": {
    "episodic": 35,
    "semantic": 42,
    "identity": 38,
    "procedural": 30
  },
  "importance_distribution": {
    "high": 45,
    "medium": 62,
    "low": 38
  }
}
```

## 🧪 Testing Scoring

```bash
# Test heuristic scoring (fast, no API calls)
pytest tests/test_cognitive_scoring.py::TestHybridScoringEngine::test_heuristic_scoring_high_importance -v

# Test LLM scoring (requires API key)
pytest tests/test_cognitive_scoring.py::TestHybridScoringEngine -v

# Test reinforcement
pytest tests/test_reinforcement.py -v

# Test state machine
pytest tests/test_memory_state.py -v

# All tests
pytest tests/ -v
```

## 🔧 Advanced: Manual Reinforcement

Manually reinforce a memory:

```python
from sqlalchemy.orm import Session
from app.services.reinforcement import MemoryReinforcementEngine

def reinforce_memory(session: Session, user_id, memory_id):
    engine = MemoryReinforcementEngine(session)
    result = engine.reinforce_memory(
        memory_id, 
        reinforcement_context="User explicitly reinforced",
        strength_increase=0.15
    )
    return result
```

## 🚨 Troubleshooting

### High latency in scoring

**Solution**: Use heuristic scoring only
```bash
POST /cognitive/score with use_llm=false
# ~10ms instead of ~1500ms
```

### Memory not reinforcing

**Check**: 
- Are concepts detected correctly?
- Is memory_strength high enough?
- Has enough time passed?

```bash
curl http://localhost:8000/cognitive/importance/{memory_id}?user_id={user_id}
# Check reinforcement_count and decay_rate
```

### State not transitioning

**Check**:
- How many days since last access?
- What's the current state?
- Is reinforcement_count sufficient?

**Manual transition**:
```python
from app.services.memory_state import transition_memory
transition_memory(memory, CognitiveMemoryStateEnum.ACTIVE, reason="Manual recovery")
```

## 📚 Key Concepts

**Cognitive State**: Where in the lifecycle is this memory?

**Memory Strength**: How confident are we in this memory? (0.0-1.0)

**Decay Rate**: How fast does this memory forget? (0.01-0.15)
- Low = persists long (identity memories)
- High = fades fast (ephemeral memories)

**Reinforcement Count**: How many times has this been strengthened?

**Retrieval Count**: How many times has this been accessed?

## 🎓 Learn More

- Full docs: `DAY2_COGNITIVE_ENGINE.md`
- Architecture: `ARCHITECTURE.md`
- API reference: `COMMANDS_REFERENCE.md`
- Integration: `INTEGRATION.md`

---

**NeuroWeave Day 2: Making AI Remember Like Humans**
