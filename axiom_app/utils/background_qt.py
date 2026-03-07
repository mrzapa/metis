"""axiom_app.utils.background_qt — Qt signal bridge for BackgroundRunner.

Replaces the ``root.after()`` poll loop with a ``QTimer`` that drains
the ``BackgroundRunner`` queue and emits typed Qt signals.  The existing
``BackgroundRunner`` and ``CancelToken`` classes remain unchanged (pure
Python, no framework dependency) so all existing tests keep passing.

Usage in ``app.py``::

    bridge = QtBackgroundBridge(controller.background_runner)
    bridge.status_received.connect(...)
    bridge.start()
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal

from axiom_app.utils.background import BackgroundRunner


class QtBackgroundBridge(QObject):
    """QTimer-based poller that emits Qt signals for BackgroundRunner messages."""

    status_received = Signal(str, str)        # (text, task_name)
    progress_received = Signal(int, object)   # (current, total_or_None)
    error_received = Signal(str, str, str)    # (text, traceback, task_name)
    done_received = Signal(object, str)       # (result, task_name)
    log_received = Signal(str)                # (text,)

    def __init__(
        self,
        runner: BackgroundRunner,
        poll_ms: int = 100,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._runner = runner
        self._timer = QTimer(self)
        self._timer.setInterval(poll_ms)
        self._timer.timeout.connect(self._poll)

    def start(self) -> None:
        """Start the poll timer."""
        self._timer.start()

    def stop(self) -> None:
        """Stop the poll timer."""
        self._timer.stop()

    def _poll(self) -> None:
        for msg in self._runner.poll_messages():
            mtype = msg.get("type")
            if mtype == "status":
                self.status_received.emit(
                    msg.get("text", ""), msg.get("task_name", "")
                )
            elif mtype == "progress":
                self.progress_received.emit(
                    int(msg.get("current", 0)), msg.get("total")
                )
            elif mtype == "error":
                self.error_received.emit(
                    msg.get("text", ""),
                    msg.get("traceback", ""),
                    msg.get("task_name", ""),
                )
            elif mtype == "done":
                self.done_received.emit(
                    msg.get("result"), msg.get("task_name", "")
                )
            elif mtype == "log":
                self.log_received.emit(msg.get("text", ""))
