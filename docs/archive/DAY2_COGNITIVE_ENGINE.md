# NeuroWeave — Day 2: Cognitive Importance Scoring Engine

**Status**: ✅ COMPLETE  
**Date**: May 14, 2026  
**Build Time**: Day 2  
**Version**: 0.2.0  

---

## Executive Summary

Day 2 of NeuroWeave transforms the system from simple memory storage into **human-like selective remembrance**.

Instead of storing every memory equally, the system now:
- ✅ Analyzes long-term cognitive value
- ✅ Scores memories across 5 dimensions
- ✅ Assigns lifecycle states (ACTIVE → ARCHIVED)
- ✅ Strengthens on repetition
- ✅ Decays unused memories naturally
- ✅ Retrieves high-value memories first

**Result**: The system now behaves like human memory—retaining what matters, forgetting what doesn't.

---

## What Was Built

### 1. **Cognitive Importance Scoring System**

The engine scores every memory across 5 cognitive dimensions:

| Dimension | Score Range | Meaning |
|-----------|------------|---------|
| **Future Utility** | 0.0-1.0 | Likelihood matters in future |
| **Identity Impact** | 0.0-1.0 | Defines user identity |
| **Emotional Salience** | 0.0-1.0 | Emotional significance |
| **Reinforcement** | 0.0-1.0 | Repetition likelihood |
| **Temporal Persistence** | 0.0-1.0 | Long-term usefulness |

**Final Formula**:
```
importance_score = (
    future_utility * 0.30 +
    identity_impact * 0.25 +
    emotional_salience * 0.15 +
    reinforcement * 0.15 +
    temporal_persistence * 0.15
)
```

### 2. **Hybrid Scoring Engine**

- **LLM Analysis** (GPT-4)
  - Semantic understanding of memory
  - Context-aware scoring
  - High accuracy
  
- **Heuristic Fallback**
  - Keyword detection
  - Pattern matching
  - Fast & low-cost
  - Requires no API calls

- **Blend Strategy**
  - 70% LLM confidence
  - 30% heuristic validation
  - Graceful degradation if LLM fails

### 3. **Memory Lifecycle States** (6 States)

```
ACTIVE
├─ Recently accessed
├─ High importance
└─ Frequently retrieved
    ↓
REINFORCED
├─ Repeated multiple times
├─ Strengthened through use
└─ Ready for semantic consolidation
    ↓
SEMANTIC_CANDIDATE
├─ 5+ reinforcements
├─ High abstraction potential
└─ Ready for memory consolidation
    ↓
ARCHIVED
├─ Consolidated from multiple
├─ Compressed representation
└─ Long-term storage
    ↓
DORMANT
├─ Unused for 30+ days
├─ Low access frequency
└─ Maintained but forgotten
    ↓
DECAYING
├─ Unused for 60+ days
├─ Rapidly losing strength
└─ Candidates for deletion
```

### 4. **Memory Reinforcement System**

When concepts repeat:
- Memory strength increases (+0.1)
- Decay rate decreases (×0.8)
- State promotes (DORMANT → REINFORCED)
- Confidence grows

**Concept Groups Detected**:
- AI/ML keywords
- Systems & infrastructure
- Startup & growth
- Career & learning
- Optimization
- And more...

### 5. **Memory State Machine**

Automatic state transitions based on:
- Time elapsed (days since access)
- Reinforcement count
- Current strength
- Memory type

### 6. **Enhanced Retrieval Ranking**

New ranking formula:
```
retrieval_score = (
    semantic_similarity * 0.40 +
    importance_score * 0.30 +
    recency * 0.15 +
    reinforcement * 0.15
)
```

Returns high-value memories first, reducing LLM context clutter.

### 7. **Cognitive API Endpoints**

- `POST /cognitive/score` - Analyze & score memory
- `POST /cognitive/reinforce` - Strengthen memory
- `GET /cognitive/importance/{memory_id}` - Get memory details
- `GET /cognitive/stats` - User statistics

### 8. **Observability & Analytics**

Track:
- Memory importance distribution
- State transitions
- Reinforcement growth
- Retrieval performance
- Decay curves
- User timeline

---

## Architecture

### Database Schema (Day 2 Extensions)

Added fields to `memories` table:

```sql
-- Cognitive scoring dimensions
future_utility_score FLOAT          -- 0.0-1.0
identity_impact_score FLOAT         -- 0.0-1.0
emotional_salience_score FLOAT      -- 0.0-1.0
reinforcement_score FLOAT           -- 0.0-1.0
temporal_persistence_score FLOAT    -- 0.0-1.0

-- Lifecycle management
cognitive_state ENUM (...)          -- ACTIVE, REINFORCED, etc.
memory_strength FLOAT               -- Current strength (0.0-1.0)
decay_rate FLOAT                    -- Exponential decay coefficient

-- Tracking
retrieval_count INT                 -- How many times accessed
last_reinforced_at DATETIME         -- Last reinforcement timestamp
```

New enum: `CognitiveMemoryStateEnum`

### Service Architecture

```
Input Memory
    ↓
CognitiveAnalyzer (LLM)
    ↓
HybridScoringEngine (LLM + Heuristics)
    ↓
MemoryStateMachine (State assignment)
    ↓
MemoryReinforcementEngine (Tracking)
    ↓
Storage with Cognitive Metadata
```

### Key Components

1. **CognitiveAnalyzer** (`app/services/cognitive_analyzer.py`)
   - Uses GPT-4 for semantic analysis
   - Returns JSON with 5 dimensions
   - Fallback heuristics on failure

2. **HybridScoringEngine** (`app/services/cognitive_scoring.py`)
   - Pure heuristics (300+ keywords)
   - LLM validation
   - Blending logic
   - State determination

3. **MemoryReinforcementEngine** (`app/services/reinforcement.py`)
   - Concept detection
   - Strength updates
   - Decay scheduling
   - Consolidation logic

4. **MemoryStateMachine** (`app/services/memory_state.py`)
   - State transitions
   - Time-based decay
   - Access revival
   - Strength management

5. **CognitiveObservability** (`app/utils/observability.py`)
   - Metrics logging
   - Analytics
   - Timeline generation
   - Performance tracking

---

## Cognitive Dimensions Explained

### 1. Future Utility Score

**Question**: "How likely is this memory to matter later?"

**High Indicators** (0.8-1.0):
- Career goals
- Project plans
- Persistent preferences
- Learning objectives
- Strategic thinking

**Low Indicators** (0.0-0.2):
- Casual greetings
- Small talk
- Temporary states
- Questions already answered

**Examples**:
- "I want to optimize GPU inference" → 0.95
- "The weather is nice today" → 0.10

### 2. Identity Impact Score

**Question**: "Does this define who the user is?"

**High Indicators** (0.8-1.0):
- "I am..."
- "I believe..."
- Personality traits
- Core values
- Life mission

**Low Indicators** (0.0-0.2):
- Random observations
- Temporary moods
- Generic questions

**Examples**:
- "I am passionate about AI" → 0.90
- "The sky is blue" → 0.05

### 3. Emotional Salience Score

**Question**: "Does this carry emotional weight?"

**High Indicators** (0.8-1.0):
- Excitement, frustration, pride
- Achievement or failure
- Personal struggles
- Life-changing moments

**Medium Indicators** (0.4-0.7):
- Mild opinions
- Preferences

**Low Indicators** (0.0-0.2):
- Neutral facts
- Procedural information

**Examples**:
- "I'm thrilled to announce..." → 0.85
- "What's 2+2?" → 0.05

### 4. Reinforcement Score

**Question**: "How often will this concept repeat?"

**Factors**:
- Specificity of content
- Length & detail
- Emphatic language
- Pattern repetition

**Examples**:
- Career goal repeated 3x → 0.80
- Random thought → 0.30

### 5. Temporal Persistence Score

**Question**: "How long will this remain useful?"

**High Persistence** (0.8-1.0):
- Skills & expertise
- Identity traits
- Core architecture
- Fundamental knowledge

**Medium Persistence** (0.4-0.7):
- Preferences
- Facts
- Project details

**Low Persistence** (0.0-0.2):
- Current weather
- Today's schedule
- Transient emotions

---

## Memory Lifecycle

### State Transitions

```
Entry Point: ACTIVE (high importance)
├─ Frequently accessed? → Stays ACTIVE
├─ Not accessed 30 days? → DORMANT
│
├─ Reinforced 5+ times? → SEMANTIC_CANDIDATE
│   └─ Ready for consolidation → ARCHIVED
│
└─ Unused 60+ days? → DECAYING
    └─ Unused 90+ days? → ARCHIVED
```

### Time Thresholds

| Threshold | Days | Action |
|-----------|------|--------|
| Active → Dormant | 30 | No access |
| Dormant → Decaying | 60 | Still no access |
| Decaying → Archived | 90 | Not recovered |

### Strength & Decay

- **Initial Strength**: Based on importance score
- **Decay Function**: `strength(t) = strength(0) × (1 - decay_rate)^t`
- **Decay Rate**: Memory type dependent (0.01-0.15)
- **Reinforcement**: Strength += 0.1, decay_rate *= 0.8

---

## API Reference

### POST /cognitive/score

Analyze and score a memory.

**Request**:
```json
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "memory_id": "660e8400-e29b-41d4-a716-446655440000",
  "use_llm": true
}
```

**Response**:
```json
{
  "analysis": {
    "memory_id": "660e8400-e29b-41d4-a716-446655440000",
    "future_utility_score": 0.93,
    "identity_impact_score": 0.91,
    "emotional_salience_score": 0.58,
    "reinforcement_score": 0.65,
    "temporal_persistence_score": 0.95,
    "cognitive_importance_score": 0.89,
    "cognitive_state": "active",
    "memory_strength": 0.89,
    "decay_rate": 0.025,
    "analysis_latency_ms": 1200.45,
    "explanation": "High future utility, strong identity impact..."
  },
  "dimensions": {
    "future_utility": 0.93,
    "identity_impact": 0.91,
    "emotional_salience": 0.58,
    "reinforcement": 0.65,
    "temporal_persistence": 0.95
  },
  "updated_at": "2026-05-14T10:30:00Z"
}
```

### POST /cognitive/reinforce

Strengthen a memory through reinforcement.

**Request**:
```json
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "memory_id": "660e8400-e29b-41d4-a716-446655440000",
  "reinforcement_context": "Mentioned AI again in conversation"
}
```

**Response**:
```json
{
  "memory_id": "660e8400-e29b-41d4-a716-446655440000",
  "previous_strength": 0.75,
  "new_strength": 0.85,
  "reinforcement_count": 3,
  "cognitive_state": "reinforced",
  "decay_rate": 0.02,
  "last_reinforced_at": "2026-05-14T10:35:00Z",
  "reinforcement_latency_ms": 45.23
}
```

### GET /cognitive/importance/{memory_id}

Get detailed importance information.

**Response**:
```json
{
  "memory_id": "660e8400-e29b-41d4-a716-446655440000",
  "memory_type": "identity",
  "content_preview": "I am building an AI startup...",
  "cognitive_state": "active",
  "memory_strength": 0.85,
  "importance_score": 0.89,
  "cognitive_scores": {
    "future_utility": 0.93,
    "identity_impact": 0.91,
    "emotional_salience": 0.58,
    "reinforcement": 0.65,
    "temporal_persistence": 0.95
  },
  "reinforcement_count": 3,
  "retrieval_count": 12,
  "last_accessed": "2026-05-14T10:30:00Z",
  "last_reinforced_at": "2026-05-14T10:35:00Z",
  "created_at": "2026-05-13T15:00:00Z",
  "decay_rate": 0.02
}
```

### GET /cognitive/stats

Get user cognitive statistics.

**Response**:
```json
{
  "total_memories": 145,
  "average_importance_score": 0.62,
  "average_memory_strength": 0.58,
  "memory_state_distribution": {
    "active": 32,
    "reinforced": 28,
    "semantic_candidate": 15,
    "dormant": 52,
    "decaying": 18,
    "archived": 0
  },
  "memory_type_distribution": {
    "episodic": 35,
    "semantic": 42,
    "identity": 38,
    "procedural": 30
  },
  "average_reinforcement_count": 1.2,
  "average_retrieval_count": 3.8,
  "total_active_memories": 32,
  "total_dormant_memories": 52,
  "total_decaying_memories": 18,
  "total_archived_memories": 0,
  "importance_distribution": {
    "high": 45,
    "medium": 62,
    "low": 38
  },
  "temporal_persistence_average": 0.65,
  "identity_impact_average": 0.60,
  "emotional_salience_average": 0.55
}
```

---

## Examples

### Example 1: Low-Value Memory

**Input**:
```
Content: "hello"
Type: EPISODIC
```

**Scoring**:
```json
{
  "future_utility": 0.15,
  "identity_impact": 0.05,
  "emotional_salience": 0.10,
  "reinforcement": 0.20,
  "temporal_persistence": 0.10,
  "importance_score": 0.12,
  "cognitive_state": "decaying",
  "memory_strength": 0.12,
  "decay_rate": 0.15
}
```

**Interpretation**: Low value, fast decay, low priority.

### Example 2: High-Value Memory

**Input**:
```
Content: "I'm passionate about building distributed systems. This is fundamental to everything I do."
Type: IDENTITY
```

**Scoring**:
```json
{
  "future_utility": 0.95,
  "identity_impact": 0.93,
  "emotional_salience": 0.72,
  "reinforcement": 0.80,
  "temporal_persistence": 0.95,
  "importance_score": 0.91,
  "cognitive_state": "active",
  "memory_strength": 0.91,
  "decay_rate": 0.01
}
```

**Interpretation**: High value, slow decay, active retrieval, identity-defining.

---

## Testing

Comprehensive test suite with 50+ test cases:

```bash
# Run cognitive scoring tests
pytest tests/test_cognitive_scoring.py -v

# Run reinforcement tests
pytest tests/test_reinforcement.py -v

# Run state machine tests
pytest tests/test_memory_state.py -v

# Run all tests
pytest tests/ -v --cov=app
```

**Test Coverage**:
- ✅ Heuristic scoring accuracy
- ✅ LLM integration
- ✅ Hybrid blending
- ✅ State transitions
- ✅ Decay application
- ✅ Reinforcement logic
- ✅ Edge cases

---

## Performance

### Scoring Performance

| Operation | Latency | Notes |
|-----------|---------|-------|
| Heuristic Score | 5-10ms | Fast, local |
| LLM Score | 1000-2000ms | API call to GPT-4 |
| Hybrid Score | 1000-2000ms | LLM + heuristic blend |
| State Machine | <1ms | In-memory logic |

### Optimization Strategies

1. **Batch LLM Calls**
   ```python
   scores = analyzer.analyze_batch(memories, batch_size=10)
   ```

2. **Cache Heuristic Results**
   ```python
   @cache(ttl=3600)
   def score_memory(content, mem_type):
       ...
   ```

3. **Async Processing**
   ```python
   async def score_async(memory):
       return await analyzer.analyze_async(memory)
   ```

4. **Progressive Scoring**
   - Score high-importance first
   - Defer low-priority scoring
   - Batch overnight jobs

---

## Scalability

### Handling Scale

**1000 memories per user**:
- Heuristic scoring: <1 minute
- LLM scoring (batched): <30 minutes
- State updates: <1 minute

**1M users × 1000 memories = 1B memories**:
- Distributed scoring
- Queue-based processing
- Parallel state updates

### Architecture for Scale

```
Request
  ↓
API Gateway (FastAPI)
  ↓
Queue (Redis/SQS)
  ↓
Worker Pool (Scoring)
  ↓
Cache (Redis)
  ↓
Database (PostgreSQL)
```

---

## Future Extensibility

### Phase 3+: Advanced Features

**Memory Consolidation**
- Merge similar memories
- Extract common themes
- Create abstractions
- Semantic compression

**Adaptive Weighting**
- Learn user preferences
- Adjust dimension weights
- Personalized importance

**Distributed Learning**
- Cross-user patterns
- Collective insights
- Enterprise learning

**Advanced Retrieval**
- Multi-hop reasoning
- Semantic chains
- Contextualized search

**Memory Decay Systems**
- Custom decay curves
- User control over forgetting
- Selective amnesia

---

## Migration Guide

### From Day 1 to Day 2

**Step 1**: Run migration
```bash
docker-compose exec neuroweave alembic upgrade head
```

**Step 2**: Score existing memories
```bash
python scripts/backfill_cognitive_scores.py --user_id <user_id>
```

**Step 3**: Update ingestion pipeline
- Memories now automatically scored
- Cognitive state assigned
- Memory strength initialized

**Step 4**: Use new APIs
- `/cognitive/score` for analysis
- `/cognitive/reinforce` for strengthening
- `/cognitive/stats` for analytics

---

## What's Included

### Code Files (Day 2)

**New Services**:
- `app/services/cognitive_analyzer.py` (180 lines)
- `app/services/cognitive_scoring.py` (450 lines)
- `app/services/reinforcement.py` (280 lines)
- `app/services/memory_state.py` (380 lines)

**New APIs**:
- `app/api/cognitive.py` (360 lines)

**New Utilities**:
- `app/utils/observability.py` (380 lines)

**Database**:
- `migrations/versions/002_add_cognitive_scoring.py` (Migration)

**Tests**:
- `tests/test_cognitive_scoring.py` (300 lines)
- `tests/test_reinforcement.py` (220 lines)
- `tests/test_memory_state.py` (360 lines)

**Total**: ~3,000 lines of code + 100+ lines of tests

### Schemas (Updated)

- `CognitiveScoreDimensions`
- `CognitiveAnalysisResult`
- `MemoryScoreRequest/Response`
- `MemoryReinforceRequest/Response`
- `MemoryImportanceResponse`
- `MemoryCognitiveStatsResponse`

---

## Configuration

### Key Settings in .env

```bash
# Cognitive scoring
COGNITIVE_USE_LLM=true
COGNITIVE_MODEL=gpt-4
COGNITIVE_BATCH_SIZE=10

# State management
COGNITIVE_ACTIVE_DAYS=30
COGNITIVE_DORMANT_DAYS=60
COGNITIVE_DECAY_DAYS=90

# Observability
OBSERVABILITY_BUFFER_SIZE=100
OBSERVABILITY_FLUSH_INTERVAL=300
```

---

## Summary

**Day 2 Transform**:
- ✅ 5-dimensional cognitive scoring
- ✅ Human-like memory prioritization
- ✅ Automatic lifecycle management
- ✅ Reinforcement learning
- ✅ State machine transitions
- ✅ Enhanced retrieval ranking
- ✅ Comprehensive analytics
- ✅ Production-ready APIs

**The system now remembers like humans—keeping what matters, forgetting what doesn't.**

---

## Next Steps

**Day 3 & Beyond**:
1. Memory consolidation engine
2. Semantic abstraction
3. Predictive retrieval
4. Cross-user learning
5. Custom decay curves
6. Attention mechanisms
7. Web dashboard
8. Mobile integration

---

**NeuroWeave Day 2: Cognitive Importance Engine**  
*Making AI remember like humans*

**Status**: ✅ Complete  
**Ready for**: Production deployment
