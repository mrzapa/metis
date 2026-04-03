"""Forecasting helpers backed by TimesFM with dependency-gated covariates."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import csv
import importlib
import importlib.util
import math
from pathlib import Path
from typing import Any

_DEFAULT_MODEL_ID = "google/timesfm-2.5-200m-pytorch"
_DEFAULT_MAX_CONTEXT = 16000
_DEFAULT_MAX_HORIZON = 1000
_DEFAULT_XREG_MODE = "xreg + timesfm"
_FORECAST_SELECTED_MODE = "Forecast"
_DEFAULT_QUANTILE_LABELS = [
    "mean",
    "p10",
    "p20",
    "p30",
    "p40",
    "p50",
    "p60",
    "p70",
    "p80",
    "p90",
]
_TIMESTAMP_FORMATS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%Y/%m/%d %H:%M:%S",
    "%m/%d/%Y",
    "%m/%d/%Y %H:%M",
    "%m/%d/%Y %H:%M:%S",
    "%d/%m/%Y",
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y %H:%M:%S",
)


def _unique_in_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        key = value.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        ordered.append(value)
    return ordered


def _safe_float(value: str) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.replace(",", "")
    try:
        parsed = float(normalized)
    except ValueError:
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _safe_timestamp(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    iso_candidate = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(iso_candidate)
    except ValueError:
        pass
    for fmt in _TIMESTAMP_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _format_timestamp(value: datetime) -> str:
    return value.isoformat()


def _format_value(value: float | None) -> str:
    if value is None or not math.isfinite(value):
        return "n/a"
    rounded = round(value, 4)
    if abs(rounded) >= 100 or rounded.is_integer():
        return f"{rounded:,.2f}"
    return f"{rounded:,.4f}".rstrip("0").rstrip(".")


def _downsample_points(
    points: list[dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    if len(points) <= limit or limit <= 0:
        return points
    if limit == 1:
        return [points[-1]]
    step = (len(points) - 1) / (limit - 1)
    selected: list[dict[str, Any]] = []
    for index in range(limit):
        selected_index = round(index * step)
        selected.append(points[selected_index])
    return selected


def _module_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


@dataclass(slots=True)
class ForecastMapping:
    timestamp_column: str
    target_column: str
    dynamic_covariates: list[str] = field(default_factory=list)
    static_covariates: list[str] = field(default_factory=list)

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | "ForecastMapping" | None) -> "ForecastMapping | None":
        if payload is None:
            return None
        if isinstance(payload, ForecastMapping):
            return payload
        if not isinstance(payload, dict):
            raise ValueError("mapping must be an object")
        timestamp_column = str(payload.get("timestamp_column") or "").strip()
        target_column = str(payload.get("target_column") or "").strip()
        dynamic_covariates = _unique_in_order(
            [str(item).strip() for item in list(payload.get("dynamic_covariates") or []) if str(item).strip()]
        )
        static_covariates = _unique_in_order(
            [str(item).strip() for item in list(payload.get("static_covariates") or []) if str(item).strip()]
        )
        return cls(
            timestamp_column=timestamp_column,
            target_column=target_column,
            dynamic_covariates=dynamic_covariates,
            static_covariates=static_covariates,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp_column": self.timestamp_column,
            "target_column": self.target_column,
            "dynamic_covariates": list(self.dynamic_covariates),
            "static_covariates": list(self.static_covariates),
        }


@dataclass(slots=True)
class ForecastSchemaColumn:
    name: str
    detected_type: str
    non_null_count: int
    unique_count: int
    numeric_ratio: float
    timestamp_ratio: float
    sample_values: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "detected_type": self.detected_type,
            "non_null_count": self.non_null_count,
            "unique_count": self.unique_count,
            "numeric_ratio": self.numeric_ratio,
            "timestamp_ratio": self.timestamp_ratio,
            "sample_values": list(self.sample_values),
        }


@dataclass(slots=True)
class ForecastValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    history_row_count: int = 0
    future_row_count: int = 0
    inferred_horizon: int = 0
    resolved_horizon: int = 0
    inferred_frequency: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "history_row_count": self.history_row_count,
            "future_row_count": self.future_row_count,
            "inferred_horizon": self.inferred_horizon,
            "resolved_horizon": self.resolved_horizon,
            "inferred_frequency": self.inferred_frequency,
        }


@dataclass(slots=True)
class ForecastSchemaResult:
    file_path: str
    file_name: str
    delimiter: str
    row_count: int
    column_count: int
    columns: list[ForecastSchemaColumn]
    timestamp_candidates: list[str]
    numeric_target_candidates: list[str]
    suggested_mapping: ForecastMapping | None
    validation: ForecastValidationResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "file_name": self.file_name,
            "delimiter": self.delimiter,
            "row_count": self.row_count,
            "column_count": self.column_count,
            "columns": [column.to_dict() for column in self.columns],
            "timestamp_candidates": list(self.timestamp_candidates),
            "numeric_target_candidates": list(self.numeric_target_candidates),
            "suggested_mapping": self.suggested_mapping.to_dict() if self.suggested_mapping else None,
            "validation": self.validation.to_dict(),
        }


@dataclass(slots=True)
class ForecastPreflightResult:
    ready: bool
    timesfm_available: bool
    covariates_available: bool
    model_id: str
    max_context: int
    max_horizon: int
    xreg_mode: str
    force_xreg_cpu: bool
    warnings: list[str] = field(default_factory=list)
    install_guidance: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "timesfm_available": self.timesfm_available,
            "covariates_available": self.covariates_available,
            "model_id": self.model_id,
            "max_context": self.max_context,
            "max_horizon": self.max_horizon,
            "xreg_mode": self.xreg_mode,
            "force_xreg_cpu": self.force_xreg_cpu,
            "warnings": list(self.warnings),
            "install_guidance": list(self.install_guidance),
        }


@dataclass(slots=True)
class ForecastQueryResult:
    run_id: str
    answer_text: str
    selected_mode: str
    model_backend: str
    model_id: str
    horizon: int
    context_used: int
    warnings: list[str] = field(default_factory=list)
    artifacts: list[dict[str, Any]] | None = None


@dataclass(slots=True)
class _LoadedTable:
    file_path: str
    file_name: str
    delimiter: str
    fieldnames: list[str]
    rows: list[dict[str, str]]
    columns: list[ForecastSchemaColumn]
    timestamp_candidates: list[str]
    numeric_target_candidates: list[str]
    suggested_mapping: ForecastMapping | None


@dataclass(slots=True)
class _PreparedDataset:
    file_path: str
    file_name: str
    mapping: ForecastMapping
    history_timestamps: list[datetime]
    future_timestamps: list[datetime]
    history_target: list[float]
    dynamic_numerical_covariates: dict[str, list[float]]
    dynamic_categorical_covariates: dict[str, list[str]]
    static_numerical_covariates: dict[str, float]
    static_categorical_covariates: dict[str, str]
    frequency_label: str
    horizon: int
    validation: ForecastValidationResult


class ForecastService:
    """Schema inference and TimesFM execution for structured forecast runs."""

    _model_cache: dict[tuple[str, int, int, bool, bool], Any] = {}

    def preflight(self, settings: dict[str, Any] | None = None) -> ForecastPreflightResult:
        resolved_settings = dict(settings or {})
        timesfm_available = _module_available("timesfm") and _module_available("torch")
        covariates_available = timesfm_available and _module_available("jax") and _module_available("sklearn")
        warnings: list[str] = []
        install_guidance: list[str] = []

        if not timesfm_available:
            install_guidance.append(
                "Install forecasting support with `pip install 'metis-app[forecast]'` or `pip install timesfm torch`."
            )
        if timesfm_available and not covariates_available:
            warnings.append(
                "TimesFM is available, but covariate-backed XReg runs are disabled until JAX and scikit-learn are installed."
            )
            install_guidance.append(
                "Enable covariates with `pip install 'metis-app[forecast-xreg]'` or `pip install jax scikit-learn`."
            )

        return ForecastPreflightResult(
            ready=timesfm_available,
            timesfm_available=timesfm_available,
            covariates_available=covariates_available,
            model_id=str(resolved_settings.get("forecast_model_id") or _DEFAULT_MODEL_ID),
            max_context=max(1, int(resolved_settings.get("forecast_max_context") or _DEFAULT_MAX_CONTEXT)),
            max_horizon=max(1, int(resolved_settings.get("forecast_max_horizon") or _DEFAULT_MAX_HORIZON)),
            xreg_mode=str(resolved_settings.get("forecast_xreg_mode") or _DEFAULT_XREG_MODE),
            force_xreg_cpu=bool(resolved_settings.get("forecast_force_xreg_cpu", True)),
            warnings=warnings,
            install_guidance=install_guidance,
        )

    def inspect_schema(
        self,
        *,
        file_path: str | Path,
        mapping: ForecastMapping | dict[str, Any] | None = None,
        horizon: int | None = None,
    ) -> ForecastSchemaResult:
        table = self._load_table(file_path)
        resolved_mapping = ForecastMapping.from_payload(mapping) or table.suggested_mapping
        validation = self._validate_table(table, resolved_mapping, horizon=horizon)
        return ForecastSchemaResult(
            file_path=table.file_path,
            file_name=table.file_name,
            delimiter=table.delimiter,
            row_count=len(table.rows),
            column_count=len(table.fieldnames),
            columns=list(table.columns),
            timestamp_candidates=list(table.timestamp_candidates),
            numeric_target_candidates=list(table.numeric_target_candidates),
            suggested_mapping=table.suggested_mapping,
            validation=validation,
        )

    def run_forecast(
        self,
        *,
        file_path: str | Path,
        mapping: ForecastMapping | dict[str, Any],
        settings: dict[str, Any],
        prompt: str = "",
        horizon: int | None = None,
        run_id: str = "",
    ) -> ForecastQueryResult:
        preflight = self.preflight(settings)
        if not preflight.ready:
            detail = preflight.install_guidance[0] if preflight.install_guidance else "TimesFM is not installed."
            raise RuntimeError(detail)

        table = self._load_table(file_path)
        resolved_mapping = ForecastMapping.from_payload(mapping)
        if resolved_mapping is None:
            raise ValueError("A valid forecast mapping is required.")
        validation = self._validate_table(table, resolved_mapping, horizon=horizon)
        if not validation.valid:
            raise ValueError("; ".join(validation.errors))

        dataset = self._prepare_dataset(table, resolved_mapping, validation)
        uses_covariates = bool(
            dataset.dynamic_numerical_covariates
            or dataset.dynamic_categorical_covariates
            or dataset.static_numerical_covariates
            or dataset.static_categorical_covariates
        )
        if uses_covariates and not preflight.covariates_available:
            detail = preflight.install_guidance[-1] if preflight.install_guidance else "Covariates are unavailable."
            raise RuntimeError(detail)

        model = self._get_model(settings=settings, uses_covariates=uses_covariates)
        history_values = dataset.history_target[-preflight.max_context :]
        context_used = len(history_values)
        future_timestamps = list(dataset.future_timestamps)
        if len(future_timestamps) < dataset.horizon:
            future_timestamps.extend(
                self._generate_future_timestamps(
                    history_timestamps=dataset.history_timestamps,
                    existing=future_timestamps,
                    horizon=dataset.horizon,
                )
            )
        future_timestamps = future_timestamps[: dataset.horizon]

        point_forecast: list[float]
        quantile_payload: dict[str, list[float]] = {}
        xreg_mode = str(settings.get("forecast_xreg_mode") or _DEFAULT_XREG_MODE)

        if uses_covariates:
            dynamic_numerical_covariates = {
                name: [values[-(context_used + dataset.horizon) :]]
                for name, values in dataset.dynamic_numerical_covariates.items()
            }
            dynamic_categorical_covariates = {
                name: [values[-(context_used + dataset.horizon) :]]
                for name, values in dataset.dynamic_categorical_covariates.items()
            }
            static_numerical_covariates = (
                {name: [value] for name, value in dataset.static_numerical_covariates.items()}
                or None
            )
            static_categorical_covariates = (
                {name: [value] for name, value in dataset.static_categorical_covariates.items()}
                or None
            )
            raw_points, raw_quantiles = model.forecast_with_covariates(
                inputs=[history_values],
                dynamic_numerical_covariates=dynamic_numerical_covariates or None,
                dynamic_categorical_covariates=dynamic_categorical_covariates or None,
                static_numerical_covariates=static_numerical_covariates,
                static_categorical_covariates=static_categorical_covariates,
                xreg_mode=xreg_mode,
                force_on_cpu=bool(settings.get("forecast_force_xreg_cpu", True)),
            )
        else:
            raw_points, raw_quantiles = model.forecast(
                horizon=dataset.horizon,
                inputs=[history_values],
            )

        point_forecast = self._coerce_point_series(raw_points)[0][: dataset.horizon]
        quantile_payload = self._coerce_quantiles(raw_quantiles, limit=dataset.horizon)

        artifacts = self._build_artifacts(
            dataset=dataset,
            future_timestamps=future_timestamps,
            point_forecast=point_forecast,
            quantile_payload=quantile_payload,
            model_id=preflight.model_id,
            model_backend="timesfm-2.5-torch",
            context_used=context_used,
            xreg_mode=xreg_mode if uses_covariates else "univariate",
        )
        answer_text = self._summarize_forecast(
            dataset=dataset,
            point_forecast=point_forecast,
            quantile_payload=quantile_payload,
            context_used=context_used,
            prompt=prompt,
        )

        return ForecastQueryResult(
            run_id=str(run_id or ""),
            answer_text=answer_text,
            selected_mode=_FORECAST_SELECTED_MODE,
            model_backend="timesfm-2.5-torch",
            model_id=preflight.model_id,
            horizon=dataset.horizon,
            context_used=context_used,
            warnings=list(_unique_in_order([*validation.warnings, *preflight.warnings])),
            artifacts=artifacts,
        )

    def _load_table(self, file_path: str | Path) -> _LoadedTable:
        candidate = Path(file_path).expanduser()
        if not candidate.exists():
            raise ValueError(f"Forecast file does not exist: {candidate}")
        if candidate.suffix.lower() not in {".csv", ".tsv"}:
            raise ValueError("Forecast mode currently supports CSV and TSV files only.")

        raw_text = candidate.read_text(encoding="utf-8-sig")
        if not raw_text.strip():
            raise ValueError("Forecast file is empty.")

        delimiter = "\t" if candidate.suffix.lower() == ".tsv" else ","
        preview = raw_text[:2048]
        try:
            sniffed = csv.Sniffer().sniff(preview, delimiters=",\t")
            delimiter = sniffed.delimiter or delimiter
        except csv.Error:
            pass

        reader = csv.DictReader(raw_text.splitlines(), delimiter=delimiter)
        fieldnames = [str(name or "").strip() for name in list(reader.fieldnames or []) if str(name or "").strip()]
        if not fieldnames:
            raise ValueError("Forecast file must include a header row.")

        rows: list[dict[str, str]] = []
        for raw_row in reader:
            row: dict[str, str] = {}
            for field in fieldnames:
                row[field] = str((raw_row or {}).get(field) or "").strip()
            rows.append(row)
        if not rows:
            raise ValueError("Forecast file does not contain any data rows.")

        columns = [self._profile_column(field, rows) for field in fieldnames]
        timestamp_candidates = [column.name for column in columns if column.timestamp_ratio >= 0.6]
        numeric_target_candidates = [column.name for column in columns if column.numeric_ratio >= 0.8]
        suggested_mapping = self._suggest_mapping(columns)

        return _LoadedTable(
            file_path=str(candidate),
            file_name=candidate.name,
            delimiter=delimiter,
            fieldnames=fieldnames,
            rows=rows,
            columns=columns,
            timestamp_candidates=timestamp_candidates,
            numeric_target_candidates=numeric_target_candidates,
            suggested_mapping=suggested_mapping,
        )

    def _profile_column(self, column_name: str, rows: list[dict[str, str]]) -> ForecastSchemaColumn:
        raw_values = [str(row.get(column_name) or "").strip() for row in rows]
        non_empty = [value for value in raw_values if value]
        numeric_hits = sum(1 for value in non_empty if _safe_float(value) is not None)
        timestamp_hits = sum(1 for value in non_empty if _safe_timestamp(value) is not None)
        sample_values = _unique_in_order(non_empty)[:5]
        detected_type = "string"
        if not non_empty:
            detected_type = "empty"
        elif timestamp_hits / max(len(non_empty), 1) >= 0.8:
            detected_type = "timestamp"
        elif numeric_hits / max(len(non_empty), 1) >= 0.8:
            detected_type = "numeric"
        return ForecastSchemaColumn(
            name=column_name,
            detected_type=detected_type,
            non_null_count=len(non_empty),
            unique_count=len(set(non_empty)),
            numeric_ratio=round(numeric_hits / max(len(non_empty), 1), 4) if non_empty else 0.0,
            timestamp_ratio=round(timestamp_hits / max(len(non_empty), 1), 4) if non_empty else 0.0,
            sample_values=sample_values,
        )

    def _suggest_mapping(self, columns: list[ForecastSchemaColumn]) -> ForecastMapping | None:
        timestamp_column = ""
        target_column = ""

        def _priority(name: str, preferred: tuple[str, ...]) -> tuple[int, str]:
            lowered = name.lower()
            best_rank = len(preferred)
            for index, candidate in enumerate(preferred):
                if lowered == candidate or lowered.endswith(f"_{candidate}") or candidate in lowered:
                    best_rank = index
                    break
            return (best_rank, lowered)

        timestamp_candidates = sorted(
            [column for column in columns if column.detected_type == "timestamp"],
            key=lambda column: (_priority(column.name, ("timestamp", "date", "datetime", "time", "ds")), -column.timestamp_ratio),
        )
        if timestamp_candidates:
            timestamp_column = timestamp_candidates[0].name

        target_candidates = sorted(
            [
                column
                for column in columns
                if column.detected_type == "numeric" and column.name != timestamp_column
            ],
            key=lambda column: (_priority(column.name, ("target", "value", "y", "sales", "demand", "count")), -column.numeric_ratio),
        )
        if target_candidates:
            target_column = target_candidates[0].name

        if not timestamp_column or not target_column:
            return None

        return ForecastMapping(
            timestamp_column=timestamp_column,
            target_column=target_column,
        )

    def _validate_table(
        self,
        table: _LoadedTable,
        mapping: ForecastMapping | None,
        *,
        horizon: int | None,
    ) -> ForecastValidationResult:
        errors: list[str] = []
        warnings: list[str] = []
        if mapping is None:
            return ForecastValidationResult(
                valid=False,
                errors=["METIS could not infer a timestamp and target column from the uploaded file."],
            )

        if mapping.timestamp_column not in table.fieldnames:
            errors.append("The selected timestamp column does not exist in the uploaded file.")
        if mapping.target_column not in table.fieldnames:
            errors.append("The selected target column does not exist in the uploaded file.")
        if mapping.timestamp_column and mapping.timestamp_column == mapping.target_column:
            errors.append("Timestamp and target columns must be different.")

        overlaps = set(mapping.dynamic_covariates) & set(mapping.static_covariates)
        if overlaps:
            errors.append(
                f"Columns cannot be both dynamic and static covariates: {', '.join(sorted(overlaps))}."
            )
        duplicate_targets = set(mapping.dynamic_covariates) | set(mapping.static_covariates)
        duplicate_targets &= {mapping.timestamp_column, mapping.target_column}
        if duplicate_targets:
            errors.append("Timestamp/target columns cannot also be marked as covariates.")

        if errors:
            return ForecastValidationResult(valid=False, errors=errors)

        rows_with_timestamps: list[tuple[datetime, dict[str, str]]] = []
        for row in table.rows:
            parsed_timestamp = _safe_timestamp(row.get(mapping.timestamp_column, ""))
            if parsed_timestamp is None:
                errors.append("Every forecast row must include a parseable timestamp value.")
                break
            rows_with_timestamps.append((parsed_timestamp, row))

        if errors:
            return ForecastValidationResult(valid=False, errors=errors)

        if rows_with_timestamps != sorted(rows_with_timestamps, key=lambda item: item[0]):
            warnings.append("Rows were not time-sorted; METIS will sort them before forecasting.")
            rows_with_timestamps = sorted(rows_with_timestamps, key=lambda item: item[0])

        target_values = [row.get(mapping.target_column, "") for _, row in rows_with_timestamps]
        history_indices = [index for index, value in enumerate(target_values) if str(value).strip()]
        if not history_indices:
            errors.append("The selected target column does not contain any historical values.")
            return ForecastValidationResult(valid=False, errors=errors)

        last_history_index = history_indices[-1]
        future_row_count = len(rows_with_timestamps) - last_history_index - 1

        for value in target_values[: last_history_index + 1]:
            if not str(value).strip():
                errors.append(
                    "Future forecast rows must be trailing rows with blank target values; missing target values were found inside the historical segment."
                )
                break
            if _safe_float(value) is None:
                errors.append("Historical target values must be numeric.")
                break

        for value in target_values[last_history_index + 1 :]:
            if str(value).strip():
                errors.append("Rows after the forecast horizon must leave the target column blank.")
                break

        history_row_count = last_history_index + 1
        inferred_horizon = future_row_count
        resolved_horizon = inferred_horizon

        if mapping.dynamic_covariates:
            if inferred_horizon <= 0:
                errors.append(
                    "Dynamic covariates require future rows with blank target values so METIS can infer the forecast horizon."
                )
            for column_name in mapping.dynamic_covariates:
                if column_name not in table.fieldnames:
                    errors.append(f"Dynamic covariate column '{column_name}' does not exist.")
                    continue
                column_values = [row.get(column_name, "") for _, row in rows_with_timestamps]
                if any(not str(value).strip() for value in column_values):
                    errors.append(f"Dynamic covariate '{column_name}' contains blank values.")
                    continue
                sample_profile = next((column for column in table.columns if column.name == column_name), None)
                if sample_profile and sample_profile.detected_type == "numeric":
                    if any(_safe_float(value) is None for value in column_values):
                        errors.append(f"Dynamic covariate '{column_name}' must remain numeric for all rows.")
                future_values = column_values[history_row_count:]
                if inferred_horizon > 0 and len(future_values) < inferred_horizon:
                    errors.append(f"Dynamic covariate '{column_name}' is missing future values.")
        else:
            if horizon is None:
                if inferred_horizon > 0:
                    resolved_horizon = inferred_horizon
                else:
                    errors.append("Provide a horizon when no dynamic covariates are selected.")
            else:
                resolved_horizon = int(horizon)

        if resolved_horizon <= 0:
            errors.append("Forecast horizon must be a positive integer.")

        inferred_frequency = self._infer_frequency(
            [timestamp for timestamp, _ in rows_with_timestamps[:history_row_count]]
        )

        for column_name in mapping.static_covariates:
            if column_name not in table.fieldnames:
                errors.append(f"Static covariate column '{column_name}' does not exist.")
                continue
            non_null_values = _unique_in_order(
                [row.get(column_name, "") for _, row in rows_with_timestamps if str(row.get(column_name, "")).strip()]
            )
            if len(non_null_values) == 0:
                errors.append(f"Static covariate '{column_name}' must include at least one non-null value.")
            elif len(non_null_values) > 1:
                errors.append(
                    f"Static covariate '{column_name}' must reduce to one non-null value for the whole run."
                )

        return ForecastValidationResult(
            valid=not errors,
            errors=errors,
            warnings=warnings,
            history_row_count=history_row_count,
            future_row_count=future_row_count,
            inferred_horizon=inferred_horizon,
            resolved_horizon=resolved_horizon,
            inferred_frequency=inferred_frequency,
        )

    def _prepare_dataset(
        self,
        table: _LoadedTable,
        mapping: ForecastMapping,
        validation: ForecastValidationResult,
    ) -> _PreparedDataset:
        rows_with_timestamps = [
            (_safe_timestamp(row[mapping.timestamp_column]), row)
            for row in table.rows
        ]
        rows_with_timestamps = sorted(
            [(timestamp, row) for timestamp, row in rows_with_timestamps if timestamp is not None],
            key=lambda item: item[0],
        )

        history_rows = rows_with_timestamps[: validation.history_row_count]
        future_rows = rows_with_timestamps[validation.history_row_count : validation.history_row_count + validation.resolved_horizon]

        history_timestamps = [timestamp for timestamp, _ in history_rows]
        future_timestamps = [timestamp for timestamp, _ in future_rows]
        history_target = [_safe_float(row[mapping.target_column]) or 0.0 for _, row in history_rows]

        dynamic_numerical_covariates: dict[str, list[float]] = {}
        dynamic_categorical_covariates: dict[str, list[str]] = {}
        for column_name in mapping.dynamic_covariates:
            values = [row[column_name] for _, row in [*history_rows, *future_rows]]
            profile = next((column for column in table.columns if column.name == column_name), None)
            if profile and profile.detected_type == "numeric":
                dynamic_numerical_covariates[column_name] = [
                    _safe_float(value) if _safe_float(value) is not None else 0.0 for value in values
                ]
            else:
                dynamic_categorical_covariates[column_name] = [str(value) for value in values]

        static_numerical_covariates: dict[str, float] = {}
        static_categorical_covariates: dict[str, str] = {}
        for column_name in mapping.static_covariates:
            values = _unique_in_order(
                [row[column_name] for _, row in rows_with_timestamps if str(row[column_name]).strip()]
            )
            value = values[0] if values else ""
            profile = next((column for column in table.columns if column.name == column_name), None)
            numeric_value = _safe_float(value)
            if profile and profile.detected_type == "numeric" and numeric_value is not None:
                static_numerical_covariates[column_name] = numeric_value
            else:
                static_categorical_covariates[column_name] = value

        return _PreparedDataset(
            file_path=table.file_path,
            file_name=table.file_name,
            mapping=mapping,
            history_timestamps=history_timestamps,
            future_timestamps=future_timestamps,
            history_target=history_target,
            dynamic_numerical_covariates=dynamic_numerical_covariates,
            dynamic_categorical_covariates=dynamic_categorical_covariates,
            static_numerical_covariates=static_numerical_covariates,
            static_categorical_covariates=static_categorical_covariates,
            frequency_label=validation.inferred_frequency,
            horizon=validation.resolved_horizon,
            validation=validation,
        )

    def _infer_frequency(self, timestamps: list[datetime]) -> str:
        if len(timestamps) < 2:
            return ""
        deltas = [timestamps[index + 1] - timestamps[index] for index in range(len(timestamps) - 1)]
        delta_counter = Counter(delta for delta in deltas if delta.total_seconds() > 0)
        if not delta_counter:
            return ""
        most_common_delta = delta_counter.most_common(1)[0][0]
        if most_common_delta == timedelta(days=1):
            return "daily"
        if most_common_delta == timedelta(weeks=1):
            return "weekly"
        if timedelta(days=27) <= most_common_delta <= timedelta(days=32):
            return "monthly"
        if most_common_delta == timedelta(hours=1):
            return "hourly"
        total_seconds = int(most_common_delta.total_seconds())
        if total_seconds % 3600 == 0:
            return f"{total_seconds // 3600}h"
        if total_seconds % 60 == 0:
            return f"{total_seconds // 60}m"
        return f"{total_seconds}s"

    def _generate_future_timestamps(
        self,
        *,
        history_timestamps: list[datetime],
        existing: list[datetime],
        horizon: int,
    ) -> list[datetime]:
        if len(existing) >= horizon:
            return []
        last_timestamp = existing[-1] if existing else history_timestamps[-1]
        if len(existing) >= 2:
            delta = existing[-1] - existing[-2]
        elif len(history_timestamps) >= 2:
            delta = history_timestamps[-1] - history_timestamps[-2]
        else:
            delta = timedelta(days=1)
        if delta.total_seconds() <= 0:
            delta = timedelta(days=1)
        generated: list[datetime] = []
        cursor = last_timestamp
        while len(existing) + len(generated) < horizon:
            cursor = cursor + delta
            generated.append(cursor)
        return generated

    def _get_model(self, *, settings: dict[str, Any], uses_covariates: bool) -> Any:
        model_id = str(settings.get("forecast_model_id") or _DEFAULT_MODEL_ID)
        max_context = max(1, int(settings.get("forecast_max_context") or _DEFAULT_MAX_CONTEXT))
        max_horizon = max(1, int(settings.get("forecast_max_horizon") or _DEFAULT_MAX_HORIZON))
        use_quantiles = bool(settings.get("forecast_use_quantiles", True))
        cache_key = (model_id, max_context, max_horizon, use_quantiles, uses_covariates)
        cached_model = self._model_cache.get(cache_key)
        if cached_model is not None:
            return cached_model

        timesfm = importlib.import_module("timesfm")
        try:
            torch = importlib.import_module("torch")
            if hasattr(torch, "set_float32_matmul_precision"):
                torch.set_float32_matmul_precision("high")
        except ImportError:
            pass

        model = timesfm.TimesFM_2p5_200M_torch.from_pretrained(model_id)
        model.compile(
            timesfm.ForecastConfig(
                max_context=max_context,
                max_horizon=max_horizon,
                normalize_inputs=True,
                use_continuous_quantile_head=use_quantiles,
                force_flip_invariance=True,
                infer_is_positive=False,
                fix_quantile_crossing=True,
                return_backcast=uses_covariates,
            )
        )
        self._model_cache[cache_key] = model
        return model

    def _coerce_point_series(self, value: Any) -> list[list[float]]:
        if hasattr(value, "tolist"):
            value = value.tolist()
        result: list[list[float]] = []
        for row in list(value or []):
            if hasattr(row, "tolist"):
                row = row.tolist()
            result.append([float(item) for item in list(row or [])])
        return result

    def _coerce_quantiles(self, value: Any, *, limit: int) -> dict[str, list[float]]:
        if hasattr(value, "tolist"):
            value = value.tolist()
        rows = list(value or [])
        if not rows:
            return {}
        first = rows[0]
        if hasattr(first, "tolist"):
            first = first.tolist()
        if not first:
            return {}
        matrix = [list(item.tolist() if hasattr(item, "tolist") else item) for item in list(first)]
        if not matrix:
            return {}
        width = min(len(matrix[0]), len(_DEFAULT_QUANTILE_LABELS))
        if width == 0:
            return {}
        quantiles: dict[str, list[float]] = {}
        for offset in range(width):
            label = _DEFAULT_QUANTILE_LABELS[offset]
            quantiles[label] = [float(row[offset]) for row in matrix[:limit]]
        if "mean" in quantiles:
            quantiles.pop("mean", None)
        return quantiles

    def _build_artifacts(
        self,
        *,
        dataset: _PreparedDataset,
        future_timestamps: list[datetime],
        point_forecast: list[float],
        quantile_payload: dict[str, list[float]],
        model_id: str,
        model_backend: str,
        context_used: int,
        xreg_mode: str,
    ) -> list[dict[str, Any]]:
        history_points = _downsample_points(
            [
                {"timestamp": _format_timestamp(timestamp), "value": float(value)}
                for timestamp, value in zip(dataset.history_timestamps, dataset.history_target)
            ],
            limit=160,
        )
        forecast_points = [
            {"timestamp": _format_timestamp(timestamp), "value": float(value)}
            for timestamp, value in zip(future_timestamps, point_forecast)
        ]
        quantiles = {
            label: [
                {"timestamp": forecast_points[index]["timestamp"], "value": float(value)}
                for index, value in enumerate(values[: len(forecast_points)])
            ]
            for label, values in quantile_payload.items()
        }
        uncertainty_summary = ""
        if forecast_points and "p10" in quantiles and "p90" in quantiles:
            lower = quantiles["p10"][-1]["value"]
            upper = quantiles["p90"][-1]["value"]
            uncertainty_summary = f"{_format_value(lower)} to {_format_value(upper)}"

        session_state = {
            "file_path": dataset.file_path,
            "file_name": dataset.file_name,
            "mapping": dataset.mapping.to_dict(),
            "horizon": dataset.horizon,
        }
        forecast_report = {
            "mapping": {
                **dataset.mapping.to_dict(),
                "file_path": dataset.file_path,
                "file_name": dataset.file_name,
            },
            "metadata": {
                "horizon": dataset.horizon,
                "context_used": context_used,
                "model_backend": model_backend,
                "model_id": model_id,
                "xreg_mode": xreg_mode,
                "frequency": dataset.frequency_label,
                "history_row_count": dataset.validation.history_row_count,
                "future_row_count": dataset.validation.future_row_count,
            },
            "history_points": history_points,
            "forecast_points": forecast_points,
            "quantiles": quantiles,
            "warnings": list(dataset.validation.warnings),
            "session_state": session_state,
        }

        metric_cards = {
            "metrics": [
                {"label": "Horizon", "value": dataset.horizon},
                {"label": "Context used", "value": context_used},
                {
                    "label": "Covariates",
                    "value": len(dataset.mapping.dynamic_covariates) + len(dataset.mapping.static_covariates),
                    "delta": f"{len(dataset.mapping.dynamic_covariates)} dynamic · {len(dataset.mapping.static_covariates)} static",
                },
                {"label": "Backend", "value": model_backend},
                {
                    "label": "Uncertainty",
                    "value": uncertainty_summary or "Point forecast only",
                },
            ]
        }

        return [
            {
                "id": "forecast_report",
                "type": "forecast_report",
                "summary": f"{dataset.mapping.target_column} forecast",
                "path": f"forecast/{Path(dataset.file_name).stem}.json",
                "mime_type": "application/vnd.metis.forecast+json",
                "payload": forecast_report,
            },
            {
                "id": "forecast_metric_cards",
                "type": "metric_cards",
                "summary": "Forecast metrics",
                "path": "",
                "mime_type": "application/json",
                "payload": metric_cards,
            },
        ]

    def _summarize_forecast(
        self,
        *,
        dataset: _PreparedDataset,
        point_forecast: list[float],
        quantile_payload: dict[str, list[float]],
        context_used: int,
        prompt: str,
    ) -> str:
        start_value = point_forecast[0] if point_forecast else None
        end_value = point_forecast[-1] if point_forecast else None
        last_observed = dataset.history_target[-1] if dataset.history_target else None
        trend = "flat"
        if start_value is not None and end_value is not None:
            delta = end_value - start_value
            if abs(delta) > max(abs(start_value) * 0.02, 1e-9):
                trend = "upward" if delta > 0 else "downward"

        prompt_clause = f" {prompt.strip()}" if str(prompt or "").strip() else ""
        summary = (
            f"TimesFM forecasted {dataset.horizon} step(s) for `{dataset.mapping.target_column}` using {context_used} historical point(s)."
            f"{prompt_clause}".rstrip()
        )
        range_summary = (
            f" The point forecast moves from {_format_value(start_value)} to {_format_value(end_value)}"
            f" after a last observed value of {_format_value(last_observed)}, indicating an {trend} outlook."
        )
        uncertainty_summary = ""
        if "p10" in quantile_payload and "p90" in quantile_payload and quantile_payload["p10"] and quantile_payload["p90"]:
            uncertainty_summary = (
                f" The final-step 10th-90th percentile band spans"
                f" {_format_value(quantile_payload['p10'][-1])} to {_format_value(quantile_payload['p90'][-1])}."
            )
        covariate_summary = ""
        covariate_count = len(dataset.mapping.dynamic_covariates) + len(dataset.mapping.static_covariates)
        if covariate_count > 0:
            covariate_summary = (
                f" Covariates used: {len(dataset.mapping.dynamic_covariates)} dynamic and"
                f" {len(dataset.mapping.static_covariates)} static."
            )
        return f"{summary}{range_summary}{uncertainty_summary}{covariate_summary}".strip()
