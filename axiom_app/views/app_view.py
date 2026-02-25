"""axiom_app.views.app_view — Top-level application window.

Provides a ttk.Notebook with four tabs (Documents, Chat, Settings, Logs),
a determinate/indeterminate ttk.Progressbar, and a status label — all
wired with grid so the window resizes cleanly.

Public widget handles (set by controller via wire_events):
  btn_open_files   — "Open Text File…" button in Documents tab
  btn_build_index  — "Build Index" button in Documents tab
  btn_send         — "Send" button in Chat tab
  prompt_entry     — ttk.Entry in Chat tab

Public view-mutating methods (called from main thread only):
  set_status(text)
  set_progress(current, total)
  reset_progress()
  append_log(line)
  set_file_list(paths)   — refreshes the Documents listbox
  append_chat(text)      — appends text to the Chat output area
  clear_prompt()         — empties the prompt entry

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
        self._progress_mode: str = "determinate"
        self._build()

    # ------------------------------------------------------------------
    # Window construction
    # ------------------------------------------------------------------

    def _build(self) -> None:
        self.root.title("Axiom")
        self.root.geometry("900x640")
        self.root.minsize(600, 420)

        # Root grid: row 0 = notebook (expands), row 1 = bottom bar (fixed).
        self.root.rowconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=0)
        self.root.columnconfigure(0, weight=1)

        # ── Notebook ─────────────────────────────────────────────────
        self.notebook = ttk.Notebook(self.root)
        self.notebook.grid(row=0, column=0, sticky="nsew", padx=8, pady=(8, 4))

        self.tab_documents = self._make_documents_tab()
        self.tab_chat      = self._make_chat_tab()
        self.tab_settings  = self._make_placeholder_tab("Settings",
            "Provider and embedding settings will appear here.")
        self.tab_logs      = self._make_log_tab()

        self.notebook.add(self.tab_documents, text="Documents")
        self.notebook.add(self.tab_chat,      text="Chat")
        self.notebook.add(self.tab_settings,  text="Settings")
        self.notebook.add(self.tab_logs,      text="Logs")

        # ── Bottom bar ───────────────────────────────────────────────
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

    # ── Tab builders ─────────────────────────────────────────────────

    def _make_documents_tab(self) -> ttk.Frame:
        """Documents tab: toolbar + file listbox + index-state label."""
        frame = ttk.Frame(self.notebook, padding=8)
        frame.rowconfigure(1, weight=1)
        frame.columnconfigure(0, weight=1)

        # Row 0 — toolbar
        toolbar = ttk.Frame(frame)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 6))

        self.btn_open_files = ttk.Button(toolbar, text="Open Text File…")
        self.btn_open_files.pack(side="left", padx=(0, 4))

        self.btn_build_index = ttk.Button(toolbar, text="Build Index")
        self.btn_build_index.pack(side="left")

        self._index_info_var = tk.StringVar(value="No index built.")
        ttk.Label(toolbar, textvariable=self._index_info_var, foreground="gray").pack(
            side="left", padx=(12, 0)
        )

        # Row 1 — file listbox with scrollbar
        lb_frame = ttk.Frame(frame)
        lb_frame.grid(row=1, column=0, sticky="nsew")
        lb_frame.rowconfigure(0, weight=1)
        lb_frame.columnconfigure(0, weight=1)

        self._file_listbox = tk.Listbox(
            lb_frame,
            selectmode="extended",
            activestyle="dotbox",
        )
        self._file_listbox.grid(row=0, column=0, sticky="nsew")

        _sb = ttk.Scrollbar(lb_frame, orient="vertical",
                            command=self._file_listbox.yview)
        _sb.grid(row=0, column=1, sticky="ns")
        self._file_listbox.configure(yscrollcommand=_sb.set)

        _hsb = ttk.Scrollbar(lb_frame, orient="horizontal",
                             command=self._file_listbox.xview)
        _hsb.grid(row=1, column=0, sticky="ew")
        self._file_listbox.configure(xscrollcommand=_hsb.set)

        return frame

    def _make_chat_tab(self) -> ttk.Frame:
        """Chat tab: scrollable output area + prompt entry + Send button."""
        frame = ttk.Frame(self.notebook, padding=8)
        frame.rowconfigure(0, weight=1)
        frame.rowconfigure(1, weight=0)
        frame.columnconfigure(0, weight=1)

        # Row 0 — chat output
        self._chat_output = scrolledtext.ScrolledText(
            frame,
            state="disabled",
            wrap="word",
            font=("TkDefaultFont", 10),
        )
        self._chat_output.grid(row=0, column=0, sticky="nsew", pady=(0, 6))

        # Row 1 — input bar (entry + send button)
        input_bar = ttk.Frame(frame)
        input_bar.grid(row=1, column=0, sticky="ew")
        input_bar.columnconfigure(0, weight=1)
        input_bar.columnconfigure(1, weight=0)

        self.prompt_entry = ttk.Entry(input_bar, font=("TkDefaultFont", 10))
        self.prompt_entry.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        self.btn_send = ttk.Button(input_bar, text="Send", width=8)
        self.btn_send.grid(row=0, column=1, sticky="e")

        return frame

    def _make_placeholder_tab(self, title: str, hint: str) -> ttk.Frame:
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

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=1, column=0, sticky="e", pady=(4, 0))
        ttk.Button(btn_frame, text="Clear log", command=self._clear_log).pack()

        return frame

    # ------------------------------------------------------------------
    # Public interface (called from main thread only)
    # ------------------------------------------------------------------

    def set_status(self, text: str) -> None:
        """Update the status-bar label."""
        self._status_var.set(text)

    def set_index_info(self, text: str) -> None:
        """Update the index-state label in the Documents toolbar."""
        self._index_info_var.set(text)

    def set_progress(self, current: int, total: int | None) -> None:
        """Update the progress bar (indeterminate when total is None/0)."""
        if not total:
            if self._progress_mode != "indeterminate":
                self._progressbar.configure(mode="indeterminate")
                self._progress_mode = "indeterminate"
                self._progressbar.start(15)
        else:
            if self._progress_mode != "determinate":
                self._progressbar.stop()
                self._progressbar.configure(mode="determinate")
                self._progress_mode = "determinate"
            self._progressbar["value"] = min(100, int(current / total * 100))

    def reset_progress(self) -> None:
        """Stop animation and zero the progress bar."""
        if self._progress_mode == "indeterminate":
            self._progressbar.stop()
            self._progressbar.configure(mode="determinate")
            self._progress_mode = "determinate"
        self._progressbar["value"] = 0

    def set_file_list(self, paths: list[str]) -> None:
        """Replace the Documents listbox contents with *paths*."""
        self._file_listbox.delete(0, "end")
        for p in paths:
            self._file_listbox.insert("end", p)

    def append_chat(self, text: str) -> None:
        """Append *text* to the Chat output area."""
        self._chat_output.configure(state="normal")
        self._chat_output.insert("end", text)
        self._chat_output.see("end")
        self._chat_output.configure(state="disabled")

    def get_prompt_text(self) -> str:
        """Return the current contents of the prompt entry."""
        return self.prompt_entry.get()

    def clear_prompt(self) -> None:
        """Empty the prompt entry."""
        self.prompt_entry.delete(0, "end")

    def append_log(self, line: str) -> None:
        """Append *line* to the Logs tab."""
        self._log_text.configure(state="normal")
        self._log_text.insert("end", line if line.endswith("\n") else line + "\n")
        self._log_text.see("end")
        self._log_text.configure(state="disabled")

    def _clear_log(self) -> None:
        self._log_text.configure(state="normal")
        self._log_text.delete("1.0", "end")
        self._log_text.configure(state="disabled")

    def show(self) -> None:
        """Make the window visible."""
        self.root.deiconify()
        self.root.lift()
