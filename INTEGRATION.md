# NeuroWeave System Integration Guide

## Overview

This document provides the complete system integration details for NeuroWeave Day 1.

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                      CLIENT APPLICATION                          │
└──────────────────────┬──────────────────────────────────────────┘
                       │
                       │ HTTP/REST
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                     FASTAPI APPLICATION                          │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                    API LAYER                             │  │
│  │  ├─ POST /memory/ingest                                 │  │
│  │  ├─ POST /memory/retrieve                               │  │
│  │  ├─ POST /memory/reconstruct                            │  │
│  │  ├─ GET /health                                         │  │
│  │  └─ GET /readiness                                      │  │
│  └──────────────────────────────────────────────────────────┘  │
│                       │                                         │
│                       ▼                                         │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                  SERVICE LAYER                           │  │
│  │  ├─ Memory Extraction Service                           │  │
│  │  ├─ Importance Scoring Engine                           │  │
│  │  ├─ Embedding Service                                   │  │
│  │  ├─ Memory Storage Service                              │  │
│  │  ├─ Retrieval Engine                                    │  │
│  │  └─ Context Reconstruction Service                      │  │
│  └──────────────────────────────────────────────────────────┘  │
│                       │                                         │
└───────────────────────┼─────────────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
        ▼              ▼              ▼
    ┌────────┐   ┌─────────┐   ┌──────────┐
    │  PostgreSQL  │  Redis     │  OpenAI  │
    │  + pgvector  │  Cache     │  API     │
    ├────────┤   ├─────────┤   ├──────────┤
    │ Memories   │ Sessions   │ Embeddings│
    │ Users      │ Metadata   │ Extracts  │
    │ Embeddings │ Temp Data  │ Scoring   │
    └────────┘   └─────────┘   └──────────┘
```

## Data Flow

### 1. Memory Ingestion Flow

```
User Conversation
        │
        ▼
┌─────────────────────────────┐
│ Memory Extraction Service   │
│ (LLM-powered extraction)    │
│ Input: Raw conversation    │
│ Output: Structured memories│
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────┐
│ Importance Scoring Engine   │
│ Dual-mode scoring           │
│ (LLM + Heuristic)           │
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────┐
│ Embedding Service           │
│ Generate vector embeddings  │
│ (text-embedding-3-small)    │
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────┐
│ Memory Storage Service      │
│ Store in PostgreSQL         │
│ + pgvector embeddings       │
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────┐
│ Response to Client          │
│ Extracted memories          │
│ Token savings               │
│ Ingestion latency           │
└─────────────────────────────┘
```

### 2. Memory Retrieval Flow

```
Query from Client
        │
        ▼
┌─────────────────────────────┐
│ Embedding Service           │
│ Generate query embedding    │
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────┐
│ Retrieval Engine            │
│ Vector similarity search    │
│ (pgvector + cosine sim)     │
│ Filtering by importance     │
│ Filtering by memory type    │
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────┐
│ Context Compression         │
│ Merge related memories      │
│ Remove duplicates           │
│ Format for LLM              │
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────┐
│ Response to Client          │
│ Retrieved memories          │
│ Compressed context          │
│ Token reduction %           │
│ Retrieval latency           │
└─────────────────────────────┘
```

## Component Integration

### API Layer → Service Layer

**Endpoint**: `POST /memory/ingest`
```python
# app/api/ingest.py
def ingest_memories(request: MemoryIngestRequest) -> MemoryIngestResponse:
    # 1. Extract memories
    extracted = memory_extraction_service.extract_memories(request.conversation)
    
    # 2. Score memories
    scored = [
        ExtractedMemory(
            **mem.dict(),
            importance_score=scoring_engine.score(mem)
        )
        for mem in extracted
    ]
    
    # 3. Filter by threshold
    filtered = [m for m in scored if m.importance_score >= 0.3]
    
    # 4. Generate embeddings
    embeddings = embedding_service.embed_batch([m.content for m in filtered])
    
    # 5. Store in database
    stored = memory_storage_service.store_memories_batch(
        session, request.user_id, 
        list(zip(filtered, embeddings))
    )
    
    return MemoryIngestResponse(...)
```

**Endpoint**: `POST /memory/retrieve`
```python
# app/api/retrieval.py
def retrieve_memories(request: MemoryRetrievalRequest) -> MemoryRetrievalResponse:
    # 1. Retrieve similar memories
    retrieved, latency = memory_retrieval_engine.retrieve_relevant_memories(
        session, request.user_id, request.query, ...
    )
    
    # 2. Compress context
    compressed = memory_retrieval_engine.compress_context(
        retrieved, request.query
    )
    
    return MemoryRetrievalResponse(...)
```

### Database Layer

**ORM Models**: `app/db/models.py`
- User (one-to-many: memories, sessions)
- Memory (with embeddings, logs)
- MemoryEmbedding (stores pgvector)
- RetrievalLog (for analytics)
- Session (tracks interactions)
- MemoryConsolidation (for future consolidation)

**Connection Management**: `app/db/database.py`
- Async engine (for async operations)
- Sync engine (for migrations)
- Session factories
- Connection pooling

## Service Dependencies

```
MemoryExtractionService
  └─ OpenAI API (gpt-4)

ImportanceScoringEngine
  ├─ Heuristic analysis
  └─ Keyword matching

EmbeddingService
  └─ OpenAI API (text-embedding-3-small)

MemoryStorageService
  └─ Database (PostgreSQL)

MemoryRetrievalEngine
  ├─ EmbeddingService (query embedding)
  ├─ Database (pgvector search)
  └─ Cosine similarity calculation

ContextReconstructionService
  └─ MemoryRetrievalEngine
```

## Configuration Management

### Settings Hierarchy

```
app/core/config.py (Settings class)
  ├─ Environment Variables (.env)
  ├─ Default Values
  └─ Validation via Pydantic
```

### Environment Variable Usage

```python
from app.core.config import settings

# Database
settings.database_url  # PostgreSQL connection
settings.database_pool_size  # Connection pool size

# OpenAI
settings.openai_api_key  # API key
settings.openai_embedding_model  # Model name
settings.openai_embedding_dimension  # 1536

# Memory
settings.memory_importance_threshold  # Min importance to store
settings.memory_retrieval_top_k  # Top K results
settings.memory_context_token_limit  # Max tokens

# Application
settings.environment  # production/development
settings.debug  # Enable debug logging
```

## Error Handling & Recovery

### Error Scenarios

1. **Memory Extraction Failure**
   - OpenAI API timeout
   - Malformed JSON response
   - Recovery: Log error, skip memory, continue

2. **Embedding Generation Failure**
   - OpenAI API rate limit
   - Network timeout
   - Recovery: Retry with exponential backoff, store without embedding

3. **Database Connection Loss**
   - Connection pool exhausted
   - Recovery: Queue operations, fail fast to client

4. **Redis Unavailable**
   - Cache connection failed
   - Recovery: Continue without cache, slight latency increase

## Performance Optimization

### Indexing Strategy

```sql
-- Memory lookups by user
CREATE INDEX idx_memory_user_id ON memories(user_id);

-- Importance-based sorting
CREATE INDEX idx_memory_importance ON memories(importance_score DESC);

-- Type filtering
CREATE INDEX idx_memory_type ON memories(memory_type);

-- Time-based queries
CREATE INDEX idx_memory_created_at ON memories(created_at DESC);

-- Vector search (pgvector)
-- Automatically created by pgvector extension
```

### Caching Strategy

**Redis Cache Layers**:
1. User profile (1-hour TTL)
2. Hot memories (24-hour TTL)
3. Session data (temporary)
4. Rate limiting (per minute)

### Batch Operations

```python
# Batch embedding generation (64 items)
embeddings = embedding_service.embed_batch(texts)

# Batch storage (all at once)
memory_storage_service.store_memories_batch(session, user_id, memories)

# Bulk indexing
# Indexes automatically updated with batch inserts
```

## Monitoring & Observability

### Key Metrics

```python
# API Metrics
- request_latency_ms
- request_count (by endpoint)
- error_rate
- active_connections

# Memory Metrics
- ingestion_latency_ms
- extraction_quality_score
- importance_score_distribution
- memory_count_per_user

# Retrieval Metrics
- retrieval_latency_ms
- token_reduction_percent
- memory_recall_rate
- cache_hit_rate

# Database Metrics
- query_latency_ms
- connection_pool_usage
- table_sizes
- index_performance
```

### Logging

```python
# Structured logging
logger.info(
    f"Memory ingested",
    extra={
        "user_id": user_id,
        "memory_count": len(memories),
        "total_tokens_saved": tokens_saved,
        "latency_ms": latency_ms
    }
)
```

## Testing Strategy

### Unit Tests
- Memory extraction accuracy
- Importance scoring logic
- Embedding generation
- Context compression

### Integration Tests
- Full ingestion pipeline
- Retrieval workflow
- Database operations
- API endpoints

### Performance Tests
- Latency benchmarks
- Token efficiency
- Concurrent operations
- Database query performance

## Deployment Considerations

### Pre-Deployment
- [ ] All tests passing (85%+ coverage)
- [ ] Load testing completed
- [ ] Database backups configured
- [ ] Monitoring dashboards created
- [ ] Rollback procedures documented

### Post-Deployment
- [ ] Health checks passing
- [ ] Latency within SLA
- [ ] Token savings > 70%
- [ ] Error rate < 0.1%
- [ ] Memory growth tracking

## Future Extensibility

### Adding New Memory Type

1. Update `MemoryTypeEnum` in `app/db/models.py`
2. Add extraction logic in `memory_extraction_service`
3. Add scoring heuristics in `scoring_engine`
4. Update compression in `context_reconstruction_service`

### Adding New Embedding Model

1. Update `EmbeddingService`
2. Handle dimension changes
3. Migrate existing embeddings (Phase 2)
4. Benchmark performance

### Adding New Retrieval Strategy

1. Extend `MemoryRetrievalEngine`
2. Implement custom scoring
3. Update API parameters
4. Benchmark recall/latency

## Troubleshooting Guide

### High Ingestion Latency
- Check OpenAI API status
- Monitor network latency
- Review batch size settings
- Check database connection pool

### Low Token Savings
- Review importance threshold
- Check extraction quality
- Analyze query diversity
- Validate compression logic

### Database Issues
- Check connection pool
- Verify PostgreSQL health
- Review slow queries
- Check disk space

### Memory Growth
- Monitor memory count per user
- Check importance threshold
- Analyze extraction patterns
- Plan consolidation strategy

---

**This integration guide provides a complete picture of how NeuroWeave Day 1 components work together as a unified system.**
