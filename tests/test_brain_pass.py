from __future__ import annotations

import sys
import types

import pytest

from metis_app.services import brain_pass


def test_resolve_tribev2_remote_repo_id_downloads_snapshot(monkeypatch, tmp_path) -> None:
    calls: dict[str, str] = {}
    snapshot_dir = tmp_path / "tribev2-snapshot"
    snapshot_dir.mkdir()
    (snapshot_dir / "config.yaml").write_text("model: stub\n", encoding="utf-8")
    (snapshot_dir / "best.ckpt").write_text("stub", encoding="utf-8")

    def fake_download(repo_id: str, cache_folder: str, checkpoint_name: str = "best.ckpt") -> str:
        calls["repo_id"] = repo_id
        calls["cache_folder"] = cache_folder
        calls["checkpoint_name"] = checkpoint_name
        return str(snapshot_dir)

    monkeypatch.setattr(brain_pass, "_download_tribev2_snapshot", fake_download)

    resolved = brain_pass._resolve_tribev2_checkpoint_dir(
        "facebook/tribev2",
        str(tmp_path / "cache"),
    )

    assert resolved == str(snapshot_dir)
    assert calls == {
        "repo_id": "facebook/tribev2",
        "cache_folder": str(tmp_path / "cache"),
        "checkpoint_name": "best.ckpt",
    }


def test_windows_posixpath_compat_temporarily_aliases_posixpath(monkeypatch) -> None:
    original_posix_path = brain_pass.pathlib.PosixPath

    monkeypatch.setattr(brain_pass.os, "name", "nt")

    with brain_pass._windows_posixpath_compat():
        assert brain_pass.pathlib.PosixPath is brain_pass.pathlib.WindowsPath

    assert brain_pass.pathlib.PosixPath is original_posix_path


def test_resolve_tribev2_whisperx_runtime_uses_cpu_safe_defaults() -> None:
    assert brain_pass._resolve_tribev2_whisperx_runtime("cpu") == ("cpu", "float32", "4")
    assert brain_pass._resolve_tribev2_whisperx_runtime("cuda:0") == ("cuda", "float16", "16")


def test_tribev2_whisperx_compat_temporarily_overrides_cpu_loader(monkeypatch) -> None:
    fake_tribev2 = types.ModuleType("tribev2")
    fake_eventstransforms = types.ModuleType("tribev2.eventstransforms")

    class FakeExtractWordsFromAudio:
        @staticmethod
        def _get_transcript_from_audio(*_args, **_kwargs):
            return "original"

    fake_eventstransforms.ExtractWordsFromAudio = FakeExtractWordsFromAudio
    monkeypatch.setitem(sys.modules, "tribev2", fake_tribev2)
    monkeypatch.setitem(sys.modules, "tribev2.eventstransforms", fake_eventstransforms)

    original_loader = FakeExtractWordsFromAudio._get_transcript_from_audio

    with brain_pass._tribev2_whisperx_compat("cpu"):
        assert FakeExtractWordsFromAudio._get_transcript_from_audio is not original_loader

    assert FakeExtractWordsFromAudio._get_transcript_from_audio is original_loader


def test_run_brain_pass_uses_native_provider_when_native_inference_succeeds(
    monkeypatch,
    tmp_path,
) -> None:
    src = tmp_path / "notes.txt"
    src.write_text(
        "Research evidence and reasoning should stay grounded to the right faculty.\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(brain_pass, "_native_tribev2_available", lambda: True)
    monkeypatch.setattr(
        brain_pass,
        "_run_native_tribev2",
        lambda **_kwargs: {
            "native_input_mode": "text",
            "top_rois": ["ifs-lh", "sts-rh"],
            "model_id": "facebook/tribev2",
        },
    )

    result = brain_pass.run_brain_pass(
        [str(src)],
        {
            "enable_brain_pass": True,
            "brain_pass_native_enabled": True,
            "brain_pass_native_text_enabled": True,
            "brain_pass_allow_fallback": True,
            "document_loader": "plain",
        },
    )

    assert result.provider == "tribev2"
    assert result.analysis["native_input_mode"] == "text"
    assert result.placement.provenance == "tribev2-text"


def test_run_brain_pass_tribev2_with_empty_top_rois_keeps_tribev2_provenance(
    monkeypatch,
    tmp_path,
) -> None:
    src = tmp_path / "notes.txt"
    src.write_text(
        "Research evidence and reasoning should stay grounded to the right faculty.\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(brain_pass, "_native_tribev2_available", lambda: True)
    monkeypatch.setattr(
        brain_pass,
        "_run_native_tribev2",
        lambda **_kwargs: {
            "native_input_mode": "text",
            "top_rois": [],
            "model_id": "facebook/tribev2",
        },
    )

    result = brain_pass.run_brain_pass(
        [str(src)],
        {
            "enable_brain_pass": True,
            "brain_pass_native_enabled": True,
            "brain_pass_native_text_enabled": True,
            "brain_pass_allow_fallback": True,
            "document_loader": "plain",
        },
    )

    assert result.provider == "tribev2"
    assert result.placement.provenance.startswith("tribev2-")


def test_run_brain_pass_records_native_error_when_native_inference_fails(
    monkeypatch,
    tmp_path,
) -> None:
    src = tmp_path / "notes.txt"
    src.write_text(
        "Research evidence and reasoning should stay grounded to the right faculty.\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(brain_pass, "_native_tribev2_available", lambda: True)

    def fail_native(**_kwargs):
        raise RuntimeError("native download failed")

    monkeypatch.setattr(brain_pass, "_run_native_tribev2", fail_native)

    result = brain_pass.run_brain_pass(
        [str(src)],
        {
            "enable_brain_pass": True,
            "brain_pass_native_enabled": True,
            "brain_pass_native_text_enabled": True,
            "brain_pass_allow_fallback": True,
            "document_loader": "plain",
        },
    )

    assert result.provider == "fallback"
    assert result.analysis["native_error"] == "native download failed"


def test_run_brain_pass_skips_native_text_when_disabled(
    monkeypatch,
    tmp_path,
) -> None:
    src = tmp_path / "notes.txt"
    src.write_text(
        "Research evidence and reasoning should stay grounded to the right faculty.\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(brain_pass, "_native_tribev2_available", lambda: True)

    def fail_if_called(**_kwargs):
        raise AssertionError("native Tribev2 should not run for text sources when explicitly disabled")

    monkeypatch.setattr(brain_pass, "_run_native_tribev2", fail_if_called)

    result = brain_pass.run_brain_pass(
        [str(src)],
        {
            "enable_brain_pass": True,
            "brain_pass_native_enabled": True,
            "brain_pass_native_text_enabled": False,
            "brain_pass_allow_fallback": True,
            "document_loader": "plain",
        },
    )

    assert result.provider == "fallback"
    assert result.analysis["native_sources_attempted"] == 0
    assert result.analysis["native_error"] == (
        "Native Tribev2 analysis for text-backed sources is disabled unless "
        "brain_pass_native_text_enabled is true."
    )


def test_run_brain_pass_uses_native_text_by_default_when_not_disabled(
    monkeypatch,
    tmp_path,
) -> None:
    src = tmp_path / "notes.txt"
    src.write_text("Research evidence and reasoning should stay grounded.\n", encoding="utf-8")

    monkeypatch.setattr(brain_pass, "_native_tribev2_available", lambda: True)
    monkeypatch.setattr(
        brain_pass,
        "_run_native_tribev2",
        lambda **_kwargs: {
            "native_input_mode": "text",
            "top_rois": ["ifs-lh"],
            "model_id": "facebook/tribev2",
        },
    )

    result = brain_pass.run_brain_pass(
        [str(src)],
        {
            "enable_brain_pass": True,
            "brain_pass_native_enabled": True,
            "brain_pass_allow_fallback": True,
            "document_loader": "plain",
        },
    )

    assert result.provider == "tribev2"
    assert result.analysis["native_input_mode"] == "text"


def test_run_brain_pass_disabled_by_setting_uses_disabled_provider_and_provenance(
    monkeypatch,
    tmp_path,
) -> None:
    src = tmp_path / "notes.txt"
    src.write_text("Any content", encoding="utf-8")

    monkeypatch.setattr(brain_pass, "_native_tribev2_available", lambda: True)

    result = brain_pass.run_brain_pass(
        [str(src)],
        {
            "enable_brain_pass": False,
            "brain_pass_native_enabled": True,
            "brain_pass_allow_fallback": True,
            "document_loader": "plain",
        },
    )

    assert result.provider == "disabled"
    assert result.placement.provenance == "disabled"


def test_run_brain_pass_native_failure_without_fallback_uses_disabled_provider_and_provenance(
    monkeypatch,
    tmp_path,
) -> None:
    src = tmp_path / "notes.txt"
    src.write_text("Any content", encoding="utf-8")

    monkeypatch.setattr(brain_pass, "_native_tribev2_available", lambda: True)

    def fail_native(**_kwargs):
        raise RuntimeError("native failed")

    monkeypatch.setattr(brain_pass, "_run_native_tribev2", fail_native)

    result = brain_pass.run_brain_pass(
        [str(src)],
        {
            "enable_brain_pass": True,
            "brain_pass_native_enabled": True,
            "brain_pass_native_text_enabled": True,
            "brain_pass_allow_fallback": False,
            "document_loader": "plain",
        },
    )

    assert result.provider == "disabled"
    assert result.placement.provenance == "disabled"


def test_resolve_tribev2_runtime_device_returns_cpu_without_accelerator(monkeypatch) -> None:
    # Simulate an environment with no GPU.
    torch = pytest.importorskip("torch", reason="torch not installed")

    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    if hasattr(torch.backends, "mps"):
        monkeypatch.setattr(torch.backends.mps, "is_available", lambda: False)

    assert brain_pass._resolve_tribev2_runtime_device("cpu") == "cpu"
    assert brain_pass._resolve_tribev2_runtime_device("auto") == "cpu"
    # Explicit CUDA without a GPU falls back to CPU.
    assert brain_pass._resolve_tribev2_runtime_device("cuda") == "cpu"
    assert brain_pass._resolve_tribev2_runtime_device("cuda:0") == "cpu"


def test_remap_tribev2_feature_devices_sets_device_on_all_extractors() -> None:
    class _FakeExtractor:
        def __init__(self, device: str = "cuda") -> None:
            self.device = device

    class _FakeData:
        text_feature = _FakeExtractor("cuda")
        audio_feature = _FakeExtractor("cuda")
        image_feature = _FakeExtractor("cuda")
        video_feature = _FakeExtractor("cuda")

    class _FakeModel:
        data = _FakeData()

    model = _FakeModel()
    brain_pass._remap_tribev2_feature_devices(model, "cpu")

    assert model.data.text_feature.device == "cpu"
    assert model.data.audio_feature.device == "cpu"
    assert model.data.image_feature.device == "cpu"
    assert model.data.video_feature.device == "cpu"


def test_remap_tribev2_feature_devices_handles_nested_sub_extractors() -> None:
    class _FakeInner:
        def __init__(self) -> None:
            self.device = "cuda"

    class _FakeExtractor:
        def __init__(self) -> None:
            self.device = "cuda"
            self.model = _FakeInner()

    class _FakeData:
        audio_feature = _FakeExtractor()

    class _FakeModel:
        data = _FakeData()

    model = _FakeModel()
    brain_pass._remap_tribev2_feature_devices(model, "mps")

    assert model.data.audio_feature.device == "mps"
    assert model.data.audio_feature.model.device == "mps"


def test_run_native_tribev2_text_uses_audio_proxy_path(monkeypatch, tmp_path) -> None:
    """Text input should be synthesised via gTTS and fed as Audio events."""
    txt = tmp_path / "doc.txt"
    txt.write_text("The quick brown fox jumps over the lazy dog.\n", encoding="utf-8")

    mp3_path = tmp_path / "fake.mp3"
    mp3_path.write_bytes(b"FAKE")

    gTTS_calls: list[dict] = []

    class _FakegTTS:
        def __init__(self, text: str, lang: str) -> None:
            gTTS_calls.append({"text": text, "lang": lang})

        def save(self, path: str) -> None:
            import pathlib
            pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
            pathlib.Path(path).write_bytes(b"FAKE")

    predict_calls: list = []

    class _FakeModel:
        def predict(self, events, *, verbose=True):
            predict_calls.append(events)
            return [], []

    monkeypatch.setattr(brain_pass, "_load_tribev2_model", lambda *_a, **_kw: _FakeModel())
    monkeypatch.setattr(brain_pass, "_synthesize_text_to_audio_windows", lambda *_a, **_kw: False)

    import sys
    import types

    # mock tribev2.eventstransforms so _tribev2_whisperx_compat can enter cleanly
    fake_tribev2_mod = types.ModuleType("tribev2")
    fake_eventstransforms = types.ModuleType("tribev2.eventstransforms")

    class _FakeExtractWordsFromAudio:
        @staticmethod
        def _get_transcript_from_audio(*_a, **_kw):
            return []

    fake_eventstransforms.ExtractWordsFromAudio = _FakeExtractWordsFromAudio  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "tribev2", fake_tribev2_mod)
    monkeypatch.setitem(sys.modules, "tribev2.eventstransforms", fake_eventstransforms)

    fake_gtts_mod = types.ModuleType("gtts")
    fake_gtts_mod.gTTS = _FakegTTS  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "gtts", fake_gtts_mod)

    fake_pandas_mod = types.ModuleType("pandas")
    fake_pandas_mod.DataFrame = lambda data: data  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pandas", fake_pandas_mod)

    fake_neuralset = types.ModuleType("neuralset")
    fake_neuralset_events = types.ModuleType("neuralset.events")
    fake_neuralset_events_utils = types.ModuleType("neuralset.events.utils")
    fake_neuralset_events_utils.standardize_events = lambda df: df  # identity  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "neuralset", fake_neuralset)
    monkeypatch.setitem(sys.modules, "neuralset.events", fake_neuralset_events)
    monkeypatch.setitem(sys.modules, "neuralset.events.utils", fake_neuralset_events_utils)

    result = brain_pass._run_native_tribev2(
        input_mode="text",
        input_path=str(txt),
        settings={
            "brain_pass_model_id": "facebook/tribev2",
            "brain_pass_cache_dir": str(tmp_path / "cache"),
            "brain_pass_device": "cpu",
        },
    )

    assert result is not None
    assert result["native_input_mode"] == "text-via-audio-proxy"
    assert len(predict_calls) == 1
    assert len(gTTS_calls) == 1


def test_text_to_audio_proxy_prefers_local_backend_without_gtts(monkeypatch, tmp_path) -> None:
    local_audio = tmp_path / "local.wav"
    local_audio.write_bytes(b"FAKE")

    monkeypatch.setattr(
        brain_pass,
        "_synthesize_text_to_audio_local",
        lambda *_args, **_kwargs: str(local_audio),
    )

    import sys
    import types

    fake_langdetect = types.ModuleType("langdetect")
    fake_langdetect.detect = lambda _text: "en"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "langdetect", fake_langdetect)

    # If gTTS gets imported in this path, the test should fail.
    if "gtts" in sys.modules:
        monkeypatch.delitem(sys.modules, "gtts", raising=False)

    result = brain_pass._text_to_audio_proxy("hello world", str(tmp_path / "cache"))

    assert result == str(local_audio)


def test_run_brain_pass_mixed_sources_attempts_native_per_source(monkeypatch, tmp_path) -> None:
    txt = tmp_path / "notes.txt"
    txt.write_text("Reasoning and evidence for decision making.", encoding="utf-8")
    audio = tmp_path / "meeting.mp3"
    audio.write_bytes(b"FAKE")

    monkeypatch.setattr(brain_pass, "_native_tribev2_available", lambda: True)

    native_calls: list[tuple[str, str]] = []

    def fake_run_native(**kwargs):
        native_calls.append((kwargs["input_mode"], kwargs["input_path"]))
        return {
            "native_input_mode": kwargs["input_mode"],
            "top_rois": ["ifs-lh"] if kwargs["input_mode"] == "text" else ["a1-rh"],
            "model_id": "facebook/tribev2",
            "timesteps": 2,
            "vertex_count": 10,
        }

    monkeypatch.setattr(brain_pass, "_run_native_tribev2", fake_run_native)

    result = brain_pass.run_brain_pass(
        [str(txt), str(audio)],
        {
            "enable_brain_pass": True,
            "brain_pass_native_enabled": True,
            "brain_pass_native_text_enabled": True,
            "brain_pass_allow_fallback": True,
            "document_loader": "plain",
        },
    )

    assert len(native_calls) == 2
    assert sorted(mode for mode, _path in native_calls) == ["audio", "text"]
    assert result.provider == "tribev2"
    assert result.analysis["native_sources_attempted"] == 2
    assert result.analysis["native_sources_used"] == 2
    assert result.analysis["native_sources_failed"] == 0
    assert result.analysis["native_input_mode"] == "mixed"
    assert set(result.analysis["top_rois"]) == {"ifs-lh", "a1-rh"}


def test_run_brain_pass_partial_native_failure_keeps_successful_sources(monkeypatch, tmp_path) -> None:
    txt = tmp_path / "report.txt"
    txt.write_text("Research and memory synthesis.", encoding="utf-8")
    audio = tmp_path / "call.mp3"
    audio.write_bytes(b"FAKE")

    monkeypatch.setattr(brain_pass, "_native_tribev2_available", lambda: True)

    def fake_run_native(**kwargs):
        if kwargs["input_mode"] == "audio":
            raise RuntimeError("audio native failed")
        return {
            "native_input_mode": kwargs["input_mode"],
            "top_rois": ["vwfa-lh"],
            "model_id": "facebook/tribev2",
            "timesteps": 1,
            "vertex_count": 10,
        }

    monkeypatch.setattr(brain_pass, "_run_native_tribev2", fake_run_native)

    result = brain_pass.run_brain_pass(
        [str(txt), str(audio)],
        {
            "enable_brain_pass": True,
            "brain_pass_native_enabled": True,
            "brain_pass_native_text_enabled": True,
            "brain_pass_allow_fallback": True,
            "document_loader": "plain",
        },
    )

    assert result.provider == "tribev2"
    assert result.analysis["native_sources_attempted"] == 2
    assert result.analysis["native_sources_used"] == 1
    assert result.analysis["native_sources_failed"] == 1
    assert len(result.analysis["native_by_source"]) == 1
    assert len(result.analysis["native_errors_by_source"]) == 1
    assert result.analysis["native_errors_by_source"][0]["error"] == "audio native failed"


def test_run_brain_pass_exposes_provenance_blend_fields(monkeypatch, tmp_path) -> None:
    src = tmp_path / "notes.txt"
    src.write_text("Evidence and analysis with strategy context.", encoding="utf-8")

    monkeypatch.setattr(brain_pass, "_native_tribev2_available", lambda: True)
    monkeypatch.setattr(
        brain_pass,
        "_run_native_tribev2",
        lambda **_kwargs: {
            "native_input_mode": "text",
            "top_rois": ["ifs-lh", "sts-rh"],
            "model_id": "facebook/tribev2",
            "timesteps": 1,
            "vertex_count": 8,
        },
    )

    result = brain_pass.run_brain_pass(
        [str(src)],
        {
            "enable_brain_pass": True,
            "brain_pass_native_enabled": True,
            "brain_pass_native_text_enabled": True,
            "brain_pass_allow_fallback": True,
            "document_loader": "plain",
        },
    )

    placement_dict = result.placement.to_dict()
    assert placement_dict["native_score"] >= 0.0
    assert placement_dict["heuristic_score"] >= 0.0
    assert isinstance(placement_dict["native_evidence"], list)
    assert isinstance(placement_dict["heuristic_evidence"], list)
    assert placement_dict["blend_mode"] in {"pure_native", "pure_fallback", "blended"}
    assert set(placement_dict["blend_weights"].keys()) == {"native", "heuristic"}
    assert isinstance(placement_dict["final_blend_explanation"], str)

    assert result.analysis["native_score"] == placement_dict["native_score"]
    assert result.analysis["heuristic_score"] == placement_dict["heuristic_score"]
    assert result.analysis["blend_mode"] == placement_dict["blend_mode"]
    assert result.analysis["blend_weights"] == placement_dict["blend_weights"]
