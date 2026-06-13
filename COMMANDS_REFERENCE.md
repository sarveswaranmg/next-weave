# NeuroWeave Command & Endpoint Reference

## 🚀 Quick Start Commands

### Setup & Installation
```bash
# Clone and navigate
cd /Users/sarves/Desktop/NextWeave

# Install dependencies (local development)
pip install -r requirements.txt

# Copy environment template
cp .env.example .env

# Edit .env with your OpenAI API key
nano .env  # or use your editor
```

### Docker Commands
```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f neuroweave

# Run migrations
docker-compose exec neuroweave alembic upgrade head

# Stop all services
docker-compose down

# Rebuild images
docker-compose build --no-cache

# Access PostgreSQL
docker-compose exec postgres psql -U neuroweave -d neuroweave

# Access Redis CLI
docker-compose exec redis redis-cli

# Check service health
docker-compose exec neuroweave curl http://localhost:8000/health
```

### Development Commands (Make)
```bash
# Run development server
make dev

# Run tests
make test

# Run linting
make lint

# Format code
make format

# Clean cache
make clean

# Start Docker
make docker-up

# Stop Docker
make docker-down

# View Docker logs
make docker-logs

# Run migrations
make migrate

# Create database
make db-create

# Show help
make help
```

### Manual Docker Startup
```bash
# Using provided script
chmod +x docker-start.sh
./docker-start.sh

# Or use quickstart script
chmod +x quickstart.sh
./quickstart.sh
```

---

## 📡 API Endpoints

### Base URL
```
http://localhost:8000
```

### Documentation
```
Swagger UI:    http://localhost:8000/docs
ReDoc:         http://localhost:8000/redoc
OpenAPI JSON:  http://localhost:8000/openapi.json
```

---

## 🧠 Memory Ingestion

### Endpoint
```
POST /memory/ingest
```

### Request
```bash
curl -X POST http://localhost:8000/memory/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "550e8400-e29b-41d4-a716-446655440000",
    "conversation": "I am building an AI startup focused on inference optimization. I prefer concise technical answers.",
    "session_metadata": {}
  }'
```

### Python Example
```python
import requests

response = requests.post(
    "http://localhost:8000/memory/ingest",
    json={
        "user_id": "550e8400-e29b-41d4-a716-446655440000",
        "conversation": "Your conversation text here",
        "session_metadata": {}
    }
)

print(response.json())
```

### Response
```json
{
  "extracted_memories": [
    {
      "memory_type": "identity",
      "content": "Building AI startup focused on inference optimization",
      "summary": "User is building inference optimization startup",
      "importance_score": 0.94,
      "metadata": {"extraction_method": "llm"}
    }
  ],
  "total_tokens_saved": 420,
  "ingestion_latency_ms": 1842.35
}
```

---

## 🔍 Memory Retrieval

### Endpoint
```
POST /memory/retrieve
```

### Request
```bash
curl -X POST http://localhost:8000/memory/retrieve \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "550e8400-e29b-41d4-a716-446655440000",
    "query": "What am I building?",
    "top_k": 10,
    "memory_types": null,
    "min_importance": 0.3
  }'
```

### Python Example
```python
import requests

response = requests.post(
    "http://localhost:8000/memory/retrieve",
    json={
        "user_id": "550e8400-e29b-41d4-a716-446655440000",
        "query": "What am I building?",
        "top_k": 10
    }
)

retrieved = response.json()
print(f"Found {len(retrieved['retrieved_memories'])} memories")
print(f"Token reduction: {retrieved['context_token_reduction_percent']}%")
print(f"Latency: {retrieved['retrieval_latency_ms']}ms")
```

### Response
```json
{
  "retrieved_memories": [
    {
      "id": "650e8400-e29b-41d4-a716-446655440000",
      "user_id": "550e8400-e29b-41d4-a716-446655440000",
      "memory_type": "identity",
      "content": "Building AI startup focused on inference optimization",
      "summary": "User is building inference optimization startup",
      "importance_score": 0.94,
      "reinforcement_count": 0,
      "access_count": 2,
      "last_accessed": "2026-05-13T10:30:00Z",
      "created_at": "2026-05-13T10:00:00Z",
      "updated_at": "2026-05-13T10:30:00Z",
      "metadata": {}
    }
  ],
  "compressed_context": {
    "user_profile": "User Profile:\n- Building AI startup focused on inference optimization",
    "relevant_memories": ["Building AI startup..."],
    "context_summary": "Query: What am I building?\n\nRelevant Context:\n- [identity] Building AI startup...",
    "estimated_tokens": 127
  },
  "retrieval_latency_ms": 523.45,
  "context_token_reduction_percent": 81.2
}
```

---

## 🔄 Context Reconstruction

### Endpoint
```
POST /memory/reconstruct
```

### Request
```bash
curl -X POST http://localhost:8000/memory/reconstruct \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "550e8400-e29b-41d4-a716-446655440000",
    "query": "Help me design the inference pipeline",
    "include_procedural": true,
    "context_token_limit": 2000
  }'
```

### Python Example
```python
import requests

response = requests.post(
    "http://localhost:8000/memory/reconstruct",
    json={
        "user_id": "550e8400-e29b-41d4-a716-446655440000",
        "query": "Help me design the inference pipeline",
        "include_procedural": True
    }
)

context = response.json()
print("Reconstructed Context:")
print(context["reconstructed_context"])
print(f"Tokens: {context['estimated_tokens']}")
```

### Response
```json
{
  "reconstructed_context": "Query: Help me design the inference pipeline...\n\nUser Context:\nInteraction Style:\n- Prefers concise technical answers\n\nUser Profile:\n- Building AI startup...",
  "source_memory_count": 5,
  "estimated_tokens": 256,
  "reconstruction_latency_ms": 412.78
}
```

---

## ❤️ Health & Status

### Health Check
```bash
curl http://localhost:8000/health
```

### Response
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "environment": "development",
  "timestamp": "2026-05-13T10:35:00Z"
}
```

### Readiness Check
```bash
curl http://localhost:8000/readiness
```

### Response
```json
{
  "status": "ready",
  "timestamp": "2026-05-13T10:35:00Z"
}
```

---

## 🗄️ Database Commands

### PostgreSQL Access
```bash
# Connect to database
docker-compose exec postgres psql -U neuroweave -d neuroweave

# Useful queries
psql -U neuroweave -d neuroweave -c "SELECT COUNT(*) FROM memories;"
psql -U neuroweave -d neuroweave -c "SELECT * FROM users LIMIT 5;"
psql -U neuroweave -d neuroweave -c "SELECT memory_type, COUNT(*) FROM memories GROUP BY memory_type;"
```

### Database Backup
```bash
# Backup
docker-compose exec postgres pg_dump -U neuroweave neuroweave > backup.sql

# Restore
docker-compose exec -T postgres psql -U neuroweave neuroweave < backup.sql
```

### Migration Commands
```bash
# Run migrations
docker-compose exec neuroweave alembic upgrade head

# Create new migration
docker-compose exec neuroweave alembic revision --autogenerate -m "Add new table"

# View migration history
docker-compose exec neuroweave alembic history

# Downgrade
docker-compose exec neuroweave alembic downgrade -1
```

---

## 🚀 Testing Commands

### Run All Tests
```bash
pytest -v

# With coverage
pytest -v --cov=app --cov-report=html

# Specific test
pytest tests/test_extraction.py -v

# Watch mode (requires pytest-watch)
pytest-watch

# Specific test function
pytest tests/test_extraction.py::test_extraction_success -v
```

### Linting & Formatting
```bash
# Lint
flake8 app

# Type check
mypy app

# Format
black app

# Sort imports
isort app

# All at once
make lint && make format
```

---

## 🔧 Configuration & Environment

### View Current Config
```bash
# From Python
python -c "from app.core.config import settings; print(settings.dict())"
```

### Update Environment
```bash
# Edit .env file
nano .env

# Or set individual variables
export DATABASE_URL="postgresql://..."
export OPENAI_API_KEY="sk-..."
```

### Common Settings
```bash
# Development
DEBUG=true
LOG_LEVEL=DEBUG
ENVIRONMENT=development

# Production
DEBUG=false
LOG_LEVEL=WARNING
ENVIRONMENT=production

# Memory
MEMORY_IMPORTANCE_THRESHOLD=0.3
MEMORY_RETRIEVAL_TOP_K=10
MEMORY_CONTEXT_TOKEN_LIMIT=2000

# Database
DATABASE_POOL_SIZE=50
DATABASE_MAX_OVERFLOW=100
```

---

## 📊 Monitoring & Logs

### View Logs
```bash
# All services
docker-compose logs

# Specific service
docker-compose logs -f neuroweave

# Last 50 lines
docker-compose logs --tail 50 neuroweave

# API service specifically
docker-compose logs -f neuroweave | grep "memory"
```

### Check Services
```bash
# Service status
docker-compose ps

# Service health
curl http://localhost:8000/health

# Database health
docker-compose exec postgres pg_isready -U neuroweave

# Redis health
docker-compose exec redis redis-cli ping

# Database connections
docker-compose exec postgres psql -U neuroweave -d neuroweave -c "SELECT count(*) FROM pg_stat_activity;"
```

---

## 🎯 Common Workflows

### Complete Memory Lifecycle
```bash
# 1. Ingest
curl -X POST http://localhost:8000/memory/ingest ...

# 2. Retrieve
curl -X POST http://localhost:8000/memory/retrieve ...

# 3. Reconstruct
curl -X POST http://localhost:8000/memory/reconstruct ...

# 4. Use in LLM
# Inject reconstructed_context into your LLM prompt
```

### Development Workflow
```bash
# 1. Start services
docker-compose up -d

# 2. Run migrations
docker-compose exec neuroweave alembic upgrade head

# 3. Start dev server
make dev

# 4. Test endpoints
curl http://localhost:8000/docs

# 5. Check logs
docker-compose logs -f neuroweave

# 6. Stop when done
docker-compose down
```

### Local Development
```bash
# 1. Create virtual environment
python -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Export environment
export DATABASE_URL="postgresql://neuroweave:neuroweave@localhost:5432/neuroweave"
export REDIS_URL="redis://localhost:6379/0"
export OPENAI_API_KEY="sk-..."

# 4. Run server
uvicorn app.main:app --reload

# 5. Test
pytest -v
```

---

## 🐛 Troubleshooting Commands

### Check Everything
```bash
# Health check
curl http://localhost:8000/health

# Database connection
docker-compose exec postgres psql -U neuroweave -d neuroweave -c "SELECT 1"

# Redis connection
docker-compose exec redis redis-cli ping

# API responsiveness
curl -I http://localhost:8000/docs

# Service logs
docker-compose logs --tail 100 neuroweave
```

### Fix Common Issues
```bash
# Restart all services
docker-compose down
docker-compose up -d

# Reset database
docker-compose exec postgres psql -U neuroweave -d neuroweave -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
docker-compose exec neuroweave alembic upgrade head

# Clear cache
docker-compose exec redis redis-cli FLUSHALL

# Rebuild containers
docker-compose build --no-cache
docker-compose up -d
```

---

## 📚 Documentation Commands

### View Documentation
```bash
# Overview
cat README.md

# Architecture
cat ARCHITECTURE.md

# Integration
cat INTEGRATION.md

# Testing
cat TESTING.md

# Deployment
cat DEPLOYMENT.md

# Complete summary
cat COMPLETION_SUMMARY.md

# File reference
cat FILE_REFERENCE.md
```

### Generate Docs
```bash
# API documentation (auto-generated)
http://localhost:8000/docs

# Coverage report
pytest --cov=app --cov-report=html
open htmlcov/index.html
```

---

## 🎓 Learning Resources

### Understand the System
1. README.md - Overview
2. ARCHITECTURE.md - Design
3. examples.py - API examples
4. INTEGRATION.md - Components

### Start Development
1. make dev - Run locally
2. http://localhost:8000/docs - Test API
3. app/main.py - Entry point
4. app/api/ - Endpoints

### Deploy to Production
1. DEPLOYMENT.md - Guide
2. docker-compose.yml - Setup
3. .env.example - Config
4. Dockerfile - Container

---

## ✨ Pro Tips

```bash
# Quick health check loop
watch -n 2 'curl -s http://localhost:8000/health | json_pp'

# Monitor logs in real-time
docker-compose logs -f neuroweave | grep -i "error\|latency"

# Run full pipeline test
./examples.py

# Database size analysis
docker-compose exec postgres psql -U neuroweave -d neuroweave -c \
  "SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) FROM pg_tables WHERE schemaname != 'pg_catalog' ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;"

# Memory statistics
docker-compose exec postgres psql -U neuroweave -d neuroweave -c \
  "SELECT memory_type, COUNT(*), AVG(importance_score), MAX(importance_score) FROM memories GROUP BY memory_type;"
```

---

## 📞 Quick Support

| Issue | Command |
|-------|---------|
| API not responding | `curl http://localhost:8000/health` |
| DB connection error | `docker-compose exec postgres pg_isready -U neuroweave` |
| High latency | `docker-compose logs neuroweave \| tail -20` |
| Out of memory | `docker-compose exec postgres pg_stat_activity` |
| Need backup | `docker-compose exec postgres pg_dump -U neuroweave neuroweave > backup.sql` |

---

**NeuroWeave Command Reference**  
*All commands for development, testing, and deployment*

Last Updated: May 13, 2026
