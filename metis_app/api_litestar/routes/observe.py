"""Litestar observe routes — thin async wrappers over metis_app.api.observe."""

from __future__ import annotations

from typing import Any

from litestar import Router, get, post

from metis_app.api.observe import (
    get_discover as _get_discover,
    get_run_semantic as _get_run_semantic,
    post_trace_feedback as _post_trace_feedback,
    get_trace_feedback as _get_trace_feedback,
    export_run_as_skill as _export_skill,
    export_run_as_eval as _export_eval,
    FeedbackBody,
)


@get("/v1/traces/discover")
async def get_discover(limit: int = 50) -> dict[str, Any]:
    return _get_discover(limit=limit)


@get("/v1/traces/feedback")
async def get_trace_feedback(
    label: str = "",
    run_id: str = "",
    limit: int = 50,
) -> dict[str, Any]:
    return _get_trace_feedback(label=label, run_id=run_id, limit=limit)


@get("/v1/traces/{run_id:str}/semantic")
async def get_run_semantic(run_id: str) -> dict[str, Any]:
    return _get_run_semantic(run_id=run_id)


@post("/v1/traces/{run_id:str}/feedback")
async def post_trace_feedback(run_id: str, data: FeedbackBody) -> dict[str, Any]:
    return _post_trace_feedback(run_id=run_id, body=data)


@post("/v1/traces/{run_id:str}/export/skill")
async def export_run_as_skill(run_id: str, skill_id: str = "") -> dict[str, Any]:
    return _export_skill(run_id=run_id, skill_id=skill_id)


@post("/v1/traces/{run_id:str}/export/eval")
async def export_run_as_eval(run_id: str) -> dict[str, Any]:
    return _export_eval(run_id=run_id)


router = Router(
    path="",
    route_handlers=[
        get_discover,
        get_trace_feedback,
        get_run_semantic,
        post_trace_feedback,
        export_run_as_skill,
        export_run_as_eval,
    ],
    tags=["observe"],
)
