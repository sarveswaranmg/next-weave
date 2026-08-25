"""
Observability Platform: Prometheus Metrics

Exposes counters/histograms for the runtime's key operations via
`prometheus_client`, scraped at `GET /metrics`. Real, standard Prometheus
exposition format — wire it to an actual Prometheus server + Grafana
dashboard (see `grafana/neuroweave-dashboard.json`) to visualize; this
module only owns instrumentation, not the dashboard itself.
"""
import logging
from prometheus_client import Counter, Histogram, CollectorRegistry, generate_latest

logger = logging.getLogger(__name__)

registry = CollectorRegistry()

CHAT_REQUESTS = Counter(
    "neuroweave_chat_requests_total", "Total chat requests processed",
    ["provider", "status"], registry=registry,
)
CHAT_LATENCY = Histogram(
    "neuroweave_chat_latency_seconds", "End-to-end chat turn latency",
    ["provider"], registry=registry,
)
MEMORY_INGESTED = Counter(
    "neuroweave_memories_ingested_total", "Total memories ingested",
    ["memory_type"], registry=registry,
)
BENCHMARK_RUNS = Counter(
    "neuroweave_benchmark_runs_total", "Total benchmark runs executed",
    ["strategy"], registry=registry,
)
DREAM_SESSIONS = Counter(
    "neuroweave_dream_sessions_total", "Total dream sessions run",
    ["status"], registry=registry,
)


def record_chat(provider: str, status: str, latency_seconds: float) -> None:
    CHAT_REQUESTS.labels(provider=provider, status=status).inc()
    CHAT_LATENCY.labels(provider=provider).observe(latency_seconds)


def record_memory_ingested(memory_type: str) -> None:
    MEMORY_INGESTED.labels(memory_type=memory_type).inc()


def record_benchmark_run(strategy: str) -> None:
    BENCHMARK_RUNS.labels(strategy=strategy).inc()


def record_dream_session(status: str) -> None:
    DREAM_SESSIONS.labels(status=status).inc()


def render_metrics() -> bytes:
    """Render current metrics in Prometheus text exposition format."""
    return generate_latest(registry)
