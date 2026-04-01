"""Heretic abliteration routes for the METIS v1 API.

Endpoints
---------
GET  /v1/heretic/preflight
     Check availability of the heretic CLI and llama.cpp convert script.

POST /v1/heretic/abliterate/stream
     Run the full abliterate-then-convert-to-GGUF pipeline, streaming
     progress events as SSE (``text/event-stream``).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import ConfigDict

from metis_app.api.models import AbliterateStreamRequest
from metis_app.services.heretic_service import HereticService

router = APIRouter(prefix="/v1/heretic", tags=["heretic"])

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/preflight")
def preflight() -> dict[str, Any]:
    """Check that all required tools are installed.

    Returns
    -------
    dict
        ``ready``              – True if both heretic and the convert script are found.
        ``heretic_available``  – True if the ``heretic`` CLI is on ``$PATH``.
        ``convert_script``     – Absolute path to ``convert_hf_to_gguf.py`` or null.
        ``errors``             – List of human-readable error strings.
    """
    svc = HereticService()
    result = svc.preflight()
    return {
        "ready": result["ready"],
        "heretic_available": result["heretic"],
        "convert_script": result["convert_script"],
        "errors": result["errors"],
    }


@router.post("/abliterate/stream")
async def abliterate_stream(payload: AbliterateStreamRequest) -> StreamingResponse:
    """Run the abliteration pipeline and stream progress events (SSE).

    Pipeline
    --------
    1. ``heretic <model_id>`` – directional abliteration (AGPL-isolated subprocess).
    2. ``convert_hf_to_gguf.py`` – convert the saved weights to GGUF format.

    Each SSE event carries a JSON payload with a ``type`` field:

    * ``"started"``   – pipeline has begun.
    * ``"progress"``  – stdout line from heretic or the convert script.
    * ``"complete"``  – pipeline finished; includes ``gguf_path``.
    * ``"error"``     – pipeline failed; includes ``message``.

    The client should set ``Accept: text/event-stream`` and handle the
    ``Last-Event-ID`` header for resumable streams.
    """
    loop = asyncio.get_running_loop()
    event_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    def _progress_cb(event: dict[str, Any]) -> None:
        loop.call_soon_threadsafe(event_queue.put_nowait, event)

    svc = HereticService()
    future: asyncio.Future[Any] = loop.run_in_executor(
        None,
        lambda: svc.run_pipeline(
            payload.model_id,
            bnb_4bit=payload.bnb_4bit,
            outtype=payload.outtype,
            post_message=_progress_cb,
        ),
    )

    async def _event_gen():  # type: ignore[return]
        yield (
            "event: message\n"
            f"data: {json.dumps({'type': 'started', 'message': f'Starting abliteration pipeline for {payload.model_id}'})}\n\n"
        )

        while not future.done():
            try:
                event = await asyncio.wait_for(event_queue.get(), timeout=0.05)
                if event.get("type") == "status":
                    event = {"type": "progress", "message": event.get("text", "")}
                yield f"event: message\ndata: {json.dumps(event)}\n\n"
            except asyncio.TimeoutError:
                pass

        # Drain any remaining queued events.
        await asyncio.sleep(0)
        while not event_queue.empty():
            event = event_queue.get_nowait()
            if event.get("type") == "status":
                event = {"type": "progress", "message": event.get("text", "")}
            yield f"event: message\ndata: {json.dumps(event)}\n\n"

        try:
            gguf_path = future.result()
            yield (
                "event: message\n"
                f"data: {json.dumps({'type': 'complete', 'message': 'Abliteration pipeline complete', 'gguf_path': str(gguf_path)})}\n\n"
            )
        except Exception as exc:
            log.exception("Abliteration pipeline failed for %s", payload.model_id)
            yield (
                "event: message\n"
                f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
            )

    return StreamingResponse(
        _event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
