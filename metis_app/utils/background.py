"""metis_app.utils.background — Thread-safe background task runner.

Provides two public classes:

CancelToken
    Lightweight threading.Event wrapper.  Pass one to a worker function so
    it can cooperatively check for cancellation without importing threading.

BackgroundRunner
    Wraps a ThreadPoolExecutor and a queue.Queue.  Worker functions post
    structured messages (status, progress, error, done) onto the queue;
    the Tk main thread drains it with poll_messages() from a recurring
    root.after() call.

Message schema
--------------
All messages are plain dicts.  Defined types:

    {"type": "status",   "text": str,             "task_name": str}
    {"type": "progress", "current": int,
                         "total": int,             "task_name": str}
    {"type": "error",    "text": str,
                         "traceback": str,         "task_name": str}
    {"type": "done",     "result": Any,            "task_name": str}

Only BackgroundRunner itself posts "status" and "done"/"error" wrappers.
Worker functions post "progress" (and optional extra "status") via the
``post_message`` callable they receive as their first argument — see
``submit`` docstring.

Usage example (inside a controller method)::

    def on_build_index(self) -> None:
        def _worker(post_message, cancel_token):
            for i, doc in enumerate(self.model.documents):
                if cancel_token.cancelled:
                    return None
                # ... process doc ...
                post_message({"type": "progress",
                              "current": i + 1,
                              "total": len(self.model.documents)})
            return {"indexed": len(self.model.documents)}

        self.start_task("Build index", _worker)

    # The controller's _poll() picks up messages and routes them to the view.
"""

from __future__ import annotations

import queue
import traceback as _traceback
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Event
from typing import Any, Callable


# ---------------------------------------------------------------------------
# CancelToken
# ---------------------------------------------------------------------------


class CancelToken:
    """Thread-safe cancellation flag.

    Create one per task; pass it to the worker function.  The worker
    checks ``token.cancelled`` at safe points; the controller calls
    ``token.cancel()`` from the main thread.
    """

    def __init__(self) -> None:
        self._event = Event()

    @property
    def cancelled(self) -> bool:
        """True once ``cancel()`` has been called."""
        return self._event.is_set()

    def cancel(self) -> None:
        """Signal cancellation (idempotent, thread-safe)."""
        self._event.set()


# ---------------------------------------------------------------------------
# BackgroundRunner
# ---------------------------------------------------------------------------


class BackgroundRunner:
    """Submits callables to a thread pool and routes their output to a queue.

    Parameters
    ----------
    max_workers:
        Maximum number of concurrent worker threads (default 4).

    Thread-safety
    -------------
    ``post_message`` and ``submit`` may be called from any thread.
    ``poll_messages`` and ``shutdown`` must be called from the main (Tk) thread.
    """

    def __init__(self, max_workers: int = 4) -> None:
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="metis-bg")
        self._queue: queue.Queue[dict[str, Any]] = queue.Queue()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def post_message(self, msg: dict[str, Any]) -> None:
        """Put *msg* on the message queue (safe to call from any thread)."""
        self._queue.put_nowait(msg)

    def submit(
        self,
        fn: Callable[..., Any],
        /,
        *args: Any,
        cancel_token: CancelToken | None = None,
        task_name: str = "",
    ) -> Future:
        """Schedule *fn* on the thread pool.

        The worker receives two leading positional arguments prepended by
        the runner before any *args*:

        1. ``post_message`` — callable accepting a single dict; lets the
           worker emit "status" or "progress" messages mid-task.
        2. ``cancel_token`` — the CancelToken passed to submit (or a fresh
           no-op token if none was given).

        So a worker signature looks like::

            def my_worker(post_message, cancel_token, path, chunk_size):
                ...

        BackgroundRunner automatically posts "status" (on submission),
        "done" (on success), and "error" (on exception) messages.

        Returns
        -------
        concurrent.futures.Future
            The underlying future; the caller may inspect ``.done()`` or
            ``.result()`` but should not block on it from the main thread.
        """
        if cancel_token is None:
            cancel_token = CancelToken()

        self._queue.put_nowait(
            {
                "type": "status",
                "text": f"{task_name} started" if task_name else "Task started",
                "task_name": task_name,
            }
        )

        def _wrapper() -> Any:
            try:
                result = fn(self.post_message, cancel_token, *args)
                self._queue.put_nowait(
                    {"type": "done", "result": result, "task_name": task_name}
                )
                return result
            except Exception as exc:
                self._queue.put_nowait(
                    {
                        "type": "error",
                        "text": str(exc),
                        "traceback": _traceback.format_exc(),
                        "task_name": task_name,
                    }
                )
                raise

        return self._pool.submit(_wrapper)

    def poll_messages(self, max_items: int = 50) -> list[dict[str, Any]]:
        """Drain up to *max_items* messages from the queue (non-blocking).

        Call this from the main thread (e.g. inside a ``root.after()``
        callback) to process worker output without blocking the UI.
        """
        messages: list[dict[str, Any]] = []
        for _ in range(max_items):
            try:
                messages.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return messages

    def shutdown(self, wait: bool = False) -> None:
        """Shut down the thread pool.

        Parameters
        ----------
        wait:
            If True, block until all running workers finish.  Pass False
            (default) for a fast teardown on window close.
        """
        self._pool.shutdown(wait=wait, cancel_futures=True)
