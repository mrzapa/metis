"""M16 Phase 2 — settings-key contract tests.

ADR 0018 freezes the privacy posture: ``evals_share_optin`` must remain
inert for v1, and the four keys ``evals_enabled`` /
``evals_cadence_hours`` / ``evals_auto_seed_enabled`` /
``evals_share_optin`` must be reachable through the existing settings
store without growing a second config surface.
"""

from __future__ import annotations

import json
from pathlib import Path

from metis_app import settings_store


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SETTINGS_PATH = REPO_ROOT / "metis_app" / "default_settings.json"


def test_default_settings_json_has_evals_keys() -> None:
    raw = json.loads(DEFAULT_SETTINGS_PATH.read_text(encoding="utf-8"))
    raw.pop("_comment", None)
    assert "evals_enabled" in raw
    assert "evals_cadence_hours" in raw
    assert "evals_auto_seed_enabled" in raw
    assert "evals_share_optin" in raw


def test_default_settings_match_adr_0018_privacy_posture() -> None:
    raw = json.loads(DEFAULT_SETTINGS_PATH.read_text(encoding="utf-8"))
    raw.pop("_comment", None)
    # Default-off matches ADR 0018: no eval activity unless the user
    # opts in. Prevents the base-rate problem from surfacing as a
    # hollow report on a fresh install.
    assert raw["evals_enabled"] is False
    # Auto-seed must default off so a fresh install does not silently
    # promote runs into the corpus before the user has any visibility.
    assert raw["evals_auto_seed_enabled"] is False
    # Share opt-in must default false and stay reserved per ADR 0018.
    assert raw["evals_share_optin"] is False
    # Cadence default mirrors the seedling overnight cycle so eval
    # runs piggyback on the existing background cadence rather than
    # introducing a second scheduler.
    assert raw["evals_cadence_hours"] == 24


def test_load_settings_exposes_evals_keys() -> None:
    merged = settings_store.load_settings()
    for key in (
        "evals_enabled",
        "evals_cadence_hours",
        "evals_auto_seed_enabled",
        "evals_share_optin",
    ):
        assert key in merged, f"missing settings key: {key}"
