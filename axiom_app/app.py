"""axiom_app.app — MVC application bootstrap.

Entry point for the refactored Axiom application.  Initialises logging
first (so even Tk startup errors land in the log), then instantiates
model/view/controller, wires events, starts an always-on message-poll
loop, and hands off to the Tk main loop.

Usage (via env-var switch in main.py)::

    AXIOM_NEW_APP=1 python main.py

Or directly::

    python -m axiom_app.app
"""

from __future__ import annotations

import logging
import pathlib
import sys
import tkinter as tk
import traceback
from tkinter import messagebox

from axiom_app.controllers.app_controller import AppController
from axiom_app.models.app_model import AppModel
from axiom_app.utils.dependency_bootstrap import ensure_startup_dependencies
from axiom_app.utils.logging_setup import setup_logging
from axiom_app.views.app_view import AppView

# Poll interval in milliseconds — matches BackgroundRunner's expected cadence.
_POLL_MS = 100

# Log directory relative to the repo root (parent of the axiom_app package).
_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def run_app() -> None:
    """Initialise logging, instantiate the MVC triad, enter Tk mainloop."""

    # ── 1. Logging — must be first so every subsequent call can log ──
    # Resolve log_dir from settings if possible, but settings aren't
    # loaded yet, so use a safe default and re-check after model init.
    _default_log_dir = _REPO_ROOT / "logs"
    logger = setup_logging(_default_log_dir, level="DEBUG")
    logger.info("Log file: %s", (_default_log_dir / "axiom.log").resolve())
    logger.info("=" * 60)
    logger.info("Axiom starting up  (AXIOM_NEW_APP=1)")

    # ── 1b. Dependency guardrail ───────────────────────────────────
    ensure_startup_dependencies(logger)

    # ── 2. Tk root — hidden until construction is complete ───────────
    root = tk.Tk()
    root.withdraw()
    logger.debug("Tk root created")

    try:
        # ── 3. Model + settings ──────────────────────────────────────
        model = AppModel()
        model.load_settings()

        # If settings specify a different log_dir, re-initialise logging.
        settings_log_dir = model.settings.get("log_dir", "")
        if settings_log_dir:
            resolved = pathlib.Path(settings_log_dir)
            if not resolved.is_absolute():
                resolved = _REPO_ROOT / resolved
            if resolved != _default_log_dir:
                logger = setup_logging(resolved, level=model.settings.get("log_level", "DEBUG"))
                logger.info("Log file: %s", (resolved / "axiom.log").resolve())
                logger.debug("Log directory updated to %s from settings", resolved)

        logger.info(
            "Settings loaded — backend=%s  theme=%s  embeddings=%s",
            model.settings.get("ui_backend", "?"),
            model.settings.get("theme", "?"),
            model.settings.get("embeddings_backend", "?"),
        )

        # ── 4. View ───────────────────────────────────────────────────
        theme_name = model.settings.get("theme", "space_dust")
        view = AppView(root, theme_name=theme_name)
        logger.debug("AppView constructed (theme=%s)", theme_name)

        # ── 5. Controller ─────────────────────────────────────────────
        controller = AppController(model, view)
        controller.wire_events()
        logger.debug("AppController wired")

        # ── 6. Always-on poll loop ────────────────────────────────────
        # Runs every _POLL_MS milliseconds for the window's lifetime.
        # Drains the background-runner queue and routes messages to the view.
        def _poll_loop() -> None:
            controller.poll_and_dispatch()
            root.after(_POLL_MS, _poll_loop)

        root.after(_POLL_MS, _poll_loop)

        # ── 7. Initial UI state + reveal ──────────────────────────────
        index_state = "built" if model.index_state.get("built") else "not built"
        view.set_status(f"Documents: {len(model.documents)}  |  Index: {index_state}")
        view.append_log("Axiom MVC skeleton started (AXIOM_NEW_APP=1).\n")
        view.show()

        logger.info("Entering Tk mainloop")
        root.mainloop()
        logger.info("Tk mainloop exited — application shutting down")

    except Exception as exc:
        detail = traceback.format_exc()
        concise = f"Startup Error: {exc}"
        logger.critical("Fatal startup error: %s", exc, exc_info=True)
        print(concise, file=sys.stderr)
        print(detail, file=sys.stderr)
        try:
            messagebox.showerror(
                "Startup Error",
                f"{concise}\n\nDetails have been written to stderr and the log.",
            )
        except Exception:
            pass

    finally:
        logger.info("Axiom process ending")
        logger.info("=" * 60)


if __name__ == "__main__":
    run_app()
