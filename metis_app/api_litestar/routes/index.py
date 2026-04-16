"""Index build and list endpoints."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from litestar import Router, delete, get, post
from litestar.exceptions import HTTPException as LitestarHTTPException
from litestar.response import ServerSentEvent
from pydantic import BaseModel, Field

from metis_app.api.models import IndexBuildRequestModel, IndexBuildResultModel, IndexDeleteResultModel
from metis_app.engine import list_indexes
from metis_app.services.workspace_orchestrator import WorkspaceOrchestrator
from metis_app.services.star_archetype import detect_archetypes, RankedArchetype

from metis_app.api_litestar.common import run_engine


# ---------------------------------------------------------------------------
# Archetype suggest models
# ---------------------------------------------------------------------------

class SuggestArchetypesRequest(BaseModel):
    file_paths: list[str] = Field(min_length=0)


def _ranked_to_dict(r: RankedArchetype) -> dict[str, Any]:
    return {
        "id": r.archetype.id,
        "name": r.archetype.name,
        "description": r.archetype.description,
        "icon_hint": r.archetype.icon_hint,
        "settings_overrides": r.archetype.settings_overrides,
        "score": r.score,
        "why": r.why,
    }

@post("/v1/index/build")
def api_build_index(data: IndexBuildRequestModel) -> dict[str, Any]:
    """Build a new index from documents."""
    orchestrator = WorkspaceOrchestrator()
    result = run_engine(
        orchestrator.build_index,
        data.document_paths,
        data.settings,
        index_id=data.index_id,
    )
    return IndexBuildResultModel.from_engine(result).model_dump()


@get("/v1/index/list")
def api_list_indexes() -> list[dict[str, Any]]:
    """List all available indexes."""
    return run_engine(list_indexes)


@delete("/v1/index", status_code=200)
def api_delete_index(manifest_path: str) -> dict[str, Any]:
    """Delete a persisted index by manifest path."""
    orchestrator = WorkspaceOrchestrator()
    try:
        result = run_engine(orchestrator.delete_index, manifest_path)
    except FileNotFoundError as exc:
        raise LitestarHTTPException(status_code=404, detail="Index not found.") from exc
    return IndexDeleteResultModel(**result).model_dump()


@post("/v1/index/build/stream")
async def api_build_index_stream(payload: IndexBuildRequestModel) -> ServerSentEvent:
    """Build an index and stream progress events over SSE."""
    orchestrator = WorkspaceOrchestrator()
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

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

    async def _event_generator() -> Any:
        yield {
            "event": "message",
            "data": json.dumps({"type": "build_started"}, ensure_ascii=False),
        }
        while not future.done():
            try:
                event = await asyncio.wait_for(queue.get(), timeout=0.05)
                yield {
                    "event": "message",
                    "data": json.dumps(event, ensure_ascii=False),
                }
            except asyncio.TimeoutError:
                pass

        await asyncio.sleep(0)
        while not queue.empty():
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
                        "index_id": result.index_id,
                        "manifest_path": str(result.manifest_path),
                        "document_count": result.document_count,
                        "chunk_count": result.chunk_count,
                        "embedding_signature": result.embedding_signature,
                        "vector_backend": result.vector_backend,
                        "brain_pass": result.brain_pass,
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


@post("/v1/index/suggest-archetypes")
def api_suggest_archetypes(data: SuggestArchetypesRequest) -> dict[str, Any]:
    """Return ranked star archetype suggestions for a list of uploaded file paths."""
    ranked = detect_archetypes(data.file_paths)
    return {
        "archetypes": [_ranked_to_dict(r) for r in ranked],
        "top_id": ranked[0].archetype.id if ranked else None,
    }


router = Router(
    path="",
    route_handlers=[
        api_build_index,
        api_list_indexes,
        api_delete_index,
        api_build_index_stream,
        api_suggest_archetypes,
    ],
    tags=["index"],
)
