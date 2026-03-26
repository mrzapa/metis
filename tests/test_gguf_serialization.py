"""Tests for shared GGUF serialization logic."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from metis_app.services.gguf_serialization import (
    GgufValidationError,
    build_recommendation_summary,
    extract_caveats,
    hardware_payload_from_recommender,
    is_caveat,
    serialize_hardware_profile,
    serialize_catalog_entry,
    validate_model_path,
)


class TestIsCaveat:
    """Test caveat detection logic."""

    def test_detects_advisory_caveat(self) -> None:
        assert is_caveat("Requires advisory review")
        assert is_caveat("ADVISORY: performance may vary")

    def test_detects_bottleneck_caveat(self) -> None:
        assert is_caveat("Memory bottleneck detected")
        assert is_caveat("BOTTLENECK")

    def test_detects_insufficient_caveat(self) -> None:
        assert is_caveat("Insufficient VRAM available")

    def test_detects_limited_caveat(self) -> None:
        assert is_caveat("Limited context length")

    def test_detects_overridden_caveat(self) -> None:
        assert is_caveat("Overridden recommendation")

    def test_detects_reduced_caveat(self) -> None:
        assert is_caveat("Performance reduced")

    def test_detects_slow_caveat(self) -> None:
        assert is_caveat("Slow inference speed")

    def test_detects_spilling_caveat(self) -> None:
        assert is_caveat("Memory spilling detected")

    def test_detects_tight_caveat(self) -> None:
        assert is_caveat("Tight memory constraints")

    def test_not_caveat_for_normal_notes(self) -> None:
        assert not is_caveat("GPU: model loaded into VRAM")
        assert not is_caveat("Baseline estimated speed: 45.0 tok/s")

    def test_caveat_case_insensitive(self) -> None:
        assert is_caveat("ADVISORY")
        assert is_caveat("advisory")
        assert is_caveat("Advisory")

    def test_caveat_with_whitespace(self) -> None:
        assert is_caveat("  advisory  ")
        assert is_caveat("\nreduced\n")

    def test_caveat_none_input(self) -> None:
        assert not is_caveat(None)

    def test_caveat_empty_string(self) -> None:
        assert not is_caveat("")


class TestExtractCaveats:
    """Test caveat extraction from note lists."""

    def test_extracts_caveats_from_mixed_notes(self) -> None:
        notes = [
            "GPU: model loaded into VRAM",
            "Baseline estimated speed: 45.0 tok/s",
            "Performance will be significantly reduced",
        ]
        caveats = extract_caveats(notes)
        assert len(caveats) == 1
        assert "reduced" in caveats[0].lower()

    def test_extracts_multiple_caveats(self) -> None:
        notes = [
            "Advisory: may require optimization",
            "GPU: model loaded",
            "Memory bottleneck detected",
            "Normal note",
        ]
        caveats = extract_caveats(notes)
        assert len(caveats) == 2

    def test_extracts_empty_when_no_caveats(self) -> None:
        notes = [
            "GPU: model loaded",
            "Baseline speed: 45 tok/s",
        ]
        caveats = extract_caveats(notes)
        assert len(caveats) == 0

    def test_extracts_from_empty_list(self) -> None:
        caveats = extract_caveats([])
        assert caveats == []


class TestBuildRecommendationSummary:
    """Test recommendation summary generation."""

    def test_builds_summary_with_all_fields(self) -> None:
        entry = {
            "fit_level": "good",
            "run_mode": "gpu",
            "best_quant": "Q4_K_M",
            "recommended_context_length": 4096,
            "memory_required_gb": 4.5,
            "memory_available_gb": 24.0,
            "estimated_tps": 45.0,
        }
        summary = build_recommendation_summary(entry)
        assert "Good fit" in summary
        assert "gpu" in summary.lower()
        assert "Q4_K_M" in summary
        assert "4,096" in summary  # Formatted with comma
        assert "4.5 GB" in summary
        assert "24.0 GB" in summary
        assert "45.0 tok/s" in summary

    def test_builds_summary_with_missing_fields_uses_defaults(self) -> None:
        entry = {}
        summary = build_recommendation_summary(entry)
        assert isinstance(summary, str)
        assert len(summary) > 0
        assert "Unknown" in summary
        assert "cpu only" in summary.lower()  # Changed from "cpu_only"

    def test_builds_summary_with_underscores_replaced(self) -> None:
        entry = {
            "fit_level": "very_good",
            "run_mode": "gpu_quantized",
        }
        summary = build_recommendation_summary(entry)
        assert "_" not in summary
        assert "Very Good" in summary  # Title case applied
        assert "gpu quantized" in summary

    def test_builds_summary_context_length_minimum(self) -> None:
        entry = {
            "recommended_context_length": 128,  # Below minimum of 256
        }
        summary = build_recommendation_summary(entry)
        assert "256" in summary

    def test_builds_summary_number_formatting(self) -> None:
        entry = {
            "recommended_context_length": 4096,
            "memory_required_gb": 4.123456,
            "memory_available_gb": 24.987654,
            "estimated_tps": 45.123456,
        }
        summary = build_recommendation_summary(entry)
        assert "4,096" in summary
        assert "4.1 GB" in summary
        assert "25.0 GB" in summary
        assert "45.1 tok/s" in summary


class TestSerializeCatalogEntry:
    """Test catalog entry serialization."""

    def test_serializes_complete_entry(self) -> None:
        entry = {
            "model_name": "Qwen2.5-7B",
            "provider": "bartowski",
            "parameter_count": "7B",
            "architecture": "qwen2",
            "use_case": "chat",
            "fit_level": "good",
            "run_mode": "gpu",
            "best_quant": "Q4_K_M",
            "estimated_tps": 45.0,
            "memory_required_gb": 4.5,
            "memory_available_gb": 24.0,
            "recommended_context_length": 4096,
            "score": 88.4,
            "notes": [
                "GPU: model loaded into VRAM",
                "Baseline speed: 45.0 tok/s",
                "Performance reduced",
            ],
            "score_components": {
                "quality": 82.0,
                "speed": 100.0,
                "fit": 100.0,
                "context": 100.0,
            },
            "source_repo": "Qwen/Qwen2.5-7B-Instruct-GGUF",
            "source_provider": "bartowski",
        }

        result = serialize_catalog_entry(entry)

        assert result["model_name"] == "Qwen2.5-7B"
        assert result["provider"] == "bartowski"
        assert result["parameter_count"] == "7B"
        assert result["architecture"] == "qwen2"
        assert result["use_case"] == "chat"
        assert result["fit_level"] == "good"
        assert result["run_mode"] == "gpu"
        assert result["best_quant"] == "Q4_K_M"
        assert result["estimated_tps"] == 45.0
        assert result["memory_required_gb"] == 4.5
        assert result["memory_available_gb"] == 24.0
        assert result["recommended_context_length"] == 4096
        assert result["score"] == 88.4
        assert len(result["notes"]) == 3
        assert len(result["caveats"]) == 1  # "Performance reduced"
        assert "reduced" in result["caveats"][0].lower()
        assert "Good fit" in result["recommendation_summary"]
        assert result["score_components"]["quality"] == 82.0
        assert result["source_repo"] == "Qwen/Qwen2.5-7B-Instruct-GGUF"
        assert result["source_provider"] == "bartowski"

    def test_serializes_entry_with_missing_fields(self) -> None:
        entry = {
            "model_name": "TestModel",
        }

        result = serialize_catalog_entry(entry)

        assert result["model_name"] == "TestModel"
        assert result["provider"] == ""
        assert result["parameter_count"] == ""
        assert result["recommended_context_length"] == 2048
        assert result["estimated_tps"] == 0.0
        assert result["memory_required_gb"] == 0.0
        assert result["notes"] == []
        assert result["caveats"] == []
        assert result["score_components"] == {}

    def test_serializes_score_components_with_type_conversion(self) -> None:
        entry = {
            "score_components": {
                "quality": "82.5",  # String to float
                "speed": 100,  # int to float
                "fit": "88.0",
            },
        }

        result = serialize_catalog_entry(entry)

        assert result["score_components"]["quality"] == 82.5
        assert result["score_components"]["speed"] == 100.0
        assert result["score_components"]["fit"] == 88.0

    def test_serializes_notes_to_strings(self) -> None:
        entry = {
            "notes": [
                "String note",
                123,  # int should convert to str
            ],
        }

        result = serialize_catalog_entry(entry)

        assert result["notes"] == ["String note", "123"]
        assert all(isinstance(note, str) for note in result["notes"])

    def test_serializes_optional_numeric_fields_none_handling(self) -> None:
        entry = {
            "estimated_tps": None,
            "memory_required_gb": None,
            "score": None,
        }

        result = serialize_catalog_entry(entry)

        assert result["estimated_tps"] == 0.0
        assert result["memory_required_gb"] == 0.0
        assert result["score"] == 0.0

    def test_serializes_returns_all_required_fields(self) -> None:
        entry = {}
        result = serialize_catalog_entry(entry)

        required_fields = {
            "model_name",
            "provider",
            "parameter_count",
            "architecture",
            "use_case",
            "fit_level",
            "run_mode",
            "best_quant",
            "estimated_tps",
            "memory_required_gb",
            "memory_available_gb",
            "recommended_context_length",
            "score",
            "recommendation_summary",
            "notes",
            "caveats",
            "score_components",
            "source_repo",
            "source_provider",
        }

        assert all(field in result for field in required_fields)

    def test_serializes_dict_is_not_pydantic_model(self) -> None:
        """Ensure result is a plain dict, not a Pydantic model."""
        entry = {"model_name": "Test"}
        result = serialize_catalog_entry(entry)

        assert isinstance(result, dict)
        assert not hasattr(result, "model_dump")
        assert not hasattr(result, "model_validate")


class TestCrossFrameworkConsistency:
    """Test that FastAPI and Litestar produce identical JSON."""

    def test_fastapi_and_litestar_serialize_identically(self) -> None:
        """Verify both frameworks produce identical JSON from same input."""
        from metis_app.api.models import GgufCatalogEntryModel

        entry_dict = {
            "model_name": "Qwen2.5-7B",
            "provider": "bartowski",
            "parameter_count": "7B",
            "architecture": "qwen2",
            "use_case": "chat",
            "fit_level": "good",
            "run_mode": "gpu",
            "best_quant": "Q4_K_M",
            "estimated_tps": 45.0,
            "memory_required_gb": 4.5,
            "memory_available_gb": 24.0,
            "recommended_context_length": 4096,
            "score": 88.4,
            "notes": ["GPU: model loaded into VRAM", "Performance reduced"],
            "score_components": {"quality": 82.0, "speed": 100.0},
            "source_repo": "Qwen/Qwen2.5-7B-Instruct-GGUF",
            "source_provider": "bartowski",
        }

        # Litestar returns plain dict (shared serialization output)
        litestar_result = serialize_catalog_entry(entry_dict)

        # FastAPI wraps in Pydantic model and converts back to dict
        fastapi_pydantic = GgufCatalogEntryModel(**serialize_catalog_entry(entry_dict))
        fastapi_result = fastapi_pydantic.model_dump()

        # Both should have identical structure and values
        assert set(fastapi_result.keys()) == set(litestar_result.keys())

        for key in litestar_result.keys():
            if isinstance(litestar_result[key], (list, dict)):
                assert litestar_result[key] == fastapi_result[key]
            elif isinstance(litestar_result[key], float):
                assert abs(litestar_result[key] - fastapi_result[key]) < 0.0001
            else:
                assert litestar_result[key] == fastapi_result[key]


class TestHardwarePayloadHelpers:
    """Test shared hardware payload normalization for both route adapters."""

    def test_serialize_hardware_profile_matches_contract(self) -> None:
        hardware = MagicMock()
        hardware.total_ram_gb = 32.0
        hardware.available_ram_gb = 16.0
        hardware.total_cpu_cores = 8
        hardware.cpu_name = "Intel"
        hardware.has_gpu = True
        hardware.gpu_vram_gb = 12.0
        hardware.total_gpu_vram_gb = 12.0
        hardware.gpu_name = "RTX"
        hardware.gpu_count = 1
        hardware.unified_memory = False
        hardware.backend = "cuda"
        hardware.detected = True
        hardware.override_enabled = False
        hardware.notes = ["ok"]

        payload = serialize_hardware_profile(hardware)

        assert payload["total_ram_gb"] == 32.0
        assert payload["available_ram_gb"] == 16.0
        assert payload["total_cpu_cores"] == 8
        assert payload["has_gpu"] is True
        assert payload["gpu_name"] == "RTX"
        assert payload["backend"] == "cuda"
        assert payload["notes"] == ["ok"]

    def test_hardware_payload_from_recommender_uses_detect_hardware(self) -> None:
        hardware = MagicMock()
        hardware.total_ram_gb = 16.0
        hardware.available_ram_gb = 8.0
        hardware.total_cpu_cores = 4
        hardware.cpu_name = "CPU"
        hardware.has_gpu = False
        hardware.gpu_vram_gb = None
        hardware.total_gpu_vram_gb = None
        hardware.gpu_name = ""
        hardware.gpu_count = 0
        hardware.unified_memory = False
        hardware.backend = "cpu_x86"
        hardware.detected = True
        hardware.override_enabled = False
        hardware.notes = []

        recommender = MagicMock()
        recommender.detect_hardware.return_value = hardware

        payload = hardware_payload_from_recommender(recommender)

        recommender.detect_hardware.assert_called_once_with()
        assert payload["total_ram_gb"] == 16.0
        assert payload["has_gpu"] is False


class TestValidateModelPath:
    """Test shared GGUF model-path validation helper."""

    def test_validate_model_path_success(self, tmp_path) -> None:
        model_file = tmp_path / "Qwen2.5-7B-Q4_K_M.gguf"
        model_file.write_bytes(b"fake gguf")

        result = validate_model_path(str(model_file))

        assert result.payload["valid"] is True
        assert result.payload["path"] == str(model_file)
        assert result.payload["filename"] == "Qwen2.5-7B-Q4_K_M.gguf"
        assert result.payload["quant"] == "Q4_K_M"
        assert result.payload["is_instruct"] is False
        assert result.filename_is_conventional is True

    def test_validate_model_path_raises_for_missing(self, tmp_path) -> None:
        missing = tmp_path / "missing.gguf"

        with pytest.raises(GgufValidationError) as exc_info:
            validate_model_path(str(missing))

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()

    def test_validate_model_path_raises_for_invalid_extension(self, tmp_path) -> None:
        model_file = tmp_path / "model.bin"
        model_file.write_bytes(b"not gguf")

        with pytest.raises(GgufValidationError) as exc_info:
            validate_model_path(str(model_file))

        assert exc_info.value.status_code == 400
        assert ".gguf" in exc_info.value.detail.lower()
