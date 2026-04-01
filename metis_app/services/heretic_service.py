"""metis_app.services.heretic_service — Heretic abliteration integration.

Wraps the ``heretic-llm`` CLI to abliterate a HuggingFace model and then
converts the result to GGUF format using llama.cpp's ``convert_hf_to_gguf.py``.

The entire pipeline runs as subprocess calls so that:
 1. The AGPL-licensed heretic code is never imported into METIS's MIT process.
 2. Long-running GPU work does not block the Python GIL.
"""

from __future__ import annotations

import collections
import logging
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from typing import Any, Callable

from metis_app.utils.background import CancelToken

_log = logging.getLogger(__name__)

# Maximum recent output lines kept for error diagnostics.
_ERROR_TAIL_LINES = 5

# Rich markup stripper — removes tags like [bold], [/], [blue underline], etc.
_RICH_TAG_RE = re.compile(r"\[/?[^\]]*\]")

_VALID_OUTTYPES: frozenset[str] = frozenset(
    {"f16", "bf16", "f32", "q4_0", "q4_k_m", "q6_k", "q8_0", "auto"}
)


def _strip_rich(text: str) -> str:
    """Strip Rich markup tags from a line of heretic output."""
    return _RICH_TAG_RE.sub("", text)

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
# Subprocess helper
# ---------------------------------------------------------------------------

def _run_streaming(
    cmd: list[str],
    *,
    label: str,
    status_cb: Callable[[str], None],
    cancel_token: CancelToken | None = None,
    cwd: str | pathlib.Path | None = None,
    timeout_seconds: int | None = None,
) -> None:
    """Run *cmd* streaming stdout line-by-line through *status_cb*.

    Raises ``RuntimeError`` on non-zero exit or cancellation.  The error
    message includes the last few output lines for diagnostics.
    """
    _log.info("Running: %s", " ".join(cmd))
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        cwd=str(cwd) if cwd else None,
    )
    assert proc.stdout is not None
    tail: collections.deque[str] = collections.deque(maxlen=_ERROR_TAIL_LINES)

    # Optional wall-clock watchdog.
    timed_out = [False]
    if timeout_seconds is not None:
        def _kill() -> None:
            if proc.poll() is None:
                _log.warning("%s: timeout after %ds — killing", label, timeout_seconds)
                timed_out[0] = True
                proc.kill()
        _watchdog: threading.Timer | None = threading.Timer(timeout_seconds, _kill)
        _watchdog.start()
    else:
        _watchdog = None

    try:
        for line in proc.stdout:
            if cancel_token is not None and cancel_token.cancelled:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                raise RuntimeError(f"{label} cancelled by user")
            line = line.rstrip()
            if line:
                tail.append(line)
                status_cb(line)
        proc.wait()
    except Exception:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        raise
    finally:
        if _watchdog is not None:
            _watchdog.cancel()

    if proc.returncode != 0:
        detail = "\n".join(tail)
        prefix = (
            f"heretic timed out after {timeout_seconds}s — "
            if timed_out[0]
            else ""
        )
        raise RuntimeError(
            f"{prefix}{label} exited with code {proc.returncode}\n{detail}"
        )


def _run_heretic_interactive(
    cmd: list[str],
    *,
    save_path: pathlib.Path,
    bnb_4bit: bool,
    label: str = "heretic",
    status_cb: Callable[[str], None],
    cancel_token: CancelToken | None = None,
    cwd: pathlib.Path | None = None,
    timeout_seconds: int = 7200,
) -> None:
    """Run heretic with automated stdin responses for interactive prompts.

    ``heretic-llm`` is an interactive CLI tool (questionary / prompt_toolkit)
    that presents several prompts after optimization completes:

    1. "Which trial do you want to use?"  → ``\\n`` accepts first Pareto trial.
    2. "What do you want to do?"           → ``\\n`` selects *Save to local folder*.
    3. "How do you want to proceed?"       → ``\\n`` (only when bnb_4bit; selects merge).
    4. "Path to the folder:"               → save_path + ``\\n``.

    The checkpoint directory is removed before calling this function so that
    no extra prompt appears asking whether to continue a previous run.  After
    "Model saved to" is detected in stdout the subprocess is sent SIGTERM —
    the model is already on disk at that point and the exit menu is skipped.

    .. note::
        AGPL isolation — heretic-llm is AGPL-3.0.  This function invokes it
        exclusively via subprocess so that no AGPL code ever executes inside
        METIS's MIT-licensed process.  Subprocess invocation is permissible
        under AGPL §13 because METIS does not distribute a modified copy of
        heretic-llm.
    """
    # Build pre-buffered stdin response sequence.
    # With a fresh checkpoint directory the prompt order is deterministic:
    #   [Q1] trial selection  → \n (first Pareto-optimal trial)
    #   [Q2] action choice    → \n ("Save the model to a local folder")
    #   [Q3] merge strategy   → \n (only if bnb_4bit; "Merge LoRA into full model")
    #   [Q4] path input       → <save_path>\n
    responses = ["\n", "\n"]              # Q1 + Q2
    if bnb_4bit:
        responses.append("\n")            # Q3 merge strategy
    responses.append(f"{save_path}\n")   # Q4 save path
    stdin_text = "".join(responses)

    _log.info("Running: %s", " ".join(cmd))
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.PIPE,
        text=True,
        bufsize=1,
        cwd=str(cwd) if cwd else None,
    )
    assert proc.stdout is not None
    assert proc.stdin is not None

    # Write all stdin responses upfront then close so questionary sees EOF
    # after consuming the expected responses.
    def _write_stdin() -> None:
        try:
            proc.stdin.write(stdin_text)  # type: ignore[union-attr]
            proc.stdin.flush()            # type: ignore[union-attr]
            proc.stdin.close()            # type: ignore[union-attr]
        except (BrokenPipeError, OSError):
            pass

    stdin_thread = threading.Thread(target=_write_stdin, daemon=True)
    stdin_thread.start()

    # Wall-clock timeout watchdog.
    def _kill_on_timeout() -> None:
        if proc.poll() is None:
            _log.warning("%s: timeout after %ds — killing", label, timeout_seconds)
            proc.kill()

    watchdog = threading.Timer(timeout_seconds, _kill_on_timeout)
    watchdog.start()

    tail: collections.deque[str] = collections.deque(maxlen=_ERROR_TAIL_LINES)
    model_saved = False
    try:
        for line in proc.stdout:
            if cancel_token is not None and cancel_token.cancelled:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                raise RuntimeError(f"{label} cancelled by user")
            line = line.rstrip()
            if line:
                tail.append(line)
                status_cb(line)
            # Detect save confirmation; terminate — model is on disk.
            if "Model saved to" in _strip_rich(line):
                _log.info("heretic: model saved — terminating interactive session")
                model_saved = True
                proc.terminate()
                break
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
    except Exception:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        raise
    finally:
        watchdog.cancel()
        stdin_thread.join(timeout=2)

    # When we terminated after a successful save the return code is non-zero
    # (SIGTERM = -15 on POSIX; 1 on Windows).  Treat this as success.
    if model_saved:
        return

    if proc.returncode != 0:
        detail = "\n".join(tail)
        raise RuntimeError(
            f"{label} exited with code {proc.returncode}\n{detail}"
        )


# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------

class HereticService:
    """Orchestrates abliteration via heretic CLI + GGUF conversion."""

    def __init__(
        self,
        output_root: str | pathlib.Path | None = None,
        timeout_seconds: int = 7200,
    ) -> None:
        self.output_root = pathlib.Path(
            output_root or pathlib.Path.home() / ".metis_heretic"
        )
        self.output_root.mkdir(parents=True, exist_ok=True)
        # Wall-clock timeout for both the abliteration and GGUF conversion steps.
        self.timeout_seconds = timeout_seconds

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
        cancel_token: CancelToken | None = None,
        bnb_4bit: bool = False,
        extra_args: list[str] | None = None,
    ) -> pathlib.Path:
        """Run ``heretic <hf_model_id>`` and return the saved model directory.

        Parameters
        ----------
        hf_model_id:
            HuggingFace model identifier, e.g. ``meta-llama/Llama-3.1-8B-Instruct``.
        post_message:
            Optional callback for progress updates (``{"type": "status", "text": ...}``).
        cancel_token:
            If provided, the subprocess is terminated when cancellation is requested.
        bnb_4bit:
            Enable 4-bit bitsandbytes quantization.  Written to a ``config.toml``
            in the working directory.  heretic-llm has **no** ``--bnb-4bit`` CLI
            flag; quantization is controlled via ``quantization = "bnb_4bit"`` in
            ``config.toml``.
        extra_args:
            Additional valid heretic CLI flags (e.g. ``["--plot-residuals"]``).
            Do **not** pass ``--output-dir`` here — it is not a valid heretic flag;
            the save path is handled interactively via stdin.

        Returns
        -------
        pathlib.Path
            The directory where heretic saved the abliterated model weights.
        """
        def _status(text: str) -> None:
            _log.info("heretic: %s", text)
            if post_message:
                post_message({"type": "status", "text": text})

        # AGPL isolation: heretic-llm is AGPL-3.0.  We invoke it exclusively
        # via subprocess so that AGPL code never runs inside METIS's MIT-licensed
        # process.  Subprocess invocation is permissible under AGPL §13 because
        # METIS does not distribute a modified copy of heretic-llm.
        heretic_bin = shutil.which("heretic")
        if heretic_bin is None:
            _log.warning(
                "heretic not found on PATH; falling back to 'python -m heretic'. "
                "Install with: pip install heretic-llm"
            )
            cmd: list[str] = [sys.executable, "-m", "heretic", "--model", hf_model_id]
        else:
            cmd = [heretic_bin, "--model", hf_model_id]

        if extra_args:
            cmd.extend(extra_args)

        output_dir = self.output_root / _safe_dirname(hf_model_id)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Write config.toml: quantization is a config-file option in heretic,
        # not a CLI flag.  ``quantization = "bnb_4bit"`` enables bitsandbytes
        # 4-bit loading; ``"none"`` disables it.
        config_lines = [
            f'quantization = "{"bnb_4bit" if bnb_4bit else "none"}"',
            'study_checkpoint_dir = "checkpoints"',
        ]
        _toml_content = "\n".join(config_lines) + "\n"
        _toml_path = output_dir / "config.toml"
        with tempfile.NamedTemporaryFile(
            mode="w",
            dir=_toml_path.parent,
            suffix=".tmp",
            delete=False,
            encoding="utf-8",
        ) as _tmp:
            _tmp.write(_toml_content)
            _tmp_path = _tmp.name
        os.replace(_tmp_path, _toml_path)

        # Remove any previous checkpoint so heretic starts fresh and no extra
        # "continue previous run?" prompt appears before the trial-selection menu.
        checkpoint_dir = output_dir / "checkpoints"
        if checkpoint_dir.exists():
            shutil.rmtree(checkpoint_dir)

        # heretic saves the abliterated weights to this subdirectory.
        save_path = output_dir / "model"
        save_path.mkdir(parents=True, exist_ok=True)

        _status(f"Starting abliteration of {hf_model_id}")
        _run_heretic_interactive(
            cmd,
            save_path=save_path,
            bnb_4bit=bnb_4bit,
            label="heretic",
            status_cb=_status,
            cancel_token=cancel_token,
            cwd=output_dir,
            timeout_seconds=self.timeout_seconds,
        )

        _status("Abliteration complete")
        return save_path

    # ----- GGUF conversion -----

    def convert_to_gguf(
        self,
        model_dir: str | pathlib.Path,
        *,
        outtype: str = "f16",
        output_path: str | pathlib.Path | None = None,
        post_message: Callable[[dict[str, Any]], None] | None = None,
        cancel_token: CancelToken | None = None,
    ) -> pathlib.Path:
        """Convert an abliterated HF model directory to GGUF format.

        Uses llama.cpp's ``convert_hf_to_gguf.py`` script.

        Parameters
        ----------
        outtype:
            Output quantization type passed to ``convert_hf_to_gguf.py``
            (e.g. ``"f16"``, ``"q4_k_m"``, ``"bf16"``).  Defaults to ``"f16"``.

        Returns the path to the generated ``.gguf`` file.
        """
        def _status(text: str) -> None:
            _log.info("gguf-convert: %s", text)
            if post_message:
                post_message({"type": "status", "text": text})

        if outtype not in _VALID_OUTTYPES:
            raise ValueError(
                f"Invalid outtype {outtype!r}; must be one of {sorted(_VALID_OUTTYPES)}"
            )

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
            "--outtype", outtype,
        ]
        _status(f"Converting to GGUF ({outtype}): {output_path.name}")
        _run_streaming(
            cmd,
            label="convert_hf_to_gguf.py",
            status_cb=_status,
            cancel_token=cancel_token,
            timeout_seconds=self.timeout_seconds,
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
        cancel_token: CancelToken | None = None,
        bnb_4bit: bool = False,
        outtype: str = "f16",
        gguf_output_dir: str | pathlib.Path | None = None,
        extra_heretic_args: list[str] | None = None,
    ) -> pathlib.Path:
        """Abliterate a HuggingFace model and convert the result to GGUF.

        Returns the path to the final ``.gguf`` file.
        """
        abliterated_dir = self.abliterate(
            hf_model_id,
            post_message=post_message,
            cancel_token=cancel_token,
            bnb_4bit=bnb_4bit,
            extra_args=extra_heretic_args,
        )

        dest_dir = (
            pathlib.Path(gguf_output_dir) if gguf_output_dir else abliterated_dir.parent
        )
        dest_dir.mkdir(parents=True, exist_ok=True)
        gguf_name = f"{_safe_dirname(hf_model_id)}-abliterated.gguf"
        gguf_path = dest_dir / gguf_name

        gguf_path = self.convert_to_gguf(
            abliterated_dir,
            outtype=outtype,
            output_path=gguf_path,
            post_message=post_message,
            cancel_token=cancel_token,
        )
        return gguf_path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_dirname(model_id: str) -> str:
    """Turn ``org/Model-Name`` into a filesystem-safe directory name."""
    return model_id.replace("/", "__").replace("\\", "__")
