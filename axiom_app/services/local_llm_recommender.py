"""Hardware-aware GGUF model recommendations and import helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import os
import pathlib
import platform
import re
import subprocess
from importlib import resources
from typing import Any, Callable
from urllib import parse, request

try:
    import psutil
except Exception:  # pragma: no cover - optional runtime dependency
    psutil = None  # type: ignore[assignment]


_GIB = 1024.0 * 1024.0 * 1024.0
_CATALOG_PACKAGE = "axiom_app.assets"
_CATALOG_NAME = "llmfit_gguf_catalog.json"
_DEFAULT_CONTEXT_CANDIDATES = (8192, 4096, 2048)
_QUANT_HIERARCHY = ("Q8_0", "Q6_K", "Q5_K_M", "Q4_K_M", "Q3_K_M", "Q2_K")
_ALL_QUANT_ORDER = ("F16", "BF16", "Q8_0", "Q6_K", "Q5_K_M", "Q4_K_M", "Q3_K_M", "Q2_K")
_SOURCE_PREFERENCE = ("bartowski", "unsloth")
_TARGET_SPEED = {
    "general": 40.0,
    "chat": 40.0,
    "coding": 40.0,
    "reasoning": 25.0,
    "embedding": 200.0,
}
_CONTEXT_TARGETS = {
    "general": 4096,
    "chat": 4096,
    "coding": 8192,
    "reasoning": 8192,
    "embedding": 512,
}
_WEIGHTS = {
    "general": (0.45, 0.30, 0.15, 0.10),
    "coding": (0.50, 0.20, 0.15, 0.15),
    "reasoning": (0.55, 0.15, 0.15, 0.15),
    "chat": (0.40, 0.35, 0.15, 0.10),
    "embedding": (0.30, 0.40, 0.20, 0.10),
}
_BACKEND_SPEED_K = {
    "metal": 160.0,
    "cuda": 220.0,
    "rocm": 180.0,
    "vulkan": 150.0,
    "sycl": 100.0,
    "cpu_arm": 90.0,
    "cpu_x86": 70.0,
    "ascend": 390.0,
}
_GPU_BANDWIDTH = {
    "rtx 4090": 1008.0,
    "rtx 4080": 717.0,
    "rtx 4070": 504.0,
    "rtx 3090": 936.0,
    "rtx 3080": 760.0,
    "rtx 3070": 448.0,
    "rtx 3060": 360.0,
    "rtx 3050": 224.0,
    "tesla t4": 320.0,
    "tesla v100": 900.0,
    "tesla p100": 732.0,
    "tesla p40": 346.0,
    "a10": 600.0,
    "a100": 1555.0,
    "a40": 696.0,
    "a5000": 768.0,
    "a6000": 768.0,
    "l4": 300.0,
    "l40": 864.0,
    "m1": 68.0,
    "m1 pro": 200.0,
    "m1 max": 400.0,
    "m1 ultra": 800.0,
    "m2": 100.0,
    "m2 pro": 200.0,
    "m2 max": 400.0,
    "m2 ultra": 800.0,
    "m3": 100.0,
    "m3 pro": 150.0,
    "m3 max": 300.0,
    "m4": 120.0,
    "m4 pro": 273.0,
    "m4 max": 546.0,
}
_QUANT_PATTERN = re.compile(
    r"(?i)(?<![a-z0-9])(bf16|f16|q8_0|q6_k|q5_k_[ms]|q4_k_[ms]|q4_0|q3_k_[ms]|q2_k)(?![a-z0-9])"
)
_MULTIMODAL_HINTS = ("vision", "vl", "vlm", "multimodal")


@dataclass(slots=True)
class HardwareProfile:
    total_ram_gb: float
    available_ram_gb: float
    total_cpu_cores: int
    cpu_name: str
    has_gpu: bool
    gpu_vram_gb: float | None
    total_gpu_vram_gb: float | None
    gpu_name: str = ""
    gpu_count: int = 0
    unified_memory: bool = False
    backend: str = "cpu_x86"
    detected: bool = True
    override_enabled: bool = False
    notes: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def effective_gpu_memory_gb(self) -> float:
        if self.unified_memory:
            return float(self.available_ram_gb)
        if self.gpu_vram_gb is None:
            return 0.0
        return float(self.gpu_vram_gb)

    def summary(self) -> str:
        parts = [
            f"RAM {self.available_ram_gb:.1f}/{self.total_ram_gb:.1f} GB free",
            f"CPU {self.total_cpu_cores} cores",
        ]
        if self.has_gpu:
            if self.unified_memory:
                parts.append(f"GPU {self.gpu_name or 'Integrated'} (unified memory)")
            else:
                parts.append(f"GPU {self.gpu_name or 'Detected'} ({(self.gpu_vram_gb or 0.0):.1f} GB VRAM)")
        else:
            parts.append("GPU not detected")
        parts.append(f"backend={self.backend}")
        if self.override_enabled:
            parts.append("overrides active")
        if not self.detected:
            parts.append("advisory only")
        return " | ".join(parts)


@dataclass(slots=True)
class CatalogModel:
    name: str
    provider: str
    parameter_count: str
    parameters_raw: int | None
    min_ram_gb: float
    recommended_ram_gb: float
    min_vram_gb: float | None
    quantization: str
    context_length: int
    use_case: str
    capabilities: list[str] = field(default_factory=list)
    architecture: str = ""
    release_date: str = ""
    is_moe: bool = False
    num_experts: int | None = None
    active_experts: int | None = None
    active_parameters: int | None = None
    gguf_sources: list[dict[str, str]] = field(default_factory=list)

    @property
    def catalog_name(self) -> str:
        return self.name

    def params_b(self) -> float:
        if self.parameters_raw:
            return max(float(self.parameters_raw) / 1_000_000_000.0, 0.1)
        text = str(self.parameter_count or "").strip().lower()
        if not text:
            return 0.1
        text = text.replace("parameters", "").replace("params", "").strip()
        if "x" in text and "b" in text:
            try:
                experts, size = text.split("x", 1)
                return float(experts) * float(size.rstrip("b"))
            except ValueError:
                pass
        match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*b", text)
        if match:
            return float(match.group(1))
        match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*m", text)
        if match:
            return float(match.group(1)) / 1000.0
        try:
            return float(text)
        except ValueError:
            return 0.1

    def estimate_memory_gb(self, quant: str, context_length: int) -> float:
        params = float(self.parameters_raw or max(int(self.params_b() * 1_000_000_000.0), 1))
        kv_cache_gb = 0.000008 * params * max(int(context_length), 1) / _GIB
        return round(((params * quant_bpp(quant)) / _GIB) + kv_cache_gb + 0.5, 3)

    def best_quant_for_budget(
        self,
        budget_gb: float,
        context_length: int,
        hierarchy: tuple[str, ...] = _QUANT_HIERARCHY,
    ) -> tuple[str, float] | None:
        for quant in hierarchy:
            required = self.estimate_memory_gb(quant, context_length)
            if required <= budget_gb:
                return quant, required
        half_context = max(int(context_length // 2), 0)
        if half_context >= 1024:
            for quant in hierarchy:
                required = self.estimate_memory_gb(quant, half_context)
                if required <= budget_gb:
                    return quant, required
        return None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "CatalogModel":
        return cls(
            name=str(payload.get("name") or ""),
            provider=str(payload.get("provider") or ""),
            parameter_count=str(payload.get("parameter_count") or ""),
            parameters_raw=_to_int(payload.get("parameters_raw")),
            min_ram_gb=float(payload.get("min_ram_gb") or 0.0),
            recommended_ram_gb=float(payload.get("recommended_ram_gb") or 0.0),
            min_vram_gb=_to_float(payload.get("min_vram_gb")),
            quantization=normalize_quant(str(payload.get("quantization") or "Q4_K_M")),
            context_length=max(int(payload.get("context_length") or 2048), 256),
            use_case=normalize_use_case(
                payload.get("use_case"),
                name=str(payload.get("name") or ""),
                capabilities=list(payload.get("capabilities") or []),
            ),
            capabilities=[str(item) for item in (payload.get("capabilities") or [])],
            architecture=str(payload.get("architecture") or ""),
            release_date=str(payload.get("release_date") or ""),
            is_moe=bool(payload.get("is_moe", False)),
            num_experts=_to_int(payload.get("num_experts")),
            active_experts=_to_int(payload.get("active_experts")),
            active_parameters=_to_int(payload.get("active_parameters")),
            gguf_sources=[dict(item) for item in (payload.get("gguf_sources") or []) if isinstance(item, dict)],
        )


@dataclass(slots=True)
class FitRecommendation:
    catalog_name: str
    fit_level: str
    run_mode: str
    score: float
    best_quant: str
    estimated_tps: float
    memory_required_gb: float
    memory_available_gb: float
    recommended_context_length: int
    notes: list[str] = field(default_factory=list)
    score_components: dict[str, float] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ImportPlan:
    source_repo: str
    source_provider: str
    filename: str
    destination_path: str
    registry_metadata: dict[str, Any]
    expected_size_bytes: int | None = None
    activation_safe: bool = False
    manual_reason: str = ""
    manual_selection_required: bool = False
    candidate_filenames: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class HuggingFaceRepoFile:
    filename: str
    size_bytes: int = 0


class LocalLlmRecommenderService:
    """Bundle catalog loading, hardware detection, fit scoring, and GGUF import."""

    def __init__(self) -> None:
        self._catalog_cache: tuple[dict[str, Any], list[CatalogModel]] | None = None
        self._hardware_cache: HardwareProfile | None = None
        self._repo_tree_cache: dict[str, list[HuggingFaceRepoFile]] = {}

    def load_catalog(self) -> tuple[dict[str, Any], list[CatalogModel]]:
        if self._catalog_cache is not None:
            return self._catalog_cache
        payload = json.loads(
            resources.files(_CATALOG_PACKAGE).joinpath(_CATALOG_NAME).read_text(encoding="utf-8")
        )
        meta = dict(payload.get("meta") or {})
        models = [CatalogModel.from_payload(item) for item in (payload.get("models") or [])]
        self._catalog_cache = (meta, models)
        return self._catalog_cache

    def list_catalog_models(self) -> list[CatalogModel]:
        return list(self.load_catalog()[1])

    def default_models_dir(self, settings: dict[str, Any] | None = None) -> pathlib.Path:
        raw = str((settings or {}).get("local_gguf_models_dir", "") or "").strip()
        if raw:
            return pathlib.Path(raw).expanduser()
        if os.name == "nt":
            base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~\\AppData\\Local")
            return pathlib.Path(base) / "Axiom" / "models" / "gguf"
        if platform.system().lower() == "darwin":
            return pathlib.Path("~/Library/Caches/Axiom/models/gguf").expanduser()
        return pathlib.Path("~/.cache/axiom/models/gguf").expanduser()

    def wizard_mode_to_use_case(self, mode: str) -> str:
        mapping = {
            "Q&A": "chat",
            "Tutor": "chat",
            "Summary": "general",
            "Book summary": "general",
            "Research": "reasoning",
            "Evidence Pack": "reasoning",
        }
        return mapping.get(str(mode or "").strip(), "general")

    def detect_hardware(self, settings: dict[str, Any] | None = None) -> HardwareProfile:
        detected = self._hardware_cache
        if detected is None:
            detected = self._detect_hardware_profile()
            self._hardware_cache = detected
        return self._apply_overrides(detected, settings or {})

    def invalidate_hardware_cache(self) -> None:
        self._hardware_cache = None

    def invalidate_repo_cache(self, repo: str | None = None) -> None:
        target = str(repo or "").strip()
        if not target:
            self._repo_tree_cache.clear()
            return
        self._repo_tree_cache.pop(target, None)

    def recommend_models(
        self,
        *,
        use_case: str,
        settings: dict[str, Any] | None = None,
        limit: int = 12,
        current_mode: str = "",
    ) -> dict[str, Any]:
        meta, models = self.load_catalog()
        hardware = self.detect_hardware(settings)
        requested_use_case = normalize_use_case(
            use_case or self.wizard_mode_to_use_case(current_mode),
            name="",
            capabilities=[],
        )
        candidates: list[dict[str, Any]] = []
        for model in models:
            model_use_case = normalize_use_case(model.use_case, name=model.name, capabilities=model.capabilities)
            if requested_use_case != "general" and model_use_case not in {requested_use_case, "general"}:
                continue
            recommendation = self._analyze_model(model, hardware, requested_use_case)
            preferred_source = self._preferred_source(model)
            candidates.append(
                {
                    "model_name": model.catalog_name,
                    "provider": model.provider,
                    "parameter_count": model.parameter_count,
                    "architecture": model.architecture,
                    "use_case": model_use_case,
                    "source_provider": str(preferred_source.get("provider") or ""),
                    "source_repo": str(preferred_source.get("repo") or ""),
                    "release_date": model.release_date,
                    "recommendation": recommendation.to_payload(),
                    "fit_rank": fit_sort_rank(recommendation.fit_level),
                }
            )
        candidates.sort(
            key=lambda row: (
                row["fit_rank"],
                -(row["recommendation"]["score"]),
                -(row["recommendation"]["estimated_tps"]),
                row["release_date"] or "",
            )
        )
        rows: list[dict[str, Any]] = []
        for row in candidates[: max(limit, 1)]:
            rec = dict(row["recommendation"])
            rows.append(
                {
                    "model_name": row["model_name"],
                    "provider": row["provider"],
                    "parameter_count": row["parameter_count"],
                    "architecture": row["architecture"],
                    "use_case": row["use_case"],
                    "source_provider": row["source_provider"],
                    "source_repo": row["source_repo"],
                    "release_date": row["release_date"],
                    "fit_level": rec["fit_level"],
                    "run_mode": rec["run_mode"],
                    "score": rec["score"],
                    "best_quant": rec["best_quant"],
                    "estimated_tps": rec["estimated_tps"],
                    "memory_required_gb": rec["memory_required_gb"],
                    "memory_available_gb": rec["memory_available_gb"],
                    "recommended_context_length": rec["recommended_context_length"],
                    "notes": list(rec["notes"]),
                    "score_components": dict(rec["score_components"]),
                }
            )
        return {
            "catalog_meta": meta,
            "hardware": hardware.to_payload(),
            "use_case": requested_use_case,
            "advisory_only": not hardware.detected,
            "rows": rows,
        }

    def find_catalog_model(self, model_name: str) -> CatalogModel | None:
        target = str(model_name or "").strip().lower()
        if not target:
            return None
        for model in self.list_catalog_models():
            if model.catalog_name.lower() == target:
                return model
        return None

    def plan_import(
        self,
        *,
        model_name: str,
        best_quant: str,
        fit_level: str,
        recommended_context_length: int,
        settings: dict[str, Any] | None = None,
        repo_files: list[HuggingFaceRepoFile] | None = None,
        selected_filename: str = "",
    ) -> ImportPlan:
        model = self.find_catalog_model(model_name)
        if model is None:
            raise ValueError(f"Unknown catalog model: {model_name}")
        source = self._preferred_source(model)
        repo = str(source.get("repo") or "").strip()
        if not repo:
            raise ValueError(f"No GGUF source is available for {model.catalog_name}.")
        files = list(repo_files or self.list_repo_files(repo))
        filename = str(selected_filename or "").strip()
        manual_required = False
        candidate_names = [item.filename for item in files]
        manual_reason = ""
        selected_file: HuggingFaceRepoFile | None = None
        if not filename:
            chosen, manual_required = self._choose_best_gguf_file(files, best_quant)
            selected_file = chosen
            filename = chosen.filename if chosen is not None else ""
            if manual_required:
                manual_reason = "Multiple GGUF files match this recommendation. Choose one explicitly."
            elif not filename:
                manual_reason = "No safe automatic GGUF file choice was available."
        else:
            selected_file = next((item for item in files if item.filename == filename), None)
        if filename and not validate_gguf_filename(filename):
            raise ValueError(f"Unsafe GGUF filename: {filename}")
        destination = self.default_models_dir(settings) / filename if filename else self.default_models_dir(settings)
        metadata = {
            "catalog_name": model.catalog_name,
            "source_repo": repo,
            "source_provider": str(source.get("provider") or ""),
            "quantization": normalize_quant(best_quant),
            "architecture": model.architecture,
            "fit_level": fit_level,
            "recommended_context_length": int(recommended_context_length),
            "parameter_count": model.parameter_count,
            "use_case": normalize_use_case(model.use_case, name=model.name, capabilities=model.capabilities),
        }
        return ImportPlan(
            source_repo=repo,
            source_provider=str(source.get("provider") or ""),
            filename=filename,
            destination_path=str(destination),
            registry_metadata=metadata,
            expected_size_bytes=selected_file.size_bytes if selected_file and selected_file.size_bytes > 0 else None,
            activation_safe=str(fit_level or "").strip().lower() in {"perfect", "good"},
            manual_reason=manual_reason,
            manual_selection_required=manual_required or not bool(filename),
            candidate_filenames=candidate_names,
        )

    def list_repo_files(self, repo: str) -> list[HuggingFaceRepoFile]:
        target_repo = str(repo or "").strip()
        if not target_repo:
            return []
        cached = self._repo_tree_cache.get(target_repo)
        if cached is not None:
            return [HuggingFaceRepoFile(item.filename, item.size_bytes) for item in cached]
        encoded_repo = parse.quote(target_repo, safe="")
        url = f"https://huggingface.co/api/models/{encoded_repo}/tree/main?recursive=1"
        payload = self._read_json(url)
        files: list[HuggingFaceRepoFile] = []
        for item in payload if isinstance(payload, list) else []:
            if not isinstance(item, dict):
                continue
            filename = str(item.get("path") or item.get("name") or "").strip()
            basename = pathlib.Path(filename).name
            if not validate_gguf_filename(basename):
                continue
            files.append(
                HuggingFaceRepoFile(
                    filename=basename,
                    size_bytes=max(int(item.get("size") or 0), 0),
                )
            )
        self._repo_tree_cache[target_repo] = [
            HuggingFaceRepoFile(item.filename, item.size_bytes) for item in files
        ]
        return files

    def describe_repo_files(self, files: list[HuggingFaceRepoFile]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for item in files:
            rows.append(
                {
                    "filename": item.filename,
                    "quant": quant_from_filename(item.filename),
                    "size_bytes": item.size_bytes,
                    "hint": "chat/instruct" if is_instruct_filename(item.filename) else "base",
                }
            )
        rows.sort(
            key=lambda row: (
                0 if row["hint"] == "chat/instruct" else 1,
                quant_rank(str(row["quant"] or "")) if row["quant"] else 999,
                int(row["size_bytes"] or 0) if row["size_bytes"] else 2**63 - 1,
                str(row["filename"]).lower(),
            )
        )
        return rows

    def download_import(
        self,
        plan: ImportPlan,
        *,
        progress_callback: Callable[[int, int | None], None] | None = None,
        cancel_token: Any | None = None,
    ) -> pathlib.Path:
        if not plan.filename:
            raise ValueError("No GGUF filename was selected for import.")
        destination = pathlib.Path(plan.destination_path).expanduser()
        destination.parent.mkdir(parents=True, exist_ok=True)
        if (
            plan.expected_size_bytes is not None
            and destination.is_file()
            and destination.stat().st_size == int(plan.expected_size_bytes)
        ):
            if progress_callback is not None:
                progress_callback(int(plan.expected_size_bytes), int(plan.expected_size_bytes))
            return destination
        part_path = destination.with_name(destination.name + ".part")
        encoded_repo = parse.quote(plan.source_repo, safe="")
        encoded_filename = parse.quote(plan.filename)
        url = f"https://huggingface.co/{encoded_repo}/resolve/main/{encoded_filename}?download=true"
        req = request.Request(url, headers={"User-Agent": "Axiom/1.0"})
        if part_path.exists():
            part_path.unlink()
        downloaded = 0
        total_bytes = int(plan.expected_size_bytes) if plan.expected_size_bytes is not None else None
        try:
            with request.urlopen(req, timeout=120) as response, part_path.open("wb") as handle:
                if total_bytes is None:
                    header_total = str(response.headers.get("Content-Length") or "").strip()
                    if header_total.isdigit():
                        total_bytes = int(header_total)
                while True:
                    if bool(getattr(cancel_token, "cancelled", False)):
                        raise InterruptedError("GGUF import cancelled.")
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback is not None:
                        progress_callback(downloaded, total_bytes)
            if total_bytes is not None and downloaded != total_bytes:
                raise ValueError(
                    f"Incomplete GGUF download for {plan.filename}: expected {total_bytes} bytes, got {downloaded}."
                )
            os.replace(part_path, destination)
        except Exception:
            if part_path.exists():
                part_path.unlink()
            raise
        return destination

    def _analyze_model(self, model: CatalogModel, hardware: HardwareProfile, use_case: str) -> FitRecommendation:
        chosen_context = select_recommended_context(model, hardware, use_case)
        return analyze_fit(model, hardware, use_case, chosen_context)

    def _preferred_source(self, model: CatalogModel) -> dict[str, str]:
        sources = [dict(item) for item in model.gguf_sources if isinstance(item, dict)]
        if not sources:
            return {}
        lowered = {str(item.get("provider") or "").strip().lower(): item for item in sources}
        for provider in _SOURCE_PREFERENCE:
            if provider in lowered:
                return lowered[provider]
        return sources[0]

    def _choose_best_gguf_file(
        self,
        files: list[HuggingFaceRepoFile],
        target_quant: str,
    ) -> tuple[HuggingFaceRepoFile | None, bool]:
        valid = [item for item in files if validate_gguf_filename(item.filename)]
        if not valid:
            return None, True
        target = normalize_quant(target_quant)
        target_rank = quant_rank(target)
        candidates: list[tuple[int, int, int, int, str, HuggingFaceRepoFile]] = []
        for item in valid:
            quant = quant_from_filename(item.filename)
            if not quant:
                continue
            rank = quant_rank(quant)
            if target_rank >= 0 and rank >= 0 and rank < target_rank:
                continue
            if target_rank >= 0 and rank < 0:
                continue
            quant_gap = 0 if quant == target else max(rank - target_rank, 1)
            preferred_name = 0 if is_instruct_filename(item.filename) else 1
            size_bytes = item.size_bytes if item.size_bytes > 0 else 2**63 - 1
            candidates.append(
                (quant_gap, preferred_name, size_bytes, rank if rank >= 0 else 999, item.filename.lower(), item)
            )
        if not candidates:
            return None, True
        candidates.sort(key=lambda item: item[:5])
        best = candidates[0][5]
        manual_required = len(candidates) > 1 and candidates[0][:4] == candidates[1][:4]
        return best, manual_required

    def _detect_hardware_profile(self) -> HardwareProfile:
        total_ram, available_ram = detect_memory_gb()
        if psutil is not None:
            cpu_cores = int(psutil.cpu_count(logical=False) or psutil.cpu_count() or os.cpu_count() or 1)
        else:
            cpu_cores = int(os.cpu_count() or 1)
        cpu_name = platform.processor() or platform.machine() or "CPU"
        notes: list[str] = []
        gpus = detect_gpu_inventory()
        has_gpu = bool(gpus)
        gpu_vram = gpus[0]["vram_gb"] if gpus else None
        total_gpu_vram = sum(item.get("vram_gb") or 0.0 for item in gpus) if gpus else None
        gpu_name = str(gpus[0].get("name") or "") if gpus else ""
        backend = detect_backend(gpus)
        unified_memory = bool(
            platform.system().lower() == "darwin" and platform.machine().lower() in {"arm64", "aarch64"}
        )
        detected = total_ram > 0.0 and available_ram > 0.0
        if not detected:
            notes.append("Could not detect system memory. Recommendations are advisory only.")
        return HardwareProfile(
            total_ram_gb=round(max(total_ram, 0.0), 2),
            available_ram_gb=round(max(available_ram, 0.0), 2),
            total_cpu_cores=max(cpu_cores, 1),
            cpu_name=str(cpu_name),
            has_gpu=has_gpu,
            gpu_vram_gb=round(gpu_vram, 2) if gpu_vram is not None else None,
            total_gpu_vram_gb=round(total_gpu_vram, 2) if total_gpu_vram is not None else None,
            gpu_name=gpu_name,
            gpu_count=len(gpus),
            unified_memory=unified_memory,
            backend=backend,
            detected=detected,
            notes=notes,
        )

    def _apply_overrides(self, profile: HardwareProfile, settings: dict[str, Any]) -> HardwareProfile:
        if not bool(settings.get("hardware_override_enabled", False)):
            return profile
        total_ram = _coalesce_float(settings.get("hardware_override_total_ram_gb"), profile.total_ram_gb)
        available_ram = _coalesce_float(settings.get("hardware_override_available_ram_gb"), profile.available_ram_gb)
        gpu_name = str(settings.get("hardware_override_gpu_name") or profile.gpu_name or "").strip()
        gpu_vram = _coalesce_float(settings.get("hardware_override_gpu_vram_gb"), profile.gpu_vram_gb or 0.0)
        gpu_count = max(
            int(_coalesce_float(settings.get("hardware_override_gpu_count"), float(profile.gpu_count or 0))),
            0,
        )
        backend = (
            str(settings.get("hardware_override_backend") or profile.backend or "cpu_x86").strip().lower()
            or "cpu_x86"
        )
        unified_memory = bool(settings.get("hardware_override_unified_memory", profile.unified_memory))
        has_gpu = bool(gpu_count > 0 or gpu_vram > 0.0 or gpu_name)
        notes = list(profile.notes)
        notes.append("Hardware assumptions were manually overridden.")
        return HardwareProfile(
            total_ram_gb=round(max(total_ram, 0.0), 2),
            available_ram_gb=round(min(max(available_ram, 0.0), max(total_ram, available_ram)), 2),
            total_cpu_cores=profile.total_cpu_cores,
            cpu_name=profile.cpu_name,
            has_gpu=has_gpu,
            gpu_vram_gb=round(gpu_vram, 2) if has_gpu else None,
            total_gpu_vram_gb=round(gpu_vram * max(gpu_count, 1), 2) if has_gpu else None,
            gpu_name=gpu_name,
            gpu_count=gpu_count if has_gpu else 0,
            unified_memory=unified_memory,
            backend=backend,
            detected=profile.detected,
            override_enabled=True,
            notes=notes,
        )

    @staticmethod
    def _read_json(url: str) -> Any:
        req = request.Request(url, headers={"User-Agent": "Axiom/1.0"})
        with request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))


def detect_memory_gb() -> tuple[float, float]:
    if psutil is not None:
        vm = psutil.virtual_memory()
        return vm.total / _GIB, vm.available / _GIB
    if os.name == "nt":
        try:
            import ctypes

            class _MemoryStatus(ctypes.Structure):
                _fields_ = [
                    ("length", ctypes.c_ulong),
                    ("memory_load", ctypes.c_ulong),
                    ("total_phys", ctypes.c_ulonglong),
                    ("avail_phys", ctypes.c_ulonglong),
                    ("total_page_file", ctypes.c_ulonglong),
                    ("avail_page_file", ctypes.c_ulonglong),
                    ("total_virtual", ctypes.c_ulonglong),
                    ("avail_virtual", ctypes.c_ulonglong),
                    ("avail_extended_virtual", ctypes.c_ulonglong),
                ]

            status = _MemoryStatus()
            status.length = ctypes.sizeof(_MemoryStatus)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
            return status.total_phys / _GIB, status.avail_phys / _GIB
        except Exception:
            return 0.0, 0.0
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        available = os.sysconf("SC_AVPHYS_PAGES")
        return (pages * page_size) / _GIB, (available * page_size) / _GIB
    except Exception:
        return 0.0, 0.0


def detect_gpu_inventory() -> list[dict[str, Any]]:
    gpus = detect_nvidia_gpus()
    if gpus:
        return gpus
    if platform.system().lower() == "darwin":
        gpus = detect_apple_gpus()
        if gpus:
            return gpus
    if os.name == "nt":
        return detect_windows_gpus()
    return []


def detect_backend(gpus: list[dict[str, Any]]) -> str:
    if not gpus:
        return "cpu_arm" if platform.machine().lower() in {"arm64", "aarch64"} else "cpu_x86"
    name = str(gpus[0].get("name") or "").lower()
    if any(token in name for token in ("nvidia", "rtx", "tesla", "geforce", "quadro")):
        return "cuda"
    if platform.system().lower() == "darwin":
        return "metal"
    if "amd" in name or "radeon" in name:
        return "rocm"
    if "intel" in name:
        return "vulkan"
    return "vulkan"


def detect_nvidia_gpus() -> list[dict[str, Any]]:
    output = _run_command(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total",
            "--format=csv,noheader,nounits",
        ]
    )
    gpus: list[dict[str, Any]] = []
    for line in output.splitlines():
        parts = [part.strip() for part in line.split(",") if part.strip()]
        if len(parts) < 2:
            continue
        try:
            vram_gb = float(parts[1]) / 1024.0
        except ValueError:
            continue
        gpus.append({"name": parts[0], "vram_gb": round(vram_gb, 2)})
    return gpus


def detect_apple_gpus() -> list[dict[str, Any]]:
    output = _run_command(["system_profiler", "SPDisplaysDataType", "SPHardwareDataType", "-json"])
    if not output:
        return []
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return []
    gpus: list[dict[str, Any]] = []
    for item in payload.get("SPDisplaysDataType", []):
        if not isinstance(item, dict):
            continue
        name = str(item.get("sppci_model") or item.get("_name") or "Apple GPU")
        gpus.append({"name": name, "vram_gb": None})
    return gpus


def detect_windows_gpus() -> list[dict[str, Any]]:
    output = _run_command(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-CimInstance Win32_VideoController | Select-Object Name,AdapterRAM | ConvertTo-Json -Compress",
        ]
    )
    if not output:
        return []
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return []
    if isinstance(payload, dict):
        payload = [payload]
    gpus: list[dict[str, Any]] = []
    for item in payload if isinstance(payload, list) else []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("Name") or "").strip()
        if not name or "basic display" in name.lower():
            continue
        raw_vram = item.get("AdapterRAM")
        try:
            vram_gb = float(raw_vram) / _GIB if raw_vram not in (None, "", 0) else None
        except (TypeError, ValueError):
            vram_gb = None
        gpus.append({"name": name, "vram_gb": round(vram_gb, 2) if vram_gb else None})
    return gpus


def analyze_fit(
    model: CatalogModel,
    hardware: HardwareProfile,
    use_case: str,
    context_length: int,
) -> FitRecommendation:
    notes: list[str] = []
    if hardware.unified_memory and hardware.has_gpu:
        notes.append("Unified memory: GPU and RAM share the same pool.")
    preferred_gpu_budget = hardware.effective_gpu_memory_gb

    def choose_quant(budget_gb: float) -> tuple[str, float] | None:
        return model.best_quant_for_budget(budget_gb, context_length, _QUANT_HIERARCHY)

    default_mem_required = model.estimate_memory_gb(model.quantization, context_length)
    run_mode = "cpu_only"
    mem_required = default_mem_required
    mem_available = max(hardware.available_ram_gb, 0.0)

    if hardware.has_gpu and preferred_gpu_budget > 0.0:
        if hardware.unified_memory:
            chosen = choose_quant(preferred_gpu_budget)
            if chosen is not None:
                run_mode = "gpu"
                mem_required = chosen[1]
                mem_available = preferred_gpu_budget
            else:
                notes.append("Unified memory is too tight for the current context budget.")
                mem_required = default_mem_required
                mem_available = preferred_gpu_budget
                run_mode = "gpu"
        else:
            if model.is_moe:
                offloaded = pick_moe_path(model, hardware)
                if offloaded is not None:
                    run_mode, mem_required, mem_available, moe_notes = offloaded
                    notes.extend(moe_notes)
                elif chosen := choose_quant(preferred_gpu_budget):
                    run_mode = "gpu"
                    mem_required = chosen[1]
                    mem_available = preferred_gpu_budget
                    notes.append("GPU: model loaded into VRAM.")
                elif chosen := choose_quant(hardware.available_ram_gb):
                    run_mode = "cpu_offload"
                    mem_required = chosen[1]
                    mem_available = hardware.available_ram_gb
                    notes.append("GPU: insufficient VRAM, spilling to system RAM.")
                    notes.append("Performance will be significantly reduced.")
                else:
                    run_mode = "gpu"
                    mem_required = default_mem_required
                    mem_available = preferred_gpu_budget
                    notes.append("Insufficient VRAM and system RAM.")
            else:
                if chosen := choose_quant(preferred_gpu_budget):
                    run_mode = "gpu"
                    mem_required = chosen[1]
                    mem_available = preferred_gpu_budget
                    notes.append("GPU: model loaded into VRAM.")
                elif chosen := choose_quant(hardware.available_ram_gb):
                    run_mode = "cpu_offload"
                    mem_required = chosen[1]
                    mem_available = hardware.available_ram_gb
                    notes.append("GPU: insufficient VRAM, spilling to system RAM.")
                    notes.append("Performance will be significantly reduced.")
                else:
                    run_mode = "gpu"
                    mem_required = default_mem_required
                    mem_available = preferred_gpu_budget
                    notes.append("Insufficient VRAM and system RAM.")
    else:
        notes.append("CPU-only: model loaded into system RAM.")
        chosen = choose_quant(hardware.available_ram_gb)
        if chosen is not None and not model.is_moe:
            mem_required = chosen[1]
        else:
            mem_required = default_mem_required if not model.is_moe else model.min_ram_gb
        mem_available = hardware.available_ram_gb
        run_mode = "cpu_only"

    fit_level = score_fit(
        mem_required=mem_required,
        mem_available=mem_available,
        recommended=model.recommended_ram_gb,
        run_mode=run_mode,
    )
    quant_choice = model.best_quant_for_budget(mem_available, context_length, _QUANT_HIERARCHY)
    best_quant = quant_choice[0] if quant_choice is not None else model.quantization
    if best_quant != model.quantization:
        notes.append(f"Best quantization for hardware: {best_quant} (model default: {model.quantization}).")
    estimated_tps = estimate_tps(model, best_quant, hardware, run_mode)
    score_components = compute_score_components(model, best_quant, use_case, estimated_tps, mem_required, mem_available)
    score = weighted_score(score_components, use_case)
    if run_mode == "cpu_only":
        notes.append("No GPU detected; inference will be slow.")
    if run_mode in {"cpu_only", "cpu_offload"} and hardware.total_cpu_cores < 4:
        notes.append("Low CPU core count may bottleneck inference.")
    if estimated_tps > 0.0:
        notes.append(f"Baseline estimated speed: {estimated_tps:.1f} tok/s.")
    return FitRecommendation(
        catalog_name=model.catalog_name,
        fit_level=fit_level,
        run_mode=run_mode,
        score=score,
        best_quant=best_quant,
        estimated_tps=estimated_tps,
        memory_required_gb=round(mem_required, 2),
        memory_available_gb=round(mem_available, 2),
        recommended_context_length=int(context_length),
        notes=notes,
        score_components=score_components,
    )


def select_recommended_context(
    model: CatalogModel,
    hardware: HardwareProfile,
    use_case: str,
    candidates: tuple[int, ...] = _DEFAULT_CONTEXT_CANDIDATES,
) -> int:
    viable = [candidate for candidate in candidates if candidate <= model.context_length]
    if not viable:
        return max(min(model.context_length, candidates[-1]), 512)
    for candidate in viable:
        fit = analyze_fit(model, hardware, use_case, candidate)
        if fit.fit_level in {"perfect", "good"}:
            return candidate
    return viable[-1]


def pick_moe_path(
    model: CatalogModel,
    hardware: HardwareProfile,
) -> tuple[str, float, float, list[str]] | None:
    if not model.is_moe or not hardware.has_gpu:
        return None
    system_vram = hardware.effective_gpu_memory_gb
    notes: list[str] = []
    for quant in _QUANT_HIERARCHY:
        moe = moe_memory_for_quant(model, quant)
        if moe is None:
            continue
        active_vram, offloaded_ram = moe
        if active_vram <= system_vram and offloaded_ram <= hardware.available_ram_gb:
            notes.append(
                f"MoE: {model.active_experts or 0}/{model.num_experts or 0} experts active in VRAM ({active_vram:.1f} GB) at {quant}."
            )
            notes.append(f"Inactive experts offloaded to system RAM ({offloaded_ram:.1f} GB).")
            return "moe_offload", active_vram, system_vram, notes
    return None


def moe_memory_for_quant(model: CatalogModel, quant: str) -> tuple[float, float] | None:
    if not model.is_moe or model.active_parameters is None or model.parameters_raw is None:
        return None
    active_params = float(model.active_parameters)
    total_params = float(model.parameters_raw)
    bpp = quant_bpp(quant)
    active_vram = max(((active_params * bpp) / _GIB) * 1.1, 0.5)
    inactive_params = max(total_params - active_params, 0.0)
    offloaded_ram = (inactive_params * bpp) / _GIB
    return round(active_vram, 3), round(offloaded_ram, 3)


def score_fit(*, mem_required: float, mem_available: float, recommended: float, run_mode: str) -> str:
    if mem_required > mem_available:
        return "too_tight"
    if run_mode == "gpu":
        if recommended <= mem_available:
            return "perfect"
        if mem_available >= mem_required * 1.2:
            return "good"
        return "marginal"
    if run_mode in {"moe_offload", "cpu_offload"}:
        return "good" if mem_available >= mem_required * 1.2 else "marginal"
    return "marginal"


def fit_sort_rank(level: str) -> int:
    return {"perfect": 0, "good": 1, "marginal": 2, "too_tight": 3}.get(
        str(level or "").strip().lower(),
        99,
    )


def estimate_tps(model: CatalogModel, quant: str, hardware: HardwareProfile, run_mode: str) -> float:
    params = (
        max(float(model.active_parameters) / 1_000_000_000.0, 0.1)
        if model.is_moe and model.active_parameters
        else max(model.params_b(), 0.1)
    )
    if run_mode != "cpu_only":
        bandwidth = gpu_memory_bandwidth_gbps(hardware.gpu_name)
        if bandwidth is not None:
            model_gb = params * quant_bytes_per_param(quant)
            raw_tps = (bandwidth / max(model_gb, 0.1)) * 0.55
            factor = {"gpu": 1.0, "moe_offload": 0.8, "cpu_offload": 0.5}.get(run_mode, 1.0)
            return round(max(raw_tps * factor, 0.1), 1)
    k = _BACKEND_SPEED_K.get(hardware.backend or "cpu_x86", 70.0)
    if hardware.backend == "metal" and hardware.unified_memory:
        k = 160.0
    base = (k / params) * quant_speed_multiplier(quant)
    if hardware.total_cpu_cores >= 8:
        base *= 1.1
    if run_mode == "moe_offload":
        base *= 0.8
    elif run_mode == "cpu_offload":
        base *= 0.5
    elif run_mode == "cpu_only":
        cpu_k = 90.0 if hardware.backend == "cpu_arm" else 70.0
        base = (cpu_k / params) * quant_speed_multiplier(quant)
        if hardware.total_cpu_cores >= 8:
            base *= 1.1
        base *= 0.3
    return round(max(base, 0.1), 1)


def compute_score_components(
    model: CatalogModel,
    quant: str,
    use_case: str,
    estimated_tps: float,
    mem_required: float,
    mem_available: float,
) -> dict[str, float]:
    return {
        "quality": quality_score(model, quant, use_case),
        "speed": speed_score(estimated_tps, use_case),
        "fit": fit_score(mem_required, mem_available),
        "context": context_score(model, use_case),
    }


def quality_score(model: CatalogModel, quant: str, use_case: str) -> float:
    params = model.params_b()
    if params < 1.0:
        base = 30.0
    elif params < 3.0:
        base = 45.0
    elif params < 7.0:
        base = 60.0
    elif params < 10.0:
        base = 75.0
    elif params < 20.0:
        base = 82.0
    elif params < 40.0:
        base = 89.0
    else:
        base = 95.0
    name = model.name.lower()
    if "qwen" in name:
        family_bump = 2.0
    elif "deepseek" in name:
        family_bump = 3.0
    elif "llama" in name:
        family_bump = 2.0
    elif "mistral" in name or "mixtral" in name:
        family_bump = 1.0
    elif "gemma" in name:
        family_bump = 1.0
    elif "starcoder" in name:
        family_bump = 1.0
    else:
        family_bump = 0.0
    task_bump = 0.0
    if use_case == "coding" and ("code" in name or "starcoder" in name or "wizard" in name):
        task_bump = 6.0
    elif use_case == "reasoning" and params >= 13.0:
        task_bump = 5.0
    score = base + family_bump + quant_quality_penalty(quant) + task_bump
    return round(min(max(score, 0.0), 100.0), 1)


def speed_score(tps: float, use_case: str) -> float:
    target = _TARGET_SPEED.get(use_case, 40.0)
    return round(min(max((tps / target) * 100.0, 0.0), 100.0), 1)


def fit_score(required: float, available: float) -> float:
    if available <= 0.0 or required > available:
        return 0.0
    ratio = required / available
    if ratio <= 0.5:
        return round(60.0 + (ratio / 0.5) * 40.0, 1)
    if ratio <= 0.8:
        return 100.0
    if ratio <= 0.9:
        return 70.0
    return 50.0


def context_score(model: CatalogModel, use_case: str) -> float:
    target = _CONTEXT_TARGETS.get(use_case, 4096)
    if model.context_length >= target:
        return 100.0
    if model.context_length >= target / 2:
        return 70.0
    return 30.0


def weighted_score(score_components: dict[str, float], use_case: str) -> float:
    quality_weight, speed_weight, fit_weight, context_weight = _WEIGHTS.get(use_case, _WEIGHTS["general"])
    raw = (
        score_components["quality"] * quality_weight
        + score_components["speed"] * speed_weight
        + score_components["fit"] * fit_weight
        + score_components["context"] * context_weight
    )
    return round(raw, 1)


def normalize_use_case(raw_use_case: Any, *, name: str, capabilities: list[str]) -> str:
    text = " ".join([str(raw_use_case or ""), str(name or ""), " ".join(capabilities or [])]).lower()
    if "embedding" in text or " bge" in f" {text}" or "embed" in text:
        return "embedding"
    if any(hint in text for hint in _MULTIMODAL_HINTS):
        return "multimodal"
    if "reason" in text or "chain-of-thought" in text or "deepseek-r1" in text:
        return "reasoning"
    if "code" in text:
        return "coding"
    if "chat" in text or "instruction" in text or "instruct" in text:
        return "chat"
    return "general"


def quant_bpp(quant: str) -> float:
    return {
        "F16": 2.0,
        "BF16": 2.0,
        "Q8_0": 1.05,
        "Q6_K": 0.80,
        "Q5_K_M": 0.68,
        "Q4_K_M": 0.58,
        "Q4_0": 0.58,
        "Q3_K_M": 0.48,
        "Q2_K": 0.37,
    }.get(normalize_quant(quant), 0.58)


def quant_speed_multiplier(quant: str) -> float:
    return {
        "F16": 0.6,
        "BF16": 0.6,
        "Q8_0": 0.8,
        "Q6_K": 0.95,
        "Q5_K_M": 1.0,
        "Q4_K_M": 1.15,
        "Q4_0": 1.15,
        "Q3_K_M": 1.25,
        "Q2_K": 1.35,
    }.get(normalize_quant(quant), 1.15)


def quant_bytes_per_param(quant: str) -> float:
    return {
        "F16": 2.0,
        "BF16": 2.0,
        "Q8_0": 1.0,
        "Q6_K": 0.75,
        "Q5_K_M": 0.625,
        "Q4_K_M": 0.5,
        "Q4_0": 0.5,
        "Q3_K_M": 0.375,
        "Q2_K": 0.25,
    }.get(normalize_quant(quant), 0.5)


def quant_quality_penalty(quant: str) -> float:
    return {
        "Q6_K": -1.0,
        "Q5_K_M": -2.0,
        "Q4_K_M": -5.0,
        "Q4_0": -5.0,
        "Q3_K_M": -8.0,
        "Q2_K": -12.0,
    }.get(normalize_quant(quant), 0.0)


def quant_rank(quant: str) -> int:
    normalized = normalize_quant(quant)
    try:
        return _ALL_QUANT_ORDER.index(normalized)
    except ValueError:
        return -1


def quant_from_filename(filename: str) -> str:
    match = _QUANT_PATTERN.search(pathlib.Path(filename).stem)
    if not match:
        return ""
    return normalize_quant(match.group(1))


def normalize_quant(raw_quant: str) -> str:
    text = str(raw_quant or "").strip().upper().replace("-", "_")
    return {
        "Q5_K_S": "Q5_K_M",
        "Q4_K_S": "Q4_K_M",
        "Q3_K_S": "Q3_K_M",
        "Q4_K": "Q4_K_M",
        "Q5_K": "Q5_K_M",
        "Q3_K": "Q3_K_M",
    }.get(text, text)


def gpu_memory_bandwidth_gbps(gpu_name: str) -> float | None:
    name = str(gpu_name or "").strip().lower()
    if not name:
        return None
    for key, value in _GPU_BANDWIDTH.items():
        if key in name:
            return value
    return None


def validate_gguf_filename(filename: str) -> bool:
    text = str(filename or "").strip()
    if not text:
        return False
    candidate = pathlib.Path(text)
    if candidate.name != text:
        return False
    if candidate.is_absolute():
        return False
    if "/" in text or "\\" in text:
        return False
    return text.lower().endswith(".gguf")


def is_instruct_filename(filename: str) -> bool:
    lower = str(filename or "").lower()
    return any(token in lower for token in ("instruct", "chat", "_it", "-it", ".it."))


def _run_command(command: list[str]) -> str:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=10,
        )
    except Exception:
        return ""
    return str(completed.stdout or "").strip() if completed.returncode == 0 else ""


def _to_int(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _coalesce_float(value: Any, fallback: float) -> float:
    parsed = _to_float(value)
    return float(fallback if parsed is None else parsed)
