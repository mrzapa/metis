"""Non-UI helper for loading and saving METIS settings JSON files.

This module intentionally avoids importing Qt or any UI toolkit so that
it can be used safely from the API layer and other non-GUI contexts.

The merge priority is:
  defaults (metis_app/default_settings.json)
  → user    (settings.json in repo root)

Schema versioning:
  - Settings have an integer schema_version field
  - On load, migrations are applied if schema_version differs from current
  - Migrations are run sequentially from old version to new
  - See _run_migrations() for available migration functions

Concurrency notes:
  - Atomic writes are used to prevent corruption from interrupted saves.
  - Multiple processes reading/writing settings.json simultaneously is supported
    at the file level (WAL would help but is not used here - settings are
    simple enough that the atomic write pattern is sufficient).
"""

from __future__ import annotations

import json
import logging
import os
import pathlib
import tempfile
from typing import Any, Callable

HERE = pathlib.Path(__file__).resolve().parent  # metis_app/
REPO_ROOT = HERE.parent  # <repo root>

DEFAULT_PATH = HERE / "default_settings.json"
USER_PATH = REPO_ROOT / "settings.json"

API_KEY_PREFIX = "api_key_"

SCHEMA_VERSION = 1

log = logging.getLogger(__name__)


def _migrate_v1_to_current(settings: dict[str, Any]) -> dict[str, Any]:
    """Migration from schema_version 1 to current. Currently a no-op."""
    return settings


_MIGRATIONS: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {
    1: _migrate_v1_to_current,
}


def _run_migrations(settings: dict[str, Any]) -> dict[str, Any]:
    """Run any pending migrations from settings schema_version to current."""
    current_schema = settings.get("schema_version", 0)

    if current_schema == SCHEMA_VERSION:
        return settings

    if current_schema > SCHEMA_VERSION:
        log.warning(
            "Settings schema version (%s) is newer than app supports (%s). "
            "Some settings may be ignored.",
            current_schema,
            SCHEMA_VERSION,
        )
        return settings

    for version in range(current_schema + 1, SCHEMA_VERSION + 1):
        migration_fn = _MIGRATIONS.get(version)
        if migration_fn:
            log.info("Running settings migration from v%d to v%d", version - 1, version)
            settings = migration_fn(settings)
            settings["schema_version"] = version

    return settings


def resolve_secret_refs(settings: dict[str, Any]) -> dict[str, Any]:
    """Replace ``'env:VAR_NAME'`` string values with the corresponding
    environment variable, leaving all other values untouched.

    This lets users store sensitive keys (API tokens, etc.) as
    ``"env:OPENAI_API_KEY"`` in *settings.json* rather than as plain text.
    If the referenced variable is not set the original ``'env:...'`` string
    is retained so that the caller can detect an unresolved reference.
    """
    resolved: dict[str, Any] = {}
    for key, value in settings.items():
        if isinstance(value, str) and value.startswith("env:"):
            var_name = value[4:].strip()
            env_value = os.environ.get(var_name)
            resolved[key] = env_value if env_value is not None else value
        else:
            resolved[key] = value
    return resolved


def load_settings() -> dict[str, Any]:
    """Return fully-merged settings (defaults → user overrides).

    Keys whose name is ``_comment`` are stripped.  Missing files are silently
    skipped so callers always receive a usable dict.
    """
    defaults: dict[str, Any] = {}
    if DEFAULT_PATH.exists():
        try:
            defaults = json.loads(DEFAULT_PATH.read_text(encoding="utf-8"))
            defaults.pop("_comment", None)
        except Exception as exc:
            log.warning("Could not read default settings (%s): %s", DEFAULT_PATH, exc)

    user: dict[str, Any] = {}
    if USER_PATH.exists():
        try:
            user = json.loads(USER_PATH.read_text(encoding="utf-8"))
            user.pop("_comment", None)
        except Exception as exc:
            log.warning("Could not read user settings (%s): %s", USER_PATH, exc)

    merged = dict(defaults)
    merged.update(user)
    merged = _run_migrations(merged)
    merged = resolve_secret_refs(merged)
    return merged


def _atomic_write(target: pathlib.Path, content: str) -> None:
    """Write content to target atomically using temp file + rename.

    On POSIX, os.replace() is atomic. On Windows, it's not guaranteed atomic
    but provides better semantics than a direct write. The temp file is written
    in the same directory as the target to ensure same filesystem.
    """
    dir_path = target.parent
    dir_path.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=dir_path,
        prefix=".settings_",
        suffix=".tmp",
        delete=False,
    ) as tmp:
        tmp.write(content)
        tmp_path = pathlib.Path(tmp.name)

    try:
        os.replace(tmp_path, target)
    except Exception:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise


def save_settings(updates: dict[str, Any]) -> dict[str, Any]:
    """Merge *updates* into the current settings and persist to settings.json.

    Uses atomic write (temp file + rename) to prevent corruption from
    interrupted saves. Ensures schema_version is set to current.

    Returns the full merged settings dict after saving.

    Raises
    ------
    OSError
        If the file cannot be written (propagated to the caller).
    """
    merged = load_settings()
    merged.update(updates)
    merged.pop("_comment", None)
    merged["schema_version"] = SCHEMA_VERSION
    content = json.dumps(merged, indent=2, ensure_ascii=False)
    _atomic_write(USER_PATH, content)
    log.info("Settings saved to %s (%d key(s))", USER_PATH, len(merged))
    return merged


def safe_settings(settings: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of *settings* with all ``api_key_*`` keys removed."""
    return {k: v for k, v in settings.items() if not k.startswith(API_KEY_PREFIX)}
