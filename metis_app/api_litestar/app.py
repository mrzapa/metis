"""METIS Litestar app factory.

This is the production API. FastAPI was retired in favour of Litestar;
see docs/experiments/deprecated/litestar_api.md for the migration history.
"""

from __future__ import annotations

import logging

from litestar import Litestar, Router
from litestar.config.cors import CORSConfig
from litestar.exceptions import HTTPException as LitestarHTTPException
from litestar.exceptions import ValidationException
from litestar.openapi.config import OpenAPIConfig

from .common import (
    cors_origins_from_env,
    handle_http_exception,
    handle_runtime_error,
    handle_validation_exception,
    handle_value_error,
    require_token_guard,
)
from .routes import (
    app_state,
    atlas,
    assistant,
    autonomous,
    comets,
    core,
    features,
    gguf,
    healthz,
    heretic,
    improvements,
    index,
    logs,
    observe,
    query,
    sessions,
    settings,
    version,
    web_graph,
)

log = logging.getLogger(__name__)


def create_app() -> Litestar:
    """Create the METIS Litestar app."""
    cors_config = CORSConfig(
        allow_origins=cors_origins_from_env(),
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["*"],
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    )

    openapi_config = OpenAPIConfig(
        title="METIS API",
        version="1.0",
    )

    protected_routes = Router(
        path="",
        guards=[require_token_guard],
        route_handlers=[
            app_state.router,
            atlas.router,
            assistant.router,
            autonomous.router,
            comets.router,
            core.router,
            features.router,
            gguf.router,
            heretic.router,
            improvements.router,
            index.router,
            logs.router,
            observe.router,
            query.router,
            sessions.router,
            settings.router,
            web_graph.router,
        ],
    )

    app = Litestar(
        debug=False,
        cors_config=cors_config,
        openapi_config=openapi_config,
        exception_handlers={
            ValueError: handle_value_error,
            RuntimeError: handle_runtime_error,
            ValidationException: handle_validation_exception,
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
