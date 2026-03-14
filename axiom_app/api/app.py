"""FastAPI surface for Axiom's engine layer."""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from axiom_app.engine import build_index, list_indexes, query_direct, query_rag

from .models import (
    DirectQueryRequestModel,
    DirectQueryResultModel,
    IndexBuildRequestModel,
    IndexBuildResultModel,
    RagQueryRequestModel,
    RagQueryResultModel,
)

_DEFAULT_LOCAL_ORIGINS = [
    "http://localhost",
    "http://127.0.0.1",
    "https://localhost",
    "https://127.0.0.1",
]


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

    @app.get("/healthz")
    def healthz() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/v1/index/build", response_model=IndexBuildResultModel)
    def api_build_index(payload: IndexBuildRequestModel) -> IndexBuildResultModel:
        return IndexBuildResultModel.from_engine(_run_engine(build_index, payload.to_engine()))

    @app.get("/v1/index/list")
    def api_list_indexes() -> list[dict[str, Any]]:
        return _run_engine(list_indexes)

    @app.post("/v1/query/rag", response_model=RagQueryResultModel)
    def api_query_rag(payload: RagQueryRequestModel) -> RagQueryResultModel:
        return RagQueryResultModel.from_engine(_run_engine(query_rag, payload.to_engine()))

    @app.post("/v1/query/direct", response_model=DirectQueryResultModel)
    def api_query_direct(payload: DirectQueryRequestModel) -> DirectQueryResultModel:
        return DirectQueryResultModel.from_engine(_run_engine(query_direct, payload.to_engine()))

    return app


def _run_engine(func: Any, *args: Any) -> Any:
    try:
        return func(*args)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


app = create_app()
