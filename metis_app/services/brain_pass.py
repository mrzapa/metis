"""Brain-inspired normalization and placement helpers for constellation uploads.

The first implementation keeps the pipeline lightweight:

* Native TRIBE v2 is attempted when the dependency is installed and the
  normalized upload can be expressed as text/audio/video.
* Otherwise METIS falls back to a deterministic placement heuristic backed by
  modality priors, extracted text, and document structure signals.

The output is designed to be persisted inside an index bundle so future UI
surfaces can explain why a source was filed into a particular faculty.
"""

from __future__ import annotations

from contextlib import ExitStack, contextmanager, redirect_stderr, redirect_stdout
from dataclasses import dataclass, field
from functools import lru_cache
import hashlib
import io
import logging
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Callable
import warnings

from metis_app.utils.document_loader import load_document

_LOG = logging.getLogger(__name__)

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}

_TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".markdown",
    ".rst",
    ".csv",
    ".json",
    ".yaml",
    ".yml",
    ".xml",
}
_DOCUMENT_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".ppt",
    ".pptx",
    ".xls",
    ".xlsx",
    ".html",
    ".htm",
    ".epub",
    ".eml",
    ".msg",
}
_IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".tiff",
    ".tif",
    ".bmp",
    ".webp",
    ".gif",
}
_AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac"}
_VIDEO_EXTENSIONS = {".mp4", ".avi", ".mkv", ".mov", ".webm", ".m4v"}

_FACULTY_IDS = (
    "autonomy",
    "emergence",
    "knowledge",
    "memory",
    "perception",
    "personality",
    "reasoning",
    "skills",
    "strategy",
    "synthesis",
    "values",
)

_FACULTY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "autonomy": ("agent", "autonomous", "independent", "self-directed"),
    "emergence": ("emergence", "novel", "adapt", "complexity", "discovery"),
    "knowledge": ("research", "study", "paper", "evidence", "reference", "document", "report"),
    "memory": ("history", "archive", "timeline", "notes", "transcript", "remember", "record"),
    "perception": ("image", "visual", "video", "audio", "sound", "scene", "observe", "sensory"),
    "personality": ("tone", "voice", "character", "emotion", "style"),
    "reasoning": ("analysis", "reason", "logic", "argument", "proof", "explain", "because"),
    "skills": ("guide", "tutorial", "workflow", "instructions", "implementation", "recipe", "step"),
    "strategy": ("plan", "roadmap", "strategy", "goal", "priorit", "objective"),
    "synthesis": ("summary", "compare", "combine", "integrate", "multimodal", "overview", "bridge"),
    "values": ("ethic", "policy", "principle", "safety", "preference", "constraint"),
}

_ROI_HINTS: dict[str, tuple[str, ...]] = {
    "perception": ("visual", "motion", "occipital", "v1", "v2", "v3", "v4", "auditory", "a1", "a5"),
    "knowledge": ("language", "word", "semantic", "vwfa", "sts", "temporal"),
    "memory": ("hippocamp", "parahippocamp", "pha"),
    "reasoning": ("broca", "ifj", "ifs", "prefrontal", "44", "45"),
    "synthesis": ("default", "tpj", "mtg", "multisensory", "integration"),
}


def _parse_boolish(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in _TRUE_VALUES:
            return True
        if lowered in _FALSE_VALUES:
            return False
    if value is None:
        return default
    return bool(value)


def detect_source_modality(path: str | pathlib.Path) -> str:
    suffix = pathlib.Path(path).suffix.lower()
    if suffix in _TEXT_EXTENSIONS:
        return "text"
    if suffix in _DOCUMENT_EXTENSIONS:
        return "document"
    if suffix in _IMAGE_EXTENSIONS:
        return "image"
    if suffix in _AUDIO_EXTENSIONS:
        return "audio"
    if suffix in _VIDEO_EXTENSIONS:
        return "video"
    return "unknown"


def _safe_excerpt(text: str, limit: int = 180) -> str:
    compact = " ".join(str(text or "").split())
    return compact[:limit]


def _looks_like_extracted_text(text: str) -> bool:
    stripped = str(text or "").strip()
    if len(stripped) < 12:
        return False
    sample = stripped[:4000]
    printable = sum(1 for char in sample if char.isprintable() or char in "\n\r\t")
    alpha = sum(1 for char in sample if char.isalpha())
    printable_ratio = printable / max(1, len(sample))
    alpha_ratio = alpha / max(1, len(sample))
    return printable_ratio >= 0.75 and alpha_ratio >= 0.05


def _placeholder_text(source_path: pathlib.Path, modality: str, reason: str) -> str:
    stem = source_path.stem.replace("_", " ").replace("-", " ").strip() or source_path.name
    return (
        f"Uploaded {modality} source '{source_path.name}'. "
        f"Working title: {stem}. {reason}"
    )


def _brain_pass_temp_dir() -> pathlib.Path:
    root = pathlib.Path(tempfile.gettempdir()) / "metis_brain_pass"
    root.mkdir(parents=True, exist_ok=True)
    return root


@contextmanager
def _temporary_env(overrides: dict[str, str]) -> None:
    original = {key: os.environ.get(key) for key in overrides}
    for key, value in overrides.items():
        os.environ[key] = value
    try:
        yield
    finally:
        for key, previous in original.items():
            if previous is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = previous


@contextmanager
def _quiet_tribev2_runtime() -> None:
    logger_names = (
        "huggingface_hub",
        "huggingface_hub.file_download",
        "huggingface_hub.utils._http",
        "neuralset",
        "neuralset.extractors.base",
        "tribev2",
        "tribev2.demo_utils",
        "tribev2.main",
    )
    sink = io.StringIO()
    levels: dict[str, int] = {}
    with ExitStack() as stack:
        stack.enter_context(_temporary_env({"HF_HUB_DISABLE_PROGRESS_BARS": "1"}))
        stack.enter_context(warnings.catch_warnings())
        warnings.filterwarnings("ignore", message=r".*event_types has not been set.*")
        warnings.filterwarnings("ignore", message=r".*torch\.cuda\.amp\.autocast.*deprecated.*")
        warnings.filterwarnings("ignore", message=r".*DataLoader will create .* worker processes.*")
        warnings.filterwarnings("ignore", message=r".*unauthenticated requests to the HF Hub.*")
        stack.enter_context(redirect_stdout(sink))
        stack.enter_context(redirect_stderr(sink))
        for name in logger_names:
            logger = logging.getLogger(name)
            levels[name] = logger.level
            logger.setLevel(logging.ERROR)
        try:
            yield
        finally:
            for name, level in levels.items():
                logging.getLogger(name).setLevel(level)


def _write_text_proxy(source_path: pathlib.Path, text: str) -> str:
    digest = hashlib.sha1(
        f"{source_path.resolve()}::{len(text)}::{source_path.stat().st_mtime if source_path.exists() else 0}".encode(
            "utf-8",
            errors="ignore",
        )
    ).hexdigest()[:12]
    target = _brain_pass_temp_dir() / f"{source_path.stem}-{digest}.txt"
    target.write_text(text, encoding="utf-8")
    return str(target)


def _download_tribev2_snapshot(
    repo_id: str,
    cache_folder: str,
    checkpoint_name: str = "best.ckpt",
) -> str:
    from huggingface_hub import snapshot_download

    snapshot_kwargs: dict[str, Any] = {
        "repo_id": repo_id,
        "allow_patterns": ["config.yaml", checkpoint_name],
    }
    if cache_folder:
        snapshot_kwargs["cache_dir"] = str(pathlib.Path(cache_folder).expanduser())
    with _quiet_tribev2_runtime():
        return str(snapshot_download(**snapshot_kwargs))


def _looks_like_remote_tribev2_model(model_id: str) -> bool:
    model_ref = str(model_id or "").strip()
    if not model_ref:
        return False
    if "\\" in model_ref or model_ref.startswith((".", "~")) or "://" in model_ref:
        return False
    return len([part for part in model_ref.split("/") if part]) == 2


def _resolve_tribev2_checkpoint_dir(
    model_id: str,
    cache_folder: str,
    checkpoint_name: str = "best.ckpt",
) -> str:
    model_ref = str(model_id or "").strip()
    if not model_ref:
        return model_ref

    candidate = pathlib.Path(model_ref)
    if candidate.exists():
        return str(candidate)

    if _looks_like_remote_tribev2_model(model_ref):
        return _download_tribev2_snapshot(
            model_ref,
            cache_folder,
            checkpoint_name=checkpoint_name,
        )

    return model_ref


def _resolve_tribev2_runtime_device(requested: str) -> str:
    """Return a validated torch device string, checking real hardware availability.

    Handles all known backends — CUDA/NVIDIA, MPS/Apple Silicon, XPU/Intel,
    and CPU.  ROCm/AMD uses PyTorch's ``"cuda"`` string.  Falls back to
    ``"cpu"`` whenever the requested backend is unavailable.
    """
    req = str(requested or "auto").strip().lower()

    def _has_cuda() -> bool:
        try:
            import torch
            return bool(torch.cuda.is_available())
        except Exception:  # noqa: BLE001
            return False

    def _has_mps() -> bool:
        try:
            import torch
            return hasattr(torch.backends, "mps") and bool(torch.backends.mps.is_available())
        except Exception:  # noqa: BLE001
            return False

    def _has_xpu() -> bool:
        try:
            import torch
            return hasattr(torch, "xpu") and bool(torch.xpu.is_available())
        except Exception:  # noqa: BLE001
            return False

    if req == "cpu":
        return "cpu"
    if req in {"cuda", "gpu"} or req.startswith("cuda:"):
        return req if _has_cuda() else "cpu"
    if req == "mps":
        return "mps" if _has_mps() else "cpu"
    if req == "xpu" or req.startswith("xpu:"):
        return "xpu" if _has_xpu() else "cpu"
    # ROCm/AMD — PyTorch surfaces ROCm under the CUDA API
    if req in {"rocm", "hip"}:
        return "cuda" if _has_cuda() else "cpu"
    if req == "auto":
        if _has_cuda():
            return "cuda"
        if _has_mps():
            return "mps"
        if _has_xpu():
            return "xpu"
        return "cpu"
    # Unknown / future backend — pass through and let torch raise at usage time
    return req


def _resolve_tribev2_whisperx_runtime(device: str) -> tuple[str, str, str]:
    requested = str(device or "auto").strip().lower()
    if requested in {"cuda", "cuda:0", "gpu"} or requested.startswith("cuda:"):
        return ("cuda", "float16", "16")
    if requested == "cpu":
        return ("cpu", "float32", "4")
    if requested not in {"", "auto"}:
        # MPS, XPU, ROCm, etc. — whisperx CPU-safe settings
        return ("cpu", "float32", "4")

    # "auto" — delegate to the portable multi-backend resolver
    resolved = _resolve_tribev2_runtime_device("auto")
    if resolved.startswith("cuda"):
        return ("cuda", "float16", "16")
    return ("cpu", "float32", "4")


def _get_bundled_ffmpeg_env() -> dict[str, str]:
    """Return an os.environ copy with a bundled ffmpeg binary on PATH.

    ``imageio-ffmpeg`` ships a static FFmpeg binary that works on Windows
    without a system-wide installation.  We copy it as ``ffmpeg.exe`` into
    a temp shim directory so that any subprocess that calls ``ffmpeg`` by
    name (e.g. whisperx via ``subprocess.run(["ffmpeg", ...])``) finds it
    without requiring ``shell=True``.  On POSIX systems a ``ffmpeg`` symlink
    is created instead.
    """
    env = {key: value for key, value in os.environ.items() if key != "MPLBACKEND"}
    try:
        import imageio_ffmpeg  # type: ignore[import-untyped]

        ffmpeg_exe = str(imageio_ffmpeg.get_ffmpeg_exe())
        shim_dir = _brain_pass_temp_dir() / "ffmpeg_shim"
        shim_dir.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            dest = shim_dir / "ffmpeg.exe"
            if not dest.exists():
                import shutil
                shutil.copy2(ffmpeg_exe, dest)
        else:
            dest = shim_dir / "ffmpeg"
            if not dest.exists():
                dest.symlink_to(ffmpeg_exe)
        env["PATH"] = f"{shim_dir};{env.get('PATH', '')}"
        _LOG.debug("Tribev2 whisperx will use bundled FFmpeg: %s -> %s", dest, ffmpeg_exe)
    except Exception as exc:  # noqa: BLE001
        _LOG.debug("imageio_ffmpeg not available for FFmpeg shim: %s", exc)
    return env


@contextmanager
def _ffmpeg_on_path():
    """Temporarily inject the bundled ffmpeg binary into the live ``os.environ['PATH']``.

    On Windows, ``subprocess.Popen`` with ``shell=False`` uses the *calling*
    process's PATH (from ``os.environ``) to locate executables, not the PATH
    from an explicit ``env=`` argument.  Modifying ``os.environ`` in-place is
    therefore the only reliable way to make the shim visible to the entire
    subprocess chain (uvx → whisperx Python → ffmpeg).
    """
    env_copy = _get_bundled_ffmpeg_env()
    shim_dir = env_copy.get("PATH", "").split(os.pathsep)[0]
    # No shim available — nothing to inject
    path_key = next((k for k in os.environ if k.upper() == "PATH"), "PATH")
    original_path = os.environ.get(path_key, "")
    if shim_dir and shim_dir not in original_path:
        os.environ[path_key] = shim_dir + os.pathsep + original_path
        _LOG.debug("Tribev2: injected ffmpeg shim into os.environ[%s]", path_key)
        try:
            yield
        finally:
            os.environ[path_key] = original_path
    else:
        yield


def _build_tribev2_transcript_loader(
    *,
    whisperx_device: str,
    compute_type: str,
    batch_size: str,
):
    def _get_transcript_from_audio(wav_filename: pathlib.Path, language: str):
        import json
        import subprocess
        import tempfile

        import pandas as pd

        language_codes = {
            "english": "en",
            "french": "fr",
            "spanish": "es",
            "dutch": "nl",
            "chinese": "zh",
        }
        if language not in language_codes:
            raise ValueError(f"Language {language} not supported")

        with tempfile.TemporaryDirectory() as output_dir:
            _LOG.info(
                "Running whisperx via uvx with %s/%s settings for Tribev2 compatibility...",
                whisperx_device,
                compute_type,
            )
            cmd = [
                "uvx",
                "whisperx",
                str(wav_filename),
                "--model",
                "large-v3",
                "--language",
                language_codes[language],
                "--device",
                whisperx_device,
                "--compute_type",
                compute_type,
                "--batch_size",
                batch_size,
                "--align_model",
                "WAV2VEC2_ASR_LARGE_LV60K_960H" if language == "english" else "",
                "--output_dir",
                output_dir,
                "--output_format",
                "json",
            ]
            cmd = [arg for arg in cmd if arg]
            with _ffmpeg_on_path():
                result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(f"whisperx failed:\n{result.stderr}")

            json_path = pathlib.Path(output_dir) / f"{wav_filename.stem}.json"
            transcript = json.loads(json_path.read_text(encoding="utf-8"))

        words = []
        for index, segment in enumerate(transcript["segments"]):
            sentence = str(segment.get("text") or "").replace('"', "")
            for word in segment.get("words") or []:
                if "start" not in word or "end" not in word:
                    continue
                words.append(
                    {
                        "text": str(word.get("word") or "").replace('"', ""),
                        "start": word["start"],
                        "duration": word["end"] - word["start"],
                        "sequence_id": index,
                        "sentence": sentence,
                    }
                )

        return pd.DataFrame(words)

    return _get_transcript_from_audio


@contextmanager
def _windows_posixpath_compat():
    if os.name != "nt":
        yield
        return

    original_posix_path = pathlib.PosixPath
    pathlib.PosixPath = pathlib.WindowsPath  # type: ignore[assignment]
    try:
        yield
    finally:
        pathlib.PosixPath = original_posix_path  # type: ignore[assignment]


@contextmanager
def _tribev2_whisperx_compat(device: str):
    whisperx_device, compute_type, batch_size = _resolve_tribev2_whisperx_runtime(device)
    if whisperx_device != "cpu":
        yield
        return

    from tribev2.eventstransforms import ExtractWordsFromAudio

    original_loader = ExtractWordsFromAudio._get_transcript_from_audio
    ExtractWordsFromAudio._get_transcript_from_audio = staticmethod(
        _build_tribev2_transcript_loader(
            whisperx_device=whisperx_device,
            compute_type=compute_type,
            batch_size=batch_size,
        )
    )
    try:
        yield
    finally:
        ExtractWordsFromAudio._get_transcript_from_audio = original_loader


def _remap_tribev2_feature_devices(model: Any, device: str) -> None:
    """Override the per-extractor device values baked into a Tribev2 checkpoint.

    Tribev2 checkpoint configs hard-code ``device: cuda`` for every feature
    extractor.  This function walks all known sub-extractors on ``model.data``
    and patches their ``.device`` attribute so that ``model.predict()`` moves
    tensors to *device* regardless of what the checkpoint originally pinned.

    Accessing a feature extractor attribute on ``model.data`` may trigger lazy
    initialisation of its underlying HuggingFace model (including a network
    download).  Gated extractors (e.g. Llama) will raise a ``401`` error at
    that point.  Each extractor is wrapped in its own try/except so that a
    single unavailable extractor cannot prevent the others from being remapped.
    """
    data = getattr(model, "data", None)
    if data is None:
        return
    # audio/image/video first so a gated text_feature 401 cannot block them
    for attr in ("audio_feature", "image_feature", "video_feature", "text_feature"):
        try:
            extractor = getattr(data, attr, None)
            if extractor is None:
                continue
            if hasattr(extractor, "device"):
                extractor.device = device
                _LOG.debug("Remapped Tribev2 %s.device \u2192 %s", attr, device)
            # Some extractors nest a sub-extractor (e.g. .image, .model)
            for sub_attr in ("image", "model", "audio", "text"):
                try:
                    sub = getattr(extractor, sub_attr, None)
                    if sub is not None and hasattr(sub, "device"):
                        sub.device = device
                        _LOG.debug("Remapped Tribev2 %s.%s.device \u2192 %s", attr, sub_attr, device)
                except Exception:  # noqa: BLE001
                    pass
        except Exception as exc:  # noqa: BLE001
            _LOG.debug(
                "Skipping device remap for Tribev2 %s (extractor unavailable or gated): %s",
                attr,
                exc,
            )


def _native_tribev2_available() -> bool:
    try:
        with _quiet_tribev2_runtime():
            from tribev2 import TribeModel  # noqa: F401
    except Exception:
        return False
    return True


@lru_cache(maxsize=2)
def _load_tribev2_model(model_id: str, cache_folder: str, device: str):
    resolved = _resolve_tribev2_runtime_device(device)
    config_update = {
        "data.num_workers": 0,
        "data.subject_id.event_types": ["Audio", "Video", "Text", "Word"],
        "data.subject_id.treat_missing_as_separate_class": True,
    }
    with _quiet_tribev2_runtime():
        from tribev2 import TribeModel

    checkpoint_dir = _resolve_tribev2_checkpoint_dir(model_id, cache_folder)
    with _quiet_tribev2_runtime(), _windows_posixpath_compat():
        model = TribeModel.from_pretrained(
            checkpoint_dir,
            cache_folder=cache_folder,
            device=resolved,
            config_update=config_update,
        )
    _remap_tribev2_feature_devices(model, resolved)
    return model


@dataclass(slots=True)
class NormalizedSource:
    source_path: str
    source_name: str
    source_modality: str
    tribev2_input_modality: str
    normalized_path: str = ""
    extracted_text: str = ""
    extraction_method: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_metadata_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "source_name": self.source_name,
            "source_modality": self.source_modality,
            "tribev2_input_modality": self.tribev2_input_modality,
            "normalized_path": self.normalized_path,
            "extraction_method": self.extraction_method,
            "text_preview": _safe_excerpt(self.extracted_text),
            "text_length": len(self.extracted_text or ""),
            "metadata": dict(self.metadata or {}),
        }


@dataclass(slots=True)
class PlacementRecommendation:
    faculty_id: str
    confidence: float
    rationale: str
    provenance: str
    secondary_faculty_id: str = ""
    evidence: list[str] = field(default_factory=list)
    native_score: float = 0.0
    heuristic_score: float = 0.0
    native_evidence: list[str] = field(default_factory=list)
    heuristic_evidence: list[str] = field(default_factory=list)
    native_sources_used: list[str] = field(default_factory=list)
    blend_mode: str = "pure_fallback"
    blend_weights: dict[str, float] = field(default_factory=dict)
    final_blend_explanation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "faculty_id": self.faculty_id,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "provenance": self.provenance,
            "secondary_faculty_id": self.secondary_faculty_id,
            "evidence": list(self.evidence),
            "native_score": self.native_score,
            "heuristic_score": self.heuristic_score,
            "native_evidence": list(self.native_evidence),
            "heuristic_evidence": list(self.heuristic_evidence),
            "native_sources_used": list(self.native_sources_used),
            "blend_mode": self.blend_mode,
            "blend_weights": dict(self.blend_weights or {}),
            "final_blend_explanation": self.final_blend_explanation,
        }


@dataclass(slots=True)
class BrainPassResult:
    provider: str
    native_available: bool
    source_modalities: list[str]
    normalized_sources: list[NormalizedSource]
    placement: PlacementRecommendation
    index_text_by_source: dict[str, str] = field(default_factory=dict)
    analysis: dict[str, Any] = field(default_factory=dict)

    def to_metadata(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "native_available": self.native_available,
            "source_modalities": list(self.source_modalities),
            "normalized_sources": [item.to_metadata_dict() for item in self.normalized_sources],
            "placement": self.placement.to_dict(),
            "analysis": dict(self.analysis or {}),
        }


def _normalize_text_backed_source(
    source_path: pathlib.Path,
    modality: str,
    *,
    use_kreuzberg: bool,
    native_text_enabled: bool,
) -> NormalizedSource:
    extracted_text = ""
    extraction_method = ""
    try:
        extracted_text = load_document(source_path, use_kreuzberg=use_kreuzberg)
        if _looks_like_extracted_text(extracted_text):
            extraction_method = "kreuzberg" if use_kreuzberg else "plain_loader"
    except Exception as exc:  # noqa: BLE001
        _LOG.debug("Brain pass text extraction failed for %s: %s", source_path, exc)

    if not _looks_like_extracted_text(extracted_text):
        extracted_text = _placeholder_text(
            source_path,
            modality,
            "Extracted text was unavailable, so METIS stored a lightweight placeholder for indexing.",
        )
        extraction_method = "placeholder"

    tribev2_input_modality = "text" if native_text_enabled and extracted_text.strip() else "none"
    normalized_path = ""
    if tribev2_input_modality == "text":
        normalized_path = (
            str(source_path)
            if source_path.suffix.lower() == ".txt"
            else _write_text_proxy(source_path, extracted_text)
        )

    return NormalizedSource(
        source_path=str(source_path),
        source_name=source_path.name,
        source_modality=modality,
        tribev2_input_modality=tribev2_input_modality,
        normalized_path=normalized_path,
        extracted_text=extracted_text,
        extraction_method=extraction_method,
        metadata={
            "uses_kreuzberg": bool(use_kreuzberg),
        },
    )


def _normalize_media_source(
    source_path: pathlib.Path,
    modality: str,
    *,
    native_available: bool,
) -> NormalizedSource:
    extracted_text = _placeholder_text(
        source_path,
        modality,
        (
            "Direct Tribev2 analysis is unavailable on this machine."
            if not native_available
            else "Direct Tribev2 analysis will use the raw media; METIS stores a lightweight placeholder for retrieval."
        ),
    )
    return NormalizedSource(
        source_path=str(source_path),
        source_name=source_path.name,
        source_modality=modality,
        tribev2_input_modality=modality if native_available else "none",
        normalized_path=str(source_path) if native_available else "",
        extracted_text=extracted_text,
        extraction_method="raw_media" if native_available else "placeholder",
    )


def _normalize_unknown_source(source_path: pathlib.Path) -> NormalizedSource:
    extracted_text = _placeholder_text(
        source_path,
        "unknown",
        "METIS could not classify the file type, so it indexed a lightweight description instead.",
    )
    return NormalizedSource(
        source_path=str(source_path),
        source_name=source_path.name,
        source_modality="unknown",
        tribev2_input_modality="none",
        extracted_text=extracted_text,
        extraction_method="placeholder",
    )


def _normalize_source(
    source_path: pathlib.Path,
    *,
    use_kreuzberg: bool,
    native_available: bool,
    native_text_enabled: bool,
) -> NormalizedSource:
    modality = detect_source_modality(source_path)
    if modality in {"text", "document", "image"}:
        return _normalize_text_backed_source(
            source_path,
            modality,
            use_kreuzberg=use_kreuzberg,
            native_text_enabled=native_text_enabled,
        )
    if modality in {"audio", "video"}:
        return _normalize_media_source(
            source_path,
            modality,
            native_available=native_available,
        )
    return _normalize_unknown_source(source_path)


def _has_text_backed_native_candidates(normalized_sources: list[NormalizedSource]) -> bool:
    return any(
        item.source_modality in {"text", "document", "image"}
        and bool((item.extracted_text or "").strip())
        for item in normalized_sources
    )


def _native_inputs_by_source(
    normalized_sources: list[NormalizedSource],
) -> list[tuple[NormalizedSource, str, str]]:
    candidates: list[tuple[NormalizedSource, str, str]] = []
    for item in normalized_sources:
        input_mode = item.tribev2_input_modality
        if input_mode == "none":
            continue
        input_path = item.normalized_path or item.source_path
        if not input_path:
            continue
        candidates.append((item, input_mode, input_path))
    return candidates


def _aggregate_native_analyses(native_results: list[dict[str, Any]]) -> dict[str, Any]:
    if not native_results:
        return {"native_input_mode": "", "top_rois": []}

    top_rois: list[str] = []
    seen: set[str] = set()
    input_modes: list[str] = []
    timesteps = 0
    vertex_count = 0
    model_id = ""
    coherence_accum: dict[str, list[float]] = {}
    fingerprint_accum: dict[int, list[float]] = {}
    for result in native_results:
        mode = str(result.get("native_input_mode") or "")
        if mode:
            input_modes.append(mode)
        model_id = str(result.get("model_id") or model_id)
        timesteps += int(result.get("timesteps") or 0)
        vertex_count = max(vertex_count, int(result.get("vertex_count") or 0))
        for roi in result.get("top_rois") or []:
            roi_text = str(roi)
            if roi_text and roi_text not in seen:
                seen.add(roi_text)
                top_rois.append(roi_text)
        coherence = result.get("coherence") or {}
        if isinstance(coherence, dict):
            for key, value in coherence.items():
                if isinstance(value, (int, float)):
                    coherence_accum.setdefault(key, []).append(float(value))
        fingerprint = result.get("fingerprint") or {}
        if isinstance(fingerprint, dict):
            for channel, amp in fingerprint.items():
                try:
                    fingerprint_accum.setdefault(int(channel), []).append(float(amp))
                except (TypeError, ValueError):
                    continue

    unique_modes = {mode for mode in input_modes if mode}
    if len(unique_modes) == 1:
        native_input_mode = next(iter(unique_modes))
    elif unique_modes:
        native_input_mode = "mixed"
    else:
        native_input_mode = ""

    coherence_summary = {
        key: (sum(values) / len(values)) if values else 0.0
        for key, values in coherence_accum.items()
    } if coherence_accum else {}
    fingerprint_summary = {
        channel: sum(values) / len(values)
        for channel, values in fingerprint_accum.items()
        if values
    }

    return {
        "native_input_mode": native_input_mode,
        "top_rois": top_rois,
        "model_id": model_id,
        "timesteps": timesteps,
        "vertex_count": vertex_count,
        "native_sources_used": len(native_results),
        "coherence": coherence_summary,
        "fingerprint": fingerprint_summary,
    }


def _synthesize_text_to_audio_windows(text: str, target_path: pathlib.Path) -> bool:
    if sys.platform != "win32":
        return False

    shell = shutil.which("powershell") or shutil.which("pwsh")
    if not shell:
        return False

    target_path.parent.mkdir(parents=True, exist_ok=True)
    encoded_text = text.encode("utf-8").hex()
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$target = $args[0]; "
        "$hex = $args[1]; "
        "$bytes = for ($i = 0; $i -lt $hex.Length; $i += 2) { [Convert]::ToByte($hex.Substring($i, 2), 16) }; "
        "$text = [System.Text.Encoding]::UTF8.GetString($bytes); "
        "$voice = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "try { $voice.SetOutputToWaveFile($target); $voice.Speak($text) } finally { $voice.Dispose() }"
    )

    try:
        completed = subprocess.run(
            [shell, "-NoProfile", "-Command", script, str(target_path), encoded_text],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception as exc:  # noqa: BLE001
        _LOG.debug("Windows system TTS unavailable for Tribev2 proxy audio: %s", exc)
        return False

    return completed.returncode == 0 and target_path.exists() and target_path.stat().st_size > 0


def _synthesize_text_to_audio_linux(text: str, target_path: pathlib.Path) -> bool:
    if not sys.platform.startswith("linux"):
        return False

    for exe in ("espeak-ng", "espeak"):
        bin_path = shutil.which(exe)
        if not bin_path:
            continue
        target_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            completed = subprocess.run(
                [bin_path, "-w", str(target_path), text],
                check=True,
                capture_output=True,
                text=True,
            )
        except Exception as exc:  # noqa: BLE001
            _LOG.debug("%s unavailable for Tribev2 proxy audio: %s", exe, exc)
            continue
        if completed.returncode == 0 and target_path.exists() and target_path.stat().st_size > 0:
            return True
    return False


def _synthesize_text_to_audio_macos(text: str, target_path: pathlib.Path) -> bool:
    if sys.platform != "darwin":
        return False

    say_path = shutil.which("say")
    if not say_path:
        return False

    target_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        completed = subprocess.run(
            [say_path, "-o", str(target_path), text],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception as exc:  # noqa: BLE001
        _LOG.debug("macOS say unavailable for Tribev2 proxy audio: %s", exc)
        return False

    return completed.returncode == 0 and target_path.exists() and target_path.stat().st_size > 0


def _synthesize_text_to_audio_pyttsx3(text: str, target_path: pathlib.Path) -> bool:
    try:
        import pyttsx3  # type: ignore[import-not-found]
    except Exception:
        return False

    target_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        engine = pyttsx3.init()
        engine.save_to_file(text, str(target_path))
        engine.runAndWait()
        engine.stop()
    except Exception as exc:  # noqa: BLE001
        _LOG.debug("pyttsx3 unavailable for Tribev2 proxy audio: %s", exc)
        return False

    return target_path.exists() and target_path.stat().st_size > 0


def _synthesize_text_to_audio_local(
    text: str,
    *,
    wav_path: pathlib.Path,
    aiff_path: pathlib.Path,
) -> str | None:
    if _synthesize_text_to_audio_windows(text, wav_path):
        return str(wav_path)
    if _synthesize_text_to_audio_linux(text, wav_path):
        return str(wav_path)
    if _synthesize_text_to_audio_pyttsx3(text, wav_path):
        return str(wav_path)
    if _synthesize_text_to_audio_macos(text, aiff_path):
        return str(aiff_path)
    return None


def _text_to_audio_proxy(text: str, cache_folder: str) -> str:
    """Synthesise *text* to audio and return the file path.

    Output is cached by a hash of the text content so repeated calls for the
    same document skip re-synthesis.  METIS first attempts local synthesis
    backends (Windows System.Speech, Linux ``espeak``, pyttsx3, macOS ``say``)
    and only falls back to gTTS when no local path is available.
    """
    try:
        from langdetect import detect
        lang_raw = detect(text[:500]) or "en"
    except Exception:  # noqa: BLE001
        lang_raw = "en"

    # Normalise to a bare 2-char code (langdetect can return "zh-cn" etc.)
    lang_code = (lang_raw.split("-")[0] or "en")[:2]

    digest = hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()[:16]
    proxy_dir = pathlib.Path(cache_folder) / "tts_proxy"
    proxy_dir.mkdir(parents=True, exist_ok=True)

    wav_path = proxy_dir / f"tts-{digest}-{lang_code}.wav"
    aiff_path = proxy_dir / f"tts-{digest}-{lang_code}.aiff"
    if wav_path.exists():
        return str(wav_path)
    if aiff_path.exists():
        return str(aiff_path)

    local_audio_path = _synthesize_text_to_audio_local(
        text,
        wav_path=wav_path,
        aiff_path=aiff_path,
    )
    if local_audio_path:
        _LOG.debug("Local TTS proxy audio saved to %s", local_audio_path)
        return local_audio_path

    from gtts import gTTS

    mp3_path = proxy_dir / f"tts-{digest}-{lang_code}.mp3"
    if not mp3_path.exists():
        gTTS(text=text, lang=lang_code).save(str(mp3_path))
        _LOG.debug("gTTS proxy audio saved to %s", mp3_path)
    return str(mp3_path)


def _run_native_tribev2(
    *,
    input_mode: str,
    input_path: str,
    settings: dict[str, Any],
    post_message: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any] | None:
    if not input_mode or not input_path:
        return None

    model_id = str(settings.get("brain_pass_model_id") or "facebook/tribev2")
    cache_folder = str(settings.get("brain_pass_cache_dir") or ".metis_cache/tribev2")
    device = str(settings.get("brain_pass_device") or "auto")

    if callable(post_message):
        post_message({"type": "status", "text": f"Running Tribev2 via {input_mode} input…"})

    model = _load_tribev2_model(model_id, cache_folder, device)

    if input_mode == "text":
        # Text-as-audio-proxy path: synthesise text → MP3, feed as Audio events.
        # This bypasses system FFmpeg, whisperx, and the gated Llama text extractor
        # that Tribev2's native text pipeline requires.
        try:
            import pandas as pd
            from neuralset.events.utils import standardize_events

            text_content = pathlib.Path(input_path).read_text(encoding="utf-8", errors="replace")
            proxy_mp3 = _text_to_audio_proxy(text_content, cache_folder)
            with _quiet_tribev2_runtime():
                events = standardize_events(
                    pd.DataFrame(
                        [
                            {
                                "type": "Audio",
                                "filepath": proxy_mp3,
                                "start": 0.0,
                                "timeline": "default",
                                "subject": "default",
                            }
                        ]
                    )
                )
            # Keep the whisperx compat patch active during predict() so that
            # the audio extractor's internal transcription also uses the
            # bundled FFmpeg shim and CPU-safe compute_type.
            with _quiet_tribev2_runtime(), _tribev2_whisperx_compat(device):
                preds, _segments = model.predict(events=events, verbose=False)
            effective_input_mode = "text-via-audio-proxy"
        except Exception as _proxy_exc:  # noqa: BLE001
            _LOG.debug(
                "gTTS audio proxy failed for text input (%s); falling back to native text path.",
                _proxy_exc,
            )
            with _quiet_tribev2_runtime(), _tribev2_whisperx_compat(device):
                events = model.get_events_dataframe(text_path=input_path)
            with _quiet_tribev2_runtime():
                preds, _segments = model.predict(events=events, verbose=False)
            effective_input_mode = "text"
    else:
        with _quiet_tribev2_runtime(), _tribev2_whisperx_compat(device):
            events = model.get_events_dataframe(**{f"{input_mode}_path": input_path})
        with _quiet_tribev2_runtime():
            preds, _segments = model.predict(events=events, verbose=False)
        effective_input_mode = input_mode

    top_rois: list[str] = []
    try:
        with _quiet_tribev2_runtime():
            import numpy as np
            from tribev2.utils import get_topk_rois

            preds_array = np.asarray(preds)
            summary_signal = preds_array.mean(axis=0) if preds_array.ndim > 1 else preds_array
            top_rois = [str(item) for item in get_topk_rois(summary_signal, k=5)]
    except Exception as exc:  # noqa: BLE001
        _LOG.debug("Unable to summarize Tribev2 ROIs for %s: %s", input_path, exc)

    timesteps = 0
    vertex_count = 0
    try:
        shape = getattr(preds, "shape", ())
        if len(shape) >= 2:
            timesteps = int(shape[0])
            vertex_count = int(shape[1])
        elif len(shape) == 1:
            timesteps = 1
            vertex_count = int(shape[0])
    except Exception:
        timesteps = 0
        vertex_count = 0

    coherence: dict[str, float] | None = None
    fingerprint: dict[int, float] | None = None
    try:
        import numpy as np

        from metis_app.utils.brain_metrics import compute_coherence
        from metis_app.utils.spatial_encoder import SpatialFingerprint

        preds_array = np.asarray(preds)
        if preds_array.ndim == 2 and preds_array.size > 0:
            # Tribev2 hands us (T, V); coherence wants (V, T).
            activity = preds_array.T
            coherence = compute_coherence(
                activity,
                downsample=int(settings.get("brain_encoder_downsample", 1) or 1),
                max_channels=int(settings.get("brain_encoder_max_channels", 64) or 64),
            )
            encoder = SpatialFingerprint(
                n_channels=int(settings.get("brain_encoder_channels", 62) or 62),
                active_k=int(settings.get("brain_encoder_active_k", 8) or 8),
                seed=int(settings.get("brain_encoder_seed", 1337) or 1337),
            )
            fingerprint = encoder.encode_vector(activity.mean(axis=1))
    except Exception as exc:  # noqa: BLE001
        _LOG.debug("Coherence/fingerprint computation failed for %s: %s", input_path, exc)

    return {
        "native_input_mode": effective_input_mode,
        "native_input_path": input_path,
        "model_id": model_id,
        "timesteps": timesteps,
        "vertex_count": vertex_count,
        "top_rois": top_rois,
        "coherence": coherence,
        "fingerprint": fingerprint,
    }


def _apply_modality_priors(scores: dict[str, float], modality: str) -> None:
    if modality == "text":
        scores["knowledge"] += 2.0
        scores["reasoning"] += 1.1
    elif modality == "document":
        scores["knowledge"] += 2.2
        scores["reasoning"] += 1.0
        scores["memory"] += 0.4
    elif modality == "image":
        scores["perception"] += 2.0
        scores["knowledge"] += 0.8
    elif modality == "audio":
        scores["perception"] += 1.6
        scores["memory"] += 0.6
        scores["knowledge"] += 0.5
    elif modality == "video":
        scores["perception"] += 2.1
        scores["synthesis"] += 0.9
        scores["knowledge"] += 0.6
    else:
        scores["knowledge"] += 0.5


def _apply_keyword_scores(scores: dict[str, float], combined_text: str) -> list[str]:
    lowered = combined_text.lower()
    evidence: list[str] = []
    for faculty_id, keywords in _FACULTY_KEYWORDS.items():
        hits = [keyword for keyword in keywords if keyword in lowered]
        if not hits:
            continue
        scores[faculty_id] += min(4.0, len(hits) * 0.75)
        evidence.extend(f"{faculty_id}:{keyword}" for keyword in hits[:2])
    return evidence


def _apply_roi_scores(scores: dict[str, float], top_rois: list[str]) -> list[str]:
    evidence: list[str] = []
    for roi in top_rois:
        lowered = roi.lower()
        for faculty_id, hints in _ROI_HINTS.items():
            if any(hint in lowered for hint in hints):
                scores[faculty_id] += 1.25
                evidence.append(f"{faculty_id}:{roi}")
                break
    return evidence


def _recommend_placement(
    normalized_sources: list[NormalizedSource],
    *,
    provider: str,
    native_analysis: dict[str, Any] | None,
) -> PlacementRecommendation:
    heuristic_scores = {faculty_id: 0.0 for faculty_id in _FACULTY_IDS}
    native_scores = {faculty_id: 0.0 for faculty_id in _FACULTY_IDS}
    combined_text = "\n\n".join(
        item.extracted_text
        for item in normalized_sources
        if item.extracted_text
    )

    for source in normalized_sources:
        _apply_modality_priors(heuristic_scores, source.source_modality)

    heuristic_evidence = _apply_keyword_scores(heuristic_scores, combined_text)
    top_rois = [str(item) for item in (native_analysis or {}).get("top_rois") or []]
    native_evidence = _apply_roi_scores(native_scores, top_rois)

    scores = {
        faculty_id: heuristic_scores[faculty_id] + native_scores[faculty_id]
        for faculty_id in _FACULTY_IDS
    }
    evidence = heuristic_evidence + native_evidence

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    primary_id, primary_score = ranked[0]
    secondary_id, _secondary_score = ranked[1]
    total_score = sum(value for _faculty_id, value in ranked)
    confidence = round(min(0.96, max(0.35, primary_score / max(1.0, total_score))), 3)

    native_total = sum(native_scores.values())
    heuristic_total = sum(heuristic_scores.values())
    if native_total > 0 and heuristic_total <= 0:
        blend_mode = "pure_native"
    elif native_total <= 0:
        blend_mode = "pure_fallback"
    else:
        blend_mode = "blended"

    contribution_total = max(1e-9, native_total + heuristic_total)
    blend_weights = {
        "native": round(native_total / contribution_total, 3) if native_total > 0 else 0.0,
        "heuristic": round(heuristic_total / contribution_total, 3) if heuristic_total > 0 else 0.0,
    }

    modality_summary = ", ".join(source.source_modality for source in normalized_sources)
    if provider == "tribev2":
        if top_rois:
            rationale = (
                f"Filed near {primary_id.title()} because the upload emphasized {modality_summary} inputs, "
                f"and Tribev2 ROI hints leaned toward {', '.join(top_rois[:3])}."
            )
        else:
            rationale = (
                f"Filed near {primary_id.title()} because the upload emphasized {modality_summary} inputs, "
                "and native Tribev2 execution completed without ROI-specific hints."
            )
        provenance = f"tribev2-{(native_analysis or {}).get('native_input_mode') or 'native'}"
    elif provider == "fallback":
        rationale = (
            f"Filed near {primary_id.title()} using METIS fallback analysis over {modality_summary} inputs, "
            f"document text, and modality priors."
        )
        provenance = "fallback-heuristic"
    else:
        rationale = f"Filed near {primary_id.title()} using the current upload metadata."
        provenance = "disabled"

    return PlacementRecommendation(
        faculty_id=primary_id,
        confidence=confidence,
        rationale=rationale,
        provenance=provenance,
        secondary_faculty_id=secondary_id,
        evidence=evidence[:8],
        native_score=round(native_scores.get(primary_id, 0.0), 3),
        heuristic_score=round(heuristic_scores.get(primary_id, 0.0), 3),
        native_evidence=native_evidence[:8],
        heuristic_evidence=heuristic_evidence[:8],
        native_sources_used=[str(item) for item in (native_analysis or {}).get("native_sources_used_paths") or []],
        blend_mode=blend_mode,
        blend_weights=blend_weights,
        final_blend_explanation=(
            "Placement derived from Tribev2-native ROI signals only."
            if blend_mode == "pure_native"
            else "Placement derived from fallback heuristics only because native signals were unavailable."
            if blend_mode == "pure_fallback"
            else "Placement blends Tribev2-native ROI signals with fallback modality and keyword heuristics."
        ),
    )


def run_brain_pass(
    document_paths: list[str],
    settings: dict[str, Any],
    *,
    post_message: Callable[[dict[str, Any]], None] | None = None,
) -> BrainPassResult:
    enabled = _parse_boolish(settings.get("enable_brain_pass", True), True)
    allow_fallback = _parse_boolish(settings.get("brain_pass_allow_fallback", True), True)

    if callable(post_message):
        post_message({"type": "status", "text": "Running METIS brain pass…"})

    source_paths = [pathlib.Path(path) for path in document_paths]
    source_modalities = [detect_source_modality(path) for path in source_paths]
    use_kreuzberg = str(settings.get("document_loader", "auto") or "auto") != "plain"
    native_requested = _parse_boolish(settings.get("brain_pass_native_enabled", True), True)
    native_text_requested = _parse_boolish(
        settings.get("brain_pass_native_text_enabled", True),
        True,
    )
    native_candidate_requested = any(modality in {"audio", "video"} for modality in source_modalities) or (
        native_text_requested and any(modality in {"text", "document", "image"} for modality in source_modalities)
    )
    native_available = (
        native_requested
        and native_candidate_requested
        and _native_tribev2_available()
    )
    native_text_enabled = native_available and native_text_requested
    normalized_sources = [
        _normalize_source(
            source_path,
            use_kreuzberg=use_kreuzberg,
            native_available=native_available,
            native_text_enabled=native_text_enabled,
        )
        for source_path in source_paths
    ]

    native_analysis: dict[str, Any] | None = None
    analysis: dict[str, Any] = {
        "native_input_mode": "",
        "top_rois": [],
        "native_by_source": [],
        "native_errors_by_source": [],
        "native_sources_attempted": 0,
        "native_sources_used": 0,
        "native_sources_failed": 0,
        "native_score": 0.0,
        "heuristic_score": 0.0,
        "native_evidence": [],
        "heuristic_evidence": [],
        "blend_mode": "pure_fallback",
        "blend_weights": {"native": 0.0, "heuristic": 1.0},
        "final_blend_explanation": "Placement derived from fallback heuristics only because native signals were unavailable.",
    }
    provider = "fallback" if enabled else "disabled"
    if enabled and native_available:
        native_inputs = _native_inputs_by_source(normalized_sources)
        analysis["native_sources_attempted"] = len(native_inputs)
        native_results: list[dict[str, Any]] = []
        native_errors: list[dict[str, str]] = []
        for source, input_mode, input_path in native_inputs:
            try:
                source_result = _run_native_tribev2(
                    input_mode=input_mode,
                    input_path=input_path,
                    settings=settings,
                    post_message=post_message,
                )
                if source_result:
                    source_record = {
                        "source_path": source.source_path,
                        "source_name": source.source_name,
                        **dict(source_result),
                    }
                    native_results.append(source_record)
            except Exception as exc:  # noqa: BLE001
                _LOG.warning("Tribev2 brain pass failed for %s: %s", source.source_path, exc)
                native_errors.append(
                    {
                        "source_path": source.source_path,
                        "source_name": source.source_name,
                        "error": str(exc),
                    }
                )

        analysis["native_by_source"] = native_results
        analysis["native_errors_by_source"] = native_errors
        analysis["native_sources_failed"] = len(native_errors)

        if native_results:
            native_analysis = _aggregate_native_analyses(native_results)
            native_analysis["native_sources_used_paths"] = [
                str(item.get("source_path") or "") for item in native_results if item.get("source_path")
            ]
            analysis.update(dict(native_analysis))
            analysis["native_sources_used"] = len(native_results)
            provider = "tribev2"
        elif native_inputs:
            if native_errors:
                analysis["native_error"] = "; ".join(item["error"] for item in native_errors[:2])
            provider = "fallback" if allow_fallback else "disabled"
        else:
            if not native_text_enabled and _has_text_backed_native_candidates(normalized_sources):
                analysis["native_error"] = (
                    "Native Tribev2 analysis for text-backed sources is disabled unless "
                    "brain_pass_native_text_enabled is true."
                )
            else:
                analysis["native_error"] = (
                    "METIS could not prepare any native Tribev2-compatible input for this upload set."
                )
            provider = "fallback" if allow_fallback else "disabled"
    elif enabled and native_requested and native_candidate_requested and not native_available:
        analysis["native_error"] = "Tribev2 runtime is not installed in this environment."
    elif enabled and native_requested and _has_text_backed_native_candidates(normalized_sources):
        analysis["native_error"] = (
            "Native Tribev2 analysis for text-backed sources is disabled unless "
            "brain_pass_native_text_enabled is true."
        )
    elif not enabled or not allow_fallback:
        provider = "disabled"

    placement = _recommend_placement(
        normalized_sources,
        provider=provider,
        native_analysis=native_analysis,
    )
    analysis["native_score"] = placement.native_score
    analysis["heuristic_score"] = placement.heuristic_score
    analysis["native_evidence"] = list(placement.native_evidence)
    analysis["heuristic_evidence"] = list(placement.heuristic_evidence)
    analysis["blend_mode"] = placement.blend_mode
    analysis["blend_weights"] = dict(placement.blend_weights or {})
    analysis["final_blend_explanation"] = placement.final_blend_explanation

    # Ensure downstream always sees a fingerprint, even when native Tribev2 did
    # not run.  The heuristic fingerprint is keyed off the faculty score vector
    # so similar-topic documents share channels.
    if not analysis.get("fingerprint"):
        try:
            from metis_app.utils.spatial_encoder import SpatialFingerprint

            encoder = SpatialFingerprint(
                n_channels=int(settings.get("brain_encoder_channels", 62) or 62),
                active_k=int(settings.get("brain_encoder_active_k", 8) or 8),
                seed=int(settings.get("brain_encoder_seed", 1337) or 1337),
            )
            analysis["fingerprint"] = encoder.encode_id(placement.faculty_id)
        except Exception as exc:  # noqa: BLE001
            _LOG.debug("Heuristic fingerprint fallback failed: %s", exc)
            analysis.setdefault("fingerprint", {})
    if "coherence" not in analysis:
        analysis["coherence"] = None
    index_text_by_source = {
        item.source_path: (item.extracted_text or _placeholder_text(pathlib.Path(item.source_path), item.source_modality, "No text extracted."))
        for item in normalized_sources
    }
    return BrainPassResult(
        provider=provider,
        native_available=native_available,
        source_modalities=[item.source_modality for item in normalized_sources],
        normalized_sources=normalized_sources,
        placement=placement,
        index_text_by_source=index_text_by_source,
        analysis=analysis,
    )


__all__ = [
    "BrainPassResult",
    "NormalizedSource",
    "PlacementRecommendation",
    "detect_source_modality",
    "run_brain_pass",
]