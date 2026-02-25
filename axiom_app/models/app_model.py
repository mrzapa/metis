"""axiom_app.models.app_model — Central application state.

AppModel is the single source of truth for mutable app state.  It owns no
Tkinter objects; the view layer observes it (via callbacks) and the controller
mutates it.

Settings loading
----------------
``load_settings()`` merges two JSON files in priority order:

1. ``axiom_app/default_settings.json``  — ships with the package;
   defines every key with a sensible default.
2. ``settings.json`` in the **repo root** (parent of ``axiom_app/``) —
   user override; only keys present here overwrite the defaults.

To customise, copy ``axiom_app/default_settings.json`` to
``<repo_root>/settings.json`` and edit as needed.
"""

from __future__ import annotations

import json
import logging
import pathlib
from typing import Any

# axiom_app/models/app_model.py  → parent = axiom_app/models/
#                                  .parent = axiom_app/
#                                  .parent = repo root
_HERE         = pathlib.Path(__file__).resolve().parent          # axiom_app/models/
_PACKAGE_ROOT = _HERE.parent                                      # axiom_app/
_REPO_ROOT    = _PACKAGE_ROOT.parent                              # <repo root>

_DEFAULT_SETTINGS_PATH = _PACKAGE_ROOT / "default_settings.json"
_USER_SETTINGS_PATH    = _REPO_ROOT    / "settings.json"


class AppModel:
    """Holds application state; owns no UI objects.

    Attributes
    ----------
    documents:
        List of loaded document paths (str) or metadata dicts.
    index_state:
        Freeform dict describing the current vector-index state
        (e.g. ``{"built": False, "doc_count": 0}``).
    chat_history:
        List of chat turn dicts, each with at least ``"role"`` and
        ``"content"`` keys.
    settings:
        Flat dict of active settings (defaults merged with user overrides).
    logger:
        Child of the ``axiom_app`` logging hierarchy; inherits handlers
        configured by ``setup_logging()``.
    """

    def __init__(self) -> None:
        self.documents: list[Any] = []
        self.index_state: dict[str, Any] = {"built": False, "doc_count": 0}
        self.chat_history: list[dict[str, Any]] = []
        self.settings: dict[str, Any] = {}
        self.logger: logging.Logger = logging.getLogger(__name__)

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def load_settings(self) -> None:
        """Merge default and user settings into ``self.settings``.

        Strategy
        --------
        * Start with ``axiom_app/default_settings.json`` (all keys present).
        * Overlay any keys found in ``<repo_root>/settings.json``.
        * Keys in the defaults that are absent from the user file are kept,
          so new defaults are picked up automatically after upgrades.
        * The ``_comment`` key (documentation aid in the JSON) is stripped.
        """
        # ── load defaults ────────────────────────────────────────────
        defaults: dict[str, Any] = {}
        if _DEFAULT_SETTINGS_PATH.exists():
            try:
                defaults = json.loads(_DEFAULT_SETTINGS_PATH.read_text(encoding="utf-8"))
                defaults.pop("_comment", None)
                self.logger.debug("Default settings loaded from %s", _DEFAULT_SETTINGS_PATH)
            except Exception as exc:
                self.logger.warning("Could not read default settings (%s): %s", _DEFAULT_SETTINGS_PATH, exc)
        else:
            self.logger.warning("Default settings file missing: %s", _DEFAULT_SETTINGS_PATH)

        self.settings = dict(defaults)

        # ── overlay user overrides ───────────────────────────────────
        if _USER_SETTINGS_PATH.exists():
            try:
                user: dict[str, Any] = json.loads(_USER_SETTINGS_PATH.read_text(encoding="utf-8"))
                user.pop("_comment", None)
                self.settings.update(user)
                self.logger.info(
                    "User settings loaded from %s (%d key(s) overriding defaults)",
                    _USER_SETTINGS_PATH,
                    len(user),
                )
            except Exception as exc:
                self.logger.warning("Could not read user settings (%s): %s", _USER_SETTINGS_PATH, exc)
        else:
            self.logger.debug(
                "No user settings.json at %s — using defaults only.", _USER_SETTINGS_PATH
            )

        self.logger.debug("Active settings: %s", self.settings)

    # ------------------------------------------------------------------
    # Documents
    # ------------------------------------------------------------------

    def set_documents(self, paths: list[Any]) -> None:
        """Replace the current document list.

        TODO: validate paths, update index_state accordingly.
        """
        self.documents = list(paths)  # TODO: enrich with metadata

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_status_snapshot(self) -> dict[str, Any]:
        """Return a lightweight dict describing current state.

        Intended for logging and status-bar updates; must not be slow.
        """
        return {
            "document_count": len(self.documents),
            "index_built": self.index_state.get("built", False),
            "chat_turns": len(self.chat_history),
            "settings_loaded": bool(self.settings),
        }
