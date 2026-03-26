"""Experimental Litestar app factory.

This is a shadow port of the METIS FastAPI for evaluation purposes.
The FastAPI implementation remains the production default.
"""

from __future__ import annotations

import logging
from typing import Any

from litestar import Litestar
from litestar.config.cors import CORSConfig
from litestar.openapi.config import OpenAPIConfig
from litestar.exceptions import HTTPException as LitestarHTTPException

from .routes import healthz, version, index, gguf

log = logging.getLogger(__name__)

_DEFAULT_LOCAL_ORIGINS = [
    "http://localhost",
    "http://127.0.0.1",
    "https://localhost",
    "https://127.0.0.1",
]


def _cors_origins_from_env() -> list[str]:
    import os

    raw = os.getenv("METIS_API_CORS_ORIGINS", "")
    if not raw.strip():
        return _DEFAULT_LOCAL_ORIGINS
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def _handle_value_error(request: Any, exc: ValueError) -> Any:
    from litestar import Response
    import json

    return Response(
        json.dumps({"detail": str(exc)}), media_type="application/json", status_code=400
    )


def _handle_runtime_error(request: Any, exc: RuntimeError) -> Any:
    from litestar import Response
    import json

    return Response(
        json.dumps({"detail": str(exc)}), media_type="application/json", status_code=503
    )


def _handle_http_exception(request: Any, exc: LitestarHTTPException) -> Any:
    from litestar import Response
    import json

    return Response(
        json.dumps({"detail": exc.detail}),
        media_type="application/json",
        status_code=exc.status_code,
    )


def create_app() -> Litestar:
    """Create the experimental Litestar app."""
    cors_config = CORSConfig(
        allow_origins=_cors_origins_from_env(),
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    openapi_config = OpenAPIConfig(
        title="METIS API (Litestar Experimental)",
        version="1.0-experimental",
    )

    app = Litestar(
        debug=False,
        cors_config=cors_config,
        openapi_config=openapi_config,
        exception_handlers={
            ValueError: _handle_value_error,
            RuntimeError: _handle_runtime_error,
            LitestarHTTPException: _handle_http_exception,
        },
        route_handlers=[
            healthz.healthz,
            version.api_version,
            index.api_build_index,
            index.api_list_indexes,
            gguf.list_catalog,
            gguf.get_hardware,
            gguf.list_installed,
            gguf.validate_model,
            gguf.refresh_catalog,
        ],
    )

    return app


# Module-level app instance for development
app = create_app()
