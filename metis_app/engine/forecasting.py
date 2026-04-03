"""Engine-facing forecast helpers for TimesFM-backed chat mode."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator

from metis_app.engine.querying import _normalize_run_id
from metis_app.services.forecast_service import (
    ForecastMapping,
    ForecastPreflightResult,
    ForecastQueryResult,
    ForecastSchemaResult,
    ForecastService,
)
from metis_app.services.stream_events import normalize_stream_event


@dataclass(slots=True)
class ForecastSchemaRequest:
    file_path: str
    mapping: ForecastMapping | dict[str, Any] | None = None
    horizon: int | None = None


@dataclass(slots=True)
class ForecastQueryRequest:
    file_path: str
    prompt: str
    mapping: ForecastMapping | dict[str, Any]
    settings: dict[str, Any]
    horizon: int | None = None
    run_id: str | None = None


def forecast_preflight(settings: dict[str, Any]) -> ForecastPreflightResult:
    return ForecastService().preflight(settings)


def inspect_forecast_schema(req: ForecastSchemaRequest) -> ForecastSchemaResult:
    return ForecastService().inspect_schema(
        file_path=req.file_path,
        mapping=req.mapping,
        horizon=req.horizon,
    )


def query_forecast(req: ForecastQueryRequest) -> ForecastQueryResult:
    run_id = _normalize_run_id(req.run_id)
    result = ForecastService().run_forecast(
        file_path=req.file_path,
        mapping=req.mapping,
        settings=req.settings,
        prompt=req.prompt,
        horizon=req.horizon,
        run_id=run_id,
    )
    result.run_id = run_id
    return result


def stream_forecast(req: ForecastQueryRequest) -> Iterator[dict[str, Any]]:
    run_id = _normalize_run_id(req.run_id)
    sequence = 0

    def _emit(event: dict[str, Any]) -> dict[str, Any]:
        nonlocal sequence
        sequence += 1
        return normalize_stream_event(event, sequence=sequence, source="forecast_stream")

    try:
        yield _emit({"type": "run_started", "run_id": run_id})
        result = ForecastService().run_forecast(
            file_path=req.file_path,
            mapping=req.mapping,
            settings=req.settings,
            prompt=req.prompt,
            horizon=req.horizon,
            run_id=run_id,
        )
        yield _emit(
            {
                "type": "final",
                "run_id": run_id,
                "answer_text": result.answer_text,
                "selected_mode": result.selected_mode,
                "model_backend": result.model_backend,
                "model_id": result.model_id,
                "horizon": result.horizon,
                "context_used": result.context_used,
                "warnings": result.warnings,
                "artifacts": list(result.artifacts or []),
            }
        )
    except Exception as exc:  # noqa: BLE001
        yield _emit({"type": "error", "run_id": run_id, "message": str(exc)})

