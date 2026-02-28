"""LLM backend adapters used by the controller.

This module intentionally keeps heavy dependencies optional.  The local GGUF
adapter lazily imports ``llama_cpp`` only when it is first initialised.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LocalGGUFConfig:
    """Configuration for a local llama.cpp-style GGUF model."""

    model_path: str
    context_length: int = 2048
    gpu_layers: int = 0
    threads: int = 0


class LocalGGUFBackend:
    """Thin adapter around ``llama_cpp.Llama`` for text completion."""

    def __init__(self, config: LocalGGUFConfig) -> None:
        model_path = str(config.model_path).strip()
        if not model_path:
            raise ValueError("local_gguf_model_path is empty")

        resolved = Path(model_path).expanduser()
        if not resolved.exists():
            raise FileNotFoundError(f"GGUF model file not found: {resolved}")

        try:
            from llama_cpp import Llama  # type: ignore
        except Exception as exc:  # pragma: no cover - import depends on env
            raise RuntimeError(
                "llama-cpp-python is not installed. Install it to use llm_provider=local_gguf."
            ) from exc

        n_threads_raw = int(config.threads)
        n_threads: int | None = n_threads_raw if n_threads_raw > 0 else None

        self._llama = Llama(
            model_path=str(resolved),
            n_ctx=int(config.context_length),
            n_gpu_layers=int(config.gpu_layers),
            n_threads=n_threads,
        )
        self._config = config

    @property
    def config(self) -> LocalGGUFConfig:
        return self._config

    def generate(self, prompt: str, *, max_tokens: int, temperature: float) -> str:
        """Run a non-chat completion and return rendered assistant text."""
        response: dict[str, Any] = self._llama(
            prompt,
            max_tokens=int(max_tokens),
            temperature=float(temperature),
            echo=False,
        )
        choices = response.get("choices") or []
        if not choices:
            return ""
        text = choices[0].get("text", "")
        return str(text).strip()
