"""Non-UI helper for loading and saving Axiom settings JSON files.

This module intentionally avoids importing Qt or any UI toolkit so that
it can be used safely from the API layer and other non-GUI contexts.

The merge priority is identical to ``AppModel.load_settings``:
  defaults (axiom_app/default_settings.json)
  → legacy  (agentic_rag_config.json, backward-compat only)
  → user    (settings.json in repo root)
"""

from __future__ import annotations

import json
import logging
import pathlib
from typing import Any

_HERE         = pathlib.Path(__file__).resolve().parent   # axiom_app/
_REPO_ROOT    = _HERE.parent                              # <repo root>

_DEFAULT_PATH = _HERE / "default_settings.json"
_USER_PATH    = _REPO_ROOT / "settings.json"
_LEGACY_PATH  = _REPO_ROOT / "agentic_rag_config.json"

_API_KEY_PREFIX = "api_key_"

log = logging.getLogger(__name__)


def load_settings() -> dict[str, Any]:
    """Return fully-merged settings (defaults → legacy → user overrides).

    Keys whose name is ``_comment`` are stripped.  Missing files are silently
    skipped so callers always receive a usable dict.
    """
    defaults: dict[str, Any] = {}
    if _DEFAULT_PATH.exists():
        try:
            defaults = json.loads(_DEFAULT_PATH.read_text(encoding="utf-8"))
            defaults.pop("_comment", None)
        except Exception as exc:
            log.warning("Could not read default settings (%s): %s", _DEFAULT_PATH, exc)

    legacy: dict[str, Any] = {}
    if _LEGACY_PATH.exists():
        try:
            legacy = json.loads(_LEGACY_PATH.read_text(encoding="utf-8"))
            legacy.pop("_comment", None)
        except Exception as exc:
            log.warning("Could not read legacy config (%s): %s", _LEGACY_PATH, exc)

    user: dict[str, Any] = {}
    if _USER_PATH.exists():
        try:
            user = json.loads(_USER_PATH.read_text(encoding="utf-8"))
            user.pop("_comment", None)
        except Exception as exc:
            log.warning("Could not read user settings (%s): %s", _USER_PATH, exc)

    merged = dict(defaults)
    for key, value in legacy.items():
        if key not in user:
            merged[key] = value
    merged.update(user)
    return merged


def save_settings(updates: dict[str, Any]) -> dict[str, Any]:
    """Merge *updates* into the current settings and persist to settings.json.

    Returns the full merged settings dict after saving.

    Raises
    ------
    OSError
        If the file cannot be written (propagated to the caller).
    """
    merged = load_settings()
    merged.update(updates)
    merged.pop("_comment", None)
    _USER_PATH.write_text(
        json.dumps(merged, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    log.info("Settings saved to %s (%d key(s))", _USER_PATH, len(merged))
    return merged


def safe_settings(settings: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of *settings* with all ``api_key_*`` keys removed."""
    return {k: v for k, v in settings.items() if not k.startswith(_API_KEY_PREFIX)}
