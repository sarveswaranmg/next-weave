# NeuroWeave - Deployment Guide

## Production Deployment Checklist

### Pre-Deployment

- [ ] All tests passing (>85% coverage)
- [ ] Code reviewed by team
- [ ] Security scan completed
- [ ] Performance benchmarks validated
- [ ] Environment variables configured
- [ ] Database backups automated
- [ ] Monitoring dashboards set up

### Database Setup

```bash
# Create PostgreSQL database
createdb -U postgres neuroweave_prod

# Enable pgvector extension
psql -U postgres -d neuroweave_prod -c "CREATE EXTENSION IF NOT EXISTS vector;"

# Run migrations
alembic upgrade head
```

### Environment Configuration

```bash
# Production .env
DATABASE_URL=postgresql://user:password@db-host:5432/neuroweave_prod
REDIS_URL=redis://redis-host:6379/0
OPENAI_API_KEY=your-production-key
DEBUG=false
ENVIRONMENT=production
LOG_LEVEL=WARNING

# Performance tuning
DATABASE_POOL_SIZE=50
DATABASE_MAX_OVERFLOW=100
MEMORY_EMBEDDING_BATCH_SIZE=64
ASYNC_WORKERS=8
CACHE_TTL_SECONDS=7200
```

### Docker Production Build

```bash
# Build production image
docker build -t neuroweave:latest -f Dockerfile .

# Tag with registry
docker tag neuroweave:latest registry.example.com/neuroweave:1.0.0

# Push to registry
docker push registry.example.com/neuroweave:1.0.0
```

### Kubernetes Deployment

```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: neuroweave-api
  labels:
    app: neuroweave
spec:
  replicas: 3
  selector:
    matchLabels:
      app: neuroweave
  template:
    metadata:
      labels:
        app: neuroweave
    spec:
      containers:
      - name: api
        image: registry.example.com/neuroweave:1.0.0
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: neuroweave-secrets
              key: database-url
        - name: REDIS_URL
          valueFrom:
            secretKeyRef:
              name: neuroweave-secrets
              key: redis-url
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: neuroweave-secrets
              key: openai-api-key
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /readiness
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
```

### Scaling Configuration

```yaml
# hpa.yaml - Horizontal Pod Autoscaler
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: neuroweave-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: neuroweave-api
  minReplicas: 3
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

### Monitoring & Alerting

```yaml
# prometheus-rules.yaml
groups:
- name: neuroweave
  rules:
  - alert: HighIngestLatency
    expr: histogram_quantile(0.95, ingest_latency_ms) > 3000
    for: 5m
    labels:
      severity: warning
  - alert: HighRetrievalError
    expr: rate(retrieval_errors_total[5m]) > 0.01
    for: 5m
    labels:
      severity: critical
  - alert: LowTokenSavings
    expr: avg(token_reduction_percent) < 60
    for: 10m
    labels:
      severity: warning
```

### Backup Strategy

```bash
# Daily automated backups
# PostgreSQL
pg_dump -U neuroweave neuroweave_prod | gzip > backups/db-$(date +%Y%m%d).sql.gz

# Verify backup integrity
gunzip -c backups/db-20260513.sql.gz | psql -U neuroweave neuroweave_test

# Store in S3
aws s3 cp backups/db-20260513.sql.gz s3://neuroweave-backups/
```

### Health Checks

```bash
# API health
curl http://localhost:8000/health

# Database health
psql -U neuroweave -d neuroweave_prod -c "SELECT 1"

# Redis health
redis-cli ping

# Vector index health
psql -U neuroweave -d neuroweave_prod -c "SELECT COUNT(*) FROM memory_embeddings"
```

### Performance Tuning

```sql
-- Optimize query performance
CREATE INDEX CONCURRENTLY idx_memory_importance_type ON memories(importance_score DESC, memory_type);
CREATE INDEX CONCURRENTLY idx_embedding_created ON memory_embeddings(created_at DESC);
ANALYZE memories;
ANALYZE memory_embeddings;

-- Vacuum regularly
VACUUM ANALYZE memories;
VACUUM ANALYZE memory_embeddings;

-- Monitor table sizes
SELECT schemaname, tablename, 
       round(pg_total_relation_size(schemaname||'.'||tablename) / 1024.0 / 1024.0, 2) AS size_mb
FROM pg_tables
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

### Rollback Procedure

```bash
# Keep previous version running
docker tag neuroweave:1.0.0 neuroweave:1.0.0-backup
docker tag neuroweave:latest neuroweave:1.0.0-live

# If issues detected, revert
kubectl set image deployment/neuroweave-api api=registry.example.com/neuroweave:0.9.0

# Verify health
kubectl logs -f deployment/neuroweave-api
curl http://api.example.com/health
```

### Post-Deployment Validation

- [ ] API responds to /health endpoint
- [ ] Memory ingestion successful
- [ ] Memory retrieval working
- [ ] Token savings > 70%
- [ ] Latency < 600ms
- [ ] No error rate spike
- [ ] Database connections healthy
- [ ] Redis cache working
- [ ] All replicas running
- [ ] Monitoring alerts configured

## Support & Troubleshooting

### Common Issues

**High Ingestion Latency**
- Check OpenAI API rate limits
- Monitor network latency
- Verify batch size configuration

**Low Token Savings**
- Review importance scoring thresholds
- Check memory extraction quality
- Analyze query diversity

**Database Connection Errors**
- Verify connection string
- Check database availability
- Review connection pool settings

**Memory Leaks**
- Monitor application memory usage
- Check for unclosed database connections
- Review async task handling

### Emergency Contacts
- On-call: ops@example.com
- Database Admin: dba@example.com
- AI/ML Lead: ai@example.com
