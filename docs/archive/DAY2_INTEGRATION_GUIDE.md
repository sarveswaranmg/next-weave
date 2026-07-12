# NeuroWeave Day 2: Integration Guide

**Complete walkthrough of how cognitive scoring integrates with your system.**

---

## 🔗 System Architecture

### Before Day 2 (Day 1)
```
User Input
  ↓
Memory Ingestion
  ↓
Vector Embedding
  ↓
Storage
  ↓
Simple Semantic Search
```

### After Day 2 (Complete System)
```
User Input
  ↓
Memory Ingestion
  ├─ Standard processing (Day 1)
  └─ NEW: Cognitive scoring
      ├─ LLM analysis
      ├─ Heuristic validation
      └─ Importance scoring
  ↓
Vector Embedding
  ↓
Storage + Cognitive Metadata
  ├─ Cognitive state
  ├─ Memory strength
  ├─ Decay rate
  └─ 5-dimension scores
  ↓
Enhanced Semantic Search
  └─ NEW: Multi-factor ranking
      ├─ Semantic similarity (40%)
      ├─ Importance score (30%)
      ├─ Recency (15%)
      └─ Reinforcement (15%)
```

---

## 📥 Integration Points

### 1. Memory Ingestion Pipeline

**File**: `app/services/ingestion.py`

```python
from app.services.cognitive_scoring import HybridScoringEngine
from app.services.memory_state import MemoryStateMachine
from app.services.reinforcement import MemoryReinforcementEngine

async def ingest_memory(memory_content: str, memory_type: str, session):
    # Day 1: Existing ingestion logic
    memory = create_memory(memory_content, memory_type)
    embedding = generate_embedding(memory_content)
    save_to_db(memory, embedding, session)
    
    # Day 2: NEW cognitive scoring
    scoring_engine = HybridScoringEngine(session)
    scores = await scoring_engine.score_memory(
        memory_id=memory.id,
        content=memory_content,
        memory_type=memory_type,
        use_llm=True  # Or False for heuristic-only
    )
    
    # Day 2: Assign initial state
    state_machine = MemoryStateMachine(session)
    state_machine.determine_initial_state(
        memory_id=memory.id,
        importance_score=scores['cognitive_importance_score']
    )
    
    return memory
```

### 2. Retrieval Pipeline Update

**File**: `app/retrieval/engine.py`

```python
def retrieve_relevant_memories(
    user_id: str,
    query: str,
    top_k: int = 10,
    exclude_archived: bool = True
):
    # Step 1: Semantic search (existing)
    candidates = semantic_search(query, user_id, top_k=50)
    
    # Step 2: Day 2 Enhancement - Cognitive Ranking
    scored_candidates = []
    
    for memory in candidates:
        semantic_score = calculate_similarity(query, memory.embedding)
        importance_score = memory.cognitive_importance_score
        recency_score = calculate_recency(memory.last_accessed)
        reinforcement_score = min(1.0, memory.reinforcement_count * 0.1)
        
        # New 4-factor ranking formula
        final_score = (
            semantic_score * 0.40 +
            importance_score * 0.30 +
            recency_score * 0.15 +
            reinforcement_score * 0.15
        )
        
        scored_candidates.append((memory, final_score))
    
    # Step 3: Sort by cognitive ranking
    scored_candidates.sort(key=lambda x: x[1], reverse=True)
    
    # Step 4: Return top-k
    return [m for m, score in scored_candidates[:top_k]]
```

### 3. Reinforcement on Repeated Concepts

**File**: `app/services/ingestion.py` (extended)

```python
async def ingest_memory(memory_content: str, memory_type: str, session):
    # ... (existing ingestion code)
    
    # NEW: Day 2 Reinforcement
    reinforcement_engine = MemoryReinforcementEngine(session)
    
    # Detect and reinforce related concepts
    reinforced_memories = await reinforcement_engine.detect_and_reinforce_concepts(
        user_id=user_id,
        new_content=memory_content,
        threshold=0.70  # Only reinforce if 70%+ match
    )
    
    if reinforced_memories:
        print(f"Reinforced {len(reinforced_memories)} related memories")
        
        # Update states on reinforced memories
        state_machine = MemoryStateMachine(session)
        for memory_id in reinforced_memories:
            state_machine.update_state_on_reinforcement(
                memory_id=memory_id,
                new_reinforcement_count=None  # Auto-increment
            )
    
    return memory
```

### 4. Lifecycle Management Background Job

**File**: `app/background_jobs/memory_decay.py` (new)

```python
async def decay_old_memories(user_id: str, session):
    """Run periodically (e.g., every hour) to manage memory decay."""
    
    state_machine = MemoryStateMachine(session)
    
    # Check all active/dormant/decaying memories
    memories = session.query(Memory).filter(
        Memory.user_id == user_id,
        Memory.cognitive_state.in_([
            CognitiveMemoryStateEnum.ACTIVE,
            CognitiveMemoryStateEnum.DORMANT,
            CognitiveMemoryStateEnum.DECAYING
        ])
    ).all()
    
    for memory in memories:
        # Apply time-based decay
        state_machine.update_state_by_time_decay(memory.id)
    
    session.commit()
    print(f"Processed decay for {len(memories)} memories")
```

Schedule in celery:
```python
from celery import shared_task

@shared_task
def scheduled_memory_decay():
    for user in get_all_users():
        decay_old_memories(user.id)
```

### 5. API Response Enhancement

**File**: `app/api/memories.py` (existing endpoint, enhanced)

```python
@router.get("/api/memories/{memory_id}", response_model=EnhancedMemoryResponse)
async def get_memory_detail(
    memory_id: str,
    user_id: str,
    session: Session = Depends(get_session)
):
    """Get memory with Day 2 cognitive data."""
    
    memory = session.query(Memory).filter_by(id=memory_id).first()
    
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    
    # Day 1 data
    response = {
        "id": memory.id,
        "content": memory.content,
        "type": memory.memory_type,
        "created_at": memory.created_at
    }
    
    # Day 2 data - NEW
    if memory.cognitive_state:  # If scored
        response.update({
            "cognitive_state": memory.cognitive_state,
            "importance_score": memory.cognitive_importance_score,
            "memory_strength": memory.memory_strength,
            "cognitive_dimensions": {
                "future_utility": memory.future_utility_score,
                "identity_impact": memory.identity_impact_score,
                "emotional_salience": memory.emotional_salience_score,
                "reinforcement": memory.reinforcement_score,
                "temporal_persistence": memory.temporal_persistence_score
            },
            "reinforcement_count": memory.reinforcement_count,
            "retrieval_count": memory.retrieval_count,
            "decay_rate": memory.decay_rate,
            "last_reinforced_at": memory.last_reinforced_at
        })
    
    return EnhancedMemoryResponse(**response)
```

---

## 🔄 Data Flow Examples

### Example 1: Complete Scoring Flow

```
User Input: "I'm passionate about distributed systems"
    ↓
Ingestion Pipeline
    ├─ Memory created
    ├─ Embedding generated
    └─ Stored in DB
    ↓
CognitiveAnalyzer (LLM)
    └─ GPT-4 analysis
    ├─ future_utility: 0.95
    ├─ identity_impact: 0.93
    ├─ emotional_salience: 0.68
    ├─ reinforcement: 0.80
    └─ temporal_persistence: 0.95
    ↓
HybridScoringEngine
    ├─ LLM scores: [0.95, 0.93, 0.68, 0.80, 0.95]
    ├─ Heuristic scores: [0.92, 0.90, 0.65, 0.78, 0.92]
    └─ Blended: 70% LLM, 30% heuristic
    ↓
Final Importance Score: 0.89 (high)
    ↓
MemoryStateMachine
    └─ Assign state: ACTIVE
    ├─ memory_strength = 0.89
    └─ decay_rate = 0.01 (slow)
    ↓
Storage (with cognitive metadata)
    └─ Ready for intelligent retrieval
```

### Example 2: Reinforcement Flow

```
New Input: "Systems architecture is my passion"
    ↓
Concept Detection
    └─ Finds "distributed systems" concept
    ↓
MemoryReinforcementEngine
    ├─ Finds previous memory about "distributed systems"
    └─ Matching score: 0.82 (above threshold)
    ↓
Previous Memory Updated
    ├─ reinforcement_count: 1 → 2
    ├─ memory_strength: 0.89 → 0.99 (capped at 1.0)
    └─ decay_rate: 0.01 → 0.008 (×0.8)
    ↓
State Update
    ├─ reinforced_count: 2
    └─ NEW state: REINFORCED (from ACTIVE)
    ↓
Impact
    └─ Memory now even more likely to be retrieved
```

### Example 3: Retrieval with Cognitive Ranking

```
User Query: "What matters for my career?"
    ↓
Semantic Search
    └─ Find 50 candidate memories
    ├─ "distributed systems" (similarity: 0.75)
    ├─ "Python skills" (similarity: 0.68)
    ├─ "Had lunch yesterday" (similarity: 0.62)
    └─ ... 47 more
    ↓
Cognitive Ranking (apply 4-factor formula)
    ├─ "distributed systems"
    │  └─ 0.75*0.40 + 0.89*0.30 + 0.95*0.15 + 0.15*0.15 = 0.78
    ├─ "Python skills"
    │  └─ 0.68*0.40 + 0.72*0.30 + 0.80*0.15 + 0.10*0.15 = 0.66
    └─ "Had lunch yesterday"
       └─ 0.62*0.40 + 0.12*0.30 + 0.05*0.15 + 0.02*0.15 = 0.30
    ↓
Ranked Results
    ├─ 1. "distributed systems" (score: 0.78)
    ├─ 2. "Python skills" (score: 0.66)
    ├─ 3. ... (other high-value)
    └─ 50. "Had lunch yesterday" (score: 0.30) - DEPRIORITIZED
    ↓
Return Top 10
    └─ High-value memories provided first
```

---

## 🛠️ Operational Procedures

### Daily Operations

**1. Monitor Memory Health**
```bash
# Check statistics
curl http://localhost:8000/cognitive/stats?user_id=$USER_ID

# Expected output:
# - average_importance_score > 0.50
# - active > dormant
# - no sudden state changes
```

**2. Review Decay**
```bash
# Check for memories aging out
SELECT * FROM memories 
WHERE cognitive_state = 'DORMANT' 
AND last_accessed < DATE_SUB(NOW(), INTERVAL 30 DAY)
AND cognitive_importance_score > 0.70;

# Action: Review if any high-importance should be recovered
```

### Weekly Operations

**1. Reinforce Key Memories**
```bash
# Manually boost important memories
curl -X POST http://localhost:8000/cognitive/reinforce \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "'$USER_ID'",
    "memory_id": "'$MEMORY_ID'"
  }'
```

**2. Analyze Patterns**
```python
from app.utils.observability import CognitiveAnalytics

analytics = CognitiveAnalytics()
timeline = analytics.get_user_cognitive_timeline(
    user_id=user_id,
    days=7
)

# Review:
# - Which states memories flow through
# - Average importance over time
# - Reinforcement patterns
```

### Monthly Operations

**1. Consolidate SEMANTIC_CANDIDATE memories**
```bash
# Find memories ready for consolidation
SELECT * FROM memories 
WHERE cognitive_state = 'SEMANTIC_CANDIDATE'
AND reinforcement_count >= 5;

# Action: Archive or consolidate these memories
```

**2. Review Archive**
```bash
# Check archived memories for possible recovery
SELECT COUNT(*) FROM memories WHERE cognitive_state = 'ARCHIVED';

# If count > 1000:
#   - Consider cleanup
#   - Or enable consolidation engine (Day 3)
```

---

## 🧠 Mental Model

### How It Works Together

1. **Ingestion** → New memories scored and assigned initial state
2. **Retrieval** → High-value memories ranked first
3. **Reinforcement** → Related concepts strengthen each other
4. **Decay** → Unused memories automatically fade
5. **Lifecycle** → Memories flow through 6 states automatically
6. **Analytics** → Observe patterns and health

### Key Insight

**The system is now self-managing**:
- No manual intervention needed for most operations
- Lifecycle transitions happen automatically
- Reinforcement strengthens important concepts
- Decay removes clutter without user action
- Retrieval returns what matters most

---

## 🔧 Customization Points

### Adjust Cognitive Weights

```python
# In HybridScoringEngine.score_memory()

WEIGHTS = {
    'future_utility': 0.30,          # Increase for future-focused users
    'identity_impact': 0.25,
    'emotional_salience': 0.15,      # Increase for emotional users
    'reinforcement': 0.15,
    'temporal_persistence': 0.15
}

# Example: Artist who values emotional memories
WEIGHTS = {
    'future_utility': 0.15,
    'identity_impact': 0.20,
    'emotional_salience': 0.40,      # 40% weight
    'reinforcement': 0.15,
    'temporal_persistence': 0.10
}
```

### Adjust Decay Rates

```python
# In MemoryStateMachine._calculate_decay_rate()

DECAY_RATES_BY_TYPE = {
    'procedural': 0.02,      # Skills fade slowly
    'identity': 0.01,        # Identity persists
    'semantic': 0.05,        # Facts fade medium
    'episodic': 0.15         # Events fade fast
}

# Customize per user if needed
```

### Adjust State Thresholds

```python
# In MemoryStateMachine.update_state_by_time_decay()

TRANSITION_DAYS = {
    'ACTIVE_TO_DORMANT': 30,     # Adjust if users want longer
    'DORMANT_TO_DECAYING': 60,
    'DECAYING_TO_ARCHIVED': 90
}
```

---

## 📊 Monitoring Metrics

### Health Metrics

**Track via CognitiveObservability**:

```python
from app.utils.observability import CognitiveAnalytics

# Memory distribution
distribution = analytics.get_importance_distribution(user_id)
# Expected: Bimodal (few high, few low, most medium)

# State distribution
states = analytics.get_memory_lifecycle_stats(user_id)
# Expected: ACTIVE > REINFORCED > SEMANTIC_CANDIDATE > ... > ARCHIVED

# Retrieval performance
perf = analytics.get_retrieval_performance(user_id)
# Expected: Avg latency stable, P99 < 2000ms
```

### Alert Conditions

| Metric | Alert Threshold | Action |
|--------|-----------------|--------|
| Avg importance score | < 0.30 | Check scoring engine |
| DORMANT memories | > 70% | May need lower decay |
| Reinforcement rate | < 0.1 | Low concept repetition |
| Retrieval latency | > 3000ms | May need caching |
| Archive size | > 10,000 | Consider consolidation |

---

## 🎯 Best Practices

### For Ingestion

1. ✅ Always provide `memory_type` (EPISODIC, SEMANTIC, IDENTITY, PROCEDURAL)
2. ✅ Let scoring run async if possible
3. ✅ Batch score old memories offline
4. ✅ Use heuristic-only scoring for real-time ingestion

### For Retrieval

1. ✅ Always use cognitive ranking (replaces simple similarity)
2. ✅ Exclude ARCHIVED by default
3. ✅ Trust the ranking formula
4. ✅ Log retrieval metrics for optimization

### For Reinforcement

1. ✅ Let automatic concept detection work
2. ✅ Manual reinforcement for critical memories
3. ✅ Don't over-reinforce (causes artificial inflation)
4. ✅ Review reinforcement patterns weekly

### For Lifecycle

1. ✅ Don't manually set states (let system manage)
2. ✅ Recovery by access (no manual intervention needed)
3. ✅ Archive old DECAYING memories monthly
4. ✅ Monitor distribution monthly

---

## 🚀 Performance Optimization

### For High Volume

```python
# Use heuristic scoring for ingestion
HybridScoringEngine.score_memory(
    use_llm=False  # Heuristic only: 10ms vs 1500ms
)

# Batch LLM scoring overnight
await batch_score_memories(
    user_id=user_id,
    importance_threshold=0.50,  # Only score medium+ importance
    batch_size=50,
    async_processing=True
)
```

### For Real-Time Retrieval

```python
# Cache cognitive rankings
@cache(ttl=3600)
def get_retrieval_ranking(query, user_id):
    return retrieve_relevant_memories(query, user_id)

# Use Redis for frequent queries
redis.setex(
    f"ranking:{query}:{user_id}",
    3600,
    json.dumps(ranking)
)
```

---

## 📝 Checklists

### Day 2 Integration Checklist

- [ ] Database migration applied (`alembic upgrade head`)
- [ ] All cognitive services running
- [ ] API endpoints responding
- [ ] Ingestion includes cognitive scoring
- [ ] Retrieval using cognitive ranking
- [ ] Background jobs scheduling memory decay
- [ ] Monitoring/observability in place
- [ ] Team trained on new features
- [ ] Documentation reviewed
- [ ] Go/No-go decision made

### Deployment Checklist

- [ ] Code review completed
- [ ] All tests passing (`pytest tests/ -v`)
- [ ] Performance tested (scoring latency acceptable)
- [ ] Migration plan documented
- [ ] Rollback plan prepared
- [ ] Team on standby for deployment
- [ ] Monitoring dashboards ready
- [ ] Customer communication prepared

---

## 🆘 Troubleshooting

### Scoring taking too long

```
Problem: POST /cognitive/score > 3 seconds
Solution: Set use_llm=false for heuristic only
Result: <100ms vs 1500ms
```

### Memories not transitioning states

```
Problem: All memories stuck in ACTIVE
Solution: Check background job is running
Command: SELECT COUNT(*) FROM memory_decay_log;
Action: Verify cron job or celery task scheduled
```

### High false positives in reinforcement

```
Problem: Unrelated memories getting reinforced
Solution: Increase concept matching threshold
Config: reinforcement_engine.similarity_threshold = 0.80
Result: Only reinforce truly related memories
```

### LLM API failures

```
Problem: Many failed scoring operations
Solution: Fall back to heuristic scoring
Code: HybridScoringEngine handles automatically
Monitor: Log failed LLM calls and retry later
```

---

## ✅ Integration Complete

Your system now has:
- ✅ Cognitive importance scoring
- ✅ Automatic lifecycle management
- ✅ Memory reinforcement
- ✅ Enhanced retrieval ranking
- ✅ Full observability

**Next step**: Day 3 - Memory Consolidation Engine

---

**Integration Guide v0.2.0**  
*NeuroWeave Day 2 Complete Integration*
