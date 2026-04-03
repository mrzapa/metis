"""Query and SSE endpoints."""

from __future__ import annotations

import json
import time
from typing import Any

from litestar import Request, Router, get, post
from litestar.exceptions import HTTPException as LitestarHTTPException
from litestar.response import ServerSentEvent

import metis_app.settings_store as _settings_store
from metis_app.api.models import (
    DirectQueryRequestModel,
    DirectQueryResultModel,
    ForecastPreflightResultModel,
    ForecastQueryRequestModel,
    ForecastQueryResultModel,
    ForecastSchemaRequestModel,
    ForecastSchemaResultModel,
    KnowledgeSearchRequestModel,
    KnowledgeSearchResultModel,
    OpenAIChatCompletionChoiceModel,
    OpenAIChatCompletionMessageOutputModel,
    OpenAIChatCompletionRequestModel,
    OpenAIChatCompletionResponseModel,
    OpenAIChatCompletionUsageModel,
    RagQueryRequestModel,
    RagQueryResultModel,
)
from metis_app.engine.querying import _normalize_run_id
from metis_app.services.stream_replay import ReplayableRunStreamManager
from metis_app.services.workspace_orchestrator import WorkspaceOrchestrator
from metis_app.utils.feature_flags import FeatureFlag, get_feature_statuses

from metis_app.api_litestar.common import parse_last_event_id, run_engine

_RAG_STREAM_MANAGER = ReplayableRunStreamManager()


@post("/v1/query/rag")
def api_query_rag(payload: RagQueryRequestModel) -> dict[str, Any]:
    orchestrator = WorkspaceOrchestrator()
    result = run_engine(
        orchestrator.run_rag_query,
        payload.to_engine(),
        session_id=payload.session_id,
    )
    return RagQueryResultModel.from_engine(result).model_dump(mode="json")


@post("/v1/search/knowledge")
def api_search_knowledge(payload: KnowledgeSearchRequestModel) -> dict[str, Any]:
    orchestrator = WorkspaceOrchestrator()
    result = run_engine(
        orchestrator.run_knowledge_search,
        payload.to_engine(),
        session_id=payload.session_id,
    )
    return KnowledgeSearchResultModel.from_engine(result).model_dump(mode="json")


@post("/v1/query/direct")
def api_query_direct(payload: DirectQueryRequestModel) -> dict[str, Any]:
    orchestrator = WorkspaceOrchestrator()
    result = run_engine(
        orchestrator.run_direct_query,
        payload.to_engine(),
        session_id=payload.session_id,
    )
    return DirectQueryResultModel.from_engine(result).model_dump(mode="json")


@get("/v1/forecast/preflight")
def api_forecast_preflight() -> dict[str, Any]:
    orchestrator = WorkspaceOrchestrator()
    return ForecastPreflightResultModel.model_validate(
        orchestrator.get_forecast_preflight()
    ).model_dump(mode="json")


@post("/v1/forecast/schema")
def api_forecast_schema(payload: ForecastSchemaRequestModel) -> dict[str, Any]:
    orchestrator = WorkspaceOrchestrator()
    return ForecastSchemaResultModel.model_validate(
        orchestrator.inspect_forecast_schema(payload.to_engine())
    ).model_dump(mode="json")


@post("/v1/query/forecast")
def api_query_forecast(payload: ForecastQueryRequestModel) -> dict[str, Any]:
    orchestrator = WorkspaceOrchestrator()
    result = run_engine(
        orchestrator.run_forecast_query,
        payload.to_engine(),
        session_id=payload.session_id,
    )
    return ForecastQueryResultModel.from_engine(result).model_dump(mode="json")


@post("/v1/query/forecast/stream")
def api_stream_forecast(payload: ForecastQueryRequestModel) -> ServerSentEvent:
    orchestrator = WorkspaceOrchestrator()

    def _event_generator() -> Any:
        for event in orchestrator.stream_forecast_query(
            payload.to_engine(),
            session_id=payload.session_id,
        ):
            yield {
                "event": "message",
                "data": json.dumps(event, ensure_ascii=False),
            }

    return ServerSentEvent(_event_generator())


@post("/v1/openai/chat/completions")
def api_openai_chat_completions(
    payload: OpenAIChatCompletionRequestModel,
) -> dict[str, Any]:
    settings = _settings_store.load_settings()
    flag_enabled = any(
        status.enabled
        for status in get_feature_statuses(settings)
        if status.name == str(FeatureFlag.API_COMPAT_OPENAI)
    )
    if not flag_enabled:
        raise LitestarHTTPException(
            status_code=404,
            detail=(
                "OpenAI compatibility endpoint is disabled. "
                "Enable feature flag 'api_compat_openai' to use it."
            ),
        )

    if payload.stream is True:
        raise LitestarHTTPException(
            status_code=501,
            detail=(
                "Streaming is not supported by this endpoint. "
                "Use stream=false or omit the field."
            ),
        )

    prompt = next(
        (message.content for message in reversed(payload.messages) if message.role == "user"),
        "",
    )
    if not prompt.strip():
        raise LitestarHTTPException(
            status_code=422,
            detail="No user message found in the messages array.",
        )

    direct_req = DirectQueryRequestModel(prompt=prompt, settings=settings)
    orchestrator = WorkspaceOrchestrator()
    result = run_engine(orchestrator.run_direct_query, direct_req.to_engine())

    response = OpenAIChatCompletionResponseModel(
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
    return response.model_dump(mode="json")


@post("/v1/query/rag/stream")
def api_stream_rag(
    payload: RagQueryRequestModel,
    request: Request[Any, Any, Any],
) -> ServerSentEvent:
    req = payload.to_engine()
    run_id = _normalize_run_id(req.run_id)
    req.run_id = run_id
    replay_after = parse_last_event_id(request.headers.get("Last-Event-ID"))
    orchestrator = WorkspaceOrchestrator()

    if replay_after is None:
        _RAG_STREAM_MANAGER.ensure_run(
            run_id,
            lambda: orchestrator.stream_rag_query(req, session_id=payload.session_id),
        )

    def _event_generator() -> Any:
        after_event_id = 0 if replay_after is None else replay_after
        for event in _RAG_STREAM_MANAGER.subscribe(run_id, after_event_id=after_event_id):
            yield {
                "id": event.event_id,
                "event": "message",
                "data": json.dumps(event.payload, ensure_ascii=False),
            }

    return ServerSentEvent(_event_generator())


router = Router(
    path="",
    route_handlers=[
        api_query_rag,
        api_search_knowledge,
        api_query_direct,
        api_forecast_preflight,
        api_forecast_schema,
        api_query_forecast,
        api_openai_chat_completions,
        api_stream_forecast,
        api_stream_rag,
    ],
    tags=["query"],
)
