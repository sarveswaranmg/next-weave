"""Day 10: Cognitive Runtime Platform API endpoints"""
import logging
import time
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.database import get_db_session
from app.db.models import BenchmarkRun
from app.core.config import settings
from app.core.security import verify_api_key
from app.schemas.runtime import (
    ChatRequest, ChatResponse, BenchmarkRequest, BenchmarkResponse, BenchmarkRunSchema,
    EvaluateRequest, EvaluateResponse, RuntimeMetricsResponse, RuntimeHealthResponse,
    RuntimeVersionResponse, PluginActionRequest, PluginActionResponse, PluginInfo,
    DashboardResponse, DeleteUserResponse,
)
from app.services.runtime_orchestrator import RuntimeOrchestrator
from app.services.benchmark_suite import NeuroBench
from app.services.runtime_metrics_service import RuntimeMetricsService
from app.services.explainability_engine import ExplainabilityEngine
from app.services.plugin_system import default_registry
from app.services.data_deletion_service import DataDeletionService
from app.utils.prometheus_metrics import record_chat, record_benchmark_run, render_metrics

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/runtime", tags=["runtime"], dependencies=[Depends(verify_api_key)])

# Separate, unauthenticated router for the Prometheus scrape endpoint -
# metrics endpoints are conventionally exempt from API auth so a scraper
# doesn't need application credentials.
metrics_router = APIRouter(tags=["observability"])


@router.post("/chat", response_model=ChatResponse)
async def runtime_chat(request: ChatRequest, session: Session = Depends(get_db_session)) -> ChatResponse:
    """
    Run one full cognitive runtime chat turn: memory ingestion, world
    model update, predictive recall + context composition, an LLM call,
    and background scheduling for memory evolution/consolidation.
    """
    start = time.time()
    provider_label = request.provider or settings.runtime_default_provider
    try:
        orchestrator = RuntimeOrchestrator(session)
        result = orchestrator.chat(
            user_id=request.user_id, message=request.message, provider=request.provider,
            model=request.model, memory=request.memory, world_model=request.world_model,
            predictive_recall=request.predictive_recall, context_composer=request.context_composer,
            token_budget=request.token_budget, schedule_background=request.schedule_background,
        )
        record_chat(result["provider"], "success", (time.time() - start))
        return ChatResponse(**result)
    except Exception as e:
        record_chat(provider_label, "error", (time.time() - start))
        logger.error(f"Runtime chat error: {e}")
        raise HTTPException(status_code=500, detail=f"Chat failed: {str(e)}")


@router.websocket("/chat/stream")
async def runtime_chat_stream(websocket: WebSocket):
    """
    Streaming chat transport: accepts `{"user_id", "message", ...}` JSON
    frames and streams the response back in chunks. The underlying
    pipeline still runs as one unit — `LLMProvider.complete()` isn't
    itself token-streaming in this build — so this chunks the completed
    response for a streaming *transport* experience; true token-by-token
    provider streaming is a natural next step behind the same
    `LLMProvider` interface (see `DAY10_RUNTIME_PLATFORM.md`).
    """
    await websocket.accept()
    try:
        while True:
            payload = await websocket.receive_json()
            session = get_db_session()
            try:
                orchestrator = RuntimeOrchestrator(session)
                result = orchestrator.chat(
                    user_id=UUID(payload["user_id"]), message=payload["message"],
                    provider=payload.get("provider"), model=payload.get("model"),
                    schedule_background=payload.get("schedule_background", True),
                )
                response_text = result["response"]
                chunk_size = 40
                for i in range(0, len(response_text), chunk_size):
                    await websocket.send_json({"type": "chunk", "content": response_text[i:i + chunk_size]})
                await websocket.send_json({
                    "type": "done", "usage": result["usage"], "total_latency_ms": result["total_latency_ms"],
                })
            finally:
                session.close()
    except WebSocketDisconnect:
        logger.info("Runtime chat stream client disconnected")
    except Exception as e:
        logger.error(f"Runtime chat stream error: {e}")
        try:
            await websocket.send_json({"type": "error", "error": str(e)})
        except Exception:
            pass


@router.post("/benchmark", response_model=BenchmarkResponse)
async def runtime_benchmark(
    request: BenchmarkRequest, session: Session = Depends(get_db_session)
) -> BenchmarkResponse:
    """Run NeuroBench: compare memory strategies on one query/history pair."""
    try:
        bench = NeuroBench(session)
        runs = bench.run(
            user_id=request.user_id, query=request.query, history=request.history,
            strategies=request.strategies, dataset=request.dataset,
        )
        for run in runs:
            record_benchmark_run(run.strategy)
        return BenchmarkResponse(runs=[BenchmarkRunSchema.model_validate(r) for r in runs])
    except Exception as e:
        logger.error(f"Runtime benchmark error: {e}")
        raise HTTPException(status_code=500, detail=f"Benchmark failed: {str(e)}")


@router.post("/evaluate", response_model=EvaluateResponse)
async def runtime_evaluate(
    request: EvaluateRequest, session: Session = Depends(get_db_session)
) -> EvaluateResponse:
    """Continuous Evaluation Pipeline entry point: generate a synthetic
    dataset and benchmark every strategy against it."""
    try:
        bench = NeuroBench(session)
        runs = bench.run_dataset(dataset_name=request.dataset_name, user_count=request.user_count, seed=request.seed)
        for run in runs:
            record_benchmark_run(run.strategy)

        summary: dict = {}
        for run in runs:
            bucket = summary.setdefault(run.strategy, {"latency_ms": [], "token_usage": [], "compression_ratio": []})
            bucket["latency_ms"].append(run.latency_ms)
            bucket["token_usage"].append(run.token_usage)
            bucket["compression_ratio"].append(run.compression_ratio)

        averaged = {
            strategy: {metric: (sum(values) / len(values) if values else 0.0) for metric, values in metrics.items()}
            for strategy, metrics in summary.items()
        }

        return EvaluateResponse(
            dataset_name=request.dataset_name, users_evaluated=request.user_count,
            runs=[BenchmarkRunSchema.model_validate(r) for r in runs], summary=averaged,
        )
    except Exception as e:
        logger.error(f"Runtime evaluate error: {e}")
        raise HTTPException(status_code=500, detail=f"Evaluation failed: {str(e)}")


@router.get("/metrics", response_model=RuntimeMetricsResponse)
async def runtime_metrics(
    user_id: Optional[UUID] = None, session: Session = Depends(get_db_session)
) -> RuntimeMetricsResponse:
    """Point-in-time rollup of memory/concept/identity/world-graph scale and health."""
    try:
        metrics = RuntimeMetricsService(session).compute(user_id=user_id)
        return RuntimeMetricsResponse(user_id=user_id, **metrics)
    except Exception as e:
        logger.error(f"Runtime metrics error: {e}")
        raise HTTPException(status_code=500, detail="Failed to compute runtime metrics")


@router.get("/health", response_model=RuntimeHealthResponse)
async def runtime_health(session: Session = Depends(get_db_session)) -> RuntimeHealthResponse:
    """Runtime health check, including database connectivity."""
    db_status = "connected"
    try:
        session.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"error: {e}"

    return RuntimeHealthResponse(
        status="healthy" if db_status == "connected" else "degraded",
        version=settings.runtime_version, environment=settings.environment,
        database=db_status, timestamp=datetime.utcnow(),
    )


@router.get("/version", response_model=RuntimeVersionResponse)
async def runtime_version() -> RuntimeVersionResponse:
    """Runtime and component version info."""
    return RuntimeVersionResponse(
        version=settings.runtime_version, app_name=settings.app_name, day=10,
        components=[
            "memory", "cognitive_scoring", "semantic_consolidation", "identity_graph",
            "predictive_recall", "context_composer", "memory_evolution", "dream_mode",
            "world_model", "runtime_platform",
        ],
    )


@router.get("/explain")
async def runtime_explain(
    user_id: UUID, subject_type: str, subject_id: Optional[UUID] = None,
    session: Session = Depends(get_db_session),
) -> dict:
    """Explain a NeuroWeave decision: why a memory was selected, why it
    evolved, why identity changed, why a dream session made the changes it
    did, or why an architectural decision was made."""
    try:
        engine = ExplainabilityEngine(session)
        return engine.explain(user_id, subject_type, subject_id)
    except Exception as e:
        logger.error(f"Runtime explain error: {e}")
        raise HTTPException(status_code=500, detail=f"Explain failed: {str(e)}")


@router.post("/plugins", response_model=PluginActionResponse)
async def runtime_plugins(request: PluginActionRequest) -> PluginActionResponse:
    """List or unregister cognitive plugins. Registering a *new* plugin
    class requires a Python import (see `PluginRegistry.register()`);
    this endpoint manages the runtime's already-imported plugin set."""
    if request.action == "list":
        pass
    elif request.action == "unregister":
        if not request.plugin_name:
            raise HTTPException(status_code=400, detail="plugin_name is required to unregister")
        default_registry.unregister(request.plugin_name)
    elif request.action == "register":
        raise HTTPException(
            status_code=400,
            detail="Registering a new plugin class requires a Python import - "
                   "see PluginRegistry.register() in app/services/plugin_system.py",
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action '{request.action}'")

    return PluginActionResponse(
        action=request.action,
        plugins=[PluginInfo(**p) for p in default_registry.list()],
    )


@router.get("/dashboard", response_model=DashboardResponse)
async def runtime_dashboard(
    user_id: Optional[UUID] = None, session: Session = Depends(get_db_session)
) -> DashboardResponse:
    """
    Bundled summary for observability dashboards: current metrics +
    recent benchmark runs. Real data contract; rendering it in an actual
    Grafana panel is a dashboard-JSON exercise (see `grafana/`), not an
    API concern.
    """
    try:
        metrics = RuntimeMetricsService(session).compute(user_id=user_id, persist=False)

        query = session.query(BenchmarkRun)
        if user_id:
            query = query.filter(BenchmarkRun.user_id == user_id)
        recent_runs = query.order_by(BenchmarkRun.created_at.desc()).limit(10).all()

        return DashboardResponse(
            user_id=user_id,
            runtime_metrics=RuntimeMetricsResponse(user_id=user_id, **metrics),
            recent_benchmark_runs=[BenchmarkRunSchema.model_validate(r) for r in recent_runs],
            version=settings.runtime_version,
        )
    except Exception as e:
        logger.error(f"Runtime dashboard error: {e}")
        raise HTTPException(status_code=500, detail="Failed to build dashboard")


@router.delete("/users/{user_id}", response_model=DeleteUserResponse)
async def delete_user_data(user_id: UUID, session: Session = Depends(get_db_session)) -> DeleteUserResponse:
    """GDPR/CCPA 'right to be forgotten': permanently delete all data for a user."""
    try:
        service = DataDeletionService(session)
        counts = service.delete_user(user_id)
        return DeleteUserResponse(user_id=user_id, deleted_counts=counts)
    except Exception as e:
        logger.error(f"Delete user error: {e}")
        raise HTTPException(status_code=500, detail=f"Deletion failed: {str(e)}")


@metrics_router.get("/metrics")
async def prometheus_metrics_endpoint():
    """Prometheus scrape endpoint (unauthenticated, standard convention)."""
    return Response(content=render_metrics(), media_type="text/plain; version=0.0.4; charset=utf-8")
