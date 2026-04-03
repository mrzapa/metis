from __future__ import annotations

from importlib import import_module
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

api_app_module = import_module("metis_app.api.app")


def test_forecast_preflight_endpoint_uses_orchestrator(monkeypatch) -> None:
    fake_orchestrator = MagicMock()
    fake_orchestrator.get_forecast_preflight.return_value = {
        "ready": True,
        "timesfm_available": True,
        "covariates_available": False,
        "model_id": "google/timesfm-2.5-200m-pytorch",
        "max_context": 16000,
        "max_horizon": 1000,
        "xreg_mode": "xreg + timesfm",
        "force_xreg_cpu": True,
        "warnings": ["Install JAX to enable covariates."],
        "install_guidance": ["pip install 'metis-app[forecast-xreg]'"],
    }
    monkeypatch.setattr(api_app_module, "WorkspaceOrchestrator", lambda: fake_orchestrator)
    client = TestClient(api_app_module.create_app())

    response = client.get("/v1/forecast/preflight")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ready"] is True
    assert payload["covariates_available"] is False
    assert "JAX" in payload["warnings"][0]


def test_forecast_schema_endpoint_uses_orchestrator(monkeypatch) -> None:
    fake_orchestrator = MagicMock()
    fake_orchestrator.inspect_forecast_schema.return_value = {
        "file_path": "/tmp/revenue.csv",
        "file_name": "revenue.csv",
        "delimiter": ",",
        "row_count": 12,
        "column_count": 3,
        "columns": [],
        "timestamp_candidates": ["ds"],
        "numeric_target_candidates": ["y"],
        "suggested_mapping": {
            "timestamp_column": "ds",
            "target_column": "y",
            "dynamic_covariates": ["promo"],
            "static_covariates": [],
        },
        "validation": {
            "valid": True,
            "errors": [],
            "warnings": [],
            "history_row_count": 10,
            "future_row_count": 2,
            "inferred_horizon": 2,
            "resolved_horizon": 2,
            "inferred_frequency": "daily",
        },
    }
    monkeypatch.setattr(api_app_module, "WorkspaceOrchestrator", lambda: fake_orchestrator)
    client = TestClient(api_app_module.create_app())

    response = client.post(
        "/v1/forecast/schema",
        json={
            "file_path": "/tmp/revenue.csv",
            "mapping": {
                "timestamp_column": "ds",
                "target_column": "y",
                "dynamic_covariates": ["promo"],
                "static_covariates": [],
            },
            "horizon": 2,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["suggested_mapping"]["timestamp_column"] == "ds"
    fake_orchestrator.inspect_forecast_schema.assert_called_once()
    req = fake_orchestrator.inspect_forecast_schema.call_args.args[0]
    assert req.file_path == "/tmp/revenue.csv"
    assert req.horizon == 2
    assert req.mapping.dynamic_covariates == ["promo"]


def test_forecast_query_endpoint_uses_orchestrator(monkeypatch) -> None:
    fake_orchestrator = MagicMock()
    fake_orchestrator.run_forecast_query.return_value = SimpleNamespace(
        run_id="forecast-run-1",
        answer_text="Forecast summary.",
        selected_mode="Forecast",
        model_backend="timesfm-2.5-torch",
        model_id="google/timesfm-2.5-200m-pytorch",
        horizon=3,
        context_used=24,
        warnings=[],
        artifacts=[
            {
                "id": "forecast_report",
                "type": "forecast_report",
                "summary": "Revenue forecast",
                "path": "forecast/revenue.json",
                "mime_type": "application/vnd.metis.forecast+json",
                "payload": {
                    "history_points": [{"timestamp": "2026-01-01T00:00:00", "value": 100}],
                    "forecast_points": [{"timestamp": "2026-01-02T00:00:00", "value": 101}],
                    "quantiles": {},
                    "warnings": [],
                    "mapping": {
                        "file_path": "/tmp/revenue.csv",
                        "file_name": "revenue.csv",
                        "timestamp_column": "ds",
                        "target_column": "y",
                        "dynamic_covariates": [],
                        "static_covariates": [],
                    },
                    "metadata": {
                        "horizon": 3,
                        "context_used": 24,
                        "model_backend": "timesfm-2.5-torch",
                        "model_id": "google/timesfm-2.5-200m-pytorch",
                        "xreg_mode": "univariate",
                    },
                },
            }
        ],
    )
    monkeypatch.setattr(api_app_module, "WorkspaceOrchestrator", lambda: fake_orchestrator)
    client = TestClient(api_app_module.create_app())

    response = client.post(
        "/v1/query/forecast",
        json={
            "file_path": "/tmp/revenue.csv",
            "prompt": "Forecast revenue",
            "mapping": {
                "timestamp_column": "ds",
                "target_column": "y",
                "dynamic_covariates": [],
                "static_covariates": [],
            },
            "settings": {"selected_mode": "Forecast"},
            "session_id": "session-1",
            "horizon": 3,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["selected_mode"] == "Forecast"
    assert payload["artifacts"][0]["type"] == "forecast_report"
    fake_orchestrator.run_forecast_query.assert_called_once()
    assert fake_orchestrator.run_forecast_query.call_args.kwargs["session_id"] == "session-1"


def test_forecast_stream_endpoint_emits_sse(monkeypatch) -> None:
    fake_orchestrator = MagicMock()
    fake_orchestrator.stream_forecast_query.return_value = iter(
        [
            {"type": "run_started", "run_id": "forecast-run-2"},
            {
                "type": "final",
                "run_id": "forecast-run-2",
                "answer_text": "Done",
                "selected_mode": "Forecast",
                "model_backend": "timesfm-2.5-torch",
                "model_id": "google/timesfm-2.5-200m-pytorch",
                "horizon": 2,
                "context_used": 12,
                "warnings": [],
                "artifacts": [],
            },
        ]
    )
    monkeypatch.setattr(api_app_module, "WorkspaceOrchestrator", lambda: fake_orchestrator)
    client = TestClient(api_app_module.create_app())

    response = client.post(
        "/v1/query/forecast/stream",
        json={
            "file_path": "/tmp/revenue.csv",
            "prompt": "Forecast revenue",
            "mapping": {
                "timestamp_column": "ds",
                "target_column": "y",
                "dynamic_covariates": [],
                "static_covariates": [],
            },
            "settings": {"selected_mode": "Forecast"},
            "session_id": "session-2",
            "horizon": 2,
        },
    )

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    assert "run_started" in response.text
    assert '"selected_mode": "Forecast"' in response.text
