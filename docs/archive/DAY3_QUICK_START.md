# DAY 3 QUICK START GUIDE

**NeuroWeave Semantic Consolidation Engine**

---

## SETUP (5 minutes)

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

New dependencies:
- `hdbscan==0.8.30` - Advanced clustering
- `scikit-learn==1.3.2` - ML utilities
- `networkx==3.2` - Graph analysis
- `scipy==1.11.4` - Scientific computing

### 2. Run Database Migration

```bash
alembic upgrade head
```

Creates tables:
- `concept_memories`
- `memory_clusters`
- `concept_relationships`
- `consolidation_metrics`

### 3. Start Services

```bash
# Terminal 1: FastAPI server
python -m app.main

# Terminal 2: Celery worker
celery -A app.workers.celery_app worker --loglevel=info

# Terminal 3: Celery beat (optional, for periodic consolidation)
celery -A app.workers.celery_app beat --loglevel=info
```

---

## BASIC USAGE

### Create Some Memories

```bash
# Terminal 1: Send memories to ingest
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_123",
    "content": "User prefers concise technical answers",
    "memory_type": "episodic"
  }'

# Repeat for similar memories
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_123",
    "content": "User likes short explanations",
    "memory_type": "episodic"
  }'
```

### Trigger Consolidation

```bash
# Manual trigger
curl -X POST http://localhost:8000/semantic/consolidate

# Returns:
{
  "status": "success",
  "concepts_created": 2,
  "compression_ratio": 2.5,
  "memory_reduction_percentage": 60.0,
  "run_id": "run_abc123"
}
```

### List Generated Concepts

```bash
curl "http://localhost:8000/semantic/concepts?user_id=user_123&limit=20"

# Returns:
[
  {
    "id": "concept_id_1",
    "concept_name": "concise_communication_preference",
    "description": "User prefers concise and direct technical communication",
    "confidence": 0.93,
    "support_count": 3,
    "reinforcement_count": 0,
    "created_at": "2026-06-08T12:00:00Z"
  },
  ...
]
```

### View Knowledge Graph

```bash
# Get graph statistics
curl "http://localhost:8000/semantic/graph?user_id=user_123"

# Returns:
{
  "nodes": 5,
  "edges": 8,
  "density": 0.4,
  "avg_clustering_coefficient": 0.667
}

# Get subgraph around concept
curl "http://localhost:8000/semantic/graph/concept_id_1?user_id=user_123&depth=2"

# Returns nodes and edges in JSON format
```

### Search Concepts

```bash
curl -X POST "http://localhost:8000/semantic/concepts/search?user_id=user_123&query=communication"

# Returns matching concepts
```

### Get Consolidation Metrics

```bash
curl "http://localhost:8000/semantic/metrics?user_id=user_123&limit=5"

# Returns historical metrics:
[
  {
    "consolidation_run_id": "run_abc123",
    "total_memories": 100,
    "concept_count": 12,
    "memory_reduction_percentage": 88.0,
    "compression_ratio": 8.33,
    "token_reduction": 2400,
    "processing_time_ms": 1234.5,
    "avg_concept_confidence": 0.89
  }
]
```

---

## COMMON WORKFLOWS

### Workflow 1: Consolidate Daily Memories

```python
from app.services.consolidation_worker import ConsolidationWorker
from uuid import UUID

worker = ConsolidationWorker()

# Consolidate for specific user
metrics = worker.consolidate_user_memories(UUID("user_123"))

print(f"Created {metrics.concept_count} concepts")
print(f"Compression: {metrics.compression_ratio:.2f}x")
print(f"Saved ~{metrics.token_reduction} tokens")
```

### Workflow 2: Automatic Daily Consolidation

Add to your Celery beat schedule:

```python
# In app/workers/celery_app.py or celery configuration
from celery.schedules import crontab

app.conf.beat_schedule = {
    'consolidate-daily': {
        'task': 'app.workers.tasks.periodic_consolidation',
        'schedule': crontab(hour=2, minute=0),  # 2 AM daily
        'args': (50,)  # Process 50 users per run
    },
}
```

### Workflow 3: Retrieve Using Concepts (Day 4+)

```python
# Future: Retrieval will prioritize concepts
query = "How do I structure systems?"

# Get concept matches first (60-90% reduction in retrieved context)
concepts = retrieve_concepts(query, top_k=5)

# Then episodic memories if needed
episodes = retrieve_episodic(query, top_k=3)

# Returned context is highly compressed
context = concepts + episodes  # Much shorter than all 100 memories
```

### Workflow 4: Monitor Consolidation Progress

```bash
# Check current status
curl "http://localhost:8000/semantic/status?user_id=user_123"

# Returns:
{
  "concept_count": 45,
  "memory_count": 800,
  "compression_ratio": 17.8,
  "graph_nodes": 45,
  "graph_edges": 120,
  "graph_density": 0.12,
  "last_consolidation": "2026-06-08T12:00:00Z",
  "last_compression_ratio": 16.5
}
```

---

## UNDERSTANDING THE OUTPUT

### Concept Memory

```json
{
  "concept_name": "backend_systems_preference",
  "description": "User demonstrates consistent interest in backend systems...",
  "confidence": 0.92,              // How confident are we in this concept?
  "support_count": 8,              // How many memories support this?
  "reinforcement_count": 2,        // How many times has it been used?
  "supporting_memory_ids": [...]   // Which memories created this?
  "created_at": "2026-06-08T..."
}
```

### Consolidation Metrics

```json
{
  "compression_ratio": 18.5,                 // memories / concepts
  "memory_reduction_percentage": 94.6,       // (1 - concepts/memories) * 100
  "token_reduction": 4500,                   // Estimated tokens saved
  "concept_count": 127,                      // Total concepts created
  "processing_time_ms": 2345.6,              // How long did it take?
  "avg_concept_confidence": 0.87             // Quality of concepts
}
```

---

## TROUBLESHOOTING

### Issue: "No clusters formed"

**Solution**: 
- Need at least 3 similar memories
- Increase memory importance threshold in test
- Check memory embeddings are being generated

```bash
# Verify memories exist
curl "http://localhost:8000/memories?user_id=user_123&limit=100"

# Check memory importance scores
# Should have >= 3 with importance >= 0.6
```

### Issue: Low Concept Confidence

**Solution**:
- Provide more supporting memories (4+ is ideal)
- Check memory similarity in clusters
- May need to manually refine LLM prompts

```python
# Manually check cluster quality
cluster = session.query(MemoryCluster).first()
print(f"Cluster confidence: {cluster.confidence}")
print(f"Average similarity: {cluster.avg_similarity}")
```

### Issue: OOM Error During Clustering

**Solution**:
- Reduce batch size
- Run consolidation less frequently
- Increase server memory

```python
# In consolidation worker
consolidation_worker.clustering_service.min_cluster_size = 5  # Reduce clusters
```

### Issue: LLM Rate Limit

**Solution**:
- Add retry logic (already implemented)
- Reduce batch size
- Stagger consolidations across time

```bash
# Monitor Celery queue
celery -A app.workers.celery_app inspect active
```

---

## PERFORMANCE TIPS

### For Production

1. **Use Separate Worker Machines**
```bash
# Consolidation is CPU-heavy
# Run on dedicated workers:
celery -A app.workers.celery_app worker -Q consolidation --concurrency=4
```

2. **Batch Process Users**
```python
# Don't consolidate all users simultaneously
periodic_consolidation(batch_size=5)  # Process 5 users per hour
```

3. **Monitor Metrics**
```bash
# Track consolidation health
curl "http://localhost:8000/semantic/metrics?limit=10"
```

4. **Tune Thresholds**
```python
# In ConsolidationWorker
self.min_memories_for_cluster = 4  # Increase for larger clusters
self.min_similarity_for_cluster = 0.80  # Higher = stricter clustering
```

---

## NEXT STEPS

### Day 4: Semantic Reasoning Engine

Once consolidation is working:

1. **Update Retrieval Engine**
   - Prioritize concepts in results
   - Achieve 60-90% context reduction
   - Implement concept scoring

2. **Add Reasoning**
   - Multi-hop concept traversal
   - Inference over concept graph
   - Pattern completion

3. **Enable Planning**
   - Goal decomposition via concepts
   - Action selection from concepts
   - Outcome learning

### Immediate Improvements (Day 3.5)

- [ ] User feedback on concepts
- [ ] Manual concept creation
- [ ] Concept hierarchy discovery
- [ ] Cross-user concept discovery
- [ ] Concept versioning

---

## TESTING

### Run Test Suite

```bash
# All consolidation tests
pytest tests/test_consolidation.py -v

# Specific test class
pytest tests/test_consolidation.py::TestSemanticClustering -v

# With coverage
pytest tests/test_consolidation.py --cov=app/services --cov-report=html
```

### Manual Testing

```python
# Python REPL
from app.services.consolidation_worker import ConsolidationWorker
from uuid import UUID

worker = ConsolidationWorker()
metrics = worker.consolidate_user_memories(UUID("test_user"))

print(metrics)
```

---

## KEY METRICS TO WATCH

| Metric | Target | What It Means |
|--------|--------|---------------|
| Compression Ratio | 15:1 - 25:1 | Memory reduction effectiveness |
| Concept Confidence | 0.85+ | Quality of extracted concepts |
| Memory Reduction % | 85-95% | How much context saved |
| Processing Time | < 5 sec | Consolidation performance |
| Graph Density | 0.05-0.15 | Concept interconnectedness |
| Cluster Size | 3-10 avg | Cluster fragmentation |

---

## ARCHITECTURE OVERVIEW

```
EPISODIC MEMORIES (100)
        ↓
  [CLUSTERING]
        ↓
  CLUSTERS (20)
        ↓
[MERGE REDUNDANCY]
        ↓
CONSOLIDATED (15)
        ↓
[CONCEPT EXTRACTION]
        ↓
CONCEPT MEMORIES (8)
        ↓
[GRAPH BUILDING]
        ↓
KNOWLEDGE GRAPH (8 nodes, 12 edges)
        
Result: 100 → 8 concepts (92.5% reduction)
```

---

## RESOURCES

- **Full Implementation**: `DAY3_IMPLEMENTATION.md`
- **API Reference**: `ARCHITECTURE.md`
- **Code**: `app/services/consolidation_worker.py`
- **Tests**: `tests/test_consolidation.py`
- **Database**: `migrations/versions/003_semantic_consolidation.py`

---

**NeuroWeave Day 3 is live. Your system now has a semantic cortex.** 🧠

For questions or issues, see `DAY3_IMPLEMENTATION.md` for comprehensive documentation.
