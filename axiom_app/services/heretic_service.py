"""axiom_app.services.heretic_service — Heretic abliteration integration.

Wraps the ``heretic-llm`` CLI to abliterate a HuggingFace model and then
converts the result to GGUF format using llama.cpp's ``convert_hf_to_gguf.py``.

The entire pipeline runs as subprocess calls so that:
 1. The AGPL-licensed heretic code is never imported into Axiom's MIT process.
 2. Long-running GPU work does not block the Python GIL.
"""

from __future__ import annotations

import logging
import os
import pathlib
import shutil
import subprocess
import sys
from typing import Any, Callable

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Availability checks
# ---------------------------------------------------------------------------

def is_heretic_available() -> bool:
    """Return *True* if the ``heretic`` CLI is on ``$PATH``."""
    return shutil.which("heretic") is not None


def find_convert_script() -> str | None:
    """Locate llama.cpp's ``convert_hf_to_gguf.py``.

    Search order:
    1. ``LLAMA_CPP_CONVERT_SCRIPT`` env-var (explicit override).
    2. Alongside the ``llama-cpp-python`` package (vendored copy).
    3. Common clone locations (``~/llama.cpp``, ``./llama.cpp``).
    """
    env = os.environ.get("LLAMA_CPP_CONVERT_SCRIPT")
    if env and pathlib.Path(env).is_file():
        return env

    try:
        import llama_cpp  # noqa: F401
        pkg_dir = pathlib.Path(llama_cpp.__file__).resolve().parent
        for candidate in (
            pkg_dir / "convert_hf_to_gguf.py",
            pkg_dir.parent / "convert_hf_to_gguf.py",
            pkg_dir.parent / "llama_cpp" / "convert_hf_to_gguf.py",
        ):
            if candidate.is_file():
                return str(candidate)
    except ImportError:
        pass

    for base in (
        pathlib.Path.home() / "llama.cpp",
        pathlib.Path("llama.cpp"),
        pathlib.Path("/opt/llama.cpp"),
    ):
        candidate = base / "convert_hf_to_gguf.py"
        if candidate.is_file():
            return str(candidate)

    return None


# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------

class HereticService:
    """Orchestrates abliteration via heretic CLI + GGUF conversion."""

    def __init__(self, output_root: str | pathlib.Path | None = None) -> None:
        self.output_root = pathlib.Path(
            output_root or pathlib.Path.home() / ".axiom_heretic"
        )
        self.output_root.mkdir(parents=True, exist_ok=True)

    # ----- pre-flight -----

    def preflight(self) -> dict[str, Any]:
        """Check that all required tools are installed.

        Returns a dict with ``ready`` (bool), ``heretic`` (bool),
        ``convert_script`` (str | None), and ``errors`` (list[str]).
        """
        errors: list[str] = []
        heretic_ok = is_heretic_available()
        if not heretic_ok:
            errors.append(
                "heretic CLI not found. Install with: pip install heretic-llm"
            )
        convert = find_convert_script()
        if not convert:
            errors.append(
                "convert_hf_to_gguf.py not found. Clone llama.cpp or set "
                "LLAMA_CPP_CONVERT_SCRIPT env-var."
            )
        return {
            "ready": heretic_ok and convert is not None,
            "heretic": heretic_ok,
            "convert_script": convert,
            "errors": errors,
        }

    # ----- abliteration -----

    def abliterate(
        self,
        hf_model_id: str,
        *,
        post_message: Callable[[dict[str, Any]], None] | None = None,
        extra_args: list[str] | None = None,
    ) -> pathlib.Path:
        """Run ``heretic <hf_model_id>`` and return the output directory.

        Parameters
        ----------
        hf_model_id:
            HuggingFace model identifier, e.g. ``meta-llama/Llama-3.1-8B-Instruct``.
        post_message:
            Optional callback for progress updates (``{"type": "status", "text": ...}``).
        extra_args:
            Additional CLI flags passed to heretic (e.g. ``["--bnb-4bit"]``).

        Returns the path to the abliterated model directory (safetensors).
        """
        def _status(text: str) -> None:
            _log.info("heretic: %s", text)
            if post_message:
                post_message({"type": "status", "text": text})

        output_dir = self.output_root / _safe_dirname(hf_model_id)
        output_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            sys.executable, "-m", "heretic",
            hf_model_id,
            "--output-dir", str(output_dir),
        ]
        if extra_args:
            cmd.extend(extra_args)

        _status(f"Starting abliteration of {hf_model_id}")
        _log.info("Running: %s", " ".join(cmd))

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                _status(line)
        proc.wait()
        if proc.returncode != 0:
            raise RuntimeError(
                f"heretic exited with code {proc.returncode}"
            )

        _status("Abliteration complete")
        return output_dir

    # ----- GGUF conversion -----

    def convert_to_gguf(
        self,
        model_dir: str | pathlib.Path,
        *,
        output_path: str | pathlib.Path | None = None,
        post_message: Callable[[dict[str, Any]], None] | None = None,
    ) -> pathlib.Path:
        """Convert an abliterated HF model directory to GGUF format.

        Uses llama.cpp's ``convert_hf_to_gguf.py`` script.

        Returns the path to the generated ``.gguf`` file.
        """
        def _status(text: str) -> None:
            _log.info("gguf-convert: %s", text)
            if post_message:
                post_message({"type": "status", "text": text})

        convert_script = find_convert_script()
        if not convert_script:
            raise FileNotFoundError(
                "convert_hf_to_gguf.py not found. Clone llama.cpp or set "
                "LLAMA_CPP_CONVERT_SCRIPT."
            )

        model_dir = pathlib.Path(model_dir)
        if output_path is None:
            output_path = model_dir / f"{model_dir.name}.gguf"
        output_path = pathlib.Path(output_path)

        cmd = [
            sys.executable, convert_script,
            str(model_dir),
            "--outfile", str(output_path),
            "--outtype", "f16",
        ]
        _status(f"Converting to GGUF: {output_path.name}")
        _log.info("Running: %s", " ".join(cmd))

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                _status(line)
        proc.wait()
        if proc.returncode != 0:
            raise RuntimeError(
                f"convert_hf_to_gguf.py exited with code {proc.returncode}"
            )

        if not output_path.is_file():
            raise FileNotFoundError(f"Expected GGUF output not found: {output_path}")

        _status(f"GGUF conversion complete: {output_path.name}")
        return output_path

    # ----- full pipeline -----

    def run_pipeline(
        self,
        hf_model_id: str,
        *,
        post_message: Callable[[dict[str, Any]], None] | None = None,
        gguf_output_dir: str | pathlib.Path | None = None,
        extra_heretic_args: list[str] | None = None,
    ) -> pathlib.Path:
        """Abliterate a HuggingFace model and convert the result to GGUF.

        Returns the path to the final ``.gguf`` file.
        """
        abliterated_dir = self.abliterate(
            hf_model_id,
            post_message=post_message,
            extra_args=extra_heretic_args,
        )

        dest_dir = pathlib.Path(gguf_output_dir) if gguf_output_dir else abliterated_dir
        dest_dir.mkdir(parents=True, exist_ok=True)
        gguf_name = f"{_safe_dirname(hf_model_id)}-abliterated.gguf"
        gguf_path = dest_dir / gguf_name

        gguf_path = self.convert_to_gguf(
            abliterated_dir,
            output_path=gguf_path,
            post_message=post_message,
        )
        return gguf_path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_dirname(model_id: str) -> str:
    """Turn ``org/Model-Name`` into a filesystem-safe directory name."""
    return model_id.replace("/", "__").replace("\\", "__")
