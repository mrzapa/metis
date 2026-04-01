"""Core application endpoints ported from the FastAPI app module."""

from __future__ import annotations

import json
import pathlib
import secrets
import tempfile
import time
import uuid
from typing import Any

from litestar import Request, Router, get, post
from litestar.datastructures import UploadFile
from litestar.exceptions import HTTPException as LitestarHTTPException
from pydantic import ValidationError

import metis_app.settings_store as _settings_store
from metis_app.api.models import (
    LearningRoutePreviewModel,
    LearningRoutePreviewRequestModel,
    NyxCatalogComponentDetailModel,
    NyxCatalogSearchResponseModel,
    RunActionRequestModel,
    UiTelemetryIngestRequestModel,
    UiTelemetrySummaryResponseModel,
)
from metis_app.services.learning_route_service import (
    LearningRouteIndexSummary,
    LearningRouteStarSnapshot,
)
from metis_app.services.nyx_catalog import NyxCatalogComponentNotFoundError
from metis_app.services.nyx_install_executor import (
    NyxInstallActionExecutionError,
    execute_nyx_install_action,
)
from metis_app.services.nyx_runtime import NYX_INSTALL_ACTION_TYPE, find_persisted_nyx_install_action
from metis_app.services.topo_scaffold import compute_scaffold, scaffold_to_payload
from metis_app.services.trace_store import TraceStore
from metis_app.services.workspace_orchestrator import WorkspaceOrchestrator

_MAX_UI_TELEMETRY_REQUEST_BYTES = 16_384
_BRAIN_SCAFFOLD_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_BRAIN_SCAFFOLD_TTL_SECONDS = 30.0


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


@get("/v1/nyx/catalog")
async def api_search_nyx_catalog(
    q: str = "",
    limit: int | None = None,
) -> dict[str, Any]:
    if limit is not None and limit <= 0:
        raise LitestarHTTPException(status_code=422, detail="limit must be a positive integer")
    orchestrator = WorkspaceOrchestrator()
    result = orchestrator.search_nyx_catalog(query=q, limit=limit)
    return NyxCatalogSearchResponseModel.from_service(result).model_dump(mode="json")


@get("/v1/nyx/catalog/{component_name:path}")
async def api_get_nyx_component_detail(component_name: str) -> dict[str, Any]:
    orchestrator = WorkspaceOrchestrator()
    try:
        detail = orchestrator.get_nyx_component_detail(component_name)
    except NyxCatalogComponentNotFoundError as exc:
        raise LitestarHTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise LitestarHTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise LitestarHTTPException(status_code=503, detail=str(exc)) from exc
    return NyxCatalogComponentDetailModel.from_service(detail).model_dump(mode="json")


@get("/v1/brain/graph")
async def api_brain_graph() -> dict[str, Any]:
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


@post("/v1/learning-routes/preview")
async def api_learning_route_preview(
    payload: LearningRoutePreviewRequestModel,
) -> dict[str, Any]:
    orchestrator = WorkspaceOrchestrator()
    try:
        preview = orchestrator.preview_learning_route(
            origin_star=LearningRouteStarSnapshot(
                id=payload.origin_star.id,
                label=payload.origin_star.label,
                intent=payload.origin_star.intent,
                notes=payload.origin_star.notes,
                active_manifest_path=payload.origin_star.active_manifest_path,
                linked_manifest_paths=list(payload.origin_star.linked_manifest_paths),
                connected_user_star_ids=list(payload.origin_star.connected_user_star_ids),
            ),
            connected_stars=[
                LearningRouteStarSnapshot(
                    id=star.id,
                    label=star.label,
                    intent=star.intent,
                    notes=star.notes,
                    active_manifest_path=star.active_manifest_path,
                    linked_manifest_paths=list(star.linked_manifest_paths),
                    connected_user_star_ids=list(star.connected_user_star_ids),
                )
                for star in payload.connected_stars
            ],
            indexes=[
                LearningRouteIndexSummary(
                    index_id=index.index_id,
                    manifest_path=index.manifest_path,
                    document_count=index.document_count,
                    chunk_count=index.chunk_count,
                    created_at=index.created_at,
                    embedding_signature=index.embedding_signature,
                    brain_pass=dict(index.brain_pass or {}),
                )
                for index in payload.indexes
            ],
        )
    except ValueError as exc:
        raise LitestarHTTPException(status_code=400, detail=str(exc)) from exc
    return LearningRoutePreviewModel.model_validate(preview).model_dump(mode="json")


@get("/v1/brain/scaffold")
async def api_brain_scaffold() -> dict[str, Any]:
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


@post("/v1/files/upload")
async def api_upload_files(request: Request[Any, Any, Any]) -> dict[str, list[str]]:
    form_data = await request.form()
    uploads = [
        value
        for value in form_data.getall("files", [])
        if isinstance(value, UploadFile)
    ]
    if not uploads:
        raise LitestarHTTPException(status_code=422, detail="At least one file is required")

    upload_dir = pathlib.Path(tempfile.gettempdir()) / "metis_uploads"
    upload_dir.mkdir(exist_ok=True)
    saved: list[str] = []
    for upload in uploads:
        suffix = pathlib.Path(upload.filename or "file").suffix
        dest = upload_dir / f"{uuid.uuid4().hex}{suffix}"
        content = await upload.read()
        dest.write_bytes(content)
        saved.append(str(dest))
        await upload.close()
    return {"paths": saved}


@get("/v1/traces/{run_id:str}")
async def api_get_trace(run_id: str) -> list[dict[str, Any]]:
    return TraceStore().read_run_events(run_id)


@post("/v1/telemetry/ui")
async def api_ingest_ui_telemetry(request: Request[Any, Any, Any]) -> dict[str, int]:
    content_length = request.headers.get("content-length", "").strip()
    if content_length:
        try:
            if int(content_length) > _MAX_UI_TELEMETRY_REQUEST_BYTES:
                raise LitestarHTTPException(status_code=413, detail="Telemetry payload too large")
        except ValueError as exc:
            raise LitestarHTTPException(status_code=400, detail="Invalid Content-Length header") from exc

    raw_body = await request.body()
    if not raw_body:
        raise LitestarHTTPException(status_code=400, detail="Telemetry payload required")
    if len(raw_body) > _MAX_UI_TELEMETRY_REQUEST_BYTES:
        raise LitestarHTTPException(status_code=413, detail="Telemetry payload too large")

    try:
        raw_payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise LitestarHTTPException(status_code=400, detail="Malformed JSON payload") from exc

    try:
        payload = UiTelemetryIngestRequestModel.model_validate(raw_payload)
    except ValidationError as exc:
        raise LitestarHTTPException(status_code=422, detail=exc.errors()) from exc

    accepted = WorkspaceOrchestrator().ingest_ui_telemetry_events(
        [event.model_dump(mode="json") for event in payload.events]
    )
    return {"accepted": accepted}


@get("/v1/telemetry/ui/summary")
async def api_ui_telemetry_summary(
    window_hours: int = 24,
    limit: int = 50_000,
) -> dict[str, Any]:
    if window_hours <= 0:
        raise LitestarHTTPException(status_code=422, detail="window_hours must be a positive integer")
    if limit <= 0:
        raise LitestarHTTPException(status_code=422, detail="limit must be a positive integer")

    summary = WorkspaceOrchestrator().get_ui_telemetry_summary(
        window_hours=window_hours,
        limit=limit,
    )
    return UiTelemetrySummaryResponseModel.model_validate(summary).model_dump(mode="json")


@post("/v1/runs/{run_id:str}/actions")
async def api_run_action(run_id: str, payload: RunActionRequestModel) -> dict[str, Any]:
    action_payload = dict(payload.payload or {})
    action_type = str(payload.action_type or action_payload.get("action_type") or "").strip()
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
                raise LitestarHTTPException(
                    status_code=400,
                    detail="Nyx install identifiers do not match any persisted proposal for this run.",
                )
            raise LitestarHTTPException(status_code=404, detail="Nyx install proposal not found")

    if action_type == NYX_INSTALL_ACTION_TYPE:
        if persisted_action is None or trace_store is None:
            raise LitestarHTTPException(status_code=404, detail="Nyx install proposal not found")

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
                raise LitestarHTTPException(
                    status_code=400,
                    detail="Nyx install proposal token no longer matches the persisted proposal.",
                )
            if matched_by == "proposal_token" and action_id:
                raise LitestarHTTPException(
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
                extra_payload={"failure_code": exc.code, **dict(exc.metadata)},
            )
            raise LitestarHTTPException(
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

    return {"run_id": run_id, "approved": payload.approved, "status": "accepted"}


router = Router(
    path="",
    route_handlers=[
        api_search_nyx_catalog,
        api_get_nyx_component_detail,
        api_brain_graph,
        api_learning_route_preview,
        api_brain_scaffold,
        api_upload_files,
        api_get_trace,
        api_ingest_ui_telemetry,
        api_ui_telemetry_summary,
        api_run_action,
    ],
    tags=["core"],
)