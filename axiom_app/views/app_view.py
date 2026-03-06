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
import pathlib
import re
import tkinter as tk
from tkinter import ttk

from axiom_app.views.styles import (
    STYLE_CONFIG,
    UI_SPACING,
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

# ---------------------------------------------------------------------------
# Settings specification — module-level so it is defined once, not per-call.
# Format per row: (setting_key, display_label, widget_type, options_or_None)
# widget_type in: "combobox" | "entry" | "entry_password" | "checkbutton" | "text"
# ---------------------------------------------------------------------------

_SETTINGS_SPEC: list[tuple[str, list]] = [
    ("UI & Startup", [
        ("theme",                "Theme",         "combobox",
            ["space_dust", "light", "dark"]),
        ("startup_mode_setting", "Startup Mode",  "combobox",
            ["advanced", "basic", "test"]),
        ("ui_backend",           "UI Backend",    "combobox",
            ["ttk"]),
    ]),
    ("LLM", [
        ("llm_provider",    "LLM Provider",  "combobox",
            ["anthropic", "openai", "google", "xai",
             "local_lm_studio", "local_gguf", "mock"]),
        ("llm_model",       "LLM Model",     "entry",       None),
        ("llm_model_custom","Custom Model",  "entry",       None),
        ("llm_temperature", "Temperature",   "entry",       None),
        ("llm_max_tokens",  "Max Tokens",    "entry",       None),
        ("verbose_mode",    "Verbose Mode",  "checkbutton", None),
    ]),
    ("Local LLM", [
        ("local_llm_url",             "LM Studio URL",   "entry", None),
        ("local_gguf_model_path",     "GGUF Model Path", "file_browse", None),
        ("local_gguf_context_length", "Context Length",  "entry", None),
        ("local_gguf_gpu_layers",     "GPU Layers",      "entry", None),
        ("local_gguf_threads",        "CPU Threads",     "entry", None),
    ]),
    ("System Instructions", [
        ("system_instructions", "System Prompt", "text", None),
    ]),
    ("Embeddings", [
        ("embeddings_backend",    "Backend",          "combobox",
            ["mock", "sentence_transformers", "voyage", "openai"]),
        ("embedding_provider",    "Provider",         "combobox",
            ["voyage", "openai", "google",
             "local_huggingface", "local_sentence_transformers", "mock"]),
        ("embedding_model",       "Model",            "entry", None),
        ("embedding_model_custom","Custom Model",     "entry", None),
        ("sentence_transformers_model", "ST Model",   "entry", None),
        ("local_st_cache_dir",    "ST Cache Dir",     "entry", None),
        ("local_st_batch_size",   "ST Batch Size",    "entry", None),
        ("force_embedding_compat","Force Compat",     "checkbutton", None),
        ("cache_dir",             "Axiom Cache Dir",  "entry", None),
    ]),
    ("Vector DB", [
        ("vector_db_type",  "DB Type",       "combobox",
            ["chroma", "weaviate"]),
        ("weaviate_url",    "Weaviate URL",  "entry",          None),
        ("weaviate_api_key","Weaviate Key",  "entry_password", None),
    ]),
    ("API Keys", [
        ("api_key_openai",       "OpenAI",       "entry_password", None),
        ("api_key_anthropic",    "Anthropic",    "entry_password", None),
        ("api_key_google",       "Google",       "entry_password", None),
        ("api_key_xai",          "xAI",          "entry_password", None),
        ("api_key_cohere",       "Cohere",       "entry_password", None),
        ("api_key_mistral",      "Mistral",      "entry_password", None),
        ("api_key_groq",         "Groq",         "entry_password", None),
        ("api_key_azure_openai", "Azure OpenAI", "entry_password", None),
        ("api_key_together",     "Together AI",  "entry_password", None),
        ("api_key_voyage",       "Voyage",       "entry_password", None),
        ("api_key_huggingface",  "HuggingFace",  "entry_password", None),
        ("api_key_fireworks",    "Fireworks",    "entry_password", None),
        ("api_key_perplexity",   "Perplexity",   "entry_password", None),
    ]),
    ("Ingestion", [
        ("document_loader",              "Document Loader",     "combobox",
            ["auto", "plain"]),
        ("chunk_size",                   "Chunk Size",          "entry", None),
        ("chunk_overlap",                "Chunk Overlap",       "entry", None),
        ("structure_aware_ingestion",    "Structure-Aware",     "checkbutton", None),
        ("semantic_layout_ingestion",    "Semantic Layout",     "checkbutton", None),
        ("build_digest_index",           "Build Digest Index",  "checkbutton", None),
        ("build_comprehension_index",    "Build Comprehension", "checkbutton", None),
        ("comprehension_extraction_depth","Extraction Depth",   "combobox",
            ["Standard", "Deep", "Exhaustive"]),
    ]),
    ("Retrieval", [
        ("top_k",           "Top-K (final)",   "entry",    None),
        ("retrieval_k",     "Retrieval K",     "entry",    None),
        ("retrieval_mode",  "Retrieval Mode",  "combobox",
            ["flat", "hierarchical"]),
        ("search_type",     "Search Type",     "combobox",
            ["similarity", "mmr"]),
        ("kg_query_mode",   "KG Query Mode",   "combobox",
            ["naive", "local", "global", "hybrid", "mix", "bypass"]),
        ("mmr_lambda",      "MMR Lambda",      "entry",    None),
        ("use_reranker",    "Use Reranker",    "checkbutton", None),
        ("use_sub_queries", "Sub-Queries",     "checkbutton", None),
        ("subquery_max_docs","Max Sub-Q Docs", "entry",    None),
    ]),
    ("Session", [
        ("chat_history_max_turns", "History Turns", "entry", None),
        ("output_style", "Output Style", "combobox",
            ["Default answer", "Detailed answer", "Brief / exec summary",
             "Script / talk track", "Structured report", "Blinkist-style summary"]),
        ("selected_mode", "Mode", "combobox",
            ["Q&A", "Summary", "Tutor", "Research", "Evidence Pack"]),
    ]),
    ("Agentic", [
        ("agentic_mode",           "Agentic Mode",   "checkbutton", None),
        ("agentic_max_iterations", "Max Iterations", "entry",       None),
        ("show_retrieved_context", "Show Context",   "checkbutton", None),
    ]),
    ("Frontier / Advanced", [
        ("enable_summarizer",                       "Summarizer",           "checkbutton", None),
        ("enable_langextract",                      "LangExtract",          "checkbutton", None),
        ("enable_structured_extraction",            "Structured Extraction","checkbutton", None),
        ("enable_recursive_memory",                 "Recursive Memory",     "checkbutton", None),
        ("enable_recursive_retrieval",              "Recursive Retrieval",  "checkbutton", None),
        ("enable_citation_v2",                      "Citation v2",          "checkbutton", None),
        ("enable_claim_level_grounding_citefix_lite","CiteFix Lite",        "checkbutton", None),
        ("agent_lightning_enabled",                 "Lightning Mode",       "checkbutton", None),
        ("prefer_comprehension_index",              "Prefer Comprehension", "checkbutton", None),
    ]),
    ("Logging", [
        ("log_dir",   "Log Directory", "entry",    None),
        ("log_level", "Log Level",     "combobox",
            ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]),
    ]),
]

# Sections expanded by default on first open
_SETTINGS_EXPANDED = {"UI & Startup", "LLM", "Embeddings"}


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
        self._history_rows: list = []
        self._history_session_by_id: dict[str, object] = {}
        self._evidence_source_by_sid: dict[str, dict] = {}
        self._evidence_source_by_iid: dict[str, str] = {}

        # Settings display data — populated by controller via populate_settings().
        self._settings_data: dict = {}
        self._settings_entries: dict = {}          # key -> (ttk.Entry, tk.StringVar)
        self._mode_state_callback = None

        # Logs tab text widget — None until _build_logs_view() runs.
        self._logs_view_text: tk.Text | None = None
        # Accumulates all log lines before the Logs tab is first opened.
        self._log_buffer: list[str] = []

        # Will be set by _build_chat_view() / _build_library_view() / _build_settings_view():
        self.btn_send: ttk.Button
        self.btn_open_files: ttk.Button
        self.btn_build_index: ttk.Button
        self.btn_cancel_rag: ttk.Button
        self.btn_save_settings: ttk.Button
        self.btn_new_chat: ttk.Button
        self.btn_history_new_chat: ttk.Button
        self.btn_history_open: ttk.Button
        self.btn_history_delete: ttk.Button
        self.btn_history_export: ttk.Button
        self.btn_history_refresh: ttk.Button
        self.prompt_entry: tk.Text   # aliased from txt_input

        apply_ttk_theme(root, self._palette, self._fonts)
        self._build()

        # Keep toolbar mode widgets and canonical settings keys in sync.
        self._mode_var.trace_add("write", self._on_mode_var_changed)
        self._use_rag_var.trace_add("write", self._on_chat_path_var_changed)

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def apply_theme(self, theme_name: str) -> None:
        """Re-apply *theme_name* to all ttk styles and the root window.

        Called at runtime when the user saves a new theme choice via the
        Settings GUI, so the change takes effect immediately without restarting.
        """
        self._theme_name = theme_name
        self._palette = get_palette(theme_name)
        apply_ttk_theme(self.root, self._palette, self._fonts)

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
            command=self._on_rag_toggle_clicked,
        )
        self._rag_toggle.pack(side="left", padx=(0, UI_SPACING["s"]))

        # Right side: Evidence panel toggle + New Chat + LLM badge
        self._llm_badge_var = tk.StringVar(value="🤖 LLM: --")
        ttk.Label(toolbar, textvariable=self._llm_badge_var,
                  style="Badge.TLabel").pack(side="right", padx=(UI_SPACING["s"], 0))

        self.btn_new_chat = ttk.Button(
            toolbar, text="＋ New Chat", style="Secondary.TButton",
            command=self._on_new_chat,
        )
        self.btn_new_chat.pack(side="right", padx=(UI_SPACING["xs"], 0))

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
        self._build_evidence_panel()

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
        self.chat_display.tag_bind("citation", "<Button-1>", self._on_citation_click)
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

    def _build_evidence_panel(self) -> None:
        """Construct the right-side evidence pane used by chat retrieval."""
        frame = self._evidence_pane
        frame.columnconfigure(0, weight=1)

        header = ttk.Frame(frame, style="Card.Flat.TFrame")
        header.pack(fill="x", pady=(0, UI_SPACING["s"]))
        ttk.Label(header, text="Evidence", style="Header.TLabel").pack(anchor="w")
        self._evidence_status_var = tk.StringVar(value="No retrieved evidence yet.")
        ttk.Label(
            header,
            textvariable=self._evidence_status_var,
            style="Caption.TLabel",
            wraplength=360,
            justify="left",
        ).pack(anchor="w", pady=(UI_SPACING["xs"], 0))

        list_host = ttk.Frame(frame, style="Card.Elevated.TFrame")
        list_host.pack(fill="both", expand=True)
        list_host.rowconfigure(0, weight=1)
        list_host.columnconfigure(0, weight=1)

        self._evidence_tree = ttk.Treeview(
            list_host,
            columns=("sid", "source", "score"),
            show="headings",
            selectmode="browse",
            height=10,
        )
        self._evidence_tree.heading("sid", text="ID")
        self._evidence_tree.heading("source", text="Source")
        self._evidence_tree.heading("score", text="Score")
        self._evidence_tree.column("sid", width=54, anchor="center")
        self._evidence_tree.column("source", width=180, anchor="w")
        self._evidence_tree.column("score", width=72, anchor="e")
        self._evidence_tree.grid(row=0, column=0, sticky="nsew")
        evidence_scroll = ttk.Scrollbar(
            list_host,
            orient="vertical",
            command=self._evidence_tree.yview,
        )
        evidence_scroll.grid(row=0, column=1, sticky="ns")
        self._evidence_tree.configure(yscrollcommand=evidence_scroll.set)
        self._evidence_tree.bind("<<TreeviewSelect>>", self._on_evidence_selected)

        detail_host = ttk.Frame(frame, style="Card.Elevated.TFrame")
        detail_host.pack(fill="both", expand=True, pady=(UI_SPACING["s"], 0))
        detail_host.rowconfigure(0, weight=1)
        detail_host.columnconfigure(0, weight=1)

        self._evidence_detail_text = tk.Text(
            detail_host,
            wrap=tk.WORD,
            height=12,
            state="disabled",
            font=self._fonts["code"],
            bg=self._palette.get("input_bg", "#07101A"),
            fg=self._palette["text"],
            insertbackground=self._palette["text"],
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
        )
        self._evidence_detail_text.grid(row=0, column=0, sticky="nsew")
        detail_scroll = ttk.Scrollbar(
            detail_host,
            orient="vertical",
            command=self._evidence_detail_text.yview,
        )
        detail_scroll.grid(row=0, column=1, sticky="ns")
        self._evidence_detail_text.configure(yscrollcommand=detail_scroll.set)
        self._set_evidence_detail("No evidence selected.")

    def _build_library_view(self) -> None:
        """Library view: step-based file selection, build controls, and index summary."""
        frame = self._views["library"]
        frame.rowconfigure(1, weight=1)
        frame.columnconfigure(0, weight=1)

        outer = ttk.Frame(frame, style="Card.TFrame")
        outer.grid(
            row=0, column=0, rowspan=3, sticky="nsew",
            padx=UI_SPACING["m"], pady=UI_SPACING["m"],
        )
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)

        step_one = ttk.LabelFrame(
            outer,
            text="Step 1 · Source files",
            padding=(UI_SPACING["m"], UI_SPACING["s"]),
        )
        step_one.grid(row=0, column=0, sticky="ew")
        step_one.columnconfigure(0, weight=1)

        toolbar = ttk.Frame(step_one, style="Card.Flat.TFrame")
        toolbar.grid(row=0, column=0, sticky="ew")
        self.btn_open_files = ttk.Button(toolbar, text="Open Files…", style="Primary.TButton")
        self.btn_open_files.pack(side="left", padx=(0, UI_SPACING["xs"]))
        self.btn_build_index = ttk.Button(toolbar, text="Build Index", style="Secondary.TButton")
        self.btn_build_index.pack(side="left")
        ttk.Label(toolbar, textvariable=self._index_info_var, style="Caption.TLabel").pack(
            side="left", padx=(UI_SPACING["m"], 0)
        )

        lb_frame = ttk.Frame(step_one, style="Card.Elevated.TFrame")
        lb_frame.grid(row=1, column=0, sticky="nsew", pady=(UI_SPACING["s"], 0))
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

        step_two = ttk.LabelFrame(
            outer,
            text="Step 2 · Build settings",
            padding=(UI_SPACING["m"], UI_SPACING["s"]),
        )
        step_two.grid(row=1, column=0, sticky="nsew", pady=(UI_SPACING["m"], 0))
        for column in range(6):
            step_two.columnconfigure(column, weight=1 if column % 2 else 0)

        self._lib_chunk_size_var = tk.StringVar(value=str(self._settings_data.get("chunk_size", 800)))
        self._lib_chunk_overlap_var = tk.StringVar(value=str(self._settings_data.get("chunk_overlap", 100)))
        self._lib_top_k_var = tk.StringVar(value=str(self._settings_data.get("top_k", 3)))

        ttk.Label(step_two, text="Chunk Size", style="Caption.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Entry(step_two, textvariable=self._lib_chunk_size_var, width=10).grid(
            row=0, column=1, sticky="w", padx=(UI_SPACING["xs"], UI_SPACING["m"])
        )
        ttk.Label(step_two, text="Chunk Overlap", style="Caption.TLabel").grid(row=0, column=2, sticky="w")
        ttk.Entry(step_two, textvariable=self._lib_chunk_overlap_var, width=10).grid(
            row=0, column=3, sticky="w", padx=(UI_SPACING["xs"], UI_SPACING["m"])
        )
        ttk.Label(step_two, text="Top-K", style="Caption.TLabel").grid(row=0, column=4, sticky="w")
        ttk.Entry(step_two, textvariable=self._lib_top_k_var, width=10).grid(
            row=0, column=5, sticky="w", padx=(UI_SPACING["xs"], 0)
        )
        ttk.Label(
            step_two,
            text="These controls feed the current MVC index/query path directly.",
            style="Caption.TLabel",
            wraplength=900,
            justify="left",
        ).grid(row=1, column=0, columnspan=6, sticky="w", pady=(UI_SPACING["s"], 0))

        step_three = ttk.LabelFrame(
            outer,
            text="Step 3 · Active index",
            padding=(UI_SPACING["m"], UI_SPACING["s"]),
        )
        step_three.grid(row=2, column=0, sticky="ew", pady=(UI_SPACING["m"], 0))
        self._active_index_summary_var = tk.StringVar(value="No persisted index selected.")
        self._active_index_path_var = tk.StringVar(value="")
        ttk.Label(step_three, textvariable=self._active_index_summary_var, style="TLabel").pack(anchor="w")
        ttk.Label(
            step_three,
            textvariable=self._active_index_path_var,
            style="Caption.TLabel",
            wraplength=900,
            justify="left",
        ).pack(anchor="w", pady=(UI_SPACING["xs"], 0))

        self.progress = ttk.Progressbar(outer, orient="horizontal", mode="determinate")
        self.progress.grid(row=3, column=0, sticky="ew", pady=(UI_SPACING["m"], 0))

    def _build_history_view(self) -> None:
        """History view: session list, actions, and detail pane."""
        frame = self._views["history"]
        frame.rowconfigure(2, weight=1)
        frame.columnconfigure(0, weight=3)
        frame.columnconfigure(1, weight=2)

        header = ttk.Frame(frame, style="Card.Flat.TFrame", padding=(UI_SPACING["m"], UI_SPACING["s"]))
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        ttk.Label(header, text="History", style="Header.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="Resume persisted sessions, inspect summaries, and export transcripts.",
            style="Caption.TLabel",
        ).pack(anchor="w", pady=(UI_SPACING["xs"], 0))

        actions = ttk.Frame(frame, style="Card.Flat.TFrame", padding=(UI_SPACING["m"], 0))
        actions.grid(row=1, column=0, columnspan=2, sticky="ew")
        self.btn_history_new_chat = ttk.Button(actions, text="New Chat", style="Primary.TButton")
        self.btn_history_new_chat.pack(side="left")
        self.btn_history_open = ttk.Button(actions, text="Open", style="Secondary.TButton")
        self.btn_history_open.pack(side="left", padx=(UI_SPACING["xs"], 0))
        self.btn_history_delete = ttk.Button(actions, text="Delete", style="Secondary.TButton")
        self.btn_history_delete.pack(side="left", padx=(UI_SPACING["xs"], 0))
        self.btn_history_export = ttk.Button(actions, text="Export", style="Secondary.TButton")
        self.btn_history_export.pack(side="left", padx=(UI_SPACING["xs"], 0))
        self.btn_history_refresh = ttk.Button(actions, text="Refresh", style="Secondary.TButton")
        self.btn_history_refresh.pack(side="left", padx=(UI_SPACING["xs"], 0))
        ttk.Label(actions, text="Search", style="Caption.TLabel").pack(side="left", padx=(UI_SPACING["m"], UI_SPACING["xs"]))
        self._history_search_var = tk.StringVar()
        self._history_search_entry = ttk.Entry(actions, textvariable=self._history_search_var, width=28)
        self._history_search_entry.pack(side="left", fill="x", expand=True)

        left = ttk.Frame(frame, style="Card.Elevated.TFrame")
        left.grid(row=2, column=0, sticky="nsew", padx=(UI_SPACING["m"], UI_SPACING["xs"]), pady=UI_SPACING["m"])
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)

        self._history_tree = ttk.Treeview(
            left,
            columns=("title", "updated", "mode", "model"),
            show="headings",
            selectmode="browse",
        )
        for name, label, width in (
            ("title", "Title", 260),
            ("updated", "Updated", 180),
            ("mode", "Mode", 110),
            ("model", "Model", 180),
        ):
            self._history_tree.heading(name, text=label)
            self._history_tree.column(name, width=width, anchor="w")
        self._history_tree.grid(row=0, column=0, sticky="nsew")
        history_scroll = ttk.Scrollbar(left, orient="vertical", command=self._history_tree.yview)
        history_scroll.grid(row=0, column=1, sticky="ns")
        self._history_tree.configure(yscrollcommand=history_scroll.set)

        right = ttk.Frame(frame, style="Card.Elevated.TFrame", padding=UI_SPACING["m"])
        right.grid(row=2, column=1, sticky="nsew", padx=(UI_SPACING["xs"], UI_SPACING["m"]), pady=UI_SPACING["m"])
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)

        self._history_detail_summary_var = tk.StringVar(value="Select a session to inspect its details.")
        ttk.Label(
            right,
            textvariable=self._history_detail_summary_var,
            style="TLabel",
            wraplength=420,
            justify="left",
        ).grid(row=0, column=0, sticky="ew")

        self._history_detail_text = tk.Text(
            right,
            wrap=tk.WORD,
            state="disabled",
            font=self._fonts["code"],
            bg=self._palette.get("input_bg", "#07101A"),
            fg=self._palette["text"],
            insertbackground=self._palette["text"],
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
        )
        self._history_detail_text.grid(row=1, column=0, sticky="nsew", pady=(UI_SPACING["s"], 0))
        detail_scroll = ttk.Scrollbar(right, orient="vertical", command=self._history_detail_text.yview)
        detail_scroll.grid(row=1, column=1, sticky="ns", pady=(UI_SPACING["s"], 0))
        self._history_detail_text.configure(yscrollcommand=detail_scroll.set)
        self._set_history_detail_text("Select a session to inspect its details.")

    def _build_settings_view(self) -> None:
        """Settings view: scrollable editable settings pane with collapsible sections."""
        pal = self._palette
        frame = self._views["settings"]
        frame.rowconfigure(1, weight=1)
        frame.rowconfigure(2, weight=0)
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
        inner.columnconfigure(0, weight=1)

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

        # ── Build collapsible sections ─────────────────────────────────
        for sec_row, (section_title, field_specs) in enumerate(_SETTINGS_SPEC):
            expanded = section_title in _SETTINGS_EXPANDED
            coll = CollapsibleFrame(
                inner,
                title=section_title,
                expanded=expanded,
                animator=self._animator,
            )
            coll.grid(row=sec_row, column=0, sticky="ew",
                      padx=UI_SPACING["s"],
                      pady=(UI_SPACING["xs"] if sec_row == 0 else 0, 0))
            coll.content.columnconfigure(1, weight=1)

            for field_row, (key, label, wtype, options) in enumerate(field_specs):
                val = self._settings_data.get(key, "")

                if wtype == "text":
                    # Full-width multi-line text widget (e.g. system_instructions)
                    ttk.Label(
                        coll.content,
                        text=label,
                        style="Caption.TLabel",
                    ).grid(row=field_row * 2, column=0, columnspan=2,
                           sticky="w",
                           padx=UI_SPACING["m"],
                           pady=(UI_SPACING["xs"], 0))
                    widget = tk.Text(
                        coll.content,
                        height=6,
                        wrap=tk.WORD,
                        font=self._fonts["body"],
                        bg=pal.get("input_bg", "#07101A"),
                        fg=pal["text"],
                        insertbackground=pal["text"],
                        relief="flat",
                        borderwidth=0,
                        highlightthickness=1,
                        highlightbackground=pal.get("outline", "#2A3E58"),
                    )
                    widget.insert("1.0", str(val))
                    widget.grid(row=field_row * 2 + 1, column=0, columnspan=2,
                                sticky="ew",
                                padx=UI_SPACING["m"],
                                pady=(UI_SPACING["xs"], UI_SPACING["xs"]))
                    self._settings_entries[key] = (widget, None)

                else:
                    ttk.Label(
                        coll.content,
                        text=label,
                        style="Caption.TLabel",
                        anchor="e",
                        width=24,
                    ).grid(row=field_row, column=0, sticky="e",
                           padx=(UI_SPACING["m"], UI_SPACING["s"]),
                           pady=(0, UI_SPACING["xs"]))

                    if wtype == "checkbutton":
                        var: tk.Variable = tk.BooleanVar(value=bool(val))
                        widget = ttk.Checkbutton(coll.content, variable=var)
                        widget.grid(row=field_row, column=1, sticky="w",
                                    padx=(0, UI_SPACING["m"]),
                                    pady=(0, UI_SPACING["xs"]))

                    elif wtype == "combobox":
                        var = tk.StringVar(value=str(val))
                        widget = ttk.Combobox(
                            coll.content,
                            textvariable=var,
                            values=options,
                            state="readonly",
                            font=self._fonts["code"],
                        )
                        widget.grid(row=field_row, column=1, sticky="ew",
                                    padx=(0, UI_SPACING["m"]),
                                    pady=(0, UI_SPACING["xs"]))
                        if key == "llm_provider":
                            widget.bind("<<ComboboxSelected>>",
                                        self._on_llm_provider_changed)

                    elif wtype == "file_browse":
                        var = tk.StringVar(value=str(val))
                        browse_frame = ttk.Frame(coll.content)
                        browse_frame.columnconfigure(0, weight=1)
                        browse_frame.grid(row=field_row, column=1, sticky="ew",
                                          padx=(0, UI_SPACING["m"]),
                                          pady=(0, UI_SPACING["xs"]))
                        widget = ttk.Entry(
                            browse_frame,
                            textvariable=var,
                            font=self._fonts["code"],
                        )
                        widget.grid(row=0, column=0, sticky="ew")
                        ttk.Button(
                            browse_frame,
                            text="Browse…",
                            command=self._browse_gguf_file,
                        ).grid(row=0, column=1, padx=(UI_SPACING["xs"], 0))

                    elif wtype == "entry_password":
                        var = tk.StringVar(value=str(val))
                        widget = ttk.Entry(
                            coll.content,
                            textvariable=var,
                            show="*",
                            font=self._fonts["code"],
                        )
                        widget.grid(row=field_row, column=1, sticky="ew",
                                    padx=(0, UI_SPACING["m"]),
                                    pady=(0, UI_SPACING["xs"]))

                    else:  # plain "entry"
                        var = tk.StringVar(value=str(val))
                        widget = ttk.Entry(
                            coll.content,
                            textvariable=var,
                            font=self._fonts["code"],
                        )
                        widget.grid(row=field_row, column=1, sticky="ew",
                                    padx=(0, UI_SPACING["m"]),
                                    pady=(0, UI_SPACING["xs"]))

                    self._settings_entries[key] = (widget, var)

        # Bottom spacer inside the scroll area
        ttk.Frame(inner, style="Card.TFrame", height=UI_SPACING["l"]).grid(
            row=len(_SETTINGS_SPEC), column=0,
        )

        # ── Footer with Save button ────────────────────────────────────
        footer = ttk.Frame(frame, style="Card.Flat.TFrame",
                           padding=(UI_SPACING["m"], UI_SPACING["s"]))
        footer.grid(row=2, column=0, sticky="ew")
        self.btn_save_settings = ttk.Button(footer, text="Save Settings")
        self.btn_save_settings.pack(side="left", padx=(0, UI_SPACING["s"]))
        ttk.Label(
            footer,
            text="Saves to settings.json at repository root.",
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

    def get_library_build_settings(self) -> dict[str, str]:
        """Return current library build controls as strings."""
        return {
            "chunk_size": self._lib_chunk_size_var.get() if hasattr(self, "_lib_chunk_size_var") else "",
            "chunk_overlap": self._lib_chunk_overlap_var.get() if hasattr(self, "_lib_chunk_overlap_var") else "",
            "top_k": self._lib_top_k_var.get() if hasattr(self, "_lib_top_k_var") else "",
        }

    def set_active_index_summary(self, summary: str, index_path: str = "") -> None:
        """Update the active-index summary shown in the Library view."""
        if hasattr(self, "_active_index_summary_var"):
            self._active_index_summary_var.set(summary)
        if hasattr(self, "_active_index_path_var"):
            self._active_index_path_var.set(index_path)

    def append_chat(self, text: str, tag: str = "agent") -> None:
        """Append *text* (with optional *tag*) to the chat display."""
        self.chat_display.configure(state="normal")
        start = self.chat_display.index("end-1c")
        if start == "1.0" and not self.chat_display.get("1.0", "end-1c"):
            start = "1.0"
        self.chat_display.insert("end", text, tag)
        for match in re.finditer(r"S\d+", text or ""):
            tag_start = f"{start}+{match.start()}c"
            tag_end = f"{start}+{match.end()}c"
            self.chat_display.tag_add("citation", tag_start, tag_end)
        self.chat_display.see("end")
        self.chat_display.configure(state="disabled")

    def clear_chat(self) -> None:
        """Clear the chat transcript area."""
        self.chat_display.configure(state="normal")
        self.chat_display.delete("1.0", "end")
        self.chat_display.configure(state="disabled")

    def set_chat_transcript(self, messages: list) -> None:
        """Replace the chat display with a persisted transcript."""
        self.clear_chat()
        for msg in messages or []:
            role = ""
            content = ""
            if isinstance(msg, dict):
                role = str(msg.get("role", "") or "")
                content = str(msg.get("content", "") or "")
            else:
                role = str(getattr(msg, "role", "") or "")
                content = str(getattr(msg, "content", "") or "")
            role = role.strip().lower()
            if role == "user":
                self.append_chat(f"You: {content}\n{'─' * 52}\n", tag="user")
            elif role == "assistant":
                self.append_chat(f"{content}\n\n", tag="agent")
            else:
                self.append_chat(f"{content}\n\n", tag="system")

    def render_evidence_sources(self, sources: list) -> None:
        """Populate the evidence pane with structured retrieved sources."""
        if not hasattr(self, "_evidence_tree"):
            return
        self._evidence_source_by_sid = {}
        self._evidence_source_by_iid = {}
        self._evidence_tree.delete(*self._evidence_tree.get_children())
        if not sources:
            self._evidence_status_var.set("No retrieved evidence yet.")
            self._set_evidence_detail("No evidence selected.")
            return

        for idx, source in enumerate(sources, start=1):
            if isinstance(source, dict):
                sid = str(source.get("sid", "") or f"S{idx}")
                payload = dict(source)
            else:
                sid = str(getattr(source, "sid", "") or f"S{idx}")
                payload = source.to_dict() if hasattr(source, "to_dict") else {}
            self._evidence_source_by_sid[sid] = payload
            iid = f"evidence-{idx}"
            self._evidence_source_by_iid[iid] = sid
            self._evidence_tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    sid,
                    str(payload.get("source") or "unknown"),
                    f"{float(payload.get('score')):.3f}" if payload.get("score") is not None else "-",
                ),
            )
        self._evidence_status_var.set(f"{len(sources)} evidence item(s) loaded.")
        first = self._evidence_tree.get_children("")
        if first:
            self._evidence_tree.selection_set(first[0])
            self._evidence_tree.focus(first[0])
            self._on_evidence_selected()

    def focus_evidence_source(self, sid: str) -> None:
        """Select a source in the evidence pane by its stable citation id."""
        if not hasattr(self, "_evidence_tree"):
            return
        for iid, mapped_sid in self._evidence_source_by_iid.items():
            if mapped_sid == sid and self._evidence_tree.exists(iid):
                self._evidence_tree.selection_set(iid)
                self._evidence_tree.focus(iid)
                self._evidence_tree.see(iid)
                self._on_evidence_selected()
                break

    def bind_history_search(self, callback) -> None:
        """Bind the History search entry to a callback."""
        if hasattr(self, "_history_search_entry"):
            self._history_search_entry.bind("<KeyRelease>", callback)

    def bind_history_selection(self, callback) -> None:
        """Bind history selection and open actions to a callback."""
        if hasattr(self, "_history_tree"):
            self._history_tree.bind("<<TreeviewSelect>>", callback)

    def get_history_search_query(self) -> str:
        """Return the current History search query."""
        return self._history_search_var.get().strip() if hasattr(self, "_history_search_var") else ""

    def set_history_rows(self, rows: list) -> None:
        """Replace the History table contents."""
        if not hasattr(self, "_history_tree"):
            return
        self._history_rows = list(rows or [])
        self._history_session_by_id = {
            str(getattr(row, "session_id", "")): row
            for row in self._history_rows
        }
        self._history_tree.delete(*self._history_tree.get_children())
        for row in self._history_rows:
            session_id = str(getattr(row, "session_id", "") or "")
            self._history_tree.insert(
                "",
                "end",
                iid=session_id,
                values=(
                    str(getattr(row, "title", "") or "(untitled)"),
                    str(getattr(row, "updated_at", "") or ""),
                    str(getattr(row, "mode", "") or "-"),
                    str(getattr(row, "llm_model", "") or "-"),
                ),
            )

    def select_history_session(self, session_id: str) -> None:
        """Select a History row if it exists."""
        if hasattr(self, "_history_tree") and self._history_tree.exists(session_id):
            self._history_tree.selection_set(session_id)
            self._history_tree.focus(session_id)
            self._history_tree.see(session_id)

    def get_selected_history_session_id(self) -> str:
        """Return the selected History session id."""
        if not hasattr(self, "_history_tree"):
            return ""
        selected = self._history_tree.selection()
        return selected[0] if selected else ""

    def set_history_detail(self, detail) -> None:
        """Render summary and transcript metadata for a selected session."""
        summary = getattr(detail, "summary", detail)
        messages = list(getattr(detail, "messages", []) or [])
        headline = (
            f"{getattr(summary, 'title', '(untitled)')}\n"
            f"Mode: {getattr(summary, 'mode', '-') or '-'}  |  "
            f"Model: {getattr(summary, 'llm_model', '-') or '-'}  |  "
            f"Index: {getattr(summary, 'index_id', '(default)') or '(default)'}"
        )
        self._history_detail_summary_var.set(headline)

        lines = [
            f"Session ID: {getattr(summary, 'session_id', '')}",
            f"Created: {getattr(summary, 'created_at', '')}",
            f"Updated: {getattr(summary, 'updated_at', '')}",
            f"Summary: {getattr(summary, 'summary', '') or '(none)'}",
            "",
            "Transcript preview:",
            "",
        ]
        for idx, message in enumerate(messages[-8:], start=max(1, len(messages) - 7)):
            if isinstance(message, dict):
                role = str(message.get("role", "") or "").capitalize()
                content = str(message.get("content", "") or "")
            else:
                role = str(getattr(message, "role", "") or "").capitalize()
                content = str(getattr(message, "content", "") or "")
            lines.append(f"{idx}. {role}: {content[:240]}")
        self._set_history_detail_text("\n".join(lines))

    def get_prompt_text(self) -> str:
        """Return the current contents of the prompt input."""
        try:
            return self.txt_input.get("1.0", "end-1c")
        except tk.TclError:
            return ""

    def get_chat_mode(self) -> str:
        """Return the active chat mode: ``"rag"`` or ``"direct"``."""
        return "rag" if self._use_rag_var.get() else "direct"

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
        self._mode_var.set(str(self._settings_data.get("selected_mode", MODE_OPTIONS[0])))
        self._use_rag_var.set(
            str(self._settings_data.get("chat_path", "RAG")).strip().lower() != "direct"
        )
        if hasattr(self, "_lib_chunk_size_var"):
            self._lib_chunk_size_var.set(str(self._settings_data.get("chunk_size", 800)))
        if hasattr(self, "_lib_chunk_overlap_var"):
            self._lib_chunk_overlap_var.set(str(self._settings_data.get("chunk_overlap", 100)))
        if hasattr(self, "_lib_top_k_var"):
            self._lib_top_k_var.set(str(self._settings_data.get("top_k", 3)))
        self._refresh_llm_badge()
        if not self._tab_built.get("settings"):
            # Tab not yet built — data is stored and will be read by
            # _build_settings_view() when the user first opens Settings.
            return
        # Tab already built — update existing widget variables in place.
        for key, (widget, var) in self._settings_entries.items():
            val = self._settings_data.get(key, "")
            if var is None:
                # tk.Text widget (system_instructions)
                try:
                    widget.delete("1.0", "end")
                    widget.insert("1.0", str(val))
                except tk.TclError:
                    pass
            elif isinstance(var, tk.BooleanVar):
                try:
                    var.set(bool(val))
                except (tk.TclError, ValueError):
                    var.set(False)
            else:
                try:
                    if key == "selected_mode":
                        var.set(self._mode_var.get())
                    else:
                        var.set(str(val))
                except tk.TclError:
                    pass
        self._refresh_llm_badge()

    def collect_settings(self) -> dict:
        """Read all settings widget values and return as a flat dict.

        For tk.Text widgets the full text content is returned.
        For BooleanVar a Python bool is returned.
        For StringVar the current string is returned.
        Type coercion (str→int/float) is the controller's responsibility.
        """
        result: dict = {}
        for key, (widget, var) in self._settings_entries.items():
            if var is None:
                # tk.Text widget
                try:
                    result[key] = widget.get("1.0", "end-1c")
                except tk.TclError:
                    result[key] = ""
            elif isinstance(var, tk.BooleanVar):
                try:
                    result[key] = var.get()
                except tk.TclError:
                    result[key] = False
            else:
                try:
                    result[key] = var.get()
                except tk.TclError:
                    result[key] = ""

        result["selected_mode"] = self._mode_var.get()
        result["chat_path"] = "RAG" if self._use_rag_var.get() else "Direct"
        return result

    def set_mode_state_callback(self, callback) -> None:
        """Register callback invoked when selected_mode/chat_path changes."""
        self._mode_state_callback = callback

    def _emit_mode_state(self) -> None:
        chat_path = "RAG" if self._use_rag_var.get() else "Direct"
        self._settings_data["selected_mode"] = self._mode_var.get()
        self._settings_data["chat_path"] = chat_path

        mode_entry = self._settings_entries.get("selected_mode")
        if mode_entry is not None:
            _, mode_var = mode_entry
            if mode_var is not None and mode_var.get() != self._mode_var.get():
                mode_var.set(self._mode_var.get())

        if callable(self._mode_state_callback):
            self._mode_state_callback({
                "selected_mode": self._mode_var.get(),
                "chat_path": chat_path,
            })

    def _on_mode_var_changed(self, *_args) -> None:
        self._emit_mode_state()

    def _on_chat_path_var_changed(self, *_args) -> None:
        self._emit_mode_state()
        try:
            self._rag_toggle._draw()
        except Exception:
            pass

    def _on_rag_toggle_clicked(self) -> None:
        self._use_rag_var.set(not self._use_rag_var.get())

    def show(self) -> None:
        """Make the window visible."""
        self.root.deiconify()
        self.root.lift()

    # ------------------------------------------------------------------
    # GGUF file selection helpers
    # ------------------------------------------------------------------

    def _on_llm_provider_changed(self, _event: tk.Event | None = None) -> None:
        """When LLM provider is switched to local_gguf, open the GGUF file browser."""
        entry = self._settings_entries.get("llm_provider")
        if entry and entry[1] is not None:
            self._settings_data["llm_provider"] = entry[1].get()
            self._refresh_llm_badge()
        if entry and entry[1] is not None and entry[1].get() == "local_gguf":
            self._browse_gguf_file()

    def _browse_gguf_file(self) -> None:
        """Open a file dialog for .gguf files and auto-fill the relevant settings fields."""
        from tkinter import filedialog

        path = filedialog.askopenfilename(
            title="Select GGUF model file",
            filetypes=[("GGUF files", "*.gguf"), ("All files", "*.*")],
        )
        if not path:
            return

        stem = pathlib.Path(path).stem  # filename without extension

        for key, value in [
            ("local_gguf_model_path", path),
            ("llm_model",             stem),
            ("llm_model_custom",      stem),
        ]:
            self._settings_data[key] = value
            entry = self._settings_entries.get(key)
            if entry and entry[1] is not None:
                try:
                    entry[1].set(value)
                except tk.TclError:
                    pass
        self._refresh_llm_badge()

    def refresh_llm_status_badge(self) -> None:
        """Refresh the LLM badge and emit a short status line with provider/model."""
        self._refresh_llm_badge()
        provider = str(self._settings_data.get("llm_provider", "") or "").strip() or "--"
        model = (
            str(self._settings_data.get("llm_model", "") or "").strip()
            or str(self._settings_data.get("llm_model_custom", "") or "").strip()
            or "--"
        )
        self.set_status(f"Settings saved. Active LLM: {provider} / {model}")

    def _refresh_llm_badge(self) -> None:
        """Show active provider/model in the chat header badge."""
        provider = str(self._settings_data.get("llm_provider", "") or "").strip() or "--"
        model = (
            str(self._settings_data.get("llm_model", "") or "").strip()
            or str(self._settings_data.get("llm_model_custom", "") or "").strip()
            or "--"
        )
        self._llm_badge_var.set(f"🤖 LLM: {provider} / {model}")

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

    def _set_evidence_detail(self, text: str) -> None:
        if not hasattr(self, "_evidence_detail_text"):
            return
        self._evidence_detail_text.configure(state="normal")
        self._evidence_detail_text.delete("1.0", "end")
        self._evidence_detail_text.insert("1.0", text)
        self._evidence_detail_text.configure(state="disabled")

    def _on_evidence_selected(self, _event=None) -> None:
        if not hasattr(self, "_evidence_tree"):
            return
        selected = self._evidence_tree.selection()
        if not selected:
            return
        iid = selected[0]
        sid = self._evidence_source_by_iid.get(iid, "")
        payload = self._evidence_source_by_sid.get(sid, {})
        if not payload:
            self._set_evidence_detail("No evidence selected.")
            return
        detail = [
            f"Citation: {sid}",
            f"Source: {payload.get('source', 'unknown')}",
            f"Chunk ID: {payload.get('chunk_id') or '-'}",
            f"Chunk Index: {payload.get('chunk_idx') if payload.get('chunk_idx') is not None else '-'}",
            f"Score: {payload.get('score') if payload.get('score') is not None else '-'}",
            "",
            "Snippet:",
            str(payload.get("snippet") or "(no snippet)"),
        ]
        self._set_evidence_detail("\n".join(detail))

    def _on_citation_click(self, event=None) -> None:
        try:
            index = self.chat_display.index(f"@{event.x},{event.y}") if event else self.chat_display.index(tk.INSERT)
            ranges = self.chat_display.tag_prevrange("citation", index)
            if not ranges:
                return
            token = self.chat_display.get(ranges[0], ranges[1]).strip()
            match = re.search(r"S\d+", token)
            if not match:
                return
            self.focus_evidence_source(match.group(0))
            if not self._evidence_visible:
                self._toggle_evidence_panel()
        except Exception:
            pass

    def _set_history_detail_text(self, text: str) -> None:
        if not hasattr(self, "_history_detail_text"):
            return
        self._history_detail_text.configure(state="normal")
        self._history_detail_text.delete("1.0", "end")
        self._history_detail_text.insert("1.0", text)
        self._history_detail_text.configure(state="disabled")

    def _on_new_chat(self) -> None:
        """Clear chat display (placeholder — controller can override)."""
        self.clear_chat()
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
