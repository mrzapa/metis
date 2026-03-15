"""FastAPI surface for Axiom's engine layer."""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import tempfile
import uuid
from collections.abc import AsyncGenerator, Generator
from typing import Any

from fastapi import FastAPI, File, HTTPException, Header, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse

from axiom_app.engine import build_index, list_indexes, query_direct, query_rag, stream_rag_answer
from axiom_app.engine.querying import _normalize_run_id
from axiom_app.services.stream_replay import ReplayableRunStreamManager
from axiom_app.services.trace_store import TraceStore

from . import logs as _logs
from . import sessions as _sessions
from . import settings as _settings
from .models import (
    DirectQueryRequestModel,
    DirectQueryResultModel,
    IndexBuildRequestModel,
    IndexBuildResultModel,
    RagQueryRequestModel,
    RagQueryResultModel,
    RunActionRequestModel,
)

_DEFAULT_LOCAL_ORIGINS = [
    "http://localhost",
    "http://127.0.0.1",
    "https://localhost",
    "https://127.0.0.1",
]

_RAG_STREAM_MANAGER = ReplayableRunStreamManager()


def _cors_origins_from_env() -> list[str]:
    raw = os.getenv("AXIOM_API_CORS_ORIGINS", "")
    if not raw.strip():
        return _DEFAULT_LOCAL_ORIGINS
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def create_app() -> FastAPI:
    app = FastAPI(title="Axiom API", version="1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins_from_env(),
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    app.include_router(_sessions.router)
    app.include_router(_settings.router)
    app.include_router(_logs.router)

    @app.get("/v1/version")
    def api_version() -> dict[str, str]:
        from axiom_app.config import APP_VERSION
        return {"version": APP_VERSION}

    @app.get("/healthz")
    def healthz() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/v1/index/build", response_model=IndexBuildResultModel)
    def api_build_index(payload: IndexBuildRequestModel) -> IndexBuildResultModel:
        return IndexBuildResultModel.from_engine(_run_engine(build_index, payload.to_engine()))

    @app.get("/v1/index/list")
    def api_list_indexes() -> list[dict[str, Any]]:
        return _run_engine(list_indexes)

    @app.post("/v1/files/upload")
    async def api_upload_files(files: list[UploadFile] = File(...)) -> dict[str, list[str]]:
        upload_dir = pathlib.Path(tempfile.gettempdir()) / "axiom_uploads"
        upload_dir.mkdir(exist_ok=True)
        saved: list[str] = []
        for file in files:
            suffix = pathlib.Path(file.filename or "file").suffix
            dest = upload_dir / f"{uuid.uuid4().hex}{suffix}"
            content = await file.read()
            dest.write_bytes(content)
            saved.append(str(dest))
        return {"paths": saved}

    @app.post("/v1/index/build/stream")
    async def api_build_index_stream(payload: IndexBuildRequestModel) -> StreamingResponse:
        req = payload.to_engine()
        loop = asyncio.get_event_loop()
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

        def _progress_cb(event: dict[str, Any]) -> None:
            asyncio.run_coroutine_threadsafe(queue.put(event), loop)

        future = loop.run_in_executor(None, lambda: build_index(req, progress_cb=_progress_cb))

        async def _event_gen() -> AsyncGenerator[str, None]:
            yield f"event: message\ndata: {json.dumps({'type': 'build_started'})}\n\n"
            while not future.done():
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=0.05)
                    yield f"event: message\ndata: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    pass
            # Drain any remaining queued events
            while not queue.empty():
                event = queue.get_nowait()
                yield f"event: message\ndata: {json.dumps(event)}\n\n"
            try:
                result = future.result()
                yield f"event: message\ndata: {json.dumps({'type': 'build_complete', 'index_id': result.index_id, 'manifest_path': str(result.manifest_path), 'document_count': result.document_count, 'chunk_count': result.chunk_count, 'embedding_signature': result.embedding_signature, 'vector_backend': result.vector_backend})}\n\n"
            except (ValueError, RuntimeError) as exc:
                yield f"event: message\ndata: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

        return StreamingResponse(
            _event_gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/v1/query/rag", response_model=RagQueryResultModel)
    def api_query_rag(payload: RagQueryRequestModel) -> RagQueryResultModel:
        return RagQueryResultModel.from_engine(_run_engine(query_rag, payload.to_engine()))

    @app.post("/v1/query/direct", response_model=DirectQueryResultModel)
    def api_query_direct(payload: DirectQueryRequestModel) -> DirectQueryResultModel:
        return DirectQueryResultModel.from_engine(_run_engine(query_direct, payload.to_engine()))

    @app.get("/v1/traces/{run_id}")
    def api_get_trace(run_id: str) -> list[dict[str, Any]]:
        return TraceStore().read_run_events(run_id)

    @app.post("/v1/runs/{run_id}/actions")
    def api_run_action(run_id: str, payload: RunActionRequestModel) -> Response:  # noqa: ARG001
        return Response(
            content='{"detail": "Action handling not yet implemented"}',
            status_code=501,
            media_type="application/json",
        )

    @app.post("/v1/query/rag/stream")
    def api_stream_rag(
        payload: RagQueryRequestModel,
        last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    ) -> StreamingResponse:
        req = payload.to_engine()
        run_id = _normalize_run_id(req.run_id)
        req.run_id = run_id
        replay_after = _parse_last_event_id(last_event_id)

        if replay_after is None:
            _RAG_STREAM_MANAGER.ensure_run(run_id, lambda: stream_rag_answer(req))

        def _event_generator() -> Generator[str, None, None]:
            after_event_id = 0 if replay_after is None else replay_after
            for event in _RAG_STREAM_MANAGER.subscribe(run_id, after_event_id=after_event_id):
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


def _run_engine(func: Any, *args: Any) -> Any:
    try:
        return func(*args)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


app = create_app()
