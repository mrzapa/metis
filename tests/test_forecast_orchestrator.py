from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import ANY, MagicMock

import pytest

from metis_app.engine.forecasting import ForecastQueryRequest
from metis_app.models.session_types import SessionSummary
from metis_app.services.forecast_service import ForecastMapping
from metis_app.services.workspace_orchestrator import WorkspaceOrchestrator


def _make_summary(session_id: str = "session-1") -> SessionSummary:
    return SessionSummary(
        session_id=session_id,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
        title="Forecast session",
        summary="",
        active_profile="",
        mode="Forecast",
        index_id="",
        vector_backend="json",
        llm_provider="mock",
        llm_model="mock-model",
        embed_model="",
        retrieve_k=0,
        final_k=0,
        mmr_lambda=0.0,
        agentic_iterations=0,
        extra_json="{}",
    )


def _make_orchestrator(
    *,
    session_repo: MagicMock | None = None,
    assistant_service: MagicMock | None = None,
) -> WorkspaceOrchestrator:
    session_repo = session_repo or MagicMock()
    session_repo.get_session.return_value = None
    session_repo.upsert_session.return_value = _make_summary()
    assistant_service = assistant_service or MagicMock()
    assistant_service.get_snapshot.return_value = {
        "identity": {},
        "runtime": {},
        "policy": {},
        "status": {},
    }
    assistant_service.reflect.return_value = {"ok": True}
    return WorkspaceOrchestrator(
        session_repo=session_repo,
        assistant_service=assistant_service,
        index_dir="/tmp/fake-indexes",
    )


def test_run_forecast_query_persists_messages_and_forces_selected_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_repo = MagicMock()
    session_repo.get_session.return_value = None
    session_repo.upsert_session.return_value = _make_summary("session-forecast")
    assistant_service = MagicMock()
    assistant_service.get_snapshot.return_value = {"identity": {"name": "METIS"}}
    assistant_service.reflect.return_value = {"ok": True}
    orchestrator = _make_orchestrator(
        session_repo=session_repo,
        assistant_service=assistant_service,
    )
    orchestrator._trace_store.append_event = MagicMock()  # type: ignore[method-assign]

    monkeypatch.setattr(
        "metis_app.services.workspace_orchestrator._settings_store.load_settings",
        lambda: {"llm_provider": "mock", "selected_mode": "Q&A"},
    )
    monkeypatch.setattr(
        "metis_app.services.workspace_orchestrator.query_forecast",
        lambda req: SimpleNamespace(
            run_id="forecast-run-1",
            answer_text="TimesFM forecast summary.",
            selected_mode="Forecast",
            model_backend="timesfm-2.5-torch",
            model_id="google/timesfm-2.5-200m-pytorch",
            horizon=2,
            context_used=8,
            warnings=[],
            artifacts=[
                {
                    "id": "forecast_report",
                    "type": "forecast_report",
                    "summary": "Revenue forecast",
                    "path": "forecast/revenue.json",
                    "mime_type": "application/vnd.metis.forecast+json",
                    "payload": {
                        "session_state": {
                            "file_path": "/tmp/revenue.csv",
                            "file_name": "revenue.csv",
                            "mapping": {
                                "timestamp_column": "ds",
                                "target_column": "y",
                                "dynamic_covariates": [],
                                "static_covariates": [],
                            },
                            "horizon": 2,
                        }
                    },
                }
            ],
        ),
    )

    result = orchestrator.run_forecast_query(
        ForecastQueryRequest(
            file_path="/tmp/revenue.csv",
            prompt="",
            mapping=ForecastMapping(
                timestamp_column="ds",
                target_column="y",
                dynamic_covariates=[],
                static_covariates=[],
            ),
            settings={},
            horizon=2,
        ),
        session_id="session-forecast",
    )

    assert result.selected_mode == "Forecast"
    assert session_repo.append_message.call_args_list[0].kwargs["role"] == "user"
    assert session_repo.append_message.call_args_list[0].kwargs["content"] == "Forecast revenue.csv"
    assert session_repo.append_message.call_args_list[1].kwargs["role"] == "assistant"
    assert session_repo.append_message.call_args_list[1].kwargs["artifacts"][0]["type"] == "forecast_report"
    assistant_service.reflect.assert_called_once_with(
        trigger="completed_run",
        settings={
            "llm_provider": "mock",
            "selected_mode": "Forecast",
            "assistant_identity": {},
            "assistant_runtime": {},
            "assistant_policy": {},
        },
        session_id="session-forecast",
        run_id="forecast-run-1",
        _orchestrator=orchestrator,
    )


def test_stream_forecast_query_appends_final_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_repo = MagicMock()
    session_repo.get_session.return_value = None
    session_repo.upsert_session.return_value = _make_summary("session-stream")
    assistant_service = MagicMock()
    assistant_service.get_snapshot.return_value = {"identity": {"name": "METIS"}}
    assistant_service.reflect.return_value = {"ok": True}
    orchestrator = _make_orchestrator(
        session_repo=session_repo,
        assistant_service=assistant_service,
    )
    orchestrator._trace_store.append_event = MagicMock()  # type: ignore[method-assign]

    monkeypatch.setattr(
        "metis_app.services.workspace_orchestrator._settings_store.load_settings",
        lambda: {"llm_provider": "mock", "selected_mode": "Q&A"},
    )
    monkeypatch.setattr(
        "metis_app.services.workspace_orchestrator.stream_forecast",
        lambda req: iter(
            [
                {"type": "run_started", "run_id": "forecast-run-2"},
                {
                    "type": "final",
                    "run_id": "forecast-run-2",
                    "answer_text": "Final streamed forecast.",
                    "artifacts": [
                        {
                            "id": "forecast_report",
                            "type": "forecast_report",
                            "summary": "Revenue forecast",
                            "payload": {"session_state": {"file_path": "/tmp/revenue.csv"}},
                        }
                    ],
                },
            ]
        ),
    )

    events = list(
        orchestrator.stream_forecast_query(
            ForecastQueryRequest(
                file_path="/tmp/revenue.csv",
                prompt="Forecast revenue",
                mapping=ForecastMapping(
                    timestamp_column="ds",
                    target_column="y",
                    dynamic_covariates=[],
                    static_covariates=[],
                ),
                settings={},
                horizon=2,
            ),
            session_id="session-stream",
        )
    )

    assert [event["type"] for event in events] == ["run_started", "final"]
    assert session_repo.append_message.call_args_list[0].kwargs["role"] == "user"
    assert session_repo.append_message.call_args_list[1].kwargs["role"] == "assistant"
    assert session_repo.append_message.call_args_list[1].kwargs["content"] == "Final streamed forecast."
    assistant_service.reflect.assert_called_once_with(
        trigger="completed_run",
        settings={
            "llm_provider": "mock",
            "selected_mode": "Forecast",
            "assistant_identity": {},
            "assistant_runtime": {},
            "assistant_policy": {},
        },
        session_id="session-stream",
        run_id="forecast-run-2",
        _orchestrator=orchestrator,
    )
