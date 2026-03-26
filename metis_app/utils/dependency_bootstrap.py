"""Helpers for explicit dependency installation flows."""

from __future__ import annotations

import logging
import subprocess
import sys
from typing import Callable


def install_packages(
    packages: list[str],
    *,
    logger: logging.Logger,
    progress_callback: Callable[[str], None] | None = None,
) -> None:
    """Install *packages* with pip and emit optional progress lines."""

    normalized = [str(item).strip() for item in packages if str(item).strip()]
    if not normalized:
        return
    if callable(progress_callback):
        progress_callback(f"Installing packages: {', '.join(normalized)}")
    logger.info("Installing packages with pip: %s", ", ".join(normalized))
    proc = subprocess.run(
        [sys.executable, "-m", "pip", "install", *normalized],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        stdout = (proc.stdout or "").strip()
        detail = stderr or stdout or "Unknown pip failure"
        logger.error("Package installation failed: %s", detail)
        raise RuntimeError(detail)
    if callable(progress_callback):
        progress_callback("Package installation complete.")
