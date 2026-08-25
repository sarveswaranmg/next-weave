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

from neurowave_engine.db.database import get_db, get_db_session
from neurowave_engine.db.models import ApiKey, BenchmarkRun, ProviderCredential
from neurowave_engine.core.config import settings
from neurowave_engine.core.crypto import encrypt_credential
from neurowave_engine.core.security import AuthContext, Role, generate_api_key, has_permission, require_permission, verify_api_key
from neurowave_engine.schemas.runtime import (
    ChatRequest, ChatResponse, BenchmarkRequest, BenchmarkResponse, BenchmarkRunSchema,
    EvaluateRequest, EvaluateResponse, RuntimeMetricsResponse, RuntimeHealthResponse,
    RuntimeVersionResponse, PluginActionRequest, PluginActionResponse, PluginInfo,
    DashboardResponse, DeleteUserResponse, ApiKeyCreateRequest, ApiKeyCreateResponse,
    ApiKeyInfo, ApiKeyListResponse, RevokeApiKeyResponse, ProviderCredentialRequest,
    ProviderCredentialInfo, ProviderCredentialListResponse, DeleteProviderCredentialResponse,
)
from neurowave_engine.services.runtime_orchestrator import RuntimeOrchestrator
from neurowave_engine.services.benchmark_suite import NeuroBench
from neurowave_engine.services.runtime_metrics_service import RuntimeMetricsService
from neurowave_engine.services.explainability_engine import ExplainabilityEngine
from neurowave_engine.services.plugin_system import default_registry
from neurowave_engine.services.data_deletion_service import DataDeletionService
from neurowave_engine.services.tenancy import get_owned_user_or_404
from neurowave_engine.services.credential_resolver import resolve_provider_kwargs
from neurowave_engine.services.llm_providers import ProviderCredentialError
from neurowave_engine.utils.prometheus_metrics import record_chat, record_benchmark_run, render_metrics

logger = logging.getLogger(__name__)

# No router-level auth dependency anymore - each route declares the exact
# permission it needs via Depends(require_permission(...)), since
# different routes need different roles (e.g. minting a new key is
# admin-only, reading metrics isn't). /health and /version stay
# unauthenticated (see their handlers) - same convention as the
# Prometheus scrape endpoint below.
router = APIRouter(prefix="/runtime", tags=["runtime"])

# Separate, unauthenticated router for the Prometheus scrape endpoint -
# metrics endpoints are conventionally exempt from API auth so a scraper
# doesn't need application credentials.
metrics_router = APIRouter(tags=["observability"])


@router.post("/chat", response_model=ChatResponse)
async def runtime_chat(
    request: ChatRequest, session: Session = Depends(get_db),
    auth: AuthContext = Depends(require_permission("write")),
) -> ChatResponse:
    """
    Run one full cognitive runtime chat turn: memory ingestion, world
    model update, predictive recall + context composition, an LLM call,
    and background scheduling for memory evolution/consolidation.
    """
    start = time.time()
    provider_label = request.provider or settings.runtime_default_provider
    try:
        provider_kwargs = resolve_provider_kwargs(session, auth.tenant_id, provider_label)
        orchestrator = RuntimeOrchestrator(session)
        result = orchestrator.chat(
            user_id=request.user_id, tenant_id=auth.tenant_id, message=request.message, provider=request.provider,
            model=request.model, memory=request.memory, world_model=request.world_model,
            predictive_recall=request.predictive_recall, context_composer=request.context_composer,
            token_budget=request.token_budget, schedule_background=request.schedule_background,
            provider_kwargs=provider_kwargs,
        )
        record_chat(result["provider"], "success", (time.time() - start))
        return ChatResponse(**result)
    except ProviderCredentialError as e:
        record_chat(provider_label, "error", (time.time() - start))
        raise HTTPException(status_code=422, detail=str(e))
    except HTTPException:
        record_chat(provider_label, "error", (time.time() - start))
        raise
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

    WebSocket routes don't inherit router-level Depends(), so auth is
    resolved manually here from an `X-API-Key` header or `?api_key=`
    query param, before the connection is accepted.
    """
    x_api_key = websocket.headers.get("x-api-key") or websocket.query_params.get("api_key")
    auth_session = get_db_session()
    try:
        auth = await verify_api_key(x_api_key=x_api_key, db=auth_session)
    except HTTPException as e:
        await websocket.close(code=4401, reason=e.detail)
        return
    finally:
        auth_session.close()

    if not has_permission(auth.role, "write"):
        await websocket.close(code=4403, reason="API key lacks the 'write' permission")
        return

    await websocket.accept()
    try:
        while True:
            payload = await websocket.receive_json()
            session = get_db_session()
            try:
                provider_label = payload.get("provider") or settings.runtime_default_provider
                provider_kwargs = resolve_provider_kwargs(session, auth.tenant_id, provider_label)
                orchestrator = RuntimeOrchestrator(session)
                result = orchestrator.chat(
                    user_id=UUID(payload["user_id"]), tenant_id=auth.tenant_id, message=payload["message"],
                    provider=payload.get("provider"), model=payload.get("model"),
                    schedule_background=payload.get("schedule_background", True),
                    provider_kwargs=provider_kwargs,
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
    request: BenchmarkRequest, session: Session = Depends(get_db),
    auth: AuthContext = Depends(require_permission("run_benchmarks")),
) -> BenchmarkResponse:
    """Run NeuroBench: compare memory strategies on one query/history pair."""
    get_owned_user_or_404(session, request.user_id, auth.tenant_id)
    try:
        bench = NeuroBench(session)
        runs = bench.run(
            user_id=request.user_id, query=request.query, history=request.history,
            strategies=request.strategies, dataset=request.dataset,
        )
        for run in runs:
            record_benchmark_run(run.strategy)
        return BenchmarkResponse(runs=[BenchmarkRunSchema.model_validate(r) for r in runs])
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Runtime benchmark error: {e}")
        raise HTTPException(status_code=500, detail=f"Benchmark failed: {str(e)}")


@router.post("/evaluate", response_model=EvaluateResponse)
async def runtime_evaluate(
    request: EvaluateRequest, session: Session = Depends(get_db),
    auth: AuthContext = Depends(require_permission("run_benchmarks")),
) -> EvaluateResponse:
    """Continuous Evaluation Pipeline entry point: generate a synthetic
    dataset (under the caller's own tenant) and benchmark every strategy
    against it."""
    try:
        bench = NeuroBench(session)
        runs = bench.run_dataset(
            dataset_name=request.dataset_name, user_count=request.user_count, seed=request.seed,
            tenant_id=auth.tenant_id,
        )
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
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Runtime evaluate error: {e}")
        raise HTTPException(status_code=500, detail=f"Evaluation failed: {str(e)}")


@router.get("/metrics", response_model=RuntimeMetricsResponse)
async def runtime_metrics(
    user_id: UUID, session: Session = Depends(get_db),
    auth: AuthContext = Depends(require_permission("read")),
) -> RuntimeMetricsResponse:
    """
    Point-in-time rollup of memory/concept/identity/world-graph scale and
    health for one of the caller's own users. (The global, all-tenants
    rollup this service also supports is an internal ops concern, not
    exposed on this tenant-facing route - see RuntimeMetricsService for
    an internal admin script that needs it.)
    """
    get_owned_user_or_404(session, user_id, auth.tenant_id)
    try:
        metrics = RuntimeMetricsService(session).compute(user_id=user_id)
        return RuntimeMetricsResponse(user_id=user_id, **metrics)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Runtime metrics error: {e}")
        raise HTTPException(status_code=500, detail="Failed to compute runtime metrics")


@router.get("/health", response_model=RuntimeHealthResponse)
async def runtime_health(session: Session = Depends(get_db)) -> RuntimeHealthResponse:
    """
    Runtime health check, including database connectivity. Deliberately
    unauthenticated (like /metrics) - a k8s readiness/liveness probe
    shouldn't need a tenant credential.
    """
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
    """Runtime and component version info. Unauthenticated - no sensitive data."""
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
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(require_permission("read")),
) -> dict:
    """Explain a NeuroWeave decision: why a memory was selected, why it
    evolved, why identity changed, why a dream session made the changes it
    did, or why an architectural decision was made."""
    get_owned_user_or_404(session, user_id, auth.tenant_id)
    try:
        engine = ExplainabilityEngine(session)
        return engine.explain(user_id, subject_type, subject_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Runtime explain error: {e}")
        raise HTTPException(status_code=500, detail=f"Explain failed: {str(e)}")


@router.post("/plugins", response_model=PluginActionResponse)
async def runtime_plugins(
    request: PluginActionRequest,
    auth: AuthContext = Depends(require_permission("read")),
) -> PluginActionResponse:
    """List or unregister cognitive plugins. Registering a *new* plugin
    class requires a Python import (see `PluginRegistry.register()`);
    this endpoint manages the runtime's already-imported plugin set."""
    if request.action == "list":
        pass
    elif request.action == "unregister":
        if not has_permission(auth.role, "manage_plugins"):
            raise HTTPException(status_code=403, detail="API key role lacks the 'manage_plugins' permission")
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
    user_id: UUID, session: Session = Depends(get_db),
    auth: AuthContext = Depends(require_permission("read")),
) -> DashboardResponse:
    """
    Bundled summary for observability dashboards: current metrics +
    recent benchmark runs, for one of the caller's own users. Real data
    contract; rendering it in an actual Grafana panel is a dashboard-JSON
    exercise (see `grafana/`), not an API concern.
    """
    get_owned_user_or_404(session, user_id, auth.tenant_id)
    try:
        metrics = RuntimeMetricsService(session).compute(user_id=user_id, persist=False)

        recent_runs = (
            session.query(BenchmarkRun)
            .filter(BenchmarkRun.user_id == user_id)
            .order_by(BenchmarkRun.created_at.desc())
            .limit(10)
            .all()
        )

        return DashboardResponse(
            user_id=user_id,
            runtime_metrics=RuntimeMetricsResponse(user_id=user_id, **metrics),
            recent_benchmark_runs=[BenchmarkRunSchema.model_validate(r) for r in recent_runs],
            version=settings.runtime_version,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Runtime dashboard error: {e}")
        raise HTTPException(status_code=500, detail="Failed to build dashboard")


@router.delete("/users/{user_id}", response_model=DeleteUserResponse)
async def delete_user_data(
    user_id: UUID, session: Session = Depends(get_db),
    auth: AuthContext = Depends(require_permission("delete")),
) -> DeleteUserResponse:
    """GDPR/CCPA 'right to be forgotten': permanently delete all data for
    one of the caller's own users."""
    get_owned_user_or_404(session, user_id, auth.tenant_id)
    try:
        service = DataDeletionService(session)
        counts = service.delete_user(user_id)
        return DeleteUserResponse(user_id=user_id, deleted_counts=counts)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete user error: {e}")
        raise HTTPException(status_code=500, detail=f"Deletion failed: {str(e)}")


@router.post("/keys", response_model=ApiKeyCreateResponse)
async def create_api_key(
    request: ApiKeyCreateRequest, session: Session = Depends(get_db),
    auth: AuthContext = Depends(require_permission("manage_keys")),
) -> ApiKeyCreateResponse:
    """Mint an additional API key for the caller's own tenant. The
    plaintext key is returned exactly once - only its hash is stored."""
    try:
        role = Role(request.role)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown role '{request.role}'")

    raw_key, key_prefix, hashed_secret = generate_api_key()
    api_key = ApiKey(
        tenant_id=auth.tenant_id, key_prefix=key_prefix, hashed_secret=hashed_secret,
        role=role, name=request.name,
    )
    session.add(api_key)
    session.commit()
    session.refresh(api_key)

    return ApiKeyCreateResponse(
        id=api_key.id, api_key=raw_key, key_prefix=key_prefix, role=role.value, name=request.name,
    )


@router.get("/keys", response_model=ApiKeyListResponse)
async def list_api_keys(
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(require_permission("read")),
) -> ApiKeyListResponse:
    """List the caller's own tenant's API keys (prefixes only - never
    secret material)."""
    keys = session.query(ApiKey).filter(ApiKey.tenant_id == auth.tenant_id).all()
    return ApiKeyListResponse(keys=[
        ApiKeyInfo(
            id=k.id, key_prefix=k.key_prefix, role=Role(k.role).value, name=k.name,
            created_at=k.created_at, last_used_at=k.last_used_at, revoked_at=k.revoked_at,
        )
        for k in keys
    ])


@router.delete("/keys/{key_id}", response_model=RevokeApiKeyResponse)
async def revoke_api_key(
    key_id: UUID, session: Session = Depends(get_db),
    auth: AuthContext = Depends(require_permission("manage_keys")),
) -> RevokeApiKeyResponse:
    """Revoke one of the caller's own tenant's API keys."""
    api_key = session.query(ApiKey).filter(ApiKey.id == key_id).first()
    if not api_key or api_key.tenant_id != auth.tenant_id:
        raise HTTPException(status_code=404, detail=f"No API key {key_id}")

    api_key.revoked_at = datetime.utcnow()
    session.commit()
    return RevokeApiKeyResponse(id=key_id, revoked=True)


@router.post("/credentials", response_model=ProviderCredentialInfo)
async def upsert_provider_credential(
    request: ProviderCredentialRequest, session: Session = Depends(get_db),
    auth: AuthContext = Depends(require_permission("manage_keys")),
) -> ProviderCredentialInfo:
    """
    Store or replace a BYOK LLM provider credential for the caller's own
    tenant (bring-your-own-key). Encrypted at rest (see
    `app/core/crypto.py`); the raw key is never returned by this or any
    other endpoint - only whether one is configured.
    """
    encrypted = encrypt_credential(request.api_key)
    existing = (
        session.query(ProviderCredential)
        .filter(ProviderCredential.tenant_id == auth.tenant_id, ProviderCredential.provider == request.provider)
        .first()
    )
    if existing:
        existing.encrypted_api_key = encrypted
        existing.base_url_override = request.base_url_override
        credential = existing
    else:
        credential = ProviderCredential(
            tenant_id=auth.tenant_id, provider=request.provider,
            encrypted_api_key=encrypted, base_url_override=request.base_url_override,
        )
        session.add(credential)
    session.commit()
    session.refresh(credential)
    return ProviderCredentialInfo.model_validate(credential)


@router.get("/credentials", response_model=ProviderCredentialListResponse)
async def list_provider_credentials(
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(require_permission("read")),
) -> ProviderCredentialListResponse:
    """List the caller's own tenant's configured BYOK providers (never the keys themselves)."""
    credentials = session.query(ProviderCredential).filter(ProviderCredential.tenant_id == auth.tenant_id).all()
    return ProviderCredentialListResponse(
        credentials=[ProviderCredentialInfo.model_validate(c) for c in credentials]
    )


@router.delete("/credentials/{provider}", response_model=DeleteProviderCredentialResponse)
async def delete_provider_credential(
    provider: str, session: Session = Depends(get_db),
    auth: AuthContext = Depends(require_permission("manage_keys")),
) -> DeleteProviderCredentialResponse:
    """Remove a stored BYOK credential for the caller's own tenant."""
    deleted = (
        session.query(ProviderCredential)
        .filter(ProviderCredential.tenant_id == auth.tenant_id, ProviderCredential.provider == provider)
        .delete(synchronize_session=False)
    )
    session.commit()
    return DeleteProviderCredentialResponse(provider=provider, deleted=bool(deleted))


@metrics_router.get("/metrics")
async def prometheus_metrics_endpoint():
    """Prometheus scrape endpoint (unauthenticated, standard convention)."""
    return Response(content=render_metrics(), media_type="text/plain; version=0.0.4; charset=utf-8")
