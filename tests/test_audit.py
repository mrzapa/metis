from __future__ import annotations

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
