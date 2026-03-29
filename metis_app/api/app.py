"""FastAPI surface for METIS's engine layer."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import pathlib
import secrets
import tempfile
import time
import uuid
from collections.abc import AsyncGenerator, Generator
from typing import Any

from fastapi import Depends, FastAPI, File, HTTPException, Header, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import ValidationError

import metis_app.settings_store as _settings_store
from metis_app.engine import list_indexes
from metis_app.engine.querying import _normalize_run_id
from metis_app.services.nyx_catalog import NyxCatalogComponentNotFoundError
from metis_app.services.nyx_install_executor import (
    NyxInstallActionExecutionError,
    execute_nyx_install_action,
)
from metis_app.services.nyx_runtime import NYX_INSTALL_ACTION_TYPE, find_persisted_nyx_install_action
from metis_app.services.stream_replay import ReplayableRunStreamManager
from metis_app.services.topo_scaffold import compute_scaffold, scaffold_to_payload
from metis_app.services.trace_store import TraceStore
from metis_app.services.workspace_orchestrator import WorkspaceOrchestrator
from metis_app.utils.feature_flags import FeatureFlag, get_feature_statuses

from . import gguf as _gguf
from . import features as _features
from . import logs as _logs
from . import sessions as _sessions
from . import settings as _settings
from . import assistant as _assistant
from . import autonomous as _autonomous
from .models import (
    DirectQueryRequestModel,
    DirectQueryResultModel,
    IndexBuildRequestModel,
    IndexBuildResultModel,
    KnowledgeSearchRequestModel,
    KnowledgeSearchResultModel,
    NyxCatalogComponentDetailModel,
    NyxCatalogSearchResponseModel,
    OpenAIChatCompletionChoiceModel,
    OpenAIChatCompletionMessageOutputModel,
    OpenAIChatCompletionRequestModel,
    OpenAIChatCompletionResponseModel,
    OpenAIChatCompletionUsageModel,
    RagQueryRequestModel,
    RagQueryResultModel,
    RunActionRequestModel,
    UiTelemetryIngestRequestModel,
    UiTelemetrySummaryResponseModel,
)

_DEFAULT_LOCAL_ORIGINS = [
    "http://localhost",
    "http://127.0.0.1",
    "https://localhost",
    "https://127.0.0.1",
]

_RAG_STREAM_MANAGER = ReplayableRunStreamManager()
_MAX_UI_TELEMETRY_REQUEST_BYTES = 16_384
_BRAIN_SCAFFOLD_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_BRAIN_SCAFFOLD_TTL_SECONDS = 30.0

_bearer_scheme = HTTPBearer(auto_error=False)


def _cors_origins_from_env() -> list[str]:
    raw = os.getenv("METIS_API_CORS_ORIGINS", "")
    if not raw.strip():
        return _DEFAULT_LOCAL_ORIGINS
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def _require_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> None:
    """Enforce Bearer-token auth when METIS_API_TOKEN is set.

    When the environment variable is not set (the default) all requests are
    allowed, preserving backward-compatible local-only usage.  Once set, every
    request to a protected endpoint must carry a matching token.

    Raises HTTPException with status 401 if the token is required but the
    request provides no credentials or an incorrect token.
    """
    required_token = os.getenv("METIS_API_TOKEN", "").strip()
    if not required_token:
        return  # Auth not configured — allow all requests
    if credentials is None or not secrets.compare_digest(
        credentials.credentials, required_token
    ):
        raise HTTPException(status_code=401, detail="Unauthorized")


log = logging.getLogger(__name__)


def _append_nyx_install_action_event(
    *,
    trace_store: TraceStore,
    run_id: str,
    approved: bool,
    action_id: str,
    proposal_token: str,
    component_names: list[str],
    component_count: int,
    execution_status: str,
    status: str,
    extra_payload: dict[str, Any] | None = None,
) -> None:
    payload = {
        "approved": approved,
        "action_id": action_id,
        "action_type": NYX_INSTALL_ACTION_TYPE,
        "proposal_token": proposal_token,
        "component_names": component_names,
        "component_count": component_count,
        "execution_status": execution_status,
        "status": status,
    }
    if isinstance(extra_payload, dict):
        payload.update(extra_payload)
    trace_store.append_event(
        run_id=run_id,
        stage="action_required",
        event_type="nyx_install_action_submitted",
        payload=payload,
    )


def _nyx_install_http_status(error_code: str) -> int:
    if error_code in {
        "unsupported_action",
        "invalid_proposal",
        "component_mismatch",
        "action_mismatch",
        "proposal_mismatch",
    }:
        return 400
    if error_code in {
        "unsupported_component",
        "preview_only_component",
        "unsafe_component",
        "stale_proposal",
    }:
        return 409
    if error_code in {"revalidation_failed", "installer_unavailable"}:
        return 503
    return 500


def _looks_like_nyx_action_reference(
    *,
    action_type: str,
    action_id: str,
    proposal_token: str,
) -> bool:
    return (
        str(action_type or "").strip() == NYX_INSTALL_ACTION_TYPE
        or str(action_id or "").strip().startswith("nyx-install:")
        or str(proposal_token or "").strip().startswith("nyx-proposal:")
    )


def _resolve_persisted_nyx_install_action(
    *,
    run_id: str,
    trace_store: TraceStore,
    action_id: str,
    proposal_token: str,
    infer_latest: bool,
) -> tuple[dict[str, Any] | None, str]:
    exact_match = find_persisted_nyx_install_action(
        run_id=run_id,
        trace_store=trace_store,
        action_id=action_id,
        proposal_token=proposal_token,
    )
    if exact_match is not None:
        return exact_match, "exact"

    if action_id:
        action_match = find_persisted_nyx_install_action(
            run_id=run_id,
            trace_store=trace_store,
            action_id=action_id,
        )
        if action_match is not None:
            return action_match, "action_id"

    if proposal_token:
        token_match = find_persisted_nyx_install_action(
            run_id=run_id,
            trace_store=trace_store,
            proposal_token=proposal_token,
        )
        if token_match is not None:
            return token_match, "proposal_token"

    if infer_latest:
        latest_match = find_persisted_nyx_install_action(
            run_id=run_id,
            trace_store=trace_store,
            allow_latest=True,
        )
        if latest_match is not None:
            return latest_match, "latest"

    return None, ""


def create_app() -> FastAPI:
    app = FastAPI(title="METIS API", version="1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins_from_env(),
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["*"],
    )

    # Protected routers — require token when METIS_API_TOKEN is set
    _auth = [Depends(_require_token)]
    app.include_router(_sessions.router, dependencies=_auth)
    app.include_router(_settings.router, dependencies=_auth)
    app.include_router(_logs.router, dependencies=_auth)
    app.include_router(_gguf.router, dependencies=_auth)
    app.include_router(_assistant.router, dependencies=_auth)
    app.include_router(_autonomous.router, dependencies=_auth)
    app.include_router(_features.router, dependencies=_auth)

    @app.get("/v1/version")
    def api_version() -> dict[str, str]:
        from metis_app.config import APP_VERSION

        return {
            "version": APP_VERSION,
            "min_compatible": APP_VERSION,
        }

    @app.get("/healthz")
    def healthz() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/v1/index/build", response_model=IndexBuildResultModel, dependencies=_auth)
    def api_build_index(payload: IndexBuildRequestModel) -> IndexBuildResultModel:
        orchestrator = WorkspaceOrchestrator()
        return IndexBuildResultModel.from_engine(
            _run_engine(
                orchestrator.build_index,
                payload.document_paths,
                payload.settings,
                index_id=payload.index_id,
            )
        )

    @app.get("/v1/index/list", dependencies=_auth)
    def api_list_indexes() -> list[dict[str, Any]]:
        return _run_engine(list_indexes)

    @app.get(
        "/v1/nyx/catalog",
        response_model=NyxCatalogSearchResponseModel,
        dependencies=_auth,
    )
    def api_search_nyx_catalog(
        q: str = "",
        limit: int | None = None,
    ) -> NyxCatalogSearchResponseModel:
        if limit is not None and limit <= 0:
            raise HTTPException(status_code=422, detail="limit must be a positive integer")
        orchestrator = WorkspaceOrchestrator()
        return NyxCatalogSearchResponseModel.from_service(
            _run_engine(orchestrator.search_nyx_catalog, query=q, limit=limit)
        )

    @app.get(
        "/v1/nyx/catalog/{component_name:path}",
        response_model=NyxCatalogComponentDetailModel,
        dependencies=_auth,
    )
    def api_get_nyx_component_detail(component_name: str) -> NyxCatalogComponentDetailModel:
        orchestrator = WorkspaceOrchestrator()
        try:
            detail = orchestrator.get_nyx_component_detail(component_name)
        except NyxCatalogComponentNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        return NyxCatalogComponentDetailModel.from_service(detail)

    @app.get("/v1/brain/graph", dependencies=_auth)
    def api_brain_graph() -> dict[str, Any]:
        """Return the unified brain graph built from all indexes and sessions."""
        graph = WorkspaceOrchestrator().get_workspace_graph()

        return {
            "nodes": [
                {
                    "node_id": node.node_id,
                    "node_type": node.node_type,
                    "label": node.label,
                    "x": node.x,
                    "y": node.y,
                    "metadata": node.metadata,
                }
                for node in graph.nodes.values()
            ],
            "edges": [
                {
                    "source_id": edge.source_id,
                    "target_id": edge.target_id,
                    "edge_type": edge.edge_type,
                    "metadata": edge.metadata,
                    "weight": edge.weight,
                }
                for edge in graph.edges
            ],
        }

    @app.get("/v1/brain/scaffold", dependencies=_auth)
    def api_brain_scaffold() -> dict[str, Any]:
        graph = WorkspaceOrchestrator().get_workspace_graph()
        cache_key = _brain_graph_cache_key(graph)
        now = time.time()
        cached = _BRAIN_SCAFFOLD_CACHE.get(cache_key)
        if cached is not None:
            cached_at, payload = cached
            if now - cached_at <= _BRAIN_SCAFFOLD_TTL_SECONDS:
                return payload

        payload = scaffold_to_payload(compute_scaffold(graph))
        _BRAIN_SCAFFOLD_CACHE[cache_key] = (now, payload)
        if len(_BRAIN_SCAFFOLD_CACHE) > 16:
            oldest_key = min(_BRAIN_SCAFFOLD_CACHE.items(), key=lambda item: item[1][0])[0]
            _BRAIN_SCAFFOLD_CACHE.pop(oldest_key, None)
        return payload

    @app.post("/v1/files/upload", dependencies=_auth)
    async def api_upload_files(
        files: list[UploadFile] = File(...),
    ) -> dict[str, list[str]]:
        upload_dir = pathlib.Path(tempfile.gettempdir()) / "metis_uploads"
        upload_dir.mkdir(exist_ok=True)
        saved: list[str] = []
        for file in files:
            suffix = pathlib.Path(file.filename or "file").suffix
            dest = upload_dir / f"{uuid.uuid4().hex}{suffix}"
            content = await file.read()
            dest.write_bytes(content)
            saved.append(str(dest))
        return {"paths": saved}

    @app.post("/v1/index/build/stream", dependencies=_auth)
    async def api_build_index_stream(
        payload: IndexBuildRequestModel,
    ) -> StreamingResponse:
        orchestrator = WorkspaceOrchestrator()
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

        def _progress_cb(event: dict[str, Any]) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, event)

        future = loop.run_in_executor(
            None,
            lambda: orchestrator.build_index(
                payload.document_paths,
                payload.settings,
                index_id=payload.index_id,
                progress_cb=_progress_cb,
            ),
        )

        async def _event_gen() -> AsyncGenerator[str, None]:
            yield f"event: message\ndata: {json.dumps({'type': 'build_started'})}\n\n"
            while not future.done():
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=0.05)
                    yield f"event: message\ndata: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    pass
            # Drain any remaining queued events
            await asyncio.sleep(0)
            while not queue.empty():
                event = queue.get_nowait()
                yield f"event: message\ndata: {json.dumps(event)}\n\n"
            try:
                result = future.result()
                yield f"event: message\ndata: {json.dumps({'type': 'build_complete', 'index_id': result.index_id, 'manifest_path': str(result.manifest_path), 'document_count': result.document_count, 'chunk_count': result.chunk_count, 'embedding_signature': result.embedding_signature, 'vector_backend': result.vector_backend, 'brain_pass': result.brain_pass})}\n\n"
            except (ValueError, RuntimeError) as exc:
                yield f"event: message\ndata: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

        return StreamingResponse(
            _event_gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/v1/query/rag", response_model=RagQueryResultModel, dependencies=_auth)
    def api_query_rag(payload: RagQueryRequestModel) -> RagQueryResultModel:
        orchestrator = WorkspaceOrchestrator()
        return RagQueryResultModel.from_engine(
            _run_engine(
                orchestrator.run_rag_query,
                payload.to_engine(),
                session_id=payload.session_id,
            )
        )

    @app.post("/v1/search/knowledge", response_model=KnowledgeSearchResultModel, dependencies=_auth)
    def api_search_knowledge(payload: KnowledgeSearchRequestModel) -> KnowledgeSearchResultModel:
        orchestrator = WorkspaceOrchestrator()
        return KnowledgeSearchResultModel.from_engine(
            _run_engine(
                orchestrator.run_knowledge_search,
                payload.to_engine(),
                session_id=payload.session_id,
            )
        )

    @app.post("/v1/query/direct", response_model=DirectQueryResultModel, dependencies=_auth)
    def api_query_direct(payload: DirectQueryRequestModel) -> DirectQueryResultModel:
        orchestrator = WorkspaceOrchestrator()
        return DirectQueryResultModel.from_engine(
            _run_engine(
                orchestrator.run_direct_query,
                payload.to_engine(),
                session_id=payload.session_id,
            )
        )

    @app.get("/v1/traces/{run_id}", dependencies=_auth)
    def api_get_trace(run_id: str) -> list[dict[str, Any]]:
        return TraceStore().read_run_events(run_id)

    @app.post("/v1/telemetry/ui", dependencies=_auth)
    async def api_ingest_ui_telemetry(request: Request) -> dict[str, int]:
        content_length = request.headers.get("content-length", "").strip()
        if content_length:
            try:
                if int(content_length) > _MAX_UI_TELEMETRY_REQUEST_BYTES:
                    raise HTTPException(status_code=413, detail="Telemetry payload too large")
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid Content-Length header")

        raw_body = await request.body()
        if not raw_body:
            raise HTTPException(status_code=400, detail="Telemetry payload required")
        if len(raw_body) > _MAX_UI_TELEMETRY_REQUEST_BYTES:
            raise HTTPException(status_code=413, detail="Telemetry payload too large")

        try:
            raw_payload = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="Malformed JSON payload") from exc

        try:
            payload = UiTelemetryIngestRequestModel.model_validate(raw_payload)
        except ValidationError as exc:
            raise RequestValidationError(exc.errors()) from exc

        accepted = WorkspaceOrchestrator().ingest_ui_telemetry_events(
            [event.model_dump(mode="json") for event in payload.events]
        )
        return {"accepted": accepted}

    @app.get(
        "/v1/telemetry/ui/summary",
        response_model=UiTelemetrySummaryResponseModel,
        dependencies=_auth,
    )
    def api_ui_telemetry_summary(
        window_hours: int = 24,
        limit: int = 50_000,
    ) -> UiTelemetrySummaryResponseModel:
        if window_hours <= 0:
            raise HTTPException(status_code=422, detail="window_hours must be a positive integer")
        if limit <= 0:
            raise HTTPException(status_code=422, detail="limit must be a positive integer")

        summary = WorkspaceOrchestrator().get_ui_telemetry_summary(
            window_hours=window_hours,
            limit=limit,
        )
        return UiTelemetrySummaryResponseModel.model_validate(summary)

    @app.post("/v1/runs/{run_id}/actions", dependencies=_auth)
    def api_run_action(run_id: str, payload: RunActionRequestModel) -> dict[str, Any]:
        action_payload = dict(payload.payload or {})
        action_type = str(
            payload.action_type or action_payload.get("action_type") or ""
        ).strip()
        action_id = str(payload.action_id or action_payload.get("action_id") or "").strip()
        proposal_token = str(
            payload.proposal_token or action_payload.get("proposal_token") or ""
        ).strip()

        infer_latest_nyx_action = (
            not payload.approved
            and not action_id
            and not proposal_token
            and (not action_type or action_type == NYX_INSTALL_ACTION_TYPE)
        )
        should_resolve_nyx_action = _looks_like_nyx_action_reference(
            action_type=action_type,
            action_id=action_id,
            proposal_token=proposal_token,
        ) or infer_latest_nyx_action

        persisted_action: dict[str, Any] | None = None
        matched_by = ""
        trace_store: TraceStore | None = None

        if should_resolve_nyx_action:
            trace_store = TraceStore()
            persisted_action, matched_by = _resolve_persisted_nyx_install_action(
                run_id=run_id,
                trace_store=trace_store,
                action_id=action_id,
                proposal_token=proposal_token,
                infer_latest=infer_latest_nyx_action,
            )
            if persisted_action is not None:
                action_type = NYX_INSTALL_ACTION_TYPE
            elif action_type == NYX_INSTALL_ACTION_TYPE or action_id or proposal_token:
                latest_persisted_action = find_persisted_nyx_install_action(
                    run_id=run_id,
                    trace_store=trace_store,
                    allow_latest=True,
                )
                if latest_persisted_action is not None:
                    raise HTTPException(
                        status_code=400,
                        detail="Nyx install identifiers do not match any persisted proposal for this run.",
                    )
                raise HTTPException(status_code=404, detail="Nyx install proposal not found")

        if action_type == NYX_INSTALL_ACTION_TYPE:
            if persisted_action is None or trace_store is None:
                raise HTTPException(status_code=404, detail="Nyx install proposal not found")

            persisted_proposal = dict(persisted_action.get("proposal") or {})
            resolved_action_id = str(persisted_action.get("action_id") or action_id).strip()
            resolved_token = str(
                persisted_proposal.get("proposal_token")
                or proposal_token
                or action_payload.get("proposal_token")
            ).strip()
            component_names = [
                str(item)
                for item in list(persisted_proposal.get("component_names") or [])
                if str(item).strip()
            ]
            component_count = int(persisted_proposal.get("component_count") or len(component_names) or 0)

            if not payload.approved:
                if matched_by == "action_id" and proposal_token:
                    raise HTTPException(
                        status_code=400,
                        detail="Nyx install proposal token no longer matches the persisted proposal.",
                    )
                if matched_by == "proposal_token" and action_id:
                    raise HTTPException(
                        status_code=400,
                        detail="Nyx install action id no longer matches the persisted proposal.",
                    )
                _append_nyx_install_action_event(
                    trace_store=trace_store,
                    run_id=run_id,
                    approved=False,
                    action_id=resolved_action_id,
                    proposal_token=resolved_token,
                    component_names=component_names,
                    component_count=component_count,
                    execution_status="declined",
                    status="declined",
                )
                return {
                    "run_id": run_id,
                    "approved": False,
                    "status": "declined",
                    "action_id": resolved_action_id,
                    "action_type": NYX_INSTALL_ACTION_TYPE,
                    "proposal_token": resolved_token,
                    "component_names": component_names,
                    "component_count": component_count,
                    "execution_status": "declined",
                    "proposal": persisted_proposal,
                }

            try:
                execution_result = execute_nyx_install_action(
                    run_id=run_id,
                    persisted_action=persisted_action,
                    action_id=action_id or resolved_action_id,
                    proposal_token=proposal_token or resolved_token,
                    requested_component_names=action_payload.get("component_names"),
                )
            except NyxInstallActionExecutionError as exc:
                _append_nyx_install_action_event(
                    trace_store=trace_store,
                    run_id=run_id,
                    approved=True,
                    action_id=resolved_action_id,
                    proposal_token=resolved_token,
                    component_names=component_names,
                    component_count=component_count,
                    execution_status="failed",
                    status="error",
                    extra_payload={
                        "failure_code": exc.code,
                        **dict(exc.metadata),
                    },
                )
                raise HTTPException(
                    status_code=_nyx_install_http_status(exc.code),
                    detail=str(exc),
                ) from exc

            _append_nyx_install_action_event(
                trace_store=trace_store,
                run_id=run_id,
                approved=True,
                action_id=execution_result.action_id,
                proposal_token=execution_result.proposal_token,
                component_names=list(execution_result.component_names),
                component_count=execution_result.component_count,
                execution_status=execution_result.execution_status,
                status="success",
                extra_payload=execution_result.to_trace_payload(approved=True),
            )

            return execution_result.to_response_payload(run_id=run_id, approved=True)

        log.info(
            "Run action received: run_id=%s approved=%s payload=%s",
            run_id,
            payload.approved,
            payload.payload,
        )
        return {
            "run_id": run_id,
            "approved": payload.approved,
            "status": "accepted",
        }

    @app.post(
        "/v1/openai/chat/completions",
        response_model=OpenAIChatCompletionResponseModel,
        dependencies=_auth,
    )
    def api_openai_chat_completions(
        payload: OpenAIChatCompletionRequestModel,
    ) -> OpenAIChatCompletionResponseModel:
        """OpenAI-compatible chat completions endpoint (non-streaming).

        Guarded by feature flag ``api_compat_openai`` (default: off).
        Internally delegates to the existing direct-query pipeline.
        """
        settings = _settings_store.load_settings()
        flag_enabled = any(
            s.enabled
            for s in get_feature_statuses(settings)
            if s.name == str(FeatureFlag.API_COMPAT_OPENAI)
        )
        if not flag_enabled:
            raise HTTPException(
                status_code=404,
                detail="OpenAI compatibility endpoint is disabled. "
                "Enable feature flag 'api_compat_openai' to use it.",
            )

        if payload.stream is True:
            raise HTTPException(
                status_code=501,
                detail="Streaming is not supported by this endpoint. "
                "Use stream=false or omit the field.",
            )

        # Use the last user-role message as the prompt.
        prompt = next(
            (m.content for m in reversed(payload.messages) if m.role == "user"),
            "",
        )
        if not prompt.strip():
            raise HTTPException(
                status_code=422,
                detail="No user message found in the messages array.",
            )

        direct_req = DirectQueryRequestModel(prompt=prompt, settings=settings)
        orchestrator = WorkspaceOrchestrator()
        result = _run_engine(
            orchestrator.run_direct_query,
            direct_req.to_engine(),
        )

        return OpenAIChatCompletionResponseModel(
            id=f"metis-{result.run_id}",
            object="chat.completion",
            created=int(time.time()),
            model=payload.model,
            choices=[
                OpenAIChatCompletionChoiceModel(
                    index=0,
                    message=OpenAIChatCompletionMessageOutputModel(
                        role="assistant",
                        content=result.answer_text,
                    ),
                    finish_reason="stop",
                )
            ],
            usage=OpenAIChatCompletionUsageModel(
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
            ),
        )

    @app.post("/v1/query/rag/stream", dependencies=_auth)
    def api_stream_rag(
        payload: RagQueryRequestModel,
        last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    ) -> StreamingResponse:
        req = payload.to_engine()
        run_id = _normalize_run_id(req.run_id)
        req.run_id = run_id
        replay_after = _parse_last_event_id(last_event_id)
        orchestrator = WorkspaceOrchestrator()

        if replay_after is None:
            _RAG_STREAM_MANAGER.ensure_run(
                run_id,
                lambda: orchestrator.stream_rag_query(
                    req,
                    session_id=payload.session_id,
                ),
            )

        def _event_generator() -> Generator[str, None, None]:
            after_event_id = 0 if replay_after is None else replay_after
            for event in _RAG_STREAM_MANAGER.subscribe(
                run_id, after_event_id=after_event_id
            ):
                yield _encode_sse(event.payload, event_id=event.event_id)

        return StreamingResponse(
            _event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    return app


def _parse_last_event_id(raw_value: str | None) -> int | None:
    candidate = str(raw_value or "").strip()
    if not candidate:
        return None
    try:
        return max(int(candidate), 0)
    except ValueError:
        return None


def _encode_sse(payload: dict[str, Any], event_id: int | None = None) -> str:
    lines: list[str] = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.append("event: message")
    lines.append(f"data: {json.dumps(payload, ensure_ascii=False)}")
    return "\n".join(lines) + "\n\n"


def _run_engine(func: Any, *args: Any, **kwargs: Any) -> Any:
    try:
        return func(*args, **kwargs)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _brain_graph_cache_key(graph: Any) -> str:
    payload = {
        "nodes": sorted(str(node_id) for node_id in graph.nodes.keys()),
        "edges": sorted(
            (
                str(edge.source_id),
                str(edge.target_id),
                str(edge.edge_type),
                round(float(edge.weight or 0.0), 6),
            )
            for edge in graph.edges
        ),
    }
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


app = create_app()
