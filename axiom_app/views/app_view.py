"""axiom_app.views.app_view — Top-level application window with sidebar navigation.

Restores the full Axiom sidebar-based GUI from the legacy agentic_rag_gui.py inside
the clean MVC package.  Layout mirrors the original:

  ┌─────────────────────────────────────────────────────┐
  │  Sidebar (230px)  │  Main content (expandable)      │
  │  ─────────────    │  ─────────────────────────────  │
  │  [Logo]           │  [Chat / Library / History /    │
  │  Axiom            │   Settings view — one at a time]│
  │  Personal RAG...  │                                  │
  │  ─────            │                                  │
  │  💬 Chat          │                                  │
  │  📚 Library       │                                  │
  │  🕘 History       │                                  │
  │  ⚙️  Settings      │                                  │
  │  ─────            │                                  │
  │  v1.0  ttk        │                                  │
  └─────────────────────────────────────────────────────┘

Public widget handles (set after _build(); used by AppController.wire_events()):
  btn_open_files   — "Open Files…" button in Library view
  btn_build_index  — "Build Index" button in Library view
  btn_send         — "Send" button in Chat view
  prompt_entry     — tk.Text input in Chat view (aliased as prompt_entry for compat.)
  btn_cancel_rag   — "Cancel" button next to progress bar in Chat view

Public view-mutating methods (main thread only):
  set_status(text)
  set_index_info(text)
  set_progress(current, total | None)
  reset_progress()
  set_file_list(paths)
  append_chat(text, tag="agent")
  get_prompt_text() -> str
  clear_prompt()
  append_log(line)
  populate_settings(settings)  — pass settings dict from controller to display in Settings tab
  switch_view(key)    — switch sidebar active view ("chat"|"library"|"history"|"settings"|"logs")
  show()              — deiconify + lift

Only used when AXIOM_NEW_APP=1.  The legacy agentic_rag_gui UI is unchanged.
"""

from __future__ import annotations

import os
import sys
import tkinter as tk
from tkinter import ttk

from axiom_app.views.styles import (
    STYLE_CONFIG,
    UI_SPACING,
    _pal,
    apply_ttk_theme,
    get_palette,
    resolve_fonts,
)
from axiom_app.views.widgets import (
    AnimationEngine,
    CollapsibleFrame,
    IOSSegmentedToggle,
)

# ---------------------------------------------------------------------------
# App constants (keep in sync with legacy if they ever diverge)
# ---------------------------------------------------------------------------

APP_NAME    = "Axiom"
APP_VERSION = "1.0"
APP_SUBTITLE = "Personal RAG Assistant"

MODE_OPTIONS = ["Q&A", "Summary", "Tutor", "Research", "Evidence Pack"]

_SIDEBAR_W = 230  # fixed sidebar width in px


class AppView:
    """Root window with sidebar navigation and lazy-loaded content views.

    Parameters
    ----------
    root:
        The ``tk.Tk`` instance created by ``run_app()``.  AppView does not
        call ``mainloop()``; that is the caller's responsibility.
    theme_name:
        One of "space_dust" (default), "light", or "dark".
    """

    def __init__(self, root: tk.Tk, theme_name: str = "space_dust") -> None:
        self.root = root
        self._theme_name = theme_name
        self._palette = get_palette(theme_name)
        self._fonts = resolve_fonts(root)
        self._animator = AnimationEngine(root)

        # Tk variable for RAG/Direct toggle
        self._use_rag_var = tk.BooleanVar(value=True)
        # Tk variable for Mode selection
        self._mode_var = tk.StringVar(value="Q&A")
        # Tk variable for current status text
        self._status_var = tk.StringVar(value="Ready.")
        # Tk variable for index info (shown in Library toolbar)
        self._index_info_var = tk.StringVar(value="No index built.")

        self._progress_mode = "determinate"
        self._views: dict[str, ttk.Frame] = {}
        self._tab_built: dict[str, bool] = {}
        self._active_view: str | None = None
        self._sidebar_nav_buttons: dict[str, ttk.Button] = {}
        self._sidebar_accents: dict[str, tk.Frame] = {}
        self._sidebar_logo_photo = None

        # Settings display data — populated by controller via populate_settings().
        self._settings_data: dict = {}
        self._settings_entries: dict = {}          # key -> (ttk.Entry, tk.StringVar)

        # Logs tab text widget — None until _build_logs_view() runs.
        self._logs_view_text: tk.Text | None = None
        # Accumulates all log lines before the Logs tab is first opened.
        self._log_buffer: list[str] = []

        # Will be set by _build_chat_view() / _build_library_view():
        self.btn_send: ttk.Button
        self.btn_open_files: ttk.Button
        self.btn_build_index: ttk.Button
        self.btn_cancel_rag: ttk.Button
        self.prompt_entry: tk.Text   # aliased from txt_input

        apply_ttk_theme(root, self._palette, self._fonts)
        self._build()

    # ------------------------------------------------------------------
    # Window construction
    # ------------------------------------------------------------------

    def _build(self) -> None:
        self.root.title(f"{APP_NAME} — {APP_SUBTITLE}" if APP_SUBTITLE else APP_NAME)
        self.root.geometry("1320x900")
        self.root.minsize(900, 600)

        self._load_icon()

        # Root grid: col 0 = sidebar (fixed), col 1 = main content (expands)
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, minsize=_SIDEBAR_W, weight=0)
        self.root.grid_columnconfigure(1, weight=1)

        self._build_sidebar()
        self._build_main_content()

    def _build_sidebar(self) -> None:
        pal = self._palette
        outer_pad = STYLE_CONFIG["padding"]["md"]

        self.sidebar_frame = ttk.Frame(self.root, style="Sidebar.TFrame")
        self.sidebar_frame.grid(
            row=0, column=0, sticky="nsew",
            padx=(outer_pad, UI_SPACING["s"]),
            pady=(outer_pad, UI_SPACING["s"]),
        )
        self.sidebar_frame.grid_columnconfigure(0, minsize=4, weight=0)
        self.sidebar_frame.grid_columnconfigure(1, weight=1)
        self.sidebar_frame.grid_rowconfigure(50, weight=1)  # spacer

        # ── Logo ──────────────────────────────────────────────────────
        self._sidebar_logo_photo = self._load_sidebar_logo()
        if self._sidebar_logo_photo is not None:
            logo_lbl = ttk.Label(self.sidebar_frame, image=self._sidebar_logo_photo,
                                 style="Sidebar.Title.TLabel")
            logo_lbl.grid(row=0, column=0, columnspan=2, sticky="n",
                          padx=UI_SPACING["m"],
                          pady=(UI_SPACING["m"], UI_SPACING["xs"]))

        # ── Title + subtitle ──────────────────────────────────────────
        title_row_top_pad = UI_SPACING["xs"] if self._sidebar_logo_photo else UI_SPACING["l"]
        ttk.Label(
            self.sidebar_frame, text=APP_NAME, style="Sidebar.Title.TLabel"
        ).grid(row=1, column=0, columnspan=2, sticky="w",
               padx=UI_SPACING["m"], pady=(title_row_top_pad, 2))

        if APP_SUBTITLE:
            ttk.Label(
                self.sidebar_frame, text=APP_SUBTITLE, style="Sidebar.Caption.TLabel"
            ).grid(row=2, column=0, columnspan=2, sticky="w",
                   padx=UI_SPACING["m"], pady=(0, UI_SPACING["m"]))

        # ── Navigation buttons ─────────────────────────────────────────
        nav_items = [
            ("chat",     "💬  Chat"),
            ("library",  "📚  Library"),
            ("history",  "🕘  History"),
            ("settings", "⚙️   Settings"),
            ("logs",     "📋  Logs"),
        ]
        sidebar_bg = pal.get("sidebar_bg", pal.get("surface_alt", "#0D1520"))

        for idx, (key, label) in enumerate(nav_items, start=3):
            accent = tk.Frame(
                self.sidebar_frame, width=4, bd=0, highlightthickness=0,
                bg=sidebar_bg,
            )
            accent.grid(row=idx, column=0, sticky="ns", pady=(0, 3))
            self._sidebar_accents[key] = accent

            btn = ttk.Button(
                self.sidebar_frame,
                text=label,
                style="Sidebar.TButton",
                command=lambda k=key: self.switch_view(k),
            )
            btn.grid(row=idx, column=1, sticky="ew",
                     padx=(2, UI_SPACING["xs"]), pady=(0, 3))
            self._sidebar_nav_buttons[key] = btn

        # ── Bottom: separator + version badge ─────────────────────────
        ttk.Separator(self.sidebar_frame, orient="horizontal").grid(
            row=51, column=0, columnspan=2, sticky="ew",
            padx=UI_SPACING["s"], pady=(UI_SPACING["s"], 6),
        )
        ttk.Label(
            self.sidebar_frame,
            text=f"{APP_NAME} {APP_VERSION}",
            style="Sidebar.Caption.TLabel",
        ).grid(row=52, column=0, columnspan=2, sticky="w",
               padx=UI_SPACING["m"], pady=(0, UI_SPACING["xs"]))
        ttk.Label(
            self.sidebar_frame,
            text="Backend: ttk",
            style="Sidebar.Caption.TLabel",
        ).grid(row=53, column=0, columnspan=2, sticky="w",
               padx=UI_SPACING["m"], pady=(0, UI_SPACING["l"]))

    def _build_main_content(self) -> None:
        outer_pad = STYLE_CONFIG["padding"]["md"]

        self.main_content_frame = ttk.Frame(self.root, style="MainContent.TFrame")
        self.main_content_frame.grid(
            row=0, column=1, sticky="nsew",
            padx=(0, outer_pad), pady=(outer_pad, UI_SPACING["s"]),
        )
        self.main_content_frame.grid_rowconfigure(0, weight=1)
        self.main_content_frame.grid_columnconfigure(0, weight=1)

        # Create all view frames now (stacked; only one visible at a time).
        for key in ("chat", "library", "history", "settings", "logs"):
            frame = ttk.Frame(self.main_content_frame, style="Card.TFrame")
            frame.grid(row=0, column=0, sticky="nsew")
            self._views[key] = frame
            self._tab_built[key] = False

        # Build chat view immediately; others are lazy-built on first switch.
        self._build_chat_view()
        self._tab_built["chat"] = True

        # Activate chat to start.
        self.switch_view("chat")

    # ------------------------------------------------------------------
    # View builders
    # ------------------------------------------------------------------

    def _build_chat_view(self) -> None:
        """Chat view: toolbar + chat display + collapsible sections + input bar."""
        pal = self._palette
        frame = self._views["chat"]
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        outer = ttk.Frame(frame, style="Card.TFrame")
        outer.pack(fill=tk.BOTH, expand=True)

        # ── Toolbar ───────────────────────────────────────────────────
        toolbar = ttk.Frame(outer, style="Card.Flat.TFrame",
                            padding=(UI_SPACING["s"], UI_SPACING["xs"]))
        toolbar.pack(fill="x", pady=(0, UI_SPACING["xs"]))

        # Left side: Mode selector
        ttk.Label(toolbar, text="Mode:", style="Caption.TLabel").pack(
            side="left", padx=(0, 4)
        )
        self._mode_combo = ttk.Combobox(
            toolbar, textvariable=self._mode_var,
            values=MODE_OPTIONS, state="readonly", width=14,
        )
        self._mode_combo.pack(side="left", padx=(0, UI_SPACING["s"]))

        # RAG/Direct toggle
        self._rag_toggle = IOSSegmentedToggle(
            toolbar,
            options=["RAG", "Direct"],
            variable=self._use_rag_var,
            palette=pal,
        )
        self._rag_toggle.pack(side="left", padx=(0, UI_SPACING["s"]))

        # Right side: Evidence panel toggle + New Chat + LLM badge
        self._llm_badge_var = tk.StringVar(value="🤖 LLM: --")
        ttk.Label(toolbar, textvariable=self._llm_badge_var,
                  style="Badge.TLabel").pack(side="right", padx=(UI_SPACING["s"], 0))

        ttk.Button(
            toolbar, text="＋ New Chat", style="Secondary.TButton",
            command=self._on_new_chat,
        ).pack(side="right", padx=(UI_SPACING["xs"], 0))

        self._evidence_toggle_btn = ttk.Button(
            toolbar, text="⊞ Evidence", style="Secondary.TButton",
            command=self._toggle_evidence_panel,
        )
        self._evidence_toggle_btn.pack(side="right", padx=(UI_SPACING["xs"], 0))

        # ── Body: chat pane + optional evidence pane ──────────────────
        body = ttk.Frame(outer, style="Card.TFrame")
        body.pack(fill=tk.BOTH, expand=True)

        chat_pane = ttk.Frame(body, style="Card.Elevated.TFrame",
                              padding=UI_SPACING["m"])
        chat_pane.pack(side="left", fill=tk.BOTH, expand=True)

        self._evidence_sep = tk.Frame(body, width=1, bg=pal["border"],
                                      bd=0, highlightthickness=0)
        self._evidence_pane = ttk.Frame(body, style="Card.Elevated.TFrame",
                                         padding=UI_SPACING["m"])
        self._evidence_pane.pack_propagate(False)
        self._evidence_visible = False

        # ── Input bar (pack FIRST so it stays at the bottom) ──────────
        input_bar = ttk.Frame(chat_pane, style="Card.Flat.TFrame",
                              padding=UI_SPACING["m"])
        input_bar.pack(fill="x", side="bottom")

        # ── Chat display ──────────────────────────────────────────────
        chat_surface = ttk.Frame(chat_pane, style="Card.Elevated.TFrame")
        chat_surface.pack(fill=tk.BOTH, expand=True)
        chat_surface.rowconfigure(0, weight=1)
        chat_surface.columnconfigure(0, weight=1)

        self.chat_display = tk.Text(
            chat_surface,
            state="disabled",
            wrap=tk.WORD,
            font=self._fonts["body"],
            bg=pal.get("content_bg", pal["surface"]),
            fg=pal["text"],
            insertbackground=pal["text"],
            selectbackground=pal["selection_bg"],
            selectforeground=pal["selection_fg"],
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            padx=UI_SPACING["m"],
            pady=UI_SPACING["s"],
        )
        self.chat_display.grid(row=0, column=0, sticky="nsew")

        chat_scroll = ttk.Scrollbar(chat_surface, orient="vertical",
                                    command=self.chat_display.yview)
        chat_scroll.grid(row=0, column=1, sticky="ns")
        self.chat_display.configure(yscrollcommand=chat_scroll.set)

        # Text tags
        self.chat_display.tag_config(
            "user",
            font=self._fonts["body_bold"],
            spacing1=16, spacing3=16,
            lmargin1=20, lmargin2=28, rmargin=20,
            background=pal.get("chat_user_bg", pal["surface"]),
        )
        self.chat_display.tag_config(
            "agent",
            font=self._fonts["body"],
            spacing1=14, spacing3=18,
            lmargin1=20, lmargin2=20, rmargin=20,
            background=pal.get("chat_agent_bg", pal["surface"]),
        )
        self.chat_display.tag_config(
            "system",
            font=(self._fonts["caption"][0], self._fonts["caption"][1], "italic"),
            spacing1=8, spacing3=8,
            lmargin1=20, rmargin=20,
            foreground=pal.get("muted_text", "#8A9DC0"),
            background=pal.get("chat_system_bg", pal["surface"]),
        )
        self.chat_display.tag_config(
            "citation",
            foreground=pal.get("link", "#6BD4FF"),
            underline=1,
            font=self._fonts["code"],
        )
        self.chat_display.tag_config(
            "source",
            font=self._fonts["code"],
            foreground=pal.get("source", pal.get("muted_text", "#8A9DC0")),
        )
        self.chat_display.tag_config(
            "thinking_indicator",
            font=(self._fonts["caption"][0], self._fonts["caption"][1], "italic"),
            spacing1=10, spacing3=10,
            lmargin1=20, rmargin=20,
            foreground=pal.get("primary", "#4D9EFF"),
            background=pal.get("chat_agent_bg", pal["surface"]),
        )

        # ── Collapsible sections inside input bar ──────────────────────
        # Logs section
        _coll_frame = ttk.Frame(input_bar)
        _coll_frame.pack(fill="x", pady=(0, UI_SPACING["xs"]))

        self._logs_section = CollapsibleFrame(
            _coll_frame, "Logs & telemetry",
            expanded=False, animator=self._animator,
        )
        self._logs_section.pack(fill="x", pady=(0, 4))

        self._log_text = tk.Text(
            self._logs_section.content,
            state="disabled",
            wrap=tk.WORD,
            height=4,
            font=self._fonts["code"],
            bg=pal.get("input_bg", "#07101A"),
            fg=pal.get("muted_text", "#8A9DC0"),
            insertbackground=pal["text"],
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
        )
        self._log_text.pack(fill=tk.BOTH, expand=True,
                            padx=UI_SPACING["s"], pady=UI_SPACING["xs"])
        log_scroll = ttk.Scrollbar(self._logs_section.content, orient="vertical",
                                   command=self._log_text.yview)
        log_scroll.pack(side="right", fill="y")
        self._log_text.configure(yscrollcommand=log_scroll.set)

        # Progress row
        progress_row = ttk.Frame(input_bar, style="Card.Flat.TFrame")
        progress_row.pack(fill="x", pady=(0, 4))

        self._status_label = ttk.Label(
            progress_row, textvariable=self._status_var, style="Status.TLabel"
        )
        self._status_label.pack(side="left", padx=(0, UI_SPACING["s"]))

        self.rag_progress = ttk.Progressbar(
            progress_row, orient="horizontal", mode="determinate", length=180
        )
        self.rag_progress.pack(side="left", padx=(0, UI_SPACING["xs"]))

        self.btn_cancel_rag = ttk.Button(
            progress_row, text="Cancel", style="Secondary.TButton", state="disabled"
        )
        self.btn_cancel_rag.pack(side="left")

        # Text input + Send button
        input_row = ttk.Frame(input_bar, style="Card.Flat.TFrame")
        input_row.pack(fill="x", pady=(UI_SPACING["xs"], 0))
        input_row.columnconfigure(0, weight=1)
        input_row.columnconfigure(1, weight=0)

        self.txt_input = tk.Text(
            input_row,
            height=3,
            wrap=tk.WORD,
            font=self._fonts["body"],
            bg=pal.get("input_bg", "#07101A"),
            fg=pal["text"],
            insertbackground=pal["text"],
            selectbackground=pal["selection_bg"],
            selectforeground=pal["selection_fg"],
            relief="flat",
            borderwidth=0,
            highlightthickness=2,
            highlightbackground=pal.get("outline", "#2A3E58"),
            highlightcolor=pal.get("focus_ring", pal.get("primary", "#4D9EFF")),
        )
        self.txt_input.grid(row=0, column=0, sticky="ew", padx=(0, UI_SPACING["s"]))

        self.btn_send = ttk.Button(
            input_row, text="Send", style="Primary.TButton", width=8
        )
        self.btn_send.grid(row=0, column=1, sticky="e")

        # Compatibility alias: controllers reference prompt_entry
        self.prompt_entry = self.txt_input

        # Bind Ctrl+Enter to send
        self.txt_input.bind("<Control-Return>", lambda _e: self._on_ctrl_enter())

    def _build_library_view(self) -> None:
        """Library view: file picker + build index + file list."""
        frame = self._views["library"]
        frame.rowconfigure(1, weight=1)
        frame.columnconfigure(0, weight=1)

        # Toolbar
        toolbar = ttk.Frame(frame, style="Card.Flat.TFrame",
                            padding=(UI_SPACING["s"], UI_SPACING["xs"]))
        toolbar.grid(row=0, column=0, sticky="ew",
                     padx=UI_SPACING["m"], pady=(UI_SPACING["m"], UI_SPACING["xs"]))

        self.btn_open_files = ttk.Button(toolbar, text="Open Files…",
                                          style="Primary.TButton")
        self.btn_open_files.pack(side="left", padx=(0, UI_SPACING["xs"]))

        self.btn_build_index = ttk.Button(toolbar, text="Build Index",
                                           style="Secondary.TButton")
        self.btn_build_index.pack(side="left")

        ttk.Label(toolbar, textvariable=self._index_info_var,
                  style="Caption.TLabel").pack(
            side="left", padx=(UI_SPACING["m"], 0)
        )

        # File listbox
        lb_frame = ttk.Frame(frame, style="Card.Elevated.TFrame")
        lb_frame.grid(row=1, column=0, sticky="nsew",
                      padx=UI_SPACING["m"], pady=(0, UI_SPACING["m"]))
        lb_frame.rowconfigure(0, weight=1)
        lb_frame.columnconfigure(0, weight=1)

        self._file_listbox = tk.Listbox(
            lb_frame,
            selectmode="extended",
            activestyle="dotbox",
            bg=self._palette.get("surface_alt", "#1E2D42"),
            fg=self._palette["text"],
            selectbackground=self._palette["selection_bg"],
            selectforeground=self._palette["selection_fg"],
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
        )
        self._file_listbox.grid(row=0, column=0, sticky="nsew",
                                padx=UI_SPACING["s"], pady=UI_SPACING["s"])

        _vsb = ttk.Scrollbar(lb_frame, orient="vertical",
                             command=self._file_listbox.yview)
        _vsb.grid(row=0, column=1, sticky="ns",
                  pady=UI_SPACING["s"])
        self._file_listbox.configure(yscrollcommand=_vsb.set)

        _hsb = ttk.Scrollbar(lb_frame, orient="horizontal",
                             command=self._file_listbox.xview)
        _hsb.grid(row=1, column=0, sticky="ew",
                  padx=UI_SPACING["s"])
        self._file_listbox.configure(xscrollcommand=_hsb.set)

        # Library also shows index progress
        self.progress = ttk.Progressbar(
            frame, orient="horizontal", mode="determinate"
        )
        self.progress.grid(row=2, column=0, sticky="ew",
                           padx=UI_SPACING["m"], pady=(0, UI_SPACING["s"]))

    def _build_history_view(self) -> None:
        """History view: placeholder stub."""
        frame = self._views["history"]
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        ttk.Label(
            frame,
            text="[ History — Session history will appear here. ]",
            foreground=self._palette.get("muted_text", "#8A9DC0"),
            anchor="center",
            justify="center",
        ).grid(row=0, column=0, sticky="nsew")

    def _build_settings_view(self) -> None:
        """Settings view: scrollable read-only form of active settings."""
        pal = self._palette
        frame = self._views["settings"]
        frame.rowconfigure(1, weight=1)
        frame.columnconfigure(0, weight=1)

        # ── Header ────────────────────────────────────────────────────
        hdr = ttk.Frame(frame, style="Card.Flat.TFrame",
                        padding=(UI_SPACING["m"], UI_SPACING["s"]))
        hdr.grid(row=0, column=0, sticky="ew")
        ttk.Label(hdr, text="Settings", style="Header.TLabel").pack(side="left")

        # ── Scrollable canvas area ─────────────────────────────────────
        canvas_host = ttk.Frame(frame, style="Card.TFrame")
        canvas_host.grid(row=1, column=0, sticky="nsew",
                         padx=UI_SPACING["m"], pady=(UI_SPACING["xs"], 0))
        canvas_host.rowconfigure(0, weight=1)
        canvas_host.columnconfigure(0, weight=1)

        canvas = tk.Canvas(
            canvas_host,
            bg=pal.get("surface", "#111827"),
            highlightthickness=0,
            bd=0,
        )
        canvas.grid(row=0, column=0, sticky="nsew")

        vsb = ttk.Scrollbar(canvas_host, orient="vertical", command=canvas.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        canvas.configure(yscrollcommand=vsb.set)

        # Inner frame lives inside the canvas window
        inner = ttk.Frame(canvas, style="Card.TFrame")
        inner.columnconfigure(1, weight=1)

        canvas_window = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_inner_configure(_event: tk.Event) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(event: tk.Event) -> None:
            canvas.itemconfig(canvas_window, width=event.width)

        inner.bind("<Configure>", _on_inner_configure)
        canvas.bind("<Configure>", _on_canvas_configure)

        def _on_mousewheel(event: tk.Event) -> None:
            try:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except tk.TclError:
                pass

        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        # ── Section definitions ────────────────────────────────────────
        sections = [
            ("UI", [
                ("ui_backend",  "UI Backend"),
                ("theme",       "Theme"),
            ]),
            ("Embeddings", [
                ("embeddings_backend",         "Embeddings Backend"),
                ("sentence_transformers_model", "Sentence Transformers Model"),
                ("cache_dir",                  "Cache Directory"),
            ]),
            ("Ingestion", [
                ("chunk_size",      "Chunk Size"),
                ("chunk_overlap",   "Chunk Overlap"),
                ("document_loader", "Document Loader"),
            ]),
            ("Retrieval", [
                ("top_k", "Top-K Results"),
            ]),
            ("Logging", [
                ("log_dir",   "Log Directory"),
                ("log_level", "Log Level"),
            ]),
        ]

        row_idx = 0
        for section_title, keys in sections:
            ttk.Label(
                inner,
                text=section_title.upper(),
                style="Overline.TLabel",
            ).grid(
                row=row_idx, column=0, columnspan=2, sticky="w",
                padx=UI_SPACING["m"],
                pady=(UI_SPACING["l"] if row_idx > 0 else UI_SPACING["m"],
                      UI_SPACING["xs"]),
            )
            row_idx += 1

            ttk.Separator(inner, orient="horizontal").grid(
                row=row_idx, column=0, columnspan=2, sticky="ew",
                padx=UI_SPACING["m"], pady=(0, UI_SPACING["xs"]),
            )
            row_idx += 1

            for key, display_label in keys:
                ttk.Label(
                    inner,
                    text=display_label,
                    style="Caption.TLabel",
                    anchor="e",
                    width=26,
                ).grid(
                    row=row_idx, column=0, sticky="e",
                    padx=(UI_SPACING["m"], UI_SPACING["s"]),
                    pady=(0, UI_SPACING["xs"]),
                )
                val = str(self._settings_data.get(key, ""))
                entry_var = tk.StringVar(value=val)
                entry = ttk.Entry(
                    inner,
                    textvariable=entry_var,
                    state="readonly",
                    font=self._fonts["code"],
                )
                entry.grid(
                    row=row_idx, column=1, sticky="ew",
                    padx=(0, UI_SPACING["m"]),
                    pady=(0, UI_SPACING["xs"]),
                )
                self._settings_entries[key] = (entry, entry_var)
                row_idx += 1

        # Bottom spacer
        ttk.Frame(inner, style="Card.TFrame", height=UI_SPACING["l"]).grid(
            row=row_idx, column=0, columnspan=2,
        )

        # ── Footer ────────────────────────────────────────────────────
        footer = ttk.Frame(frame, style="Card.Flat.TFrame",
                           padding=(UI_SPACING["m"], UI_SPACING["s"]))
        footer.grid(row=2, column=0, sticky="ew")
        ttk.Label(
            footer,
            text="Edit settings.json at repository root to modify.",
            style="Caption.TLabel",
        ).pack(side="left")

    def _build_logs_view(self) -> None:
        """Logs view: full-screen scrollable log text area."""
        pal = self._palette
        frame = self._views["logs"]
        frame.rowconfigure(1, weight=1)
        frame.columnconfigure(0, weight=1)

        # ── Header ────────────────────────────────────────────────────
        hdr = ttk.Frame(frame, style="Card.Flat.TFrame",
                        padding=(UI_SPACING["m"], UI_SPACING["s"]))
        hdr.grid(row=0, column=0, sticky="ew")
        ttk.Label(hdr, text="Logs & Telemetry",
                  style="Header.TLabel").pack(side="left")

        # ── Text area ─────────────────────────────────────────────────
        text_host = ttk.Frame(frame, style="Card.Elevated.TFrame")
        text_host.grid(row=1, column=0, sticky="nsew",
                       padx=UI_SPACING["m"],
                       pady=(UI_SPACING["xs"], UI_SPACING["m"]))
        text_host.rowconfigure(0, weight=1)
        text_host.columnconfigure(0, weight=1)

        self._logs_view_text = tk.Text(
            text_host,
            state="disabled",
            wrap=tk.WORD,
            font=self._fonts["code"],
            bg=pal.get("input_bg", "#07101A"),
            fg=pal.get("muted_text", "#8A9DC0"),
            insertbackground=pal["text"],
            selectbackground=pal["selection_bg"],
            selectforeground=pal["selection_fg"],
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            padx=UI_SPACING["s"],
            pady=UI_SPACING["s"],
        )
        self._logs_view_text.grid(row=0, column=0, sticky="nsew")

        logs_scroll = ttk.Scrollbar(text_host, orient="vertical",
                                    command=self._logs_view_text.yview)
        logs_scroll.grid(row=0, column=1, sticky="ns")
        self._logs_view_text.configure(yscrollcommand=logs_scroll.set)

        # Replay any log lines buffered before this tab was first opened
        if self._log_buffer:
            self._logs_view_text.configure(state="normal")
            for buffered_line in self._log_buffer:
                self._logs_view_text.insert(
                    "end",
                    buffered_line if buffered_line.endswith("\n") else buffered_line + "\n",
                )
            self._logs_view_text.see("end")
            self._logs_view_text.configure(state="disabled")

    # ------------------------------------------------------------------
    # View switching
    # ------------------------------------------------------------------

    def switch_view(self, key: str) -> None:
        """Show the *key* view, lazy-building it on first access."""
        if key not in self._views:
            return

        # Lazy-build on first access
        if not self._tab_built.get(key):
            builders = {
                "library":  self._build_library_view,
                "history":  self._build_history_view,
                "settings": self._build_settings_view,
                "logs":     self._build_logs_view,
            }
            builder = builders.get(key)
            if builder:
                builder()
            self._tab_built[key] = True

        # Raise the requested view
        self._views[key].tkraise()
        self._active_view = key

        # Update sidebar accent bars
        pal = self._palette
        active_bg   = pal.get("primary",     "#4D9EFF")
        inactive_bg = pal.get("sidebar_bg",  "#0D1520")
        for k, accent in self._sidebar_accents.items():
            try:
                accent.configure(bg=active_bg if k == key else inactive_bg)
            except tk.TclError:
                pass
        for k, btn in self._sidebar_nav_buttons.items():
            btn.configure(style="Sidebar.Active.TButton" if k == key
                          else "Sidebar.TButton")

    # ------------------------------------------------------------------
    # Public interface (called from main thread only)
    # ------------------------------------------------------------------

    def set_status(self, text: str) -> None:
        """Update the status label in the chat input bar."""
        self._status_var.set(text)

    def set_index_info(self, text: str) -> None:
        """Update the index-state label in the Library toolbar."""
        self._index_info_var.set(text)

    def set_progress(self, current: int, total: int | None) -> None:
        """Update the progress bar (indeterminate when *total* is None or 0)."""
        for bar in (self.rag_progress,):
            try:
                if not total:
                    if self._progress_mode != "indeterminate":
                        bar.configure(mode="indeterminate")
                        self._progress_mode = "indeterminate"
                        bar.start(15)
                else:
                    if self._progress_mode != "determinate":
                        bar.stop()
                        bar.configure(mode="determinate")
                        self._progress_mode = "determinate"
                    bar["value"] = min(100, int(current / total * 100))
            except tk.TclError:
                pass

    def reset_progress(self) -> None:
        """Stop animation and zero the progress bar."""
        if self._progress_mode == "indeterminate":
            try:
                self.rag_progress.stop()
                self.rag_progress.configure(mode="determinate")
            except tk.TclError:
                pass
            self._progress_mode = "determinate"
        try:
            self.rag_progress["value"] = 0
        except tk.TclError:
            pass

    def set_file_list(self, paths: list[str]) -> None:
        """Replace the Library listbox contents with *paths*."""
        try:
            self._file_listbox.delete(0, "end")
            for p in paths:
                self._file_listbox.insert("end", p)
        except (tk.TclError, AttributeError):
            pass

    def append_chat(self, text: str, tag: str = "agent") -> None:
        """Append *text* (with optional *tag*) to the chat display."""
        self.chat_display.configure(state="normal")
        self.chat_display.insert("end", text, tag)
        self.chat_display.see("end")
        self.chat_display.configure(state="disabled")

    def get_prompt_text(self) -> str:
        """Return the current contents of the prompt input."""
        try:
            return self.txt_input.get("1.0", "end-1c")
        except tk.TclError:
            return ""

    def clear_prompt(self) -> None:
        """Empty the prompt input."""
        try:
            self.txt_input.delete("1.0", "end")
        except tk.TclError:
            pass

    def append_log(self, line: str) -> None:
        """Append *line* to the chat Logs collapsible section and the Logs tab."""
        # Always buffer so the Logs tab can replay on first open.
        self._log_buffer.append(line)

        # Write to chat-view collapsible log widget.
        try:
            self._log_text.configure(state="normal")
            self._log_text.insert("end", line if line.endswith("\n") else line + "\n")
            self._log_text.see("end")
            self._log_text.configure(state="disabled")
        except tk.TclError:
            pass

        # Write to dedicated Logs tab widget if it has been built.
        if self._logs_view_text is not None:
            try:
                self._logs_view_text.configure(state="normal")
                self._logs_view_text.insert(
                    "end", line if line.endswith("\n") else line + "\n"
                )
                self._logs_view_text.see("end")
                self._logs_view_text.configure(state="disabled")
            except tk.TclError:
                pass

    def populate_settings(self, settings: dict) -> None:
        """Store settings data and update the Settings view if already built.

        Called by the controller once after ``wire_events()``.  Safe to call
        before or after the Settings tab is first opened.
        """
        self._settings_data = dict(settings)
        if not self._tab_built.get("settings"):
            # Tab not yet built — data is stored and will be read by
            # _build_settings_view() when the user first opens Settings.
            return
        # Tab already built — update existing StringVars in place.
        for key, (_entry, var) in self._settings_entries.items():
            var.set(str(self._settings_data.get(key, "")))

    def show(self) -> None:
        """Make the window visible."""
        self.root.deiconify()
        self.root.lift()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _on_ctrl_enter(self) -> None:
        """Ctrl+Enter in the input box triggers the Send button."""
        try:
            if str(self.btn_send.cget("state")) != "disabled":
                self.btn_send.invoke()
        except tk.TclError:
            pass

    def _on_new_chat(self) -> None:
        """Clear chat display (placeholder — controller can override)."""
        self.chat_display.configure(state="normal")
        self.chat_display.delete("1.0", "end")
        self.chat_display.configure(state="disabled")
        self.set_status("New chat started.")

    def _toggle_evidence_panel(self) -> None:
        """Toggle the evidence side pane (placeholder; controller can wire)."""
        self._evidence_visible = not self._evidence_visible
        if self._evidence_visible:
            self._evidence_sep.pack(side="left", fill="y")
            self._evidence_pane.pack(side="left", fill="y")
            self._evidence_pane.configure(width=420)
        else:
            self._evidence_sep.pack_forget()
            self._evidence_pane.pack_forget()

    def _load_icon(self) -> None:
        """Best-effort window icon loading (PNG preferred; .ico on Windows)."""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        repo_root = os.path.join(script_dir, "..", "..")
        candidates = [
            os.path.join(repo_root, "logo.png"),
            os.path.join(repo_root, "assets", "axiom.png"),
            os.path.join(repo_root, "assets", "app.png"),
        ]
        self._app_icon_photo = None
        for path in candidates:
            if not os.path.exists(path):
                continue
            try:
                self._app_icon_photo = tk.PhotoImage(file=path)
                self.root.iconphoto(True, self._app_icon_photo)
                break
            except Exception:
                pass

    def _load_sidebar_logo(self) -> tk.PhotoImage | None:
        """Best-effort sidebar logo loading; returns a Tk image or None."""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        repo_root = os.path.join(script_dir, "..", "..")
        candidates = [
            os.path.join(repo_root, "assets", "axiom_logo.png"),
            os.path.join(repo_root, "assets", "axiom.png"),
            os.path.join(repo_root, "logo.png"),
        ]
        for path in candidates:
            if not os.path.exists(path):
                continue
            try:
                logo = tk.PhotoImage(file=path)
                max_dim = 120
                w = max(1, int(logo.width()))
                h = max(1, int(logo.height()))
                ds = max(1, (max(w, h) + max_dim - 1) // max_dim)
                if ds > 1:
                    logo = logo.subsample(ds, ds)
                return logo
            except Exception:
                pass
        return None
