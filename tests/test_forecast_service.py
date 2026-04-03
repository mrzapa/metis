from __future__ import annotations

import csv
from pathlib import Path
from types import SimpleNamespace

import pytest

import metis_app.services.forecast_service as forecast_service_module
from metis_app.services.forecast_service import ForecastMapping, ForecastService


def _write_csv(path: Path, rows: list[dict[str, object]]) -> Path:
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_inspect_schema_detects_candidates_and_invalid_static_covariates(tmp_path: Path) -> None:
    csv_path = _write_csv(
        tmp_path / "sales.csv",
        [
            {"ds": "2026-01-01", "y": 10, "promo": 0, "region": "uk"},
            {"ds": "2026-01-02", "y": 11, "promo": 1, "region": "uk"},
            {"ds": "2026-01-03", "y": "", "promo": 1, "region": "eu"},
            {"ds": "2026-01-04", "y": "", "promo": 0, "region": "uk"},
        ],
    )

    result = ForecastService().inspect_schema(
        file_path=csv_path,
        mapping=ForecastMapping(
            timestamp_column="ds",
            target_column="y",
            dynamic_covariates=["promo"],
            static_covariates=["region"],
        ),
    )

    assert "ds" in result.timestamp_candidates
    assert "y" in result.numeric_target_candidates
    assert result.validation.future_row_count == 2
    assert result.validation.valid is False
    assert any("Static covariate 'region'" in error for error in result.validation.errors)


def test_preflight_reports_univariate_ready_but_covariates_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        forecast_service_module,
        "_module_available",
        lambda module_name: module_name in {"timesfm", "torch"},
    )

    result = ForecastService().preflight()

    assert result.ready is True
    assert result.timesfm_available is True
    assert result.covariates_available is False
    assert any("covariate" in warning.lower() for warning in result.warnings)
    assert any("jax" in guidance.lower() for guidance in result.install_guidance)


def test_run_forecast_returns_univariate_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    csv_path = _write_csv(
        tmp_path / "revenue.csv",
        [
            {"ds": "2026-01-01", "y": 100},
            {"ds": "2026-01-02", "y": 102},
            {"ds": "2026-01-03", "y": 103},
        ],
    )

    class FakeModel:
        def forecast(self, *, horizon: int, inputs: list[list[float]]) -> tuple[list[list[float]], list[object]]:
            assert horizon == 2
            assert inputs == [[100.0, 102.0, 103.0]]
            return [[104.0, 105.0]], []

    monkeypatch.setattr(forecast_service_module, "_module_available", lambda _module_name: True)
    monkeypatch.setattr(
        ForecastService,
        "_get_model",
        lambda self, *, settings, uses_covariates: FakeModel(),
    )

    result = ForecastService().run_forecast(
        file_path=csv_path,
        mapping=ForecastMapping(
            timestamp_column="ds",
            target_column="y",
            dynamic_covariates=[],
            static_covariates=[],
        ),
        settings={},
        prompt="Forecast the next two periods.",
        horizon=2,
        run_id="forecast-run-1",
    )

    assert result.run_id == "forecast-run-1"
    assert result.selected_mode == "Forecast"
    assert result.horizon == 2
    assert result.context_used == 3
    assert result.artifacts is not None
    assert [artifact["type"] for artifact in result.artifacts] == ["forecast_report", "metric_cards"]
    forecast_report = result.artifacts[0]["payload"]
    assert forecast_report["metadata"]["xreg_mode"] == "univariate"
    assert forecast_report["session_state"]["mapping"]["target_column"] == "y"


def test_run_forecast_rejects_missing_future_covariates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    csv_path = _write_csv(
        tmp_path / "promo.csv",
        [
            {"ds": "2026-01-01", "y": 10, "promo": 0},
            {"ds": "2026-01-02", "y": 11, "promo": 1},
            {"ds": "2026-01-03", "y": "", "promo": ""},
        ],
    )

    monkeypatch.setattr(forecast_service_module, "_module_available", lambda _module_name: True)

    with pytest.raises(ValueError, match="Dynamic covariate 'promo' contains blank values."):
        ForecastService().run_forecast(
            file_path=csv_path,
            mapping=ForecastMapping(
                timestamp_column="ds",
                target_column="y",
                dynamic_covariates=["promo"],
                static_covariates=[],
            ),
            settings={},
            prompt="Forecast the next step.",
            run_id="forecast-run-2",
        )


def test_run_forecast_uses_covariate_path_and_force_cpu(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    csv_path = _write_csv(
        tmp_path / "promo-region.csv",
        [
            {"ds": "2026-01-01", "y": 10, "promo": 0, "region": "uk"},
            {"ds": "2026-01-02", "y": 11, "promo": 1, "region": "uk"},
            {"ds": "2026-01-03", "y": "", "promo": 1, "region": "uk"},
            {"ds": "2026-01-04", "y": "", "promo": 0, "region": "uk"},
        ],
    )
    captured: dict[str, object] = {}

    class FakeModel:
        def forecast_with_covariates(self, **kwargs: object) -> tuple[list[list[float]], list[object]]:
            captured.update(kwargs)
            return [[12.0, 13.0]], []

    monkeypatch.setattr(forecast_service_module, "_module_available", lambda _module_name: True)
    monkeypatch.setattr(
        ForecastService,
        "_get_model",
        lambda self, *, settings, uses_covariates: FakeModel(),
    )

    result = ForecastService().run_forecast(
        file_path=csv_path,
        mapping=ForecastMapping(
            timestamp_column="ds",
            target_column="y",
            dynamic_covariates=["promo"],
            static_covariates=["region"],
        ),
        settings={"forecast_xreg_mode": "xreg + timesfm", "forecast_force_xreg_cpu": True},
        prompt="Forecast with promo covariates.",
        run_id="forecast-run-3",
    )

    assert captured["xreg_mode"] == "xreg + timesfm"
    assert captured["force_on_cpu"] is True
    assert captured["dynamic_numerical_covariates"] == {"promo": [[0.0, 1.0, 1.0, 0.0]]}
    assert captured["static_categorical_covariates"] == {"region": ["uk"]}
    assert result.artifacts is not None
    assert result.artifacts[0]["payload"]["metadata"]["xreg_mode"] == "xreg + timesfm"


def test_get_model_sets_return_backcast_for_covariates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ForecastService._model_cache.clear()
    captured: dict[str, object] = {}

    class FakeModel:
        def compile(self, config: object) -> None:
            captured["config"] = config

    def fake_from_pretrained(_model_id: str) -> FakeModel:
        return FakeModel()

    def fake_forecast_config(**kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(**kwargs)

    fake_timesfm = SimpleNamespace(
        TimesFM_2p5_200M_torch=SimpleNamespace(from_pretrained=fake_from_pretrained),
        ForecastConfig=fake_forecast_config,
    )
    fake_torch = SimpleNamespace(set_float32_matmul_precision=lambda _mode: None)

    def fake_import_module(name: str) -> object:
        if name == "timesfm":
            return fake_timesfm
        if name == "torch":
            return fake_torch
        raise AssertionError(f"Unexpected module import: {name}")

    monkeypatch.setattr(forecast_service_module.importlib, "import_module", fake_import_module)

    ForecastService()._get_model(settings={}, uses_covariates=True)

    assert getattr(captured["config"], "return_backcast") is True
