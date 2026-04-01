"""Web graph index build endpoints."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from litestar import Router, post
from litestar.response import ServerSentEvent

from metis_app.api.models import WebGraphBuildRequestModel
from metis_app.services.web_graph_service import create_web_graph_service
from metis_app.services.workspace_orchestrator import WorkspaceOrchestrator

from metis_app.api_litestar.common import run_engine


@post("/v1/index/build/web-graph")
def api_build_web_graph(data: WebGraphBuildRequestModel) -> dict[str, Any]:
    """Build a wikilinked knowledge-graph index from web sources."""
    orchestrator = WorkspaceOrchestrator()
    service = create_web_graph_service(data.settings)
    return run_engine(
        service.build,
        data.topic,
        data.settings,
        orchestrator,
        index_id=data.index_id,
    )


@post("/v1/index/build/web-graph/stream")
async def api_build_web_graph_stream(payload: WebGraphBuildRequestModel) -> ServerSentEvent:
    """Build a web-graph index and stream progress events over SSE."""
    orchestrator = WorkspaceOrchestrator()
    service = create_web_graph_service(payload.settings)
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    future = loop.run_in_executor(
        None,
        lambda: service.build(
            payload.topic,
            payload.settings,
            orchestrator,
            index_id=payload.index_id,
        ),
    )

    async def _event_generator() -> Any:
        yield {
            "event": "message",
            "data": json.dumps({"type": "build_started", "topic": payload.topic}, ensure_ascii=False),
        }
        while not future.done():
            await asyncio.sleep(0.05)

        await asyncio.sleep(0)
        while not queue.empty():  # noqa: ASYNC110
            event = queue.get_nowait()
            yield {
                "event": "message",
                "data": json.dumps(event, ensure_ascii=False),
            }

        try:
            result = future.result()
            yield {
                "event": "message",
                "data": json.dumps(
                    {
                        "type": "build_complete",
                        "index_id": result["index_id"],
                        "manifest_path": result["manifest_path"],
                        "topic": result["topic"],
                        "nodes": result["nodes"],
                        "sources": result["sources"],
                        "document_count": result["document_count"],
                        "chunk_count": result["chunk_count"],
                    },
                    ensure_ascii=False,
                ),
            }
        except (ValueError, RuntimeError) as exc:
            yield {
                "event": "message",
                "data": json.dumps(
                    {"type": "error", "message": str(exc)},
                    ensure_ascii=False,
                ),
            }

    return ServerSentEvent(_event_generator())


router = Router(
    path="",
    route_handlers=[api_build_web_graph, api_build_web_graph_stream],
    tags=["web-graph"],
)
