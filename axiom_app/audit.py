"""Parity audit entrypoint for the MVC runtime."""

from __future__ import annotations

import argparse
import importlib.util
import os
import subprocess
import sys

PARITY_AUDIT_TARGETS = [
    "tests/test_session_repository.py",
    "tests/test_app_controller_persistence.py",
    "tests/test_index_service_and_cli.py",
    "tests/test_parity_services.py",
    "tests/test_response_pipeline_and_wizard.py",
    "tests/test_weaviate_support.py",
]
LIVE_BACKEND_AUDIT_TARGETS = ["tests/test_live_weaviate_proof.py"]
_REQUIRE_LIVE_ENV = "AXIOM_REQUIRE_LIVE_BACKENDS"
_STRICT_ENV = "AXIOM_PARITY_REQUIRE_LIVE_BACKENDS"

def build_audit_command(*, require_live_backends: bool = False) -> list[str]:
    targets = list(PARITY_AUDIT_TARGETS)
    if require_live_backends:
        targets.extend(LIVE_BACKEND_AUDIT_TARGETS)
    return [sys.executable, "-m", "pytest", "-q", *targets]


def build_audit_env(*, require_live_backends: bool = False) -> dict[str, str]:
    env = dict(os.environ)
    if require_live_backends:
        env[_REQUIRE_LIVE_ENV] = "1"
    else:
        env.pop(_REQUIRE_LIVE_ENV, None)
    return env


def main(argv: list[str] | None = None) -> int:
    """Run the parity audit suite and return its exit code."""
    if importlib.util.find_spec("pytest") is None:
        print(
            "pytest is required for the parity audit. Install the dev extras first.",
            file=sys.stderr,
        )
        return 1
    parser = argparse.ArgumentParser(prog="axiom-parity-audit")
    parser.add_argument(
        "--require-live-backends",
        action="store_true",
        help="Fail unless the live backend proof runs and passes.",
    )
    args = parser.parse_args(argv)
    require_live_backends = bool(args.require_live_backends or os.environ.get(_STRICT_ENV) == "1")
    command = build_audit_command(require_live_backends=require_live_backends)
    env = build_audit_env(require_live_backends=require_live_backends)
    return subprocess.call(command, env=env)


if __name__ == "__main__":
    raise SystemExit(main())
