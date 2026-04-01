"""Shared Litestar API helpers."""

from __future__ import annotations

import json
import os
import secrets
from typing import Any

from litestar import Response
from litestar.connection import ASGIConnection
from litestar.exceptions import HTTPException as LitestarHTTPException
from litestar.handlers.base import BaseRouteHandler

from metis_app.services.session_repository import SessionRepository

_DEFAULT_LOCAL_ORIGINS = [
    "http://localhost",
    "http://127.0.0.1",
    "https://localhost",
    "https://127.0.0.1",
]


def cors_origins_from_env() -> list[str]:
    raw = os.getenv("METIS_API_CORS_ORIGINS", "")
    if not raw.strip():
        return _DEFAULT_LOCAL_ORIGINS
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def json_error_response(detail: Any, *, status_code: int) -> Response[str]:
    return Response(
        json.dumps({"detail": detail}, ensure_ascii=False),
        media_type="application/json",
        status_code=status_code,
    )


def handle_value_error(_: Any, exc: ValueError) -> Response[str]:
    return json_error_response(str(exc), status_code=400)


def handle_runtime_error(_: Any, exc: RuntimeError) -> Response[str]:
    return json_error_response(str(exc), status_code=503)


def handle_http_exception(_: Any, exc: LitestarHTTPException) -> Response[str]:
    return json_error_response(exc.detail, status_code=exc.status_code)


def require_token_guard(
    connection: ASGIConnection[Any, Any, Any],
    _: BaseRouteHandler,
) -> None:
    required_token = os.getenv("METIS_API_TOKEN", "").strip()
    if not required_token:
        return

    authorization = connection.headers.get("Authorization", "").strip()
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise LitestarHTTPException(status_code=401, detail="Unauthorized")
    if not secrets.compare_digest(token, required_token):
        raise LitestarHTTPException(status_code=401, detail="Unauthorized")


def run_engine(func: Any, *args: Any, **kwargs: Any) -> Any:
    try:
        return func(*args, **kwargs)
    except ValueError as exc:
        raise LitestarHTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise LitestarHTTPException(status_code=503, detail=str(exc)) from exc


def get_session_repo() -> SessionRepository:
    db_path = os.getenv("METIS_SESSION_DB_PATH") or None
    repo = SessionRepository(db_path=db_path)
    repo.init_db()
    return repo


def parse_last_event_id(raw_value: str | None) -> int | None:
    candidate = str(raw_value or "").strip()
    if not candidate:
        return None
    try:
        return max(int(candidate), 0)
    except ValueError:
        return None