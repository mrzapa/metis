"""Index build and list endpoints."""

from typing import Any

from litestar import get, post
from litestar.exceptions import HTTPException as LitestarHTTPException

from metis_app.engine import build_index, list_indexes
from metis_app.api.models import IndexBuildRequestModel, IndexBuildResultModel


async def _run_engine(func: Any, *args: Any) -> Any:
    try:
        return func(*args)
    except ValueError as exc:
        raise LitestarHTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise LitestarHTTPException(status_code=503, detail=str(exc)) from exc


@post("/v1/index/build")
async def api_build_index(data: IndexBuildRequestModel) -> dict[str, Any]:
    """Build a new index from documents."""
    result = await _run_engine(build_index, data.to_engine())
    return IndexBuildResultModel.from_engine(result).model_dump()


@get("/v1/index/list")
async def api_list_indexes() -> list[dict[str, Any]]:
    """List all available indexes."""
    result = await _run_engine(list_indexes)
    return result
