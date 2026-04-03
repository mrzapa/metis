"""Log and metrics endpoints."""

from __future__ import annotations

from litestar import Router, get

from metis_app.api.logs import get_log_tail as _get_log_tail
from metis_app.api.logs import get_trace_metrics as _get_trace_metrics


@get("/v1/logs/tail")
async def get_log_tail() -> dict[str, object]:
    return _get_log_tail()


@get("/v1/logs/metrics")
async def get_trace_metrics() -> dict[str, object]:
    return _get_trace_metrics()


router = Router(path="", route_handlers=[get_log_tail, get_trace_metrics], tags=["logs"])