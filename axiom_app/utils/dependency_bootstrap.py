"""Startup dependency checks for the MVC GUI app.

This module performs a lightweight "importability" check for required
runtime packages and installs any missing dependencies automatically via pip.
"""

from __future__ import annotations

import importlib.util
import logging
import subprocess
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class DependencySpec:
    """Describes one runtime dependency.

    package: pip-installable name/specifier.
    module: importable module used to detect whether it is already installed.
    """

    package: str
    module: str


# Keep this list aligned with app capabilities; includes local backends so
# users can enable providers from Settings without manual pip setup.
STARTUP_DEPENDENCIES: tuple[DependencySpec, ...] = (
    DependencySpec("langchain>=0.3.0", "langchain"),
    DependencySpec("langchain-community>=0.3.0", "langchain_community"),
    DependencySpec("langchain-openai>=0.2.0", "langchain_openai"),
    DependencySpec("langchain-anthropic>=0.3.0", "langchain_anthropic"),
    DependencySpec("langchain-google-genai>=2.0.0", "langchain_google_genai"),
    DependencySpec("langchain-cohere>=0.3.0", "langchain_cohere"),
    DependencySpec("langchain-voyageai>=0.1.0", "langchain_voyageai"),
    DependencySpec("langchain-chroma>=0.1.0", "langchain_chroma"),
    DependencySpec("langchain-weaviate>=0.0.4", "langchain_weaviate"),
    DependencySpec("langchain-text-splitters>=0.3.0", "langchain_text_splitters"),
    DependencySpec("chromadb>=0.5.0", "chromadb"),
    DependencySpec("beautifulsoup4>=4.12.0", "bs4"),
    DependencySpec("tiktoken>=0.7.0", "tiktoken"),
    DependencySpec("weaviate-client>=4.0.0", "weaviate"),
    DependencySpec("sentence-transformers", "sentence_transformers"),
    DependencySpec("llama-cpp-python", "llama_cpp"),
)


def get_missing_startup_packages() -> list[str]:
    """Return package specifiers for dependencies missing from the environment."""

    missing: list[str] = []
    for dep in STARTUP_DEPENDENCIES:
        if importlib.util.find_spec(dep.module) is None:
            missing.append(dep.package)
    return missing


def ensure_startup_dependencies(logger: logging.Logger) -> None:
    """Ensure required runtime dependencies are installed.

    Installs missing packages in one pip call. Raises RuntimeError if
    installation fails so startup can surface a clear failure message.
    """

    missing = get_missing_startup_packages()
    if not missing:
        logger.info("Startup dependency check: all dependencies already installed.")
        return

    logger.warning("Missing startup dependencies detected: %s", ", ".join(missing))
    cmd = [sys.executable, "-m", "pip", "install", *missing]
    logger.info("Installing missing dependencies with pip...")

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
    )

    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        stdout = (proc.stdout or "").strip()
        detail = stderr or stdout or "Unknown pip failure"
        logger.error("Dependency installation failed: %s", detail)
        raise RuntimeError(f"Automatic dependency install failed: {detail}")

    logger.info("Startup dependency installation complete.")
