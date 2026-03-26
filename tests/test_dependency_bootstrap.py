from __future__ import annotations

import logging
import pathlib
import subprocess

import metis_app.app as mvc_app
from metis_app.utils import dependency_bootstrap as bootstrap


def test_install_packages_skips_empty_input(monkeypatch):
    called = {"ran": False}

    def fake_run(*_args, **_kwargs):
        called["ran"] = True
        raise AssertionError("pip should not be called for an empty package list")

    monkeypatch.setattr(bootstrap.subprocess, "run", fake_run)

    bootstrap.install_packages([], logger=logging.getLogger("test"))

    assert called["ran"] is False


def test_install_packages_normalizes_and_reports_progress(monkeypatch):
    calls: list[tuple[list[str], bool, bool, bool]] = []
    progress: list[str] = []

    def fake_run(cmd, *, capture_output, text, check):
        calls.append((cmd, capture_output, text, check))
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    monkeypatch.setattr(bootstrap.subprocess, "run", fake_run)

    bootstrap.install_packages(
        [" sentence-transformers ", "", "llama-cpp-python"],
        logger=logging.getLogger("test"),
        progress_callback=progress.append,
    )

    assert calls == [
        (
            [bootstrap.sys.executable, "-m", "pip", "install", "sentence-transformers", "llama-cpp-python"],
            True,
            True,
            False,
        )
    ]
    assert progress == [
        "Installing packages: sentence-transformers, llama-cpp-python",
        "Package installation complete.",
    ]


def test_install_packages_raises_on_pip_failure(monkeypatch):
    def fake_run(cmd, *, capture_output, text, check):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="resolver exploded")

    monkeypatch.setattr(bootstrap.subprocess, "run", fake_run)

    try:
        bootstrap.install_packages(["langchain-openai"], logger=logging.getLogger("test"))
    except RuntimeError as exc:
        assert str(exc) == "resolver exploded"
    else:
        raise AssertionError("install_packages should raise when pip fails")


def test_app_startup_no_longer_bootstraps_dependencies() -> None:
    source = pathlib.Path(mvc_app.__file__).read_text(encoding="utf-8")

    assert "ensure_startup_dependencies" not in source
    assert "dependency-bootstrap" not in source
    assert "Checking dependencies in background" not in source
