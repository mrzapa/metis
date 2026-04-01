"""Experimental Litestar app factory.

This is a shadow port of the METIS FastAPI for evaluation purposes.
The FastAPI implementation remains the production default.
"""

from __future__ import annotations

import logging

from litestar import Litestar, Router
from litestar.config.cors import CORSConfig
from litestar.exceptions import HTTPException as LitestarHTTPException
from litestar.openapi.config import OpenAPIConfig

from .common import (
    cors_origins_from_env,
    handle_http_exception,
    handle_runtime_error,
    handle_value_error,
    require_token_guard,
)
from .routes import (
    assistant,
    autonomous,
    core,
    features,
    gguf,
    healthz,
    heretic,
    index,
    logs,
    query,
    sessions,
    settings,
    version,
)

log = logging.getLogger(__name__)


def create_app() -> Litestar:
    """Create the experimental Litestar app."""
    cors_config = CORSConfig(
        allow_origins=cors_origins_from_env(),
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["*"],
    )

    openapi_config = OpenAPIConfig(
        title="METIS API (Litestar Experimental)",
        version="1.0-experimental",
    )

    protected_routes = Router(
        path="",
        guards=[require_token_guard],
        route_handlers=[
            assistant.router,
            autonomous.router,
            core.router,
            features.router,
            gguf.router,
            heretic.router,
            index.router,
            logs.router,
            query.router,
            sessions.router,
            settings.router,
        ],
    )

    app = Litestar(
        debug=False,
        cors_config=cors_config,
        openapi_config=openapi_config,
        exception_handlers={
            ValueError: handle_value_error,
            RuntimeError: handle_runtime_error,
            LitestarHTTPException: handle_http_exception,
        },
        route_handlers=[
            healthz.healthz,
            version.api_version,
            protected_routes,
        ],
    )

    return app


# Module-level app instance for development
app = create_app()
