"""metis_app.models.app_model — Central application state.

AppModel is the single source of truth for mutable app state.  It owns no
Tkinter objects; the view layer observes it (via callbacks) and the controller
mutates it.

Settings loading
----------------
``load_settings()`` merges two JSON files in priority order:

1. ``metis_app/default_settings.json``  — ships with the package;
   defines every key with a sensible default.
2. ``settings.json`` in the **repo root** (parent of ``metis_app/``) —
   user override; only keys present here overwrite the defaults.

To customise, copy ``metis_app/default_settings.json`` to
``<repo_root>/settings.json`` and edit as needed.
"""

from __future__ import annotations

import json
import logging
import pathlib
from typing import Any

from metis_app.models.brain_graph import BrainGraph

# metis_app/models/app_model.py  → parent = metis_app/models/
#                                  .parent = metis_app/
#                                  .parent = repo root
_HERE         = pathlib.Path(__file__).resolve().parent          # metis_app/models/
_PACKAGE_ROOT = _HERE.parent                                      # metis_app/
_REPO_ROOT    = _PACKAGE_ROOT.parent                              # <repo root>

_DEFAULT_SETTINGS_PATH = _PACKAGE_ROOT / "default_settings.json"
_USER_SETTINGS_PATH    = _REPO_ROOT    / "settings.json"
_SESSION_DB_PATH       = _REPO_ROOT    / "rag_sessions.db"
_INDEX_STORAGE_DIR     = _REPO_ROOT    / "indexes"
_PROFILES_DIR          = _REPO_ROOT    / "profiles"
_SKILLS_DIR            = _REPO_ROOT    / "skills"
_TRACE_DIR             = _REPO_ROOT    / "traces"


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
        Child of the ``metis_app`` logging hierarchy; inherits handlers
        configured by ``setup_logging()``.
    """

    def __init__(self) -> None:
        self.documents: list[Any] = []
        self.index_state: dict[str, Any] = {"built": False, "doc_count": 0, "chunk_count": 0}
        self.chat_history: list[dict[str, Any]] = []
        self.settings: dict[str, Any] = {}
        self.logger: logging.Logger = logging.getLogger(__name__)
        # In-memory index populated by the "Build Index" background task.
        # chunks[i] is a dict: {"id": str, "text": str, "source": str, "chunk_idx": int}
        # embeddings[i] is the corresponding float vector (parallel list).
        self.chunks: list[dict[str, Any]] = []
        self.embeddings: list[list[float]] = []
        self.knowledge_graph: Any | None = None
        self.entity_to_chunks: dict[str, set[int]] = {}
        self.current_session_id: str = ""
        self.session_list: list[Any] = []
        self.loaded_session: Any | None = None
        self.last_sources: list[Any] = []
        self.active_index_id: str = ""
        self.active_index_path: str = ""
        self.index_bundle: Any | None = None
        self.available_indexes: list[Any] = []
        self.brain_graph: BrainGraph | None = None
        self.selected_brain_node: str = ""
        self.current_skill_id: str = ""
        self.last_run_id: str = ""
        self.rag_blocked_reason: str = ""
        self.bootstrap_complete: bool = False
        self.session_db_path: pathlib.Path = _SESSION_DB_PATH
        self.index_storage_dir: pathlib.Path = _INDEX_STORAGE_DIR
        self.skills_dir: pathlib.Path = _SKILLS_DIR
        self.trace_dir: pathlib.Path = _TRACE_DIR

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def load_settings(self) -> None:
        """Merge default and user settings into ``self.settings``.

        Strategy
        --------
        * Start with ``metis_app/default_settings.json`` (all keys present).
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
        user: dict[str, Any] = {}
        if _USER_SETTINGS_PATH.exists():
            try:
                user = json.loads(_USER_SETTINGS_PATH.read_text(encoding="utf-8"))
                user.pop("_comment", None)
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

        self.settings.update(user)
        self.current_skill_id = str(self.settings.get("current_skill_id", self.current_skill_id) or "")

        self.logger.debug("Active settings: %s", self.settings)

    def save_settings(self, settings_dict: dict[str, Any]) -> None:
        """Persist *settings_dict* to ``<repo_root>/settings.json``.

        Writes the full merged dict as formatted JSON, then updates
        ``self.settings`` so the in-memory view stays consistent without
        requiring a full reload.

        Raises
        ------
        OSError
            If the file cannot be written (propagated to the caller).
        """
        merged = dict(self.settings)
        merged.update(settings_dict)
        merged.pop("_comment", None)
        _USER_SETTINGS_PATH.write_text(
            json.dumps(merged, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self.settings = merged
        self.logger.info(
            "Settings saved to %s (%d key(s))", _USER_SETTINGS_PATH, len(merged)
        )

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
            "active_index_id": self.active_index_id,
            "current_session_id": self.current_session_id,
            "selected_brain_node": self.selected_brain_node,
            "current_skill_id": self.current_skill_id,
            "bootstrap_complete": self.bootstrap_complete,
        }
