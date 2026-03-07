from __future__ import annotations

from pathlib import Path

from axiom_app import audit


def test_build_audit_command_defaults_to_fast_targets() -> None:
    command = audit.build_audit_command()

    assert "tests/test_live_weaviate_proof.py" not in command
    assert "tests/test_weaviate_support.py" in command


def test_build_audit_command_adds_live_targets_when_required() -> None:
    command = audit.build_audit_command(require_live_backends=True)
    env = audit.build_audit_env(require_live_backends=True)

    assert "tests/test_live_weaviate_proof.py" in command
    assert env["AXIOM_REQUIRE_LIVE_BACKENDS"] == "1"


def test_live_weaviate_ci_job_installs_required_extra() -> None:
    workflow = (
        Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"
    ).read_text(encoding="utf-8")

    assert "live-weaviate-proof:" in workflow
    assert "pip install -e .[dev,live-backends]" in workflow


def test_windows_runtime_smoke_runs_qt_smoke_tests() -> None:
    workflow = (
        Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"
    ).read_text(encoding="utf-8")

    assert "windows-runtime-smoke:" in workflow
    assert '& .\\.venv-ci\\Scripts\\python.exe -m pip install -e ".[dev]"' in workflow
    assert "-m pytest -q tests/test_app_view_smoke.py" in workflow
