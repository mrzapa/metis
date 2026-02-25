"""axiom_app.views.app_view — Top-level application window.

Provides a ttk.Notebook with four tabs (Documents, Chat, Settings, Logs),
a determinate/indeterminate ttk.Progressbar, and a status label — all
wired with grid so the window resizes cleanly.

Only used when AXIOM_NEW_APP=1.  The legacy agentic_rag_gui UI is unchanged.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import scrolledtext, ttk


class AppView:
    """Root window with tabbed layout.

    Parameters
    ----------
    root:
        The ``tk.Tk`` instance created by ``run_app()``.  AppView does not
        call ``mainloop()``; that is the responsibility of the caller.
    """

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self._progress_mode: str = "determinate"  # "determinate" | "indeterminate"
        self._build()

    # ------------------------------------------------------------------
    # Window construction
    # ------------------------------------------------------------------

    def _build(self) -> None:
        self.root.title("Axiom")
        self.root.geometry("900x620")
        self.root.minsize(540, 360)

        # Root grid: row 0 = notebook (expands), row 1 = bottom bar (fixed).
        self.root.rowconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=0)
        self.root.columnconfigure(0, weight=1)

        # ── Notebook ─────────────────────────────────────────────────
        self.notebook = ttk.Notebook(self.root)
        self.notebook.grid(row=0, column=0, sticky="nsew", padx=8, pady=(8, 4))

        self.tab_documents = self._make_placeholder_tab("Documents",
            "Document list and file-open controls will appear here.")
        self.tab_chat = self._make_placeholder_tab("Chat",
            "Chat input/output panel will appear here.")
        self.tab_settings = self._make_placeholder_tab("Settings",
            "Provider and embedding settings will appear here.")
        self.tab_logs = self._make_log_tab()

        self.notebook.add(self.tab_documents, text="Documents")
        self.notebook.add(self.tab_chat,      text="Chat")
        self.notebook.add(self.tab_settings,  text="Settings")
        self.notebook.add(self.tab_logs,      text="Logs")

        # ── Bottom bar ───────────────────────────────────────────────
        # Two-column grid inside a frame: status label (expands) | progress bar (fixed).
        bottom = ttk.Frame(self.root)
        bottom.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 6))
        bottom.columnconfigure(0, weight=1)
        bottom.columnconfigure(1, weight=0)

        self._status_var = tk.StringVar(value="Ready.")
        self._status_label = ttk.Label(
            bottom,
            textvariable=self._status_var,
            relief="sunken",
            anchor="w",
            padding=(6, 3),
        )
        self._status_label.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        self._progressbar = ttk.Progressbar(
            bottom,
            orient="horizontal",
            mode="determinate",
            length=200,
        )
        self._progressbar.grid(row=0, column=1, sticky="e")

    def _make_placeholder_tab(self, title: str, hint: str) -> ttk.Frame:
        """Return a tab frame with a centred hint label."""
        frame = ttk.Frame(self.notebook, padding=12)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        ttk.Label(
            frame,
            text=f"[ {title} — {hint} ]",
            foreground="gray",
            anchor="center",
            justify="center",
        ).grid(row=0, column=0, sticky="nsew")
        return frame

    def _make_log_tab(self) -> ttk.Frame:
        """Return the Logs tab with a scrolled text area."""
        frame = ttk.Frame(self.notebook, padding=6)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        self._log_text = scrolledtext.ScrolledText(
            frame,
            state="disabled",
            wrap="word",
            font=("TkFixedFont", 10),
            background="#1e1e1e",
            foreground="#d4d4d4",
            insertbackground="#d4d4d4",
        )
        self._log_text.grid(row=0, column=0, sticky="nsew")

        # Clear button
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=1, column=0, sticky="e", pady=(4, 0))
        ttk.Button(btn_frame, text="Clear log", command=self._clear_log).pack()

        return frame

    # ------------------------------------------------------------------
    # Public interface (called by controller / poll loop)
    # ------------------------------------------------------------------

    def set_status(self, text: str) -> None:
        """Update the status-bar label text."""
        self._status_var.set(text)

    def set_progress(self, current: int, total: int | None) -> None:
        """Update the progress bar.

        Parameters
        ----------
        current:
            Items completed so far.
        total:
            Total items, or ``None`` / ``0`` for indeterminate (bouncing) mode.
        """
        if not total:
            # Switch to indeterminate bounce (e.g. unknown total).
            if self._progress_mode != "indeterminate":
                self._progressbar.configure(mode="indeterminate")
                self._progress_mode = "indeterminate"
                self._progressbar.start(15)
        else:
            if self._progress_mode != "determinate":
                self._progressbar.stop()
                self._progressbar.configure(mode="determinate")
                self._progress_mode = "determinate"
            pct = min(100, int(current / total * 100))
            self._progressbar["value"] = pct

    def reset_progress(self) -> None:
        """Stop any animation and return the bar to zero."""
        if self._progress_mode == "indeterminate":
            self._progressbar.stop()
            self._progressbar.configure(mode="determinate")
            self._progress_mode = "determinate"
        self._progressbar["value"] = 0

    def append_log(self, line: str) -> None:
        """Append *line* to the Logs tab (thread-safe: must be called from main thread)."""
        self._log_text.configure(state="normal")
        self._log_text.insert("end", line if line.endswith("\n") else line + "\n")
        self._log_text.see("end")
        self._log_text.configure(state="disabled")

    def _clear_log(self) -> None:
        self._log_text.configure(state="normal")
        self._log_text.delete("1.0", "end")
        self._log_text.configure(state="disabled")

    def show(self) -> None:
        """Make the window visible (call after controller.wire_events())."""
        self.root.deiconify()
        self.root.lift()
