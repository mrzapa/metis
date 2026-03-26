from __future__ import annotations

import pytest

from metis_app.services.local_llm_recommender import (
    CatalogModel,
    HardwareProfile,
    HuggingFaceRepoFile,
    ImportPlan,
    LocalLlmRecommenderService,
    analyze_fit,
    pick_moe_path,
    select_recommended_context,
)


def test_select_recommended_context_falls_back_from_8192_to_4096() -> None:
    model = CatalogModel(
        name="Qwen/Test-4B-Instruct",
        provider="test",
        parameter_count="4B",
        parameters_raw=4_000_000_000,
        min_ram_gb=3.0,
        recommended_ram_gb=10.0,
        min_vram_gb=4.0,
        quantization="F16",
        context_length=8192,
        use_case="chat",
        gguf_sources=[{"repo": "bartowski/test", "provider": "bartowski"}],
    )
    hardware = HardwareProfile(
        total_ram_gb=32.0,
        available_ram_gb=24.0,
        total_cpu_cores=12,
        cpu_name="Test CPU",
        has_gpu=True,
        gpu_vram_gb=5.5,
        total_gpu_vram_gb=5.5,
        gpu_name="RTX 3060",
        gpu_count=1,
        backend="cuda",
    )

    context = select_recommended_context(model, hardware, "chat")
    fit = analyze_fit(model, hardware, "chat", context)

    assert context == 4096
    assert fit.fit_level == "good"
    assert fit.best_quant == "Q8_0"


def test_pick_moe_path_uses_expert_offload() -> None:
    model = CatalogModel(
        name="DeepSeek/Test-MoE",
        provider="test",
        parameter_count="8x7B",
        parameters_raw=46_700_000_000,
        min_ram_gb=25.0,
        recommended_ram_gb=50.0,
        min_vram_gb=25.0,
        quantization="Q8_0",
        context_length=4096,
        use_case="reasoning",
        is_moe=True,
        num_experts=8,
        active_experts=2,
        active_parameters=12_900_000_000,
        gguf_sources=[{"repo": "bartowski/moe-test", "provider": "bartowski"}],
    )
    hardware = HardwareProfile(
        total_ram_gb=64.0,
        available_ram_gb=48.0,
        total_cpu_cores=16,
        cpu_name="Test CPU",
        has_gpu=True,
        gpu_vram_gb=8.0,
        total_gpu_vram_gb=8.0,
        gpu_name="RTX 3070",
        gpu_count=1,
        backend="cuda",
    )

    run_mode, mem_required, mem_available, notes = pick_moe_path(model, hardware) or ("", 0.0, 0.0, [])

    assert run_mode == "moe_offload"
    assert mem_required <= mem_available
    assert any("experts active in VRAM" in note for note in notes)


def test_detect_hardware_applies_manual_overrides(monkeypatch) -> None:
    service = LocalLlmRecommenderService()
    base = HardwareProfile(
        total_ram_gb=16.0,
        available_ram_gb=12.0,
        total_cpu_cores=8,
        cpu_name="Detected CPU",
        has_gpu=False,
        gpu_vram_gb=None,
        total_gpu_vram_gb=None,
        backend="cpu_x86",
    )
    monkeypatch.setattr(service, "_detect_hardware_profile", lambda: base)

    profile = service.detect_hardware(
        {
            "hardware_override_enabled": True,
            "hardware_override_total_ram_gb": "24",
            "hardware_override_available_ram_gb": "20",
            "hardware_override_gpu_name": "RTX Override",
            "hardware_override_gpu_vram_gb": "10",
            "hardware_override_gpu_count": "1",
            "hardware_override_backend": "cuda",
            "hardware_override_unified_memory": False,
        }
    )

    assert profile.override_enabled is True
    assert profile.total_ram_gb == 24.0
    assert profile.available_ram_gb == 20.0
    assert profile.gpu_name == "RTX Override"
    assert profile.gpu_vram_gb == 10.0
    assert profile.backend == "cuda"


def test_detect_hardware_uses_cache_until_invalidated(monkeypatch) -> None:
    service = LocalLlmRecommenderService()
    calls = {"count": 0}
    base = HardwareProfile(
        total_ram_gb=16.0,
        available_ram_gb=12.0,
        total_cpu_cores=8,
        cpu_name="Detected CPU",
        has_gpu=False,
        gpu_vram_gb=None,
        total_gpu_vram_gb=None,
        backend="cpu_x86",
    )

    def _detect() -> HardwareProfile:
        calls["count"] += 1
        return base

    monkeypatch.setattr(service, "_detect_hardware_profile", _detect)

    service.detect_hardware({})
    service.detect_hardware({})
    service.invalidate_hardware_cache()
    service.detect_hardware({})

    assert calls["count"] == 2


def test_plan_import_prefers_bartowski_and_exact_quant_instruct_file(monkeypatch, tmp_path) -> None:
    service = LocalLlmRecommenderService()
    model = CatalogModel(
        name="Qwen/Test-7B-Instruct",
        provider="test",
        parameter_count="7B",
        parameters_raw=7_000_000_000,
        min_ram_gb=5.0,
        recommended_ram_gb=10.0,
        min_vram_gb=5.0,
        quantization="Q4_K_M",
        context_length=8192,
        use_case="chat",
        gguf_sources=[
            {"repo": "unsloth/test-unsloth", "provider": "unsloth"},
            {"repo": "bartowski/test-bartowski", "provider": "bartowski"},
        ],
    )
    monkeypatch.setattr(service, "find_catalog_model", lambda _name: model)

    plan = service.plan_import(
        model_name=model.catalog_name,
        best_quant="Q4_K_M",
        fit_level="good",
        recommended_context_length=4096,
        settings={"local_gguf_models_dir": str(tmp_path)},
        repo_files=[
            HuggingFaceRepoFile("Qwen-Test-Q5_K_M.gguf", 5_000_000),
            HuggingFaceRepoFile("Qwen-Test-Instruct-Q4_K_M.gguf", 4_000_000),
            HuggingFaceRepoFile("Qwen-Test-Q4_K_M.gguf", 4_100_000),
        ],
    )

    assert plan.source_repo == "bartowski/test-bartowski"
    assert plan.filename == "Qwen-Test-Instruct-Q4_K_M.gguf"
    assert plan.expected_size_bytes == 4_000_000
    assert plan.activation_safe is True
    assert plan.manual_reason == ""
    assert plan.manual_selection_required is False
    assert plan.destination_path.endswith("Qwen-Test-Instruct-Q4_K_M.gguf")


def test_plan_import_marks_ambiguous_selection(monkeypatch, tmp_path) -> None:
    service = LocalLlmRecommenderService()
    model = CatalogModel(
        name="Qwen/Test-7B-Instruct",
        provider="test",
        parameter_count="7B",
        parameters_raw=7_000_000_000,
        min_ram_gb=5.0,
        recommended_ram_gb=10.0,
        min_vram_gb=5.0,
        quantization="Q4_K_M",
        context_length=8192,
        use_case="chat",
        gguf_sources=[{"repo": "bartowski/test-bartowski", "provider": "bartowski"}],
    )
    monkeypatch.setattr(service, "find_catalog_model", lambda _name: model)

    plan = service.plan_import(
        model_name=model.catalog_name,
        best_quant="Q4_K_M",
        fit_level="marginal",
        recommended_context_length=4096,
        settings={"local_gguf_models_dir": str(tmp_path)},
        repo_files=[
            HuggingFaceRepoFile("Qwen-Test-Chat-Q4_K_M.gguf", 4_000_000),
            HuggingFaceRepoFile("Qwen-Test-Instruct-Q4_K_M.gguf", 4_000_000),
        ],
    )

    assert plan.manual_selection_required is True
    assert "Choose" in plan.manual_reason
    assert plan.activation_safe is False


def test_list_repo_files_uses_session_cache(monkeypatch) -> None:
    service = LocalLlmRecommenderService()
    calls = {"count": 0}

    def _read_json(_url: str):
        calls["count"] += 1
        return [{"path": "model.Q4_K_M.gguf", "size": 1234}]

    monkeypatch.setattr(service, "_read_json", _read_json)

    first = service.list_repo_files("bartowski/test")
    second = service.list_repo_files("bartowski/test")
    service.invalidate_repo_cache("bartowski/test")
    third = service.list_repo_files("bartowski/test")

    assert [item.filename for item in first] == ["model.Q4_K_M.gguf"]
    assert [item.filename for item in second] == ["model.Q4_K_M.gguf"]
    assert [item.filename for item in third] == ["model.Q4_K_M.gguf"]
    assert calls["count"] == 2


class _FakeResponse:
    def __init__(self, payload: bytes, *, content_length: int | None = None) -> None:
        self._payload = payload
        self._offset = 0
        self.headers = {}
        if content_length is not None:
            self.headers["Content-Length"] = str(content_length)

    def read(self, size: int) -> bytes:
        start = self._offset
        end = min(start + size, len(self._payload))
        self._offset = end
        return self._payload[start:end]

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *_args) -> None:
        return None


class _CancelledToken:
    cancelled = True


def test_download_import_skips_existing_matching_file(monkeypatch, tmp_path) -> None:
    service = LocalLlmRecommenderService()
    destination = tmp_path / "model.Q4_K_M.gguf"
    destination.write_bytes(b"existing")
    plan = ImportPlan(
        source_repo="bartowski/test",
        source_provider="bartowski",
        filename=destination.name,
        destination_path=str(destination),
        registry_metadata={},
        expected_size_bytes=len(b"existing"),
    )
    monkeypatch.setattr(
        "metis_app.services.local_llm_recommender.request.urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("network should not be used")),
    )

    result = service.download_import(plan)

    assert result == destination
    assert destination.read_bytes() == b"existing"


def test_download_import_is_atomic_and_cleans_partial_on_failure(monkeypatch, tmp_path) -> None:
    service = LocalLlmRecommenderService()
    destination = tmp_path / "model.Q4_K_M.gguf"
    destination.write_bytes(b"old")
    plan = ImportPlan(
        source_repo="bartowski/test",
        source_provider="bartowski",
        filename=destination.name,
        destination_path=str(destination),
        registry_metadata={},
        expected_size_bytes=10,
    )
    monkeypatch.setattr(
        "metis_app.services.local_llm_recommender.request.urlopen",
        lambda *_args, **_kwargs: _FakeResponse(b"short", content_length=10),
    )

    with pytest.raises(ValueError):
        service.download_import(plan)

    assert destination.read_bytes() == b"old"
    assert not (tmp_path / "model.Q4_K_M.gguf.part").exists()


def test_download_import_cleans_partial_on_cancel(monkeypatch, tmp_path) -> None:
    service = LocalLlmRecommenderService()
    destination = tmp_path / "model.Q4_K_M.gguf"
    plan = ImportPlan(
        source_repo="bartowski/test",
        source_provider="bartowski",
        filename=destination.name,
        destination_path=str(destination),
        registry_metadata={},
        expected_size_bytes=8,
    )
    monkeypatch.setattr(
        "metis_app.services.local_llm_recommender.request.urlopen",
        lambda *_args, **_kwargs: _FakeResponse(b"abcdefgh", content_length=8),
    )

    with pytest.raises(InterruptedError):
        service.download_import(plan, cancel_token=_CancelledToken())

    assert not destination.exists()
    assert not (tmp_path / "model.Q4_K_M.gguf.part").exists()
