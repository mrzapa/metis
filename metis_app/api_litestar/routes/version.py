"""Version endpoint."""

from litestar import get


@get("/v1/version")
async def api_version() -> dict[str, str]:
    """Return API version."""
    from metis_app.config import APP_VERSION

    return {"version": APP_VERSION}
