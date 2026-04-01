"""Health check endpoint."""

from litestar import get


@get("/healthz")
def healthz() -> dict[str, bool]:
    """Health check endpoint."""
    return {"ok": True}
