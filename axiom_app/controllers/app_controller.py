"""axiom_app.controllers.app_controller — Top-level application controller.

AppController mediates between AppModel (state) and AppView (UI).  It
binds user actions to model mutations and triggers view refreshes.

Message polling is driven externally by a recurring ``root.after()`` loop
in ``axiom_app.app`` (always-on, 100 ms interval).  The controller exposes
``poll_and_dispatch()`` which drains the queue and routes each message to
the appropriate view method — callers never touch the runner directly.

All action methods are stubs (TODO/pass) for now.  They will be filled in
as logic is extracted from agentic_rag_gui.py.
"""

from __future__ import annotations

import logging
from concurrent.futures import Future
from typing import TYPE_CHECKING, Any, Callable

from axiom_app.utils.background import BackgroundRunner, CancelToken

if TYPE_CHECKING:
    from axiom_app.models.app_model import AppModel
    from axiom_app.views.app_view import AppView


class AppController:
    """Mediates between AppModel and AppView.

    Parameters
    ----------
    model:
        The single AppModel instance holding application state.
    view:
        The AppView instance owning the root Tk window.

    Attributes
    ----------
    background_runner:
        Public reference to the BackgroundRunner; ``app.py`` calls
        ``poll_and_dispatch()`` rather than accessing the runner directly.
    """

    def __init__(self, model: AppModel, view: AppView) -> None:
        self.model = model
        self.view = view
        self.background_runner = BackgroundRunner()
        self._active_token: CancelToken | None = None
        self._active_future: Future | None = None
        self._log = logging.getLogger(__name__)

    # ------------------------------------------------------------------
    # Event wiring
    # ------------------------------------------------------------------

    def wire_events(self) -> None:
        """Bind view widgets to controller callbacks.

        TODO: connect menu items, buttons, and keyboard shortcuts to the
        action methods below once the real UI panels are migrated.
        """
        # Hook window close so the thread pool is cleaned up.
        self.view.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    # Background task management
    # ------------------------------------------------------------------

    def start_task(self, task_name: str, fn: Callable[..., Any], /, *args: Any) -> None:
        """Submit *fn* to the background runner.

        Parameters
        ----------
        task_name:
            Human-readable label used in status messages and log output.
        fn:
            Worker callable.  BackgroundRunner prepends two arguments:
            ``post_message`` and ``cancel_token`` (see BackgroundRunner.submit).
        *args:
            Additional positional arguments forwarded to *fn* after the
            two injected ones.

        If a task is already running, it is cancelled before the new one starts.
        Messages are picked up by the always-on poll loop in ``app.py``.
        """
        if self._active_token is not None:
            self._log.debug("Cancelling previous task before starting '%s'", task_name)
            self._active_token.cancel()

        token = CancelToken()
        self._active_token = token
        self._active_future = self.background_runner.submit(
            fn, *args, cancel_token=token, task_name=task_name
        )
        self._log.info("Task started: %s", task_name)

    def cancel_current_task(self) -> None:
        """Signal the active background task to stop (cooperative)."""
        if self._active_token is not None:
            self._active_token.cancel()
        self.view.set_status("Cancelling…")

    def shutdown(self) -> None:
        """Tear down the thread pool (call on window close)."""
        self._log.info("AppController shutting down")
        if self._active_token is not None:
            self._active_token.cancel()
        self.background_runner.shutdown(wait=False)

    # ------------------------------------------------------------------
    # Message dispatch (called by the poll loop in app.py)
    # ------------------------------------------------------------------

    def poll_and_dispatch(self) -> None:
        """Drain the message queue and update the view.

        Called every 100 ms from the always-on ``root.after()`` loop in
        ``axiom_app.app``.  Clears the active-task reference once the
        future is finished so the progress bar can be reset.
        """
        for msg in self.background_runner.poll_messages():
            self._handle_message(msg)

        # Once the future is done, clear tracking state.
        if self._active_future is not None and self._active_future.done():
            self._active_future = None
            self._active_token = None
            self.view.reset_progress()

    def _handle_message(self, msg: dict[str, Any]) -> None:
        mtype = msg.get("type")
        if mtype == "status":
            self.view.set_status(msg.get("text", ""))
            self.view.append_log(f"[status] {msg.get('text', '')}")
        elif mtype == "progress":
            current = int(msg.get("current", 0))
            total = msg.get("total")
            total = int(total) if total is not None else None
            self.view.set_progress(current, total)
        elif mtype == "error":
            text = msg.get("text", "unknown error")
            tb = msg.get("traceback", "")
            self._log.error("Task error [%s]: %s", msg.get("task_name", "?"), text)
            if tb:
                self._log.debug("Traceback:\n%s", tb.rstrip())
            self.view.set_status(f"Error: {text}")
            self.view.append_log(f"[error] {text}")
            if tb:
                self.view.append_log(tb)
        elif mtype == "done":
            task = msg.get("task_name", "Task")
            label = f"{task} complete." if task else "Done."
            self._log.info("Task complete: %s", task or "(unnamed)")
            self.view.set_status(label)
            self.view.append_log(f"[done]  {label}")
        elif mtype == "log":
            # Workers may emit {"type": "log", "text": "..."} for verbose output.
            self.view.append_log(msg.get("text", ""))

    # ------------------------------------------------------------------
    # Window close
    # ------------------------------------------------------------------

    def _on_close(self) -> None:
        self.shutdown()
        self.view.root.destroy()

    # ------------------------------------------------------------------
    # Action handlers (called by bound events or public API)
    # ------------------------------------------------------------------

    def on_open_files(self) -> None:
        """Let the user pick document files and load them into the model.

        TODO:
          1. Open a tk.filedialog to select files.
          2. Call self.model.set_documents(paths).
          3. Update self.view status bar.
        """
        pass  # TODO

    def on_build_index(self) -> None:
        """Trigger ingestion and vector-index construction.

        TODO:
          1. Validate self.model.documents is non-empty.
          2. Define a worker function and call self.start_task("Build index", worker).
          3. Worker updates self.model.index_state on completion via the "done" message.
        """
        pass  # TODO

    def on_send_prompt(self, prompt: str = "") -> None:
        """Dispatch a user query through the agentic RAG pipeline.

        Parameters
        ----------
        prompt:
            Raw text from the chat input widget.  Empty string is a no-op.

        TODO:
          1. Validate index is built.
          2. Append user turn to self.model.chat_history.
          3. Call self.start_task("Query", worker, prompt).
          4. Stream response tokens via "status" messages into the chat panel.
          5. Append assistant turn on "done".
        """
        pass  # TODO

    def on_cancel_job(self) -> None:
        """Cancel any running background job (ingestion or query)."""
        self.cancel_current_task()
