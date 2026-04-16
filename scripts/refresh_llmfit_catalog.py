"""Refresh the bundled GGUF catalog snapshot from llmfit upstream.

Fetches the upstream ``hf_models.json`` and latest commit metadata from
AlexsJones/llmfit on GitHub, then rewrites
``metis_app/assets/llmfit_gguf_catalog.json`` with a normalized snapshot.

Run this manually when a new llmfit release lands; there is no scheduled
trigger. Output must be reviewed and committed.

Invocation:
    python scripts/refresh_llmfit_catalog.py
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any
from urllib import request


UPSTREAM_MODELS_URL = "https://raw.githubusercontent.com/AlexsJones/llmfit/main/data/hf_models.json"
UPSTREAM_COMMIT_URL = "https://api.github.com/repos/AlexsJones/llmfit/commits/main"
OUTPUT_PATH = Path(__file__).resolve().parents[1] / "metis_app" / "assets" / "llmfit_gguf_catalog.json"
USER_AGENT = "MetisCatalogRefresh/1.0"
MULTIMODAL_HINTS = ("vision", "vl", "vlm", "multimodal")


def _read_json(url: str) -> Any:
    req = request.Request(url, headers={"User-Agent": USER_AGENT})
    with request.urlopen(req, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def normalize_use_case(raw_use_case: Any, *, name: str, capabilities: list[str]) -> str:
    text = " ".join([str(raw_use_case or ""), str(name or ""), " ".join(capabilities or [])]).lower()
    if "embedding" in text or " bge" in f" {text}" or "embed" in text:
        return "embedding"
    if any(hint in text for hint in MULTIMODAL_HINTS):
        return "multimodal"
    if "reason" in text or "chain-of-thought" in text or "deepseek-r1" in text:
        return "reasoning"
    if "code" in text:
        return "coding"
    if "chat" in text or "instruction" in text or "instruct" in text:
        return "chat"
    return "general"


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


def normalized_model_row(row: dict[str, Any]) -> dict[str, Any] | None:
    gguf_sources = [dict(item) for item in (row.get("gguf_sources") or []) if isinstance(item, dict)]
    if not gguf_sources:
        return None
    capabilities = [str(item) for item in (row.get("capabilities") or [])]
    use_case = normalize_use_case(row.get("use_case"), name=str(row.get("name") or ""), capabilities=capabilities)
    if use_case in {"embedding", "multimodal"}:
        return None
    name = str(row.get("name") or "").strip()
    if not name:
        return None
    parameter_count = str(row.get("parameter_count") or "").strip()
    if not parameter_count:
        parameter_count = _infer_parameter_count(name)
    return {
        "name": name,
        "provider": str(row.get("provider") or ""),
        "parameter_count": parameter_count,
        "parameters_raw": _coerce_int(row.get("parameters_raw")),
        "min_ram_gb": float(row.get("min_ram_gb") or 0.0),
        "recommended_ram_gb": float(row.get("recommended_ram_gb") or 0.0),
        "min_vram_gb": _coerce_float(row.get("min_vram_gb")),
        "quantization": normalize_quant(str(row.get("quantization") or "Q4_K_M")),
        "context_length": max(int(row.get("context_length") or 2048), 256),
        "use_case": use_case,
        "capabilities": capabilities,
        "architecture": str(row.get("architecture") or ""),
        "release_date": str(row.get("release_date") or ""),
        "is_moe": bool(row.get("is_moe", False)),
        "num_experts": _coerce_int(row.get("num_experts")),
        "active_experts": _coerce_int(row.get("active_experts")),
        "active_parameters": _coerce_int(row.get("active_parameters")),
        "gguf_sources": gguf_sources,
    }


def _coerce_int(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _infer_parameter_count(name: str) -> str:
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*[Bb]", str(name or ""))
    return match.group(1) + "B" if match else ""


def build_snapshot() -> dict[str, Any]:
    rows = _read_json(UPSTREAM_MODELS_URL)
    commit = _read_json(UPSTREAM_COMMIT_URL)
    models = [normalized_model_row(row) for row in rows if isinstance(row, dict)]
    filtered = [item for item in models if item is not None]
    filtered.sort(key=lambda row: (row["name"].lower(), row["provider"].lower()))
    return {
        "meta": {
            "source_repo": "AlexsJones/llmfit",
            "source_models_url": UPSTREAM_MODELS_URL,
            "source_commit": str(((commit or {}).get("sha") or "")),
            "source_commit_date": str((((commit or {}).get("commit") or {}).get("author") or {}).get("date") or ""),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "filters": [
                "keep rows with gguf_sources",
                "exclude embedding-only models",
                "exclude multimodal or vision-required models",
                "normalize quant aliases and use_case labels",
            ],
        },
        "models": filtered,
    }


def main() -> None:
    snapshot = build_snapshot()
    OUTPUT_PATH.write_text(json.dumps(snapshot, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(snapshot['models'])} models to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
