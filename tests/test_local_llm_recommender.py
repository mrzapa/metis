from __future__ import annotations

from axiom_app.services.local_llm_recommender import (
    CatalogModel,
    HardwareProfile,
    HuggingFaceRepoFile,
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
    assert plan.manual_selection_required is False
    assert plan.destination_path.endswith("Qwen-Test-Instruct-Q4_K_M.gguf")
