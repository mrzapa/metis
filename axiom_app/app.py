"""axiom_app.app — MVC application bootstrap.

Entry point for the refactored Axiom application.  Instantiates model,
view, and controller in the correct order, wires events, starts an
always-on message-poll loop, then hands off to the Tk main loop.

Usage (via env-var switch in main.py)::

    AXIOM_NEW_APP=1 python main.py

Or directly::

    python -m axiom_app.app
"""

from __future__ import annotations

import sys
import tkinter as tk
import traceback
from tkinter import messagebox

from axiom_app.controllers.app_controller import AppController
from axiom_app.models.app_model import AppModel
from axiom_app.views.app_view import AppView

# Poll interval in milliseconds — matches BackgroundRunner's expected cadence.
_POLL_MS = 100


def run_app() -> None:
    """Instantiate the MVC triad, start the poll loop, enter Tk mainloop."""
    root = tk.Tk()
    # Keep window hidden until the UI is fully constructed.
    root.withdraw()

    try:
        model = AppModel()
        model.load_settings()

        view = AppView(root)

        controller = AppController(model, view)
        controller.wire_events()

        # ── Always-on poll loop ──────────────────────────────────────
        # Runs every _POLL_MS milliseconds for the lifetime of the window.
        # Drains the background-runner queue and routes messages to the view
        # via controller.poll_and_dispatch().  This decouples task submission
        # (start_task) from polling; tasks started at any time will have their
        # messages picked up automatically.
        def _poll_loop() -> None:
            controller.poll_and_dispatch()
            root.after(_POLL_MS, _poll_loop)

        root.after(_POLL_MS, _poll_loop)

        # Set initial status and reveal the window.
        index_state = "built" if model.index_state.get("built") else "not built"
        view.set_status(f"Documents: {len(model.documents)}  |  Index: {index_state}")
        view.append_log("Axiom MVC skeleton started (AXIOM_NEW_APP=1).\n")
        view.show()

        root.mainloop()

    except Exception as exc:
        detail = traceback.format_exc()
        concise = f"Startup Error: {exc}"
        print(concise, file=sys.stderr)
        print(detail, file=sys.stderr)
        try:
            messagebox.showerror(
                "Startup Error",
                f"{concise}\n\nDetails have been written to stderr.",
            )
        except Exception:
            pass


if __name__ == "__main__":
    run_app()
