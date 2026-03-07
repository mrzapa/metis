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

import datetime as dt
import json
import os
import pathlib
import re
import sys
import tkinter as tk
from tkinter import ttk

from axiom_app.services.wizard_recommendation import (
    describe_auto_recommendation,
    estimate_setup_cost,
    recommend_auto_settings,
)
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
    RoundedCard,
    TooltipManager,
)

# ---------------------------------------------------------------------------
# App constants (keep in sync with legacy if they ever diverge)
# ---------------------------------------------------------------------------

APP_NAME    = "Axiom"
APP_VERSION = "1.0"
APP_SUBTITLE = "Personal RAG Assistant"

MODE_OPTIONS = ["Q&A", "Summary", "Tutor", "Research", "Evidence Pack"]

_SIDEBAR_W = 88
_SHELL_RADIUS = 28
_CARD_RADIUS = 22
_DEFAULT_WINDOW_W = 1480
_DEFAULT_WINDOW_H = 960
_MIN_WINDOW_W = 1180
_MIN_WINDOW_H = 760
_NAV_ITEMS = [
    ("chat", "⌂", "Chat"),
    ("library", "▣", "Library"),
    ("history", "↺", "History"),
    ("settings", "⚙", "Settings"),
    ("logs", "≡", "Logs"),
]

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
            ["json", "chroma", "weaviate"]),
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
        self.tooltip_manager = TooltipManager(root, lambda: self._palette)

        # Tk variable for RAG/Direct toggle
        self._use_rag_var = tk.BooleanVar(value=True)
        # Tk variable for Mode selection
        self._mode_var = tk.StringVar(value="Q&A")
        # Tk variable for current status text
        self._status_var = tk.StringVar(value="Ready.")
        # Tk variable for index info (shown in Library toolbar)
        self._index_info_var = tk.StringVar(value="No index built.")
        self._profile_var = tk.StringVar(value="Built-in: Default")
        self._history_profile_var = tk.StringVar(value="All Profiles")
        self._available_index_var = tk.StringVar(value="")

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
        self._event_payload_by_iid: dict[str, dict] = {}
        self._region_payload_by_iid: dict[str, dict] = {}
        self._trace_payload_by_iid: dict[str, dict] = {}
        self._outline_payload_by_iid: dict[str, dict] = {}
        self._available_index_rows: list[dict] = []
        self._theme_cards: list[tuple[RoundedCard, str, str, str | None]] = []
        self._chat_has_messages = False
        self._sidebar_brand_canvas: tk.Canvas | None = None
        self._hero_orb_canvas: tk.Canvas | None = None
        self._responsive_after_id = None

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
        self._apply_runtime_palette()

    # ------------------------------------------------------------------
    # Window construction
    # ------------------------------------------------------------------

    def _build(self) -> None:
        self.root.title(f"{APP_NAME} — {APP_SUBTITLE}" if APP_SUBTITLE else APP_NAME)
        self.root.geometry(f"{_DEFAULT_WINDOW_W}x{_DEFAULT_WINDOW_H}")
        self.root.minsize(_MIN_WINDOW_W, _MIN_WINDOW_H)

        self._load_icon()

        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        self._shell_card, shell_inner = self._create_card(
            self.root,
            radius=_SHELL_RADIUS,
            bg_key="workspace_bg",
            border_key="workspace_border",
            shadow_key="workspace_shadow",
            inner_padding=0,
            shadow_offset=4,
        )
        self._shell_card.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=STYLE_CONFIG["padding"]["lg"],
            pady=STYLE_CONFIG["padding"]["lg"],
        )
        shell_inner.grid_rowconfigure(0, weight=1)
        shell_inner.grid_columnconfigure(0, minsize=_SIDEBAR_W, weight=0)
        shell_inner.grid_columnconfigure(1, minsize=1, weight=0)
        shell_inner.grid_columnconfigure(2, weight=1)
        self._shell_inner = shell_inner

        self._build_sidebar()
        self._sidebar_divider = tk.Frame(
            shell_inner,
            width=1,
            bd=0,
            highlightthickness=0,
            bg=self._palette.get("sidebar_border", self._palette["border"]),
        )
        self._sidebar_divider.grid(row=0, column=1, sticky="ns")
        self._build_main_content()
        self._apply_runtime_palette()
        self.root.bind("<Configure>", self._schedule_responsive_layout, add="+")
        self.root.after_idle(self._refresh_responsive_layout)

    def _build_sidebar(self) -> None:
        pal = self._palette
        shell_inner = self._shell_inner

        self.sidebar_frame = ttk.Frame(shell_inner, style="Sidebar.TFrame")
        self.sidebar_frame.grid(row=0, column=0, sticky="ns", padx=(0, 0), pady=0)
        self.sidebar_frame.grid_columnconfigure(0, minsize=4, weight=0)
        self.sidebar_frame.grid_columnconfigure(1, minsize=_SIDEBAR_W - 4, weight=1)
        self.sidebar_frame.grid_rowconfigure(2, weight=1)

        brand_wrap = ttk.Frame(self.sidebar_frame, style="Sidebar.TFrame")
        brand_wrap.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(UI_SPACING["m"], UI_SPACING["l"]))
        self._sidebar_logo_photo = self._load_sidebar_logo(max_dim=46)
        self._sidebar_brand_canvas = tk.Canvas(
            brand_wrap,
            width=56,
            height=56,
            bg=pal.get("sidebar_bg", pal["surface"]),
            highlightthickness=0,
            bd=0,
        )
        self._sidebar_brand_canvas.pack(padx=UI_SPACING["m"])
        self._draw_brand_mark()
        self.tooltip_manager.register(self._sidebar_brand_canvas, f"{APP_NAME} {APP_VERSION}")

        nav_wrap = ttk.Frame(self.sidebar_frame, style="Sidebar.TFrame")
        nav_wrap.grid(row=1, column=0, columnspan=2, sticky="new")
        nav_wrap.grid_columnconfigure(1, weight=1)

        for row, (key, icon, label) in enumerate(_NAV_ITEMS[:3]):
            accent = tk.Frame(nav_wrap, width=3, bd=0, highlightthickness=0, bg=pal.get("sidebar_bg", pal["surface"]))
            accent.grid(row=row, column=0, sticky="ns", pady=(0, UI_SPACING["xs"]))
            self._sidebar_accents[key] = accent

            btn = ttk.Button(
                nav_wrap,
                text=icon,
                width=3,
                style="Sidebar.TButton",
                command=lambda item=key: self.switch_view(item),
            )
            btn.grid(row=row, column=1, sticky="ew", padx=(0, UI_SPACING["s"]), pady=(0, UI_SPACING["xs"]))
            self.tooltip_manager.register(btn, label)
            self._sidebar_nav_buttons[key] = btn

        utility_wrap = ttk.Frame(self.sidebar_frame, style="Sidebar.TFrame")
        utility_wrap.grid(row=2, column=0, columnspan=2, sticky="sew")
        utility_wrap.grid_columnconfigure(1, weight=1)
        utility_wrap.grid_rowconfigure(0, weight=1)
        utility_items = _NAV_ITEMS[3:]
        utility_start = 1
        for offset, (key, icon, label) in enumerate(utility_items):
            row = utility_start + offset
            accent = tk.Frame(utility_wrap, width=3, bd=0, highlightthickness=0, bg=pal.get("sidebar_bg", pal["surface"]))
            accent.grid(row=row, column=0, sticky="ns", pady=(0, UI_SPACING["xs"]))
            self._sidebar_accents[key] = accent

            btn = ttk.Button(
                utility_wrap,
                text=icon,
                width=3,
                style="Sidebar.TButton",
                command=lambda item=key: self.switch_view(item),
            )
            btn.grid(row=row, column=1, sticky="ew", padx=(0, UI_SPACING["s"]), pady=(0, UI_SPACING["xs"]))
            self.tooltip_manager.register(btn, label)
            self._sidebar_nav_buttons[key] = btn

        footer = ttk.Frame(self.sidebar_frame, style="Sidebar.TFrame")
        footer.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(UI_SPACING["s"], UI_SPACING["m"]))
        ttk.Label(footer, text=f"{APP_NAME} {APP_VERSION}", style="Sidebar.Caption.TLabel").pack(anchor="center")
        ttk.Label(footer, text="ttk runtime", style="Sidebar.Caption.TLabel").pack(anchor="center", pady=(3, 0))

    def _build_main_content(self) -> None:
        shell_inner = self._shell_inner

        self.main_content_frame = ttk.Frame(shell_inner, style="MainContent.TFrame")
        self.main_content_frame.grid(
            row=0,
            column=2,
            sticky="nsew",
            padx=STYLE_CONFIG["padding"]["lg"],
            pady=STYLE_CONFIG["padding"]["lg"],
        )
        self.main_content_frame.grid_rowconfigure(0, weight=1)
        self.main_content_frame.grid_columnconfigure(0, weight=1)

        # Create all view frames now (stacked; only one visible at a time).
        for key in ("chat", "library", "history", "settings", "logs"):
            frame = ttk.Frame(self.main_content_frame, style="MainContent.TFrame")
            frame.grid(row=0, column=0, sticky="nsew")
            self._views[key] = frame
            self._tab_built[key] = False

        # Build chat view immediately; others are lazy-built on first switch.
        self._build_chat_view()
        self._tab_built["chat"] = True

        # Activate chat to start.
        self.switch_view("chat")

    def _create_card(
        self,
        parent,
        *,
        radius: int = _CARD_RADIUS,
        bg_key: str = "surface",
        border_key: str = "border",
        shadow_key: str | None = "workspace_shadow",
        inner_padding: int = 18,
        shadow_offset: int = 2,
    ) -> tuple[RoundedCard, ttk.Frame]:
        """Create a rounded surface card and register it for theme updates."""
        pal = self._palette
        outer_bg = pal.get("workspace_bg", pal.get("app_bg", pal["bg"]))
        card = RoundedCard(
            parent,
            radius=radius,
            bg=pal.get(bg_key, pal["surface"]),
            outer_bg=outer_bg,
            border_color=pal.get(border_key, pal["border"]),
            border_width=1,
            shadow_color=pal.get(shadow_key, "") if shadow_key else "",
            shadow_offset=shadow_offset,
            inner_padding=inner_padding,
        )
        self._theme_cards.append((card, bg_key, border_key, shadow_key))
        inner_style = "Card.Elevated.TFrame" if bg_key == "surface_elevated" else "Card.TFrame"
        inner = ttk.Frame(card.inner, style=inner_style)
        inner.pack(fill="both", expand=True)
        return card, inner

    def _create_scrollable_page(
        self,
        parent,
        *,
        bg_key: str = "workspace_bg",
    ) -> tuple[ttk.Frame, tk.Canvas, ttk.Frame, ttk.Scrollbar]:
        """Create a vertically scrollable page shell with scoped wheel support."""
        pal = self._palette
        host = ttk.Frame(parent, style="MainContent.TFrame")
        host.rowconfigure(0, weight=1)
        host.columnconfigure(0, weight=1)

        canvas = tk.Canvas(
            host,
            bg=pal.get(bg_key, pal.get("workspace_bg", pal["surface"])),
            highlightthickness=0,
            bd=0,
        )
        canvas.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(host, orient="vertical", command=canvas.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        canvas.configure(yscrollcommand=scrollbar.set)

        inner = ttk.Frame(canvas, style="MainContent.TFrame")
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _sync_scrollregion(_event=None) -> None:
            try:
                bbox = canvas.bbox("all")
                if bbox:
                    canvas.configure(scrollregion=bbox)
            except tk.TclError:
                return

        def _sync_width(event: tk.Event) -> None:
            try:
                canvas.itemconfigure(window_id, width=event.width)
            except tk.TclError:
                return

        inner.bind("<Configure>", _sync_scrollregion, add="+")
        canvas.bind("<Configure>", _sync_width, add="+")
        self._bind_scoped_mousewheel(canvas, inner)
        return host, canvas, inner, scrollbar

    def _bind_scoped_mousewheel(self, canvas: tk.Canvas, *widgets: tk.Misc) -> None:
        """Bind wheel events only while the pointer is over a scroll region."""

        def _on_mousewheel(event: tk.Event) -> str | None:
            try:
                if getattr(event, "delta", 0):
                    canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
                    return "break"
                num = getattr(event, "num", None)
                if num == 4:
                    canvas.yview_scroll(-1, "units")
                    return "break"
                if num == 5:
                    canvas.yview_scroll(1, "units")
                    return "break"
            except tk.TclError:
                return None
            return None

        def _bind(_event=None) -> None:
            try:
                self.root.bind_all("<MouseWheel>", _on_mousewheel, add="+")
                self.root.bind_all("<Button-4>", _on_mousewheel, add="+")
                self.root.bind_all("<Button-5>", _on_mousewheel, add="+")
            except tk.TclError:
                return

        def _unbind(_event=None) -> None:
            try:
                self.root.unbind_all("<MouseWheel>")
                self.root.unbind_all("<Button-4>")
                self.root.unbind_all("<Button-5>")
            except tk.TclError:
                return

        for widget in (canvas, *widgets):
            widget.bind("<Enter>", _bind, add="+")
            widget.bind("<Leave>", _unbind, add="+")

    def _schedule_responsive_layout(self, _event=None) -> None:
        if self._responsive_after_id is not None:
            try:
                self.root.after_cancel(self._responsive_after_id)
            except tk.TclError:
                pass
        try:
            self._responsive_after_id = self.root.after(30, self._refresh_responsive_layout)
        except tk.TclError:
            self._responsive_after_id = None

    def _refresh_responsive_layout(self) -> None:
        self._responsive_after_id = None
        try:
            content_width = max(self.main_content_frame.winfo_width(), _MIN_WINDOW_W - 180)
        except Exception:
            return

        if hasattr(self, "_chat_primary_actions"):
            if content_width < 1360:
                self._chat_primary_actions.grid(row=1, column=0, columnspan=2, sticky="w", pady=(UI_SPACING["s"], 0))
            else:
                self._chat_primary_actions.grid(row=0, column=1, sticky="e", pady=0)

        if hasattr(self, "_chat_secondary_actions"):
            if content_width < 1280:
                self._chat_secondary_actions.pack_forget()
                self._chat_secondary_actions.pack(side="left", pady=(UI_SPACING["xs"], 0))
                self._chat_status_cluster.pack_forget()
                self._chat_status_cluster.pack(side="left", padx=(UI_SPACING["m"], 0), pady=(UI_SPACING["xs"], 0))
            else:
                self._chat_status_cluster.pack_forget()
                self._chat_status_cluster.pack(side="right")
                self._chat_secondary_actions.pack_forget()
                self._chat_secondary_actions.pack(side="right")

        if hasattr(self, "_suggestion_buttons"):
            columns = 4 if content_width >= 1420 else 2
            for idx in range(4):
                self._suggestion_panel.grid_columnconfigure(idx, weight=1 if idx < columns else 0)
            for idx, button in enumerate(self._suggestion_buttons):
                row = 1 + (idx // columns)
                column = idx % columns
                padx = (0 if column == 0 else UI_SPACING["xs"], 0)
                pady = (0, 0 if row == 1 else UI_SPACING["xs"])
                button.grid_configure(row=row, column=column, padx=padx, pady=pady)

        hero_wrap = max(460, min(content_width - 260, 860))
        body_wrap = max(440, min(content_width - 320, 780))
        if hasattr(self, "_hero_greeting_label"):
            self._hero_greeting_label.configure(wraplength=hero_wrap)
        if hasattr(self, "_hero_question_label"):
            self._hero_question_label.configure(wraplength=hero_wrap)
        if hasattr(self, "_hero_copy_label"):
            self._hero_copy_label.configure(wraplength=body_wrap)
        if hasattr(self, "_active_index_path_label"):
            self._active_index_path_label.configure(wraplength=max(560, content_width - 260))
        if hasattr(self, "_history_detail_summary_label"):
            self._history_detail_summary_label.configure(wraplength=max(320, int(content_width * 0.28)))
        if hasattr(self, "_evidence_status_label"):
            self._evidence_status_label.configure(wraplength=320 if content_width < 1400 else 360)
        if hasattr(self, "_evidence_pane_holder"):
            width = 360 if content_width < 1380 else 420
            try:
                self._evidence_pane_holder.configure(width=width)
                self._conversation_shell.grid_columnconfigure(1, minsize=width, weight=0)
            except tk.TclError:
                pass

    def _draw_brand_mark(self) -> None:
        if self._sidebar_brand_canvas is None:
            return
        pal = self._palette
        canvas = self._sidebar_brand_canvas
        canvas.delete("all")
        canvas.configure(bg=pal.get("sidebar_bg", pal["surface"]))
        if self._sidebar_logo_photo is None:
            self._sidebar_logo_photo = self._load_sidebar_logo(max_dim=46)
        canvas.create_oval(
            4,
            4,
            52,
            52,
            fill=pal.get("surface_alt", pal["surface"]),
            outline=pal.get("sidebar_border", pal["border"]),
            width=1,
        )
        if self._sidebar_logo_photo is not None:
            canvas.create_image(28, 28, image=self._sidebar_logo_photo)
            return
        canvas.create_oval(10, 10, 46, 46, fill=pal.get("secondary", pal["text"]), outline="")
        canvas.create_oval(18, 18, 38, 38, fill=pal.get("surface", "#FFFFFF"), outline="")
        canvas.create_text(
            28,
            28,
            text="A",
            fill=pal.get("primary", pal["text"]),
            font=(self._fonts["body_bold"][0], 15, "bold"),
        )

    def _draw_hero_orb(self) -> None:
        if self._hero_orb_canvas is None:
            return
        pal = self._palette
        canvas = self._hero_orb_canvas
        canvas.delete("all")
        canvas.configure(bg=pal.get("workspace_bg", pal["surface"]))
        center = 72
        rings = [
            (24, pal.get("primary", "#35B7FF")),
            (36, pal.get("tertiary", "#8FE7FF")),
            (52, pal.get("accent_glow", "#134A73")),
            (64, pal.get("surface_alt", pal["surface"])),
        ]
        for radius, color in reversed(rings):
            canvas.create_oval(
                center - radius,
                center - radius,
                center + radius,
                center + radius,
                fill=color,
                outline="",
            )
        canvas.create_oval(54, 42, 84, 72, fill="#FFFFFF", outline="")
        canvas.create_oval(63, 51, 77, 65, fill=pal.get("tertiary", pal["primary"]), outline="")
        canvas.create_oval(32, 88, 112, 124, fill=pal.get("surface", pal["surface_alt"]), outline="")
        canvas.create_arc(
            20,
            84,
            124,
            126,
            start=22,
            extent=148,
            style=tk.ARC,
            width=4,
            outline=pal.get("primary", "#35B7FF"),
        )

    def _configure_chat_tags(self) -> None:
        pal = self._palette
        self.chat_display.tag_config(
            "user",
            font=self._fonts["body_bold"],
            spacing1=16,
            spacing3=16,
            lmargin1=20,
            lmargin2=28,
            rmargin=20,
            background=pal.get("chat_user_bg", pal["surface_alt"]),
        )
        self.chat_display.tag_config(
            "agent",
            font=self._fonts["body"],
            spacing1=14,
            spacing3=18,
            lmargin1=20,
            lmargin2=20,
            rmargin=20,
            background=pal.get("chat_agent_bg", pal["surface"]),
        )
        self.chat_display.tag_config(
            "system",
            font=(self._fonts["caption"][0], self._fonts["caption"][1], "italic"),
            spacing1=8,
            spacing3=8,
            lmargin1=20,
            rmargin=20,
            foreground=pal.get("muted_text", pal["status"]),
            background=pal.get("chat_system_bg", pal["surface_alt"]),
        )
        self.chat_display.tag_config(
            "citation",
            foreground=pal.get("link", pal["primary"]),
            underline=1,
            font=self._fonts["code"],
        )
        self.chat_display.tag_bind("citation", "<Button-1>", self._on_citation_click)
        self.chat_display.tag_config(
            "source",
            font=self._fonts["code"],
            foreground=pal.get("source", pal.get("muted_text", pal["status"])),
        )
        self.chat_display.tag_config(
            "thinking_indicator",
            font=(self._fonts["caption"][0], self._fonts["caption"][1], "italic"),
            spacing1=10,
            spacing3=10,
            lmargin1=20,
            rmargin=20,
            foreground=pal.get("primary", "#8C5AF7"),
            background=pal.get("chat_agent_bg", pal["surface"]),
        )

    def _current_greeting(self) -> str:
        hour = dt.datetime.now().hour
        if hour < 12:
            return "Good morning."
        if hour < 18:
            return "Good afternoon."
        return "Good evening."

    def _sync_mode_chip(self) -> None:
        if hasattr(self, "_composer_mode_chip"):
            self._composer_mode_chip.set(f"Mode: {self._mode_var.get() or MODE_OPTIONS[0]}")

    def _set_chat_state(self, has_messages: bool) -> None:
        self._chat_has_messages = bool(has_messages)
        if hasattr(self, "_chat_empty_state"):
            if self._chat_has_messages:
                self._chat_empty_state.grid_remove()
            else:
                self._chat_empty_state.grid()
        if hasattr(self, "_conversation_shell"):
            if self._chat_has_messages:
                self._conversation_shell.grid()
            else:
                self._conversation_shell.grid_remove()
        if hasattr(self, "_suggestion_panel"):
            if self._chat_has_messages:
                self._suggestion_panel.grid_remove()
            else:
                self._suggestion_panel.grid()

    def _on_suggestion_clicked(self, prompt: str) -> None:
        self.set_prompt_text(prompt)
        try:
            self.txt_input.focus_set()
        except tk.TclError:
            pass

    def _configure_text_palette(
        self,
        widget: tk.Text,
        *,
        bg_key: str,
        fg_key: str = "text",
        select_bg_key: str = "selection_bg",
        select_fg_key: str = "selection_fg",
        highlight: bool = False,
    ) -> None:
        pal = self._palette
        if not widget or not widget.winfo_exists():
            return
        config = {
            "bg": pal.get(bg_key, pal["surface"]),
            "fg": pal.get(fg_key, pal["text"]),
            "insertbackground": pal["text"],
        }
        if select_bg_key:
            config["selectbackground"] = pal.get(select_bg_key, pal["selection_bg"])
        if select_fg_key:
            config["selectforeground"] = pal.get(select_fg_key, pal["selection_fg"])
        if highlight:
            config["highlightbackground"] = pal.get("border", pal["outline"])
            config["highlightcolor"] = pal.get("focus_ring", pal["primary"])
        try:
            widget.configure(**config)
        except tk.TclError:
            return

    def _apply_runtime_palette(self) -> None:
        pal = self._palette
        self.root.configure(bg=pal.get("app_bg", pal["bg"]))

        if hasattr(self, "_shell_card"):
            self._shell_card.configure_colors(
                bg=pal.get("workspace_bg", pal["surface"]),
                border_color=pal.get("workspace_border", pal["border"]),
                outer_bg=pal.get("app_bg", pal["bg"]),
                shadow_color=pal.get("workspace_shadow", ""),
            )
        for card, bg_key, border_key, shadow_key in self._theme_cards:
            if card is getattr(self, "_shell_card", None):
                continue
            card.configure_colors(
                bg=pal.get(bg_key, pal["surface"]),
                border_color=pal.get(border_key, pal["border"]),
                outer_bg=pal.get("workspace_bg", pal.get("app_bg", pal["bg"])),
                shadow_color=pal.get(shadow_key, "") if shadow_key else "",
            )

        for widget in (
            getattr(self, "chat_display", None),
            getattr(self, "_log_text", None),
            getattr(self, "_logs_view_text", None),
            getattr(self, "_evidence_detail_text", None),
            getattr(self, "_event_detail_text", None),
            getattr(self, "_region_detail_text", None),
            getattr(self, "_outline_detail_text", None),
            getattr(self, "_trace_detail_text", None),
            getattr(self, "_grounding_text", None),
            getattr(self, "_history_detail_text", None),
        ):
            if isinstance(widget, tk.Text):
                self._configure_text_palette(widget, bg_key="surface")

        if hasattr(self, "txt_input"):
            self._configure_text_palette(self.txt_input, bg_key="input_bg", highlight=True)
        if hasattr(self, "_file_listbox"):
            try:
                self._file_listbox.configure(
                    bg=pal.get("surface_alt", pal["surface"]),
                    fg=pal["text"],
                    selectbackground=pal["selection_bg"],
                    selectforeground=pal["selection_fg"],
                )
            except tk.TclError:
                pass
        for canvas_attr in ("_library_page_canvas", "_settings_canvas"):
            canvas_widget = getattr(self, canvas_attr, None)
            if isinstance(canvas_widget, tk.Canvas):
                try:
                    canvas_widget.configure(bg=pal.get("workspace_bg", pal["surface"]))
                except tk.TclError:
                    pass
        if hasattr(self, "_sidebar_divider"):
            try:
                self._sidebar_divider.configure(bg=pal.get("sidebar_border", pal["border"]))
            except tk.TclError:
                pass
        if self._sidebar_brand_canvas is not None:
            self._draw_brand_mark()
        if self._hero_orb_canvas is not None:
            self._draw_hero_orb()
        if hasattr(self, "_hero_greeting_var"):
            self._hero_greeting_var.set(self._current_greeting())
        if hasattr(self, "_hero_question_label"):
            try:
                self._hero_question_label.configure(
                    bg=pal.get("workspace_bg", pal["surface"]),
                    fg=pal["text"],
                )
            except tk.TclError:
                pass
        for widget_name in ("_chat_empty_inner", "_hero_line"):
            widget = getattr(self, widget_name, None)
            if widget is not None:
                try:
                    widget.configure(bg=pal.get("workspace_bg", pal["surface"]))
                except tk.TclError:
                    pass
        if hasattr(self, "_hero_greeting_label"):
            try:
                self._hero_greeting_label.configure(
                    bg=pal.get("workspace_bg", pal["surface"]),
                    fg=pal["text"],
                )
            except tk.TclError:
                pass
        if hasattr(self, "_hero_copy_label"):
            try:
                self._hero_copy_label.configure(
                    bg=pal.get("workspace_bg", pal["surface"]),
                    fg=pal.get("muted_text", pal["status"]),
                )
            except tk.TclError:
                pass
        if hasattr(self, "_rag_toggle"):
            self._rag_toggle.update_palette(pal)
        if hasattr(self, "chat_display"):
            self._configure_chat_tags()
        self._refresh_llm_badge()
        self._sync_mode_chip()
        self._refresh_responsive_layout()
        if self._active_view:
            self.switch_view(self._active_view)

    # ------------------------------------------------------------------
    # View builders
    # ------------------------------------------------------------------

    def _build_chat_view(self) -> None:
        """Chat view: premium prompt-first shell with a stable toolbar and dock."""
        pal = self._palette
        frame = self._views["chat"]
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        outer = ttk.Frame(frame, style="MainContent.TFrame")
        outer.grid(row=0, column=0, sticky="nsew")
        outer.grid_rowconfigure(1, weight=1)
        outer.grid_columnconfigure(0, weight=1)

        toolbar_card, toolbar_inner = self._create_card(
            outer,
            radius=18,
            bg_key="surface_elevated",
            border_key="border",
            shadow_key=None,
            inner_padding=16,
            shadow_offset=0,
        )
        toolbar_card.grid(row=0, column=0, sticky="ew", pady=(0, UI_SPACING["m"]))
        toolbar_inner.columnconfigure(0, weight=1)

        toolbar_top = ttk.Frame(toolbar_inner, style="Utility.TFrame")
        toolbar_top.grid(row=0, column=0, sticky="ew")
        toolbar_top.grid_columnconfigure(0, weight=1)
        toolbar_top.grid_columnconfigure(1, weight=0)

        self._chat_selectors = ttk.Frame(toolbar_top, style="Utility.TFrame")
        self._chat_selectors.grid(row=0, column=0, sticky="w")
        ttk.Label(self._chat_selectors, text="Mode", style="Caption.TLabel").pack(side="left", padx=(0, UI_SPACING["xs"]))
        self._mode_combo = ttk.Combobox(
            self._chat_selectors,
            textvariable=self._mode_var,
            values=MODE_OPTIONS,
            state="readonly",
            width=12,
        )
        self._mode_combo.pack(side="left", padx=(0, UI_SPACING["m"]))
        ttk.Label(self._chat_selectors, text="Profile", style="Caption.TLabel").pack(side="left", padx=(0, UI_SPACING["xs"]))
        self._profile_combo = ttk.Combobox(
            self._chat_selectors,
            textvariable=self._profile_var,
            values=["Built-in: Default"],
            state="readonly",
            width=22,
        )
        self._profile_combo.pack(side="left")

        self._chat_primary_actions = ttk.Frame(toolbar_top, style="Utility.TFrame")
        self._chat_primary_actions.grid(row=0, column=1, sticky="e")
        self.btn_profile_load = ttk.Button(self._chat_primary_actions, text="Load", style="Secondary.TButton")
        self.btn_profile_load.pack(side="left", padx=(0, UI_SPACING["xs"]))
        self.btn_profile_save = ttk.Button(self._chat_primary_actions, text="Save", style="Secondary.TButton")
        self.btn_profile_save.pack(side="left", padx=(0, UI_SPACING["xs"]))
        self.btn_profile_duplicate = ttk.Button(self._chat_primary_actions, text="Duplicate", style="Secondary.TButton")
        self.btn_profile_duplicate.pack(side="left", padx=(0, UI_SPACING["xs"]))
        self.btn_new_chat = ttk.Button(
            self._chat_primary_actions,
            text="New Chat",
            style="Primary.TButton",
            command=self._on_new_chat,
        )
        self.btn_new_chat.pack(side="left")

        toolbar_bottom = ttk.Frame(toolbar_inner, style="Utility.TFrame")
        toolbar_bottom.grid(row=1, column=0, sticky="ew", pady=(UI_SPACING["s"], 0))

        self._chat_status_cluster = ttk.Frame(toolbar_bottom, style="Utility.TFrame")
        self._chat_status_cluster.pack(side="right")
        self._llm_badge_var = tk.StringVar(value="LLM: --")
        ttk.Label(self._chat_status_cluster, textvariable=self._llm_badge_var, style="Badge.TLabel").pack(side="left")

        self._chat_secondary_actions = ttk.Frame(toolbar_bottom, style="Utility.TFrame")
        self._chat_secondary_actions.pack(side="right", padx=(UI_SPACING["m"], 0))
        self._evidence_toggle_btn = ttk.Button(
            self._chat_secondary_actions,
            text="Evidence",
            style="Secondary.TButton",
            command=self._toggle_evidence_panel,
        )
        self._evidence_toggle_btn.pack(side="left", padx=(0, UI_SPACING["xs"]))
        self.btn_feedback_up = ttk.Button(self._chat_secondary_actions, text="Up", style="Secondary.TButton", width=4)
        self.btn_feedback_up.pack(side="left", padx=(0, UI_SPACING["xs"]))
        self.btn_feedback_down = ttk.Button(self._chat_secondary_actions, text="Down", style="Secondary.TButton", width=5)
        self.btn_feedback_down.pack(side="left", padx=(0, UI_SPACING["xs"]))
        self.btn_reset_test_mode = ttk.Button(self._chat_secondary_actions, text="Reset Test Mode", style="Secondary.TButton")
        self.btn_reset_test_mode.pack(side="left")

        body = ttk.Frame(outer, style="MainContent.TFrame")
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=1)
        self._chat_body = body

        self._chat_stage = ttk.Frame(body, style="MainContent.TFrame")
        self._chat_stage.grid(row=0, column=0, sticky="nsew")
        self._chat_stage.grid_rowconfigure(0, weight=1)
        self._chat_stage.grid_columnconfigure(0, weight=1)

        self._chat_empty_state = ttk.Frame(self._chat_stage, style="MainContent.TFrame")
        self._chat_empty_state.grid(row=0, column=0, sticky="nsew")
        self._chat_empty_state.grid_rowconfigure(0, weight=1)
        self._chat_empty_state.grid_columnconfigure(0, weight=1)
        self._chat_empty_inner = tk.Frame(
            self._chat_empty_state,
            bg=pal.get("workspace_bg", pal["surface"]),
            bd=0,
            highlightthickness=0,
        )
        self._chat_empty_inner.grid(row=0, column=0, padx=UI_SPACING["xl"], pady=(UI_SPACING["xl"], UI_SPACING["m"]))

        self._hero_orb_canvas = tk.Canvas(
            self._chat_empty_inner,
            width=144,
            height=144,
            bg=pal.get("workspace_bg", pal["surface"]),
            highlightthickness=0,
            bd=0,
        )
        self._hero_orb_canvas.pack(pady=(0, UI_SPACING["s"]))
        self._draw_hero_orb()

        self._hero_greeting_var = tk.StringVar(value=self._current_greeting())
        self._hero_greeting_label = tk.Label(
            self._chat_empty_inner,
            textvariable=self._hero_greeting_var,
            font=self._fonts["h1"],
            bg=pal.get("workspace_bg", pal["surface"]),
            fg=pal["text"],
            justify="center",
        )
        self._hero_greeting_label.pack(pady=(0, UI_SPACING["xs"]))

        self._hero_line = tk.Frame(
            self._chat_empty_inner,
            bg=pal.get("workspace_bg", pal["surface"]),
            bd=0,
            highlightthickness=0,
        )
        self._hero_line.pack(pady=(0, UI_SPACING["xs"]))
        self._hero_question_label = tk.Label(
            self._hero_line,
            text="What should Axiom explore next?",
            font=self._fonts["h1"],
            bg=pal.get("workspace_bg", pal["surface"]),
            fg=pal["text"],
            justify="center",
        )
        self._hero_question_label.pack()
        self._hero_copy_label = tk.Label(
            self._chat_empty_inner,
            text="Ask questions, inspect sources, and keep retrieval settings close at hand.",
            font=self._fonts["body"],
            bg=pal.get("workspace_bg", pal["surface"]),
            fg=pal.get("muted_text", pal["status"]),
            justify="center",
        )
        self._hero_copy_label.pack()

        self._conversation_shell = ttk.Frame(self._chat_stage, style="MainContent.TFrame")
        self._conversation_shell.grid(row=0, column=0, sticky="nsew")
        self._conversation_shell.grid_rowconfigure(0, weight=1)
        self._conversation_shell.grid_columnconfigure(0, weight=1)
        self._conversation_shell.grid_columnconfigure(1, minsize=420, weight=0)

        transcript_card, transcript_inner = self._create_card(
            self._conversation_shell,
            radius=_CARD_RADIUS,
            bg_key="surface",
            border_key="border",
            shadow_key="workspace_shadow",
            shadow_offset=2,
        )
        transcript_card.grid(row=0, column=0, sticky="nsew")
        transcript_inner.rowconfigure(0, weight=1)
        transcript_inner.columnconfigure(0, weight=1)

        self.chat_display = tk.Text(
            transcript_inner,
            state="disabled",
            wrap=tk.WORD,
            font=self._fonts["body"],
            bg=pal.get("surface", pal["content_bg"]),
            fg=pal["text"],
            insertbackground=pal["text"],
            selectbackground=pal["selection_bg"],
            selectforeground=pal["selection_fg"],
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            padx=UI_SPACING["m"],
            pady=UI_SPACING["m"],
        )
        self.chat_display.grid(row=0, column=0, sticky="nsew")
        self._chat_transcript_scrollbar = ttk.Scrollbar(transcript_inner, orient="vertical", command=self.chat_display.yview)
        self._chat_transcript_scrollbar.grid(row=0, column=1, sticky="ns")
        self.chat_display.configure(yscrollcommand=self._chat_transcript_scrollbar.set)
        self._configure_chat_tags()

        self._evidence_pane_holder = ttk.Frame(self._conversation_shell, style="MainContent.TFrame")
        self._evidence_pane_holder.grid(row=0, column=1, sticky="nsew", padx=(UI_SPACING["s"], 0))
        self._evidence_pane_holder.configure(width=420)
        self._evidence_pane_holder.grid_propagate(False)
        self._evidence_visible = False
        self._build_evidence_panel()
        self._evidence_pane_holder.grid_remove()

        composer_card, composer_inner = self._create_card(
            outer,
            radius=_CARD_RADIUS,
            bg_key="surface",
            border_key="border",
            shadow_key="workspace_shadow",
            shadow_offset=2,
        )
        composer_card.grid(row=2, column=0, sticky="ew", pady=(UI_SPACING["m"], UI_SPACING["s"]))
        composer_inner.grid_columnconfigure(0, weight=1)
        composer_inner.grid_rowconfigure(1, weight=1)

        ttk.Label(
            composer_inner,
            text="Ask Axiom a question or make a request...",
            style="Muted.TLabel",
        ).grid(row=0, column=0, sticky="w", pady=(0, UI_SPACING["xs"]))

        prompt_host = ttk.Frame(composer_inner, style="Card.Flat.TFrame")
        prompt_host.grid(row=1, column=0, sticky="ew")
        prompt_host.rowconfigure(0, weight=1)
        prompt_host.columnconfigure(0, weight=1)

        self.txt_input = tk.Text(
            prompt_host,
            height=6,
            wrap=tk.WORD,
            font=self._fonts["body"],
            bg=pal.get("input_bg", pal["surface_alt"]),
            fg=pal["text"],
            insertbackground=pal["text"],
            selectbackground=pal["selection_bg"],
            selectforeground=pal["selection_fg"],
            relief="flat",
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=pal.get("border", pal["outline"]),
            highlightcolor=pal.get("focus_ring", pal["primary"]),
            padx=UI_SPACING["m"],
            pady=UI_SPACING["s"],
        )
        self.txt_input.grid(row=0, column=0, sticky="ew")
        self._prompt_scrollbar = ttk.Scrollbar(prompt_host, orient="vertical", command=self.txt_input.yview)
        self._prompt_scrollbar.grid(row=0, column=1, sticky="ns")
        self.txt_input.configure(yscrollcommand=self._prompt_scrollbar.set)

        composer_actions = ttk.Frame(composer_inner, style="Utility.TFrame")
        composer_actions.grid(row=2, column=0, sticky="ew", pady=(UI_SPACING["s"], 0))
        composer_actions.grid_columnconfigure(1, weight=1)

        left_actions = ttk.Frame(composer_actions, style="Utility.TFrame")
        left_actions.grid(row=0, column=0, sticky="w")
        self._rag_toggle = IOSSegmentedToggle(
            left_actions,
            options=["RAG", "Direct"],
            variable=self._use_rag_var,
            palette=pal,
            command=self._on_rag_toggle_clicked,
        )
        self._rag_toggle.pack(side="left", padx=(0, UI_SPACING["s"]))
        self._composer_mode_chip = tk.StringVar(value="Mode: Q&A")
        ttk.Label(left_actions, textvariable=self._composer_mode_chip, style="Badge.TLabel").pack(side="left")

        self.btn_send = ttk.Button(composer_actions, text="Send", style="Primary.TButton", width=9)
        self.btn_send.grid(row=0, column=2, sticky="e")

        self.prompt_entry = self.txt_input
        self.txt_input.bind("<Control-Return>", lambda _e: self._on_ctrl_enter())

        self._suggestion_panel = ttk.Frame(outer, style="MainContent.TFrame")
        self._suggestion_panel.grid(row=3, column=0, sticky="ew")
        ttk.Label(self._suggestion_panel, text="GET STARTED WITH AN EXAMPLE BELOW", style="Overline.TLabel").grid(
            row=0,
            column=0,
            sticky="w",
            pady=(0, UI_SPACING["s"]),
        )
        for column in range(4):
            self._suggestion_panel.grid_columnconfigure(column, weight=1)
        self._suggestion_buttons: list[ttk.Button] = []
        for idx, prompt in enumerate(
            [
                "Summarize the main ideas in my latest source",
                "Explain this topic like a tutor",
                "Generate an evidence-backed answer with citations",
                "Compare two documents and highlight differences",
            ]
        ):
            button = ttk.Button(
                self._suggestion_panel,
                text=prompt,
                style="Secondary.TButton",
                command=lambda value=prompt: self._on_suggestion_clicked(value),
            )
            button.grid(row=1, column=idx, sticky="nsew", padx=(0 if idx == 0 else UI_SPACING["xs"], 0))
            self._suggestion_buttons.append(button)

        dock_card, dock_inner = self._create_card(
            outer,
            radius=18,
            bg_key="surface_elevated",
            border_key="border",
            shadow_key=None,
            inner_padding=14,
        )
        dock_card.grid(row=4, column=0, sticky="ew", pady=(UI_SPACING["m"], 0))
        status_row = ttk.Frame(dock_inner, style="Utility.TFrame")
        status_row.pack(fill="x")
        self._status_label = ttk.Label(status_row, textvariable=self._status_var, style="Status.TLabel")
        self._status_label.pack(side="left", padx=(0, UI_SPACING["s"]))
        self.rag_progress = ttk.Progressbar(status_row, orient="horizontal", mode="determinate", length=220)
        self.rag_progress.pack(side="left", padx=(0, UI_SPACING["xs"]))
        self.btn_cancel_rag = ttk.Button(status_row, text="Cancel", style="Secondary.TButton", state="disabled")
        self.btn_cancel_rag.pack(side="left")

        self._logs_section = CollapsibleFrame(dock_inner, "Logs & telemetry", expanded=False, animator=self._animator)
        self._logs_section.pack(fill="x", pady=(UI_SPACING["s"], 0))
        self._log_text = tk.Text(
            self._logs_section.content,
            state="disabled",
            wrap=tk.WORD,
            height=4,
            font=self._fonts["code"],
            bg=pal.get("input_bg", pal["surface_alt"]),
            fg=pal.get("muted_text", pal["status"]),
            insertbackground=pal["text"],
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
        )
        self._log_text.pack(fill=tk.BOTH, expand=True, padx=UI_SPACING["s"], pady=UI_SPACING["xs"])
        self._chat_log_scrollbar = ttk.Scrollbar(self._logs_section.content, orient="vertical", command=self._log_text.yview)
        self._chat_log_scrollbar.pack(side="right", fill="y")
        self._log_text.configure(yscrollcommand=self._chat_log_scrollbar.set)

        self._refresh_llm_badge()
        self._sync_mode_chip()
        self._set_chat_state(False)

    def _build_evidence_panel(self) -> None:
        """Construct the right-side evidence inspector used by chat retrieval."""
        _, frame = self._create_card(
            self._evidence_pane_holder,
            radius=_CARD_RADIUS,
            bg_key="surface",
            border_key="border",
            shadow_key="workspace_shadow",
            shadow_offset=2,
        )
        frame.columnconfigure(0, weight=1)

        header = ttk.Frame(frame, style="Utility.TFrame")
        header.pack(fill="x", pady=(0, UI_SPACING["s"]))
        ttk.Label(header, text="Evidence inspector", style="Header.TLabel").pack(anchor="w")
        self._evidence_status_var = tk.StringVar(value="No retrieved evidence yet.")
        self._evidence_status_label = ttk.Label(
            header,
            textvariable=self._evidence_status_var,
            style="Caption.TLabel",
            wraplength=360,
            justify="left",
        )
        self._evidence_status_label.pack(anchor="w", pady=(UI_SPACING["xs"], 0))
        self._evidence_notebook = ttk.Notebook(frame)
        self._evidence_notebook.pack(fill="both", expand=True)

        self._evidence_sources_tab = ttk.Frame(self._evidence_notebook)
        self._evidence_events_tab = ttk.Frame(self._evidence_notebook)
        self._evidence_regions_tab = ttk.Frame(self._evidence_notebook)
        self._evidence_outline_tab = ttk.Frame(self._evidence_notebook)
        self._evidence_traces_tab = ttk.Frame(self._evidence_notebook)
        self._evidence_grounding_tab = ttk.Frame(self._evidence_notebook)

        self._evidence_notebook.add(self._evidence_sources_tab, text="Sources")
        self._evidence_notebook.add(self._evidence_events_tab, text="Events")
        self._evidence_notebook.add(self._evidence_regions_tab, text="Semantic Regions")
        self._evidence_notebook.add(self._evidence_outline_tab, text="Document Outline")
        self._evidence_notebook.add(self._evidence_traces_tab, text="Trace")
        self._evidence_notebook.add(self._evidence_grounding_tab, text="Grounding")

        list_host = ttk.Frame(self._evidence_sources_tab, style="Card.Elevated.TFrame")
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
        self._evidence_tree_scrollbar = ttk.Scrollbar(
            list_host,
            orient="vertical",
            command=self._evidence_tree.yview,
        )
        self._evidence_tree_scrollbar.grid(row=0, column=1, sticky="ns")
        self._evidence_tree.configure(yscrollcommand=self._evidence_tree_scrollbar.set)
        self._evidence_tree.bind("<<TreeviewSelect>>", self._on_evidence_selected)

        detail_host = ttk.Frame(self._evidence_sources_tab, style="Card.Elevated.TFrame")
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
        self._evidence_detail_scrollbar = ttk.Scrollbar(
            detail_host,
            orient="vertical",
            command=self._evidence_detail_text.yview,
        )
        self._evidence_detail_scrollbar.grid(row=0, column=1, sticky="ns")
        self._evidence_detail_text.configure(yscrollcommand=self._evidence_detail_scrollbar.set)
        self._set_evidence_detail("No evidence selected.")

        self._events_tree = self._build_simple_tree(
            self._evidence_events_tab,
            ("date", "action", "source"),
            ("Date", "Action", "Source"),
        )
        self._event_detail_text = self._build_detail_text(self._evidence_events_tab)
        self._events_tree.bind("<<TreeviewSelect>>", self._on_event_selected)

        self._regions_tree = self._build_simple_tree(
            self._evidence_regions_tab,
            ("label", "type", "file"),
            ("Region", "Type", "File"),
        )
        self._region_detail_text = self._build_detail_text(self._evidence_regions_tab)
        self._regions_tree.bind("<<TreeviewSelect>>", self._on_region_selected)

        self._outline_tree = self._build_outline_tree(self._evidence_outline_tab)
        self._outline_detail_text = self._build_detail_text(self._evidence_outline_tab)
        self._outline_tree.bind("<<TreeviewSelect>>", self._on_outline_selected)

        self._trace_tree = self._build_simple_tree(
            self._evidence_traces_tab,
            ("run_id", "stage", "event_type", "timestamp"),
            ("Run", "Stage", "Type", "Timestamp"),
        )
        self._trace_detail_text = self._build_detail_text(self._evidence_traces_tab)
        self._trace_tree.bind("<<TreeviewSelect>>", self._on_trace_selected)

        self._grounding_artifact_var = tk.StringVar(value="No grounding artifact recorded.")
        grounding_toolbar = ttk.Frame(self._evidence_grounding_tab, style="Card.Flat.TFrame")
        grounding_toolbar.grid(row=0, column=0, sticky="ew", pady=(0, UI_SPACING["s"]))
        grounding_toolbar.columnconfigure(0, weight=1)
        ttk.Label(
            grounding_toolbar,
            textvariable=self._grounding_artifact_var,
            style="Caption.TLabel",
            wraplength=340,
            justify="left",
        ).grid(row=0, column=0, sticky="w")
        self.btn_open_grounding_artifact = ttk.Button(
            grounding_toolbar,
            text="Open Artifact",
            style="Secondary.TButton",
            state="disabled",
            command=self._open_grounding_artifact,
        )
        self.btn_open_grounding_artifact.grid(row=0, column=1, padx=(UI_SPACING["s"], 0))
        self._grounding_text = self._build_detail_text(self._evidence_grounding_tab)

    def _build_simple_tree(
        self,
        parent: ttk.Frame,
        columns: tuple[str, ...],
        headings: tuple[str, ...],
    ) -> ttk.Treeview:
        parent.rowconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        parent.columnconfigure(0, weight=1)
        host = ttk.Frame(parent, style="Card.Elevated.TFrame")
        host.grid(row=0, column=0, sticky="nsew")
        host.rowconfigure(0, weight=1)
        host.columnconfigure(0, weight=1)
        tree = ttk.Treeview(host, columns=columns, show="headings", selectmode="browse")
        for column, heading in zip(columns, headings):
            tree.heading(column, text=heading)
            tree.column(column, width=120, anchor="w")
        tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(host, orient="vertical", command=tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=scroll.set)
        return tree

    def _build_outline_tree(self, parent: ttk.Frame) -> ttk.Treeview:
        parent.rowconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        parent.columnconfigure(0, weight=1)
        host = ttk.Frame(parent, style="Card.Elevated.TFrame")
        host.grid(row=0, column=0, sticky="nsew")
        host.rowconfigure(0, weight=1)
        host.columnconfigure(0, weight=1)
        tree = ttk.Treeview(host, columns=("title", "file"), show="tree headings", selectmode="browse")
        tree.heading("#0", text="Node")
        tree.heading("title", text="Title")
        tree.heading("file", text="File")
        tree.column("#0", width=100, anchor="w")
        tree.column("title", width=180, anchor="w")
        tree.column("file", width=120, anchor="w")
        tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(host, orient="vertical", command=tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=scroll.set)
        return tree

    def _build_detail_text(self, parent: ttk.Frame) -> tk.Text:
        host = ttk.Frame(parent, style="Card.Elevated.TFrame")
        host.grid(row=1, column=0, sticky="nsew", pady=(UI_SPACING["s"], 0))
        host.rowconfigure(0, weight=1)
        host.columnconfigure(0, weight=1)
        text = tk.Text(
            host,
            wrap=tk.WORD,
            height=8,
            state="disabled",
            font=self._fonts["code"],
            bg=self._palette.get("input_bg", "#07101A"),
            fg=self._palette["text"],
            insertbackground=self._palette["text"],
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
        )
        text.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(host, orient="vertical", command=text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        text.configure(yscrollcommand=scroll.set)
        return text

    def _build_library_view(self) -> None:
        """Library view: card-based source, build controls, and index summary."""
        frame = self._views["library"]
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        page_host, self._library_page_canvas, outer, self._library_page_scrollbar = self._create_scrollable_page(frame)
        page_host.grid(row=0, column=0, sticky="nsew")
        outer.columnconfigure(0, weight=1)

        header = ttk.Frame(outer, style="MainContent.TFrame")
        header.grid(row=0, column=0, sticky="ew", pady=(0, UI_SPACING["m"]))
        ttk.Label(header, text="Library", style="Header.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="Bring in source files, tune the build, and manage persisted indexes from one workspace.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(UI_SPACING["xs"], 0))

        source_card, source_inner = self._create_card(outer)
        source_card.grid(row=1, column=0, sticky="ew")
        source_inner.columnconfigure(0, weight=1)
        ttk.Label(source_inner, text="Step 1 · Source files", style="Header.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(source_inner, text="Choose one or more files to include in the current working set.", style="Caption.TLabel").grid(
            row=1,
            column=0,
            sticky="w",
            pady=(UI_SPACING["xs"], UI_SPACING["s"]),
        )

        toolbar = ttk.Frame(source_inner, style="Utility.TFrame")
        toolbar.grid(row=2, column=0, sticky="ew")
        self.btn_open_files = ttk.Button(toolbar, text="Open Files...", style="Primary.TButton")
        self.btn_open_files.pack(side="left", padx=(0, UI_SPACING["xs"]))
        self.btn_build_index = ttk.Button(toolbar, text="Build Index", style="Secondary.TButton")
        self.btn_build_index.pack(side="left")
        ttk.Label(toolbar, textvariable=self._index_info_var, style="Caption.TLabel").pack(side="left", padx=(UI_SPACING["m"], 0))

        list_host = ttk.Frame(source_inner, style="Card.Flat.TFrame")
        list_host.grid(row=3, column=0, sticky="nsew", pady=(UI_SPACING["s"], 0))
        list_host.rowconfigure(0, weight=1)
        list_host.columnconfigure(0, weight=1)
        self._file_listbox = tk.Listbox(
            list_host,
            selectmode="extended",
            activestyle="dotbox",
            height=8,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
        )
        self._file_listbox.grid(row=0, column=0, sticky="nsew", padx=UI_SPACING["s"], pady=UI_SPACING["s"])
        file_vsb = ttk.Scrollbar(list_host, orient="vertical", command=self._file_listbox.yview)
        file_vsb.grid(row=0, column=1, sticky="ns", pady=UI_SPACING["s"])
        self._file_listbox.configure(yscrollcommand=file_vsb.set)
        file_hsb = ttk.Scrollbar(list_host, orient="horizontal", command=self._file_listbox.xview)
        file_hsb.grid(row=1, column=0, sticky="ew", padx=UI_SPACING["s"])
        self._file_listbox.configure(xscrollcommand=file_hsb.set)

        settings_card, settings_inner = self._create_card(outer)
        settings_card.grid(row=2, column=0, sticky="ew", pady=(UI_SPACING["m"], 0))
        for column in range(6):
            settings_inner.columnconfigure(column, weight=1 if column % 2 else 0)
        ttk.Label(settings_inner, text="Step 2 · Build settings", style="Header.TLabel").grid(row=0, column=0, columnspan=6, sticky="w")
        ttk.Label(
            settings_inner,
            text="These controls feed the current MVC index and query path directly.",
            style="Caption.TLabel",
        ).grid(row=1, column=0, columnspan=6, sticky="w", pady=(UI_SPACING["xs"], UI_SPACING["s"]))

        self._lib_chunk_size_var = tk.StringVar(value=str(self._settings_data.get("chunk_size", 800)))
        self._lib_chunk_overlap_var = tk.StringVar(value=str(self._settings_data.get("chunk_overlap", 100)))
        self._lib_top_k_var = tk.StringVar(value=str(self._settings_data.get("top_k", 3)))
        ttk.Label(settings_inner, text="Chunk size", style="Caption.TLabel").grid(row=2, column=0, sticky="w")
        ttk.Entry(settings_inner, textvariable=self._lib_chunk_size_var, width=10).grid(
            row=2,
            column=1,
            sticky="w",
            padx=(UI_SPACING["xs"], UI_SPACING["m"]),
        )
        ttk.Label(settings_inner, text="Chunk overlap", style="Caption.TLabel").grid(row=2, column=2, sticky="w")
        ttk.Entry(settings_inner, textvariable=self._lib_chunk_overlap_var, width=10).grid(
            row=2,
            column=3,
            sticky="w",
            padx=(UI_SPACING["xs"], UI_SPACING["m"]),
        )
        ttk.Label(settings_inner, text="Top-K", style="Caption.TLabel").grid(row=2, column=4, sticky="w")
        ttk.Entry(settings_inner, textvariable=self._lib_top_k_var, width=10).grid(row=2, column=5, sticky="w", padx=(UI_SPACING["xs"], 0))

        index_card, index_inner = self._create_card(outer)
        index_card.grid(row=3, column=0, sticky="ew", pady=(UI_SPACING["m"], 0))
        index_inner.columnconfigure(1, weight=1)
        ttk.Label(index_inner, text="Step 3 · Active index", style="Header.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(index_inner, text="Load a saved index or inspect the active persisted path.", style="Caption.TLabel").grid(
            row=1,
            column=0,
            columnspan=3,
            sticky="w",
            pady=(UI_SPACING["xs"], UI_SPACING["s"]),
        )
        ttk.Label(index_inner, text="Saved indexes", style="Caption.TLabel").grid(row=2, column=0, sticky="w")
        self._available_index_combo = ttk.Combobox(
            index_inner,
            textvariable=self._available_index_var,
            values=[],
            state="readonly",
            width=72,
        )
        self._available_index_combo.grid(row=2, column=1, sticky="ew", padx=(UI_SPACING["xs"], UI_SPACING["xs"]))
        self.btn_library_load_index = ttk.Button(index_inner, text="Load Selected", style="Secondary.TButton")
        self.btn_library_load_index.grid(row=2, column=2, sticky="e")
        self._active_index_summary_var = tk.StringVar(value="No persisted index selected.")
        self._active_index_path_var = tk.StringVar(value="")
        ttk.Label(index_inner, textvariable=self._active_index_summary_var, style="TLabel").grid(
            row=3,
            column=0,
            columnspan=3,
            sticky="w",
            pady=(UI_SPACING["s"], 0),
        )
        self._active_index_path_label = ttk.Label(
            index_inner,
            textvariable=self._active_index_path_var,
            style="Caption.TLabel",
            wraplength=920,
            justify="left",
        )
        self._active_index_path_label.grid(row=4, column=0, columnspan=3, sticky="w", pady=(UI_SPACING["xs"], 0))

        self.progress = ttk.Progressbar(outer, orient="horizontal", mode="determinate")
        self.progress.grid(row=4, column=0, sticky="ew", pady=(UI_SPACING["m"], 0))
        ttk.Frame(outer, style="MainContent.TFrame", height=UI_SPACING["l"]).grid(row=5, column=0, sticky="ew")

    def _build_history_view(self) -> None:
        """History view: command bar and master-detail cards."""
        frame = self._views["history"]
        frame.rowconfigure(2, weight=1)
        frame.columnconfigure(0, weight=3)
        frame.columnconfigure(1, weight=2)

        header = ttk.Frame(frame, style="MainContent.TFrame")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, UI_SPACING["m"]))
        ttk.Label(header, text="History", style="Header.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="Resume persisted sessions, inspect summaries, and export transcripts.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(UI_SPACING["xs"], 0))

        actions = ttk.Frame(frame, style="Utility.TFrame")
        actions.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, UI_SPACING["s"]))
        self.btn_history_new_chat = ttk.Button(actions, text="New Chat", style="Primary.TButton")
        self.btn_history_new_chat.pack(side="left")
        self.btn_history_open = ttk.Button(actions, text="Open", style="Secondary.TButton")
        self.btn_history_open.pack(side="left", padx=(UI_SPACING["xs"], 0))
        self.btn_history_delete = ttk.Button(actions, text="Delete", style="Secondary.TButton")
        self.btn_history_delete.pack(side="left", padx=(UI_SPACING["xs"], 0))
        self.btn_history_rename = ttk.Button(actions, text="Rename", style="Secondary.TButton")
        self.btn_history_rename.pack(side="left", padx=(UI_SPACING["xs"], 0))
        self.btn_history_duplicate = ttk.Button(actions, text="Duplicate", style="Secondary.TButton")
        self.btn_history_duplicate.pack(side="left", padx=(UI_SPACING["xs"], 0))
        self.btn_history_export = ttk.Button(actions, text="Export", style="Secondary.TButton")
        self.btn_history_export.pack(side="left", padx=(UI_SPACING["xs"], 0))
        self.btn_history_refresh = ttk.Button(actions, text="Refresh", style="Secondary.TButton")
        self.btn_history_refresh.pack(side="left", padx=(UI_SPACING["xs"], 0))
        ttk.Label(actions, text="Profile", style="Caption.TLabel").pack(
            side="left", padx=(UI_SPACING["m"], UI_SPACING["xs"])
        )
        self._history_profile_combo = ttk.Combobox(
            actions,
            textvariable=self._history_profile_var,
            values=["All Profiles"],
            state="readonly",
            width=24,
        )
        self._history_profile_combo.pack(side="left")
        ttk.Label(actions, text="Search", style="Caption.TLabel").pack(side="left", padx=(UI_SPACING["m"], UI_SPACING["xs"]))
        self._history_search_var = tk.StringVar()
        self._history_search_entry = ttk.Entry(actions, textvariable=self._history_search_var, width=28)
        self._history_search_entry.pack(side="left", fill="x", expand=True)

        left_card, left = self._create_card(frame)
        left_card.grid(row=2, column=0, sticky="nsew", padx=(0, UI_SPACING["xs"]))
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

        right_card, right = self._create_card(frame)
        right_card.grid(row=2, column=1, sticky="nsew", padx=(UI_SPACING["xs"], 0))
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)

        self._history_detail_summary_var = tk.StringVar(value="Select a session to inspect its details.")
        self._history_detail_summary_label = ttk.Label(
            right,
            textvariable=self._history_detail_summary_var,
            style="TLabel",
            wraplength=420,
            justify="left",
        )
        self._history_detail_summary_label.grid(row=0, column=0, sticky="ew")

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
        hdr = ttk.Frame(frame, style="MainContent.TFrame")
        hdr.grid(row=0, column=0, sticky="ew", pady=(0, UI_SPACING["m"]))
        ttk.Label(hdr, text="Settings", style="Header.TLabel").pack(side="left")

        canvas_card, canvas_host = self._create_card(frame)
        canvas_card.grid(row=1, column=0, sticky="nsew")
        canvas_host.rowconfigure(0, weight=1)
        canvas_host.columnconfigure(0, weight=1)

        self._settings_canvas = tk.Canvas(
            canvas_host,
            bg=pal.get("workspace_bg", pal["surface"]),
            highlightthickness=0,
            bd=0,
        )
        self._settings_canvas.grid(row=0, column=0, sticky="nsew")

        self._settings_scrollbar = ttk.Scrollbar(
            canvas_host,
            orient="vertical",
            command=self._settings_canvas.yview,
        )
        self._settings_scrollbar.grid(row=0, column=1, sticky="ns")
        self._settings_canvas.configure(yscrollcommand=self._settings_scrollbar.set)

        inner = ttk.Frame(self._settings_canvas, style="Card.TFrame")
        inner.columnconfigure(0, weight=1)
        canvas_window = self._settings_canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_inner_configure(_event: tk.Event) -> None:
            try:
                bbox = self._settings_canvas.bbox("all")
                if bbox:
                    self._settings_canvas.configure(scrollregion=bbox)
            except tk.TclError:
                return

        def _on_canvas_configure(event: tk.Event) -> None:
            try:
                self._settings_canvas.itemconfig(canvas_window, width=event.width)
            except tk.TclError:
                return

        inner.bind("<Configure>", _on_inner_configure)
        self._settings_canvas.bind("<Configure>", _on_canvas_configure)
        self._bind_scoped_mousewheel(self._settings_canvas, inner)

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

        local_models = ttk.LabelFrame(
            inner,
            text="Local Model Registry",
            padding=(UI_SPACING["m"], UI_SPACING["s"]),
        )
        local_models.grid(
            row=len(_SETTINGS_SPEC),
            column=0,
            sticky="ew",
            padx=UI_SPACING["s"],
            pady=(UI_SPACING["m"], 0),
        )
        local_models.rowconfigure(1, weight=1)
        local_models.columnconfigure(0, weight=1)
        deps = ttk.Frame(local_models, style="Card.Flat.TFrame")
        deps.grid(row=0, column=0, sticky="ew")
        self._gguf_dependency_var = tk.StringVar(value="llama-cpp-python: missing")
        self._st_dependency_var = tk.StringVar(value="sentence-transformers: missing")
        ttk.Label(deps, textvariable=self._gguf_dependency_var, style="Caption.TLabel").pack(side="left")
        ttk.Label(deps, textvariable=self._st_dependency_var, style="Caption.TLabel").pack(
            side="left",
            padx=(UI_SPACING["m"], 0),
        )
        registry_host = ttk.Frame(local_models, style="Card.Elevated.TFrame")
        registry_host.grid(row=1, column=0, sticky="nsew", pady=(UI_SPACING["s"], 0))
        registry_host.rowconfigure(0, weight=1)
        registry_host.columnconfigure(0, weight=1)
        self._local_model_tree = ttk.Treeview(
            registry_host,
            columns=("type", "name", "path", "active"),
            show="headings",
            selectmode="browse",
            height=8,
        )
        for name, label, width in (
            ("type", "Type", 120),
            ("name", "Name", 180),
            ("path", "Path / Value", 360),
            ("active", "Active", 140),
        ):
            self._local_model_tree.heading(name, text=label)
            self._local_model_tree.column(name, width=width, anchor="w")
        self._local_model_tree.grid(row=0, column=0, sticky="nsew")
        local_scroll = ttk.Scrollbar(registry_host, orient="vertical", command=self._local_model_tree.yview)
        local_scroll.grid(row=0, column=1, sticky="ns")
        self._local_model_tree.configure(yscrollcommand=local_scroll.set)
        local_actions = ttk.Frame(local_models, style="Card.Flat.TFrame")
        local_actions.grid(row=2, column=0, sticky="ew", pady=(UI_SPACING["s"], 0))
        self.btn_add_local_gguf_model = ttk.Button(local_actions, text="Add GGUF")
        self.btn_add_local_gguf_model.pack(side="left")
        self.btn_add_local_st_model = ttk.Button(local_actions, text="Add ST")
        self.btn_add_local_st_model.pack(side="left", padx=(UI_SPACING["xs"], 0))
        self.btn_remove_local_model = ttk.Button(local_actions, text="Remove")
        self.btn_remove_local_model.pack(side="left", padx=(UI_SPACING["xs"], 0))
        self.btn_activate_local_model_llm = ttk.Button(local_actions, text="Use as LLM")
        self.btn_activate_local_model_llm.pack(side="left", padx=(UI_SPACING["xs"], 0))
        self.btn_activate_local_model_embedding = ttk.Button(local_actions, text="Use as Embedding")
        self.btn_activate_local_model_embedding.pack(side="left", padx=(UI_SPACING["xs"], 0))
        self.btn_open_local_model_folder = ttk.Button(local_actions, text="Open Folder")
        self.btn_open_local_model_folder.pack(side="left", padx=(UI_SPACING["xs"], 0))
        self.btn_install_local_gguf_dep = ttk.Button(local_actions, text="Install llama-cpp")
        self.btn_install_local_gguf_dep.pack(side="right")
        self.btn_install_local_st_dep = ttk.Button(local_actions, text="Install sentence-transformers")
        self.btn_install_local_st_dep.pack(side="right", padx=(0, UI_SPACING["xs"]))

        # Bottom spacer inside the scroll area
        ttk.Frame(inner, style="Card.TFrame", height=UI_SPACING["l"]).grid(
            row=len(_SETTINGS_SPEC) + 1, column=0,
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

        hdr = ttk.Frame(frame, style="MainContent.TFrame")
        hdr.grid(row=0, column=0, sticky="ew", pady=(0, UI_SPACING["m"]))
        ttk.Label(hdr, text="Logs & Telemetry",
                  style="Header.TLabel").pack(side="left")

        logs_card, text_host = self._create_card(frame)
        logs_card.grid(row=1, column=0, sticky="nsew")
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

        self._logs_view_scrollbar = ttk.Scrollbar(
            text_host,
            orient="vertical",
            command=self._logs_view_text.yview,
        )
        self._logs_view_scrollbar.grid(row=0, column=1, sticky="ns")
        self._logs_view_text.configure(yscrollcommand=self._logs_view_scrollbar.set)

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
        self._refresh_responsive_layout()

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

    def set_available_indexes(self, rows: list[dict], selected_path: str = "") -> None:
        """Populate the persisted-index selector in the Library view."""
        self._available_index_rows = list(rows or [])
        labels = [str(row.get("label", "") or row.get("index_id", "")) for row in self._available_index_rows]
        if hasattr(self, "_available_index_combo"):
            self._available_index_combo.configure(values=labels)
        chosen = ""
        for row in self._available_index_rows:
            if str(row.get("path", "") or "") == str(selected_path or ""):
                chosen = str(row.get("label", "") or row.get("index_id", ""))
                break
        self._available_index_var.set(chosen)

    def get_selected_available_index_path(self) -> str:
        """Return the currently selected persisted index path."""
        label = self._available_index_var.get().strip()
        for row in self._available_index_rows:
            if str(row.get("label", "") or row.get("index_id", "")) == label:
                return str(row.get("path", "") or "")
        return ""

    def set_profile_options(self, labels: list[str], selected_label: str = "") -> None:
        """Populate profile selectors in chat and history."""
        normalized = list(labels or ["Built-in: Default"])
        if hasattr(self, "_profile_combo"):
            self._profile_combo.configure(values=normalized)
        chosen = selected_label if selected_label in normalized else (normalized[0] if normalized else "Built-in: Default")
        self._profile_var.set(chosen)
        if hasattr(self, "_history_profile_combo"):
            history_values = ["All Profiles", *normalized]
            self._history_profile_combo.configure(values=history_values)
            if self._history_profile_var.get() not in history_values:
                self._history_profile_var.set("All Profiles")

    def select_profile_label(self, label: str) -> None:
        """Set the active profile selector."""
        self._profile_var.set(str(label or "Built-in: Default"))

    def get_selected_profile_label(self) -> str:
        """Return the active profile label from the chat toolbar."""
        return self._profile_var.get().strip() or "Built-in: Default"

    def set_local_model_rows(
        self,
        rows: list[dict],
        dependency_status: dict[str, bool] | None = None,
    ) -> None:
        """Render the local-model registry table and dependency status."""
        if hasattr(self, "_local_model_tree"):
            self._local_model_tree.delete(*self._local_model_tree.get_children())
            for row in rows or []:
                active = []
                if row.get("active_llm"):
                    active.append("LLM")
                if row.get("active_embedding"):
                    active.append("Embedding")
                self._local_model_tree.insert(
                    "",
                    "end",
                    iid=str(row.get("entry_id", "")),
                    values=(
                        str(row.get("model_type", "") or ""),
                        str(row.get("name", "") or ""),
                        str(row.get("path") or row.get("value") or ""),
                        ", ".join(active) or "-",
                    ),
                )
        deps = dependency_status or {}
        if hasattr(self, "_gguf_dependency_var"):
            self._gguf_dependency_var.set(
                "llama-cpp-python: ready"
                if deps.get("llama_cpp_python")
                else "llama-cpp-python: missing"
            )
        if hasattr(self, "_st_dependency_var"):
            self._st_dependency_var.set(
                "sentence-transformers: ready"
                if deps.get("sentence_transformers")
                else "sentence-transformers: missing"
            )

    def get_selected_local_model_id(self) -> str:
        """Return the selected local-model registry row id."""
        if not hasattr(self, "_local_model_tree"):
            return ""
        selected = self._local_model_tree.selection()
        return selected[0] if selected else ""

    def set_prompt_text(self, text: str) -> None:
        """Replace the current prompt text."""
        self.clear_prompt()
        try:
            self.txt_input.insert("1.0", text)
        except tk.TclError:
            pass

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
        self._set_chat_state(True)

    def clear_chat(self) -> None:
        """Clear the chat transcript area."""
        self.chat_display.configure(state="normal")
        self.chat_display.delete("1.0", "end")
        self.chat_display.configure(state="disabled")
        self._set_chat_state(False)

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
        self._set_chat_state(bool(messages))

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
                    str(payload.get("label") or payload.get("title") or payload.get("source") or "unknown"),
                    f"{float(payload.get('score')):.3f}" if payload.get("score") is not None else "-",
                ),
            )
        self._evidence_status_var.set(f"{len(sources)} evidence item(s) loaded.")
        if hasattr(self, "_evidence_notebook"):
            self._evidence_notebook.select(self._evidence_sources_tab)
        first = self._evidence_tree.get_children("")
        if first:
            self._evidence_tree.selection_set(first[0])
            self._evidence_tree.focus(first[0])
            self._on_evidence_selected()

    def focus_evidence_source(self, sid: str) -> None:
        """Select a source in the evidence pane by its stable citation id."""
        if not hasattr(self, "_evidence_tree"):
            return
        if hasattr(self, "_evidence_notebook"):
            self._evidence_notebook.select(self._evidence_sources_tab)
        for iid, mapped_sid in self._evidence_source_by_iid.items():
            if mapped_sid == sid and self._evidence_tree.exists(iid):
                self._evidence_tree.selection_set(iid)
                self._evidence_tree.focus(iid)
                self._evidence_tree.see(iid)
                self._on_evidence_selected()
                break

    def render_events(self, events: list[dict]) -> None:
        """Render extracted event metadata."""
        if not hasattr(self, "_events_tree"):
            return
        self._event_payload_by_iid = {}
        self._events_tree.delete(*self._events_tree.get_children())
        self._set_text_widget(self._event_detail_text, "No event selected.")
        for idx, event in enumerate(events or [], start=1):
            iid = f"event-{idx}"
            payload = dict(event or {})
            self._event_payload_by_iid[iid] = payload
            self._events_tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    str(payload.get("date", "") or "-"),
                    str(payload.get("action", "") or "-"),
                    ", ".join(str(item) for item in (payload.get("actors") or [])) or "-",
                ),
            )

    def render_semantic_regions(self, regions: list[dict]) -> None:
        """Render semantic-region metadata."""
        if not hasattr(self, "_regions_tree"):
            return
        self._region_payload_by_iid = {}
        self._regions_tree.delete(*self._regions_tree.get_children())
        self._set_text_widget(self._region_detail_text, "No semantic region selected.")
        for idx, region in enumerate(regions or [], start=1):
            iid = f"region-{idx}"
            payload = dict(region or {})
            self._region_payload_by_iid[iid] = payload
            self._regions_tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    str(payload.get("region_label", "") or "-"),
                    str(payload.get("region_type", "") or "-"),
                    str(payload.get("file_path", "") or "-"),
                ),
            )

    def render_document_outline(self, outline_nodes: list[dict], grounding_path: str = "") -> None:
        """Render the document outline tree."""
        if not hasattr(self, "_outline_tree"):
            return
        self._outline_payload_by_iid = {}
        self._outline_tree.delete(*self._outline_tree.get_children())
        self._set_text_widget(self._outline_detail_text, "No outline node selected.")
        for idx, node in enumerate(outline_nodes or [], start=1):
            iid = str(node.get("id") or f"outline-{idx}")
            parent = str(node.get("parent_id") or "")
            if parent and not self._outline_tree.exists(parent):
                parent = ""
            payload = dict(node or {})
            self._outline_payload_by_iid[iid] = payload
            self._outline_tree.insert(
                parent,
                "end",
                iid=iid,
                text=str(payload.get("level", "") or ""),
                values=(
                    str(payload.get("node_title", "") or ""),
                    str(payload.get("file_path", "") or ""),
                ),
            )
        if grounding_path:
            self.render_grounding_info(grounding_path)

    def render_trace_events(self, events: list[dict]) -> None:
        """Render run trace events."""
        if not hasattr(self, "_trace_tree"):
            return
        self._trace_payload_by_iid = {}
        self._trace_tree.delete(*self._trace_tree.get_children())
        self._set_text_widget(self._trace_detail_text, "No trace event selected.")
        for idx, event in enumerate(events or [], start=1):
            iid = f"trace-{idx}"
            payload = dict(event or {})
            self._trace_payload_by_iid[iid] = payload
            self._trace_tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    str(payload.get("run_id", "") or "-"),
                    str(payload.get("stage", "") or "-"),
                    str(payload.get("event_type", "") or "-"),
                    str(payload.get("timestamp", "") or "-"),
                ),
            )

    def _open_grounding_artifact(self) -> None:
        path = str(getattr(self, "_grounding_artifact_path", "") or "").strip()
        if not path or not os.path.exists(path):
            return
        if os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
            return
        import subprocess

        opener = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.Popen([opener, path])

    def render_grounding_info(self, text: str) -> None:
        """Render stored grounding info or artifact paths."""
        normalized = str(text or "").strip()
        self._grounding_artifact_path = normalized if os.path.isfile(normalized) else ""
        if hasattr(self, "_grounding_artifact_var"):
            self._grounding_artifact_var.set(
                self._grounding_artifact_path or "No grounding artifact recorded."
            )
        if hasattr(self, "btn_open_grounding_artifact"):
            self.btn_open_grounding_artifact.configure(
                state="normal" if self._grounding_artifact_path else "disabled"
            )
        if hasattr(self, "_grounding_text"):
            self._set_text_widget(self._grounding_text, normalized or "No grounding artifact recorded.")

    def bind_history_search(self, callback) -> None:
        """Bind the History search entry to a callback."""
        if hasattr(self, "_history_search_entry"):
            self._history_search_entry.bind("<KeyRelease>", callback)

    def bind_history_selection(self, callback) -> None:
        """Bind history selection and open actions to a callback."""
        if hasattr(self, "_history_tree"):
            self._history_tree.bind("<<TreeviewSelect>>", callback)

    def bind_history_profile_filter(self, callback) -> None:
        """Bind the History profile filter combo to a callback."""
        if hasattr(self, "_history_profile_combo"):
            self._history_profile_combo.bind("<<ComboboxSelected>>", callback)

    def get_history_search_query(self) -> str:
        """Return the current History search query."""
        return self._history_search_var.get().strip() if hasattr(self, "_history_search_var") else ""

    def get_history_profile_filter(self) -> str:
        """Return the selected History profile filter."""
        value = self._history_profile_var.get().strip() if hasattr(self, "_history_profile_var") else ""
        return "" if value in {"", "All Profiles"} else value

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
            f"Profile: {getattr(summary, 'active_profile', '-') or '-'}  |  "
            f"Model: {getattr(summary, 'llm_model', '-') or '-'}  |  "
            f"Index: {getattr(summary, 'index_id', '(default)') or '(default)'}"
        )
        self._history_detail_summary_var.set(headline)

        lines = [
            f"Session ID: {getattr(summary, 'session_id', '')}",
            f"Created: {getattr(summary, 'created_at', '')}",
            f"Updated: {getattr(summary, 'updated_at', '')}",
            f"Vector backend: {getattr(summary, 'vector_backend', '') or '-'}",
            f"Summary: {getattr(summary, 'summary', '') or '(none)'}",
            f"Feedback items: {len(getattr(detail, 'feedback', []) or [])}",
            f"Trace runs: {len(getattr(detail, 'traces', {}) or {})}",
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
        feedback_items = list(getattr(detail, "feedback", []) or [])
        if feedback_items:
            lines.extend(["", "Feedback:"])
            for item in feedback_items[-5:]:
                vote = "thumbs-up" if int(getattr(item, "vote", 0) or 0) > 0 else "thumbs-down"
                note = str(getattr(item, "note", "") or "").strip() or "(no note)"
                lines.append(f"- {vote}: {note}")
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
        self._profile_var.set(str(self._settings_data.get("selected_profile", "Built-in: Default") or "Built-in: Default"))
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
        self._sync_mode_chip()

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
        self._llm_badge_var.set(f"LLM: {provider} / {model}")

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

    @staticmethod
    def _format_payload(payload: dict) -> str:
        try:
            return json.dumps(payload, ensure_ascii=False, indent=2)
        except TypeError:
            return str(payload)

    def _set_text_widget(self, widget: tk.Text, text: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")

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
            f"Title: {payload.get('title') or payload.get('label') or payload.get('source', 'unknown')}",
            f"Source: {payload.get('source', 'unknown')}",
            f"Chunk ID: {payload.get('chunk_id') or '-'}",
            f"Chunk Index: {payload.get('chunk_idx') if payload.get('chunk_idx') is not None else '-'}",
            f"Score: {payload.get('score') if payload.get('score') is not None else '-'}",
            f"Section: {payload.get('section_hint') or '-'}",
            f"Locator: {payload.get('locator') or '-'}",
            f"Path: {payload.get('file_path') or '-'}",
            f"Anchor: {payload.get('anchor') or '-'}",
            f"Date: {payload.get('date') or payload.get('timestamp') or '-'}",
            f"Actor/Speaker: {payload.get('actor') or payload.get('speaker') or '-'}",
            f"Type: {payload.get('type') or '-'}",
            "",
            "Snippet:",
            str(payload.get("excerpt") or payload.get("snippet") or "(no snippet)"),
        ]
        metadata = payload.get("metadata") or {}
        if metadata:
            detail.extend(["", "Metadata:", self._format_payload(dict(metadata))])
        self._set_evidence_detail("\n".join(detail))

    def _on_event_selected(self, _event=None) -> None:
        if not hasattr(self, "_events_tree"):
            return
        selected = self._events_tree.selection()
        if not selected:
            return
        payload = self._event_payload_by_iid.get(selected[0], {})
        self._set_text_widget(self._event_detail_text, self._format_payload(payload))

    def _on_region_selected(self, _event=None) -> None:
        if not hasattr(self, "_regions_tree"):
            return
        selected = self._regions_tree.selection()
        if not selected:
            return
        payload = self._region_payload_by_iid.get(selected[0], {})
        self._set_text_widget(self._region_detail_text, self._format_payload(payload))

    def _on_outline_selected(self, _event=None) -> None:
        if not hasattr(self, "_outline_tree"):
            return
        selected = self._outline_tree.selection()
        if not selected:
            return
        payload = self._outline_payload_by_iid.get(selected[0], {})
        self._set_text_widget(self._outline_detail_text, self._format_payload(payload))

    def _on_trace_selected(self, _event=None) -> None:
        if not hasattr(self, "_trace_tree"):
            return
        selected = self._trace_tree.selection()
        if not selected:
            return
        payload = self._trace_payload_by_iid.get(selected[0], {})
        self._set_text_widget(self._trace_detail_text, self._format_payload(payload))

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
        """Clear the chat display immediately before the controller handles session state."""
        self.clear_chat()
        self.set_status("New chat started.")
        self._toggle_evidence_panel(force=False)

    def _toggle_evidence_panel(self, force: bool | None = None) -> None:
        """Toggle the evidence side pane."""
        self._evidence_visible = (not self._evidence_visible) if force is None else bool(force)
        if not hasattr(self, "_evidence_pane_holder"):
            return
        if self._evidence_visible:
            self._evidence_pane_holder.grid()
        else:
            self._evidence_pane_holder.grid_remove()

    def show_wizard_step(self, title: str) -> None:
        """Expose the current wizard step in the status bar."""
        self.set_status(f"Wizard: {title}")

    def show_setup_wizard(self, initial_state: dict, index_options: list[dict]) -> dict | None:
        """Show a modal setup dialog and return the selected values."""
        from tkinter import filedialog

        self.show_wizard_step("Setup")
        dialog = tk.Toplevel(self.root)
        dialog.title("Axiom Setup Wizard")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.geometry("760x620")
        dialog.minsize(680, 520)
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(0, weight=1)

        notebook = ttk.Notebook(dialog)
        notebook.grid(row=0, column=0, sticky="nsew", padx=UI_SPACING["m"], pady=UI_SPACING["m"])

        source_tab = ttk.Frame(notebook, padding=UI_SPACING["m"])
        ingest_tab = ttk.Frame(notebook, padding=UI_SPACING["m"])
        provider_tab = ttk.Frame(notebook, padding=UI_SPACING["m"])
        keys_tab = ttk.Frame(notebook, padding=UI_SPACING["m"])
        mode_tab = ttk.Frame(notebook, padding=UI_SPACING["m"])
        confirm_tab = ttk.Frame(notebook, padding=UI_SPACING["m"])
        for tab, title in (
            (source_tab, "1. Source"),
            (ingest_tab, "2. Ingestion"),
            (provider_tab, "3. Providers"),
            (keys_tab, "4. API Keys"),
            (mode_tab, "5. Mode"),
            (confirm_tab, "6. Confirm"),
        ):
            notebook.add(tab, text=title)
            tab.columnconfigure(1, weight=1)

        file_var = tk.StringVar(value=str(initial_state.get("file_path", "") or ""))
        index_label_map = {
            str(row.get("label", "") or row.get("index_id", "")): str(row.get("path", "") or "")
            for row in index_options or []
        }
        selected_index_label = ""
        initial_index_path = str(initial_state.get("selected_index_path", "") or "")
        for label, path in index_label_map.items():
            if path == initial_index_path:
                selected_index_label = label
                break
        index_var = tk.StringVar(value=selected_index_label)
        recommendation = dict(initial_state.get("wizard_recommendation") or {})
        chunk_size_var = tk.StringVar(value=str(initial_state.get("chunk_size", recommendation.get("chunk_size", 1000))))
        overlap_var = tk.StringVar(value=str(initial_state.get("chunk_overlap", recommendation.get("chunk_overlap", 100))))
        digest_var = tk.BooleanVar(value=bool(initial_state.get("build_digest_index", True)))
        comprehension_var = tk.BooleanVar(value=bool(initial_state.get("build_comprehension_index", False)))
        comprehension_depth_var = tk.StringVar(value=str(initial_state.get("comprehension_extraction_depth", "Standard")))
        prefer_comprehension_var = tk.BooleanVar(value=bool(initial_state.get("prefer_comprehension_index", True)))
        llm_provider_var = tk.StringVar(value=str(initial_state.get("llm_provider", "") or "mock"))
        llm_model_var = tk.StringVar(value=str(initial_state.get("llm_model", "") or ""))
        embedding_provider_var = tk.StringVar(value=str(initial_state.get("embedding_provider", "") or "mock"))
        embedding_model_var = tk.StringVar(value=str(initial_state.get("embedding_model", "") or ""))
        retrieval_k_var = tk.StringVar(value=str(initial_state.get("retrieval_k", recommendation.get("retrieval_k", 25))))
        top_k_var = tk.StringVar(value=str(initial_state.get("top_k", recommendation.get("final_k", 5))))
        mmr_lambda_var = tk.StringVar(value=str(initial_state.get("mmr_lambda", recommendation.get("mmr_lambda", 0.5))))
        retrieval_mode_var = tk.StringVar(value=str(initial_state.get("retrieval_mode", recommendation.get("retrieval_mode", "flat")) or "flat"))
        agentic_mode_var = tk.BooleanVar(value=bool(initial_state.get("agentic_mode", recommendation.get("agentic_mode", False))))
        agentic_iterations_var = tk.StringVar(
            value=str(initial_state.get("agentic_max_iterations", recommendation.get("agentic_max_iterations", 2)))
        )
        output_style_var = tk.StringVar(value=str(initial_state.get("output_style", "") or "Default answer"))
        reranker_var = tk.BooleanVar(value=bool(initial_state.get("use_reranker", recommendation.get("use_reranker", False))))
        openai_key_var = tk.StringVar(value=str(self._settings_data.get("api_key_openai", "") or ""))
        anthropic_key_var = tk.StringVar(value=str(self._settings_data.get("api_key_anthropic", "") or ""))
        google_key_var = tk.StringVar(value=str(self._settings_data.get("api_key_google", "") or ""))
        xai_key_var = tk.StringVar(value=str(self._settings_data.get("api_key_xai", "") or ""))
        mode_var = tk.StringVar(value=str(initial_state.get("mode_preset", "Q&A") or "Q&A"))
        deepread_var = tk.BooleanVar(value=bool(initial_state.get("deepread_mode", self._settings_data.get("deepread_mode", False))))
        backend_var = tk.StringVar(value=str(self._settings_data.get("vector_db_type", "json") or "json"))
        recommendation_text_var = tk.StringVar(value="")

        ttk.Label(source_tab, text="New source file", style="Caption.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Entry(source_tab, textvariable=file_var).grid(row=0, column=1, sticky="ew", padx=(UI_SPACING["xs"], 0))
        ttk.Button(
            source_tab,
            text="Browse…",
            command=lambda: file_var.set(
                filedialog.askopenfilename(title="Select source file") or file_var.get()
            ),
        ).grid(row=0, column=2, padx=(UI_SPACING["xs"], 0))
        ttk.Label(source_tab, text="Or restore existing index", style="Caption.TLabel").grid(row=1, column=0, sticky="w", pady=(UI_SPACING["s"], 0))
        ttk.Combobox(
            source_tab,
            textvariable=index_var,
            values=list(index_label_map.keys()),
            state="readonly",
            width=70,
        ).grid(row=1, column=1, columnspan=2, sticky="ew", padx=(UI_SPACING["xs"], 0), pady=(UI_SPACING["s"], 0))

        recommendation_host = ttk.Frame(ingest_tab, style="Card.Flat.TFrame")
        recommendation_host.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, UI_SPACING["s"]))
        recommendation_host.columnconfigure(0, weight=1)
        ttk.Label(
            recommendation_host,
            textvariable=recommendation_text_var,
            style="Caption.TLabel",
            wraplength=520,
            justify="left",
        ).grid(row=0, column=0, sticky="w")
        ttk.Button(
            recommendation_host,
            text="Apply Recommendation",
            style="Secondary.TButton",
            command=lambda: _apply_recommendation(_current_recommendation()),
        ).grid(row=0, column=1, padx=(UI_SPACING["s"], 0))

        ttk.Label(ingest_tab, text="Chunk size", style="Caption.TLabel").grid(row=1, column=0, sticky="w")
        ttk.Entry(ingest_tab, textvariable=chunk_size_var).grid(row=1, column=1, sticky="ew", padx=(UI_SPACING["xs"], 0))
        ttk.Label(ingest_tab, text="Chunk overlap", style="Caption.TLabel").grid(row=2, column=0, sticky="w", pady=(UI_SPACING["s"], 0))
        ttk.Entry(ingest_tab, textvariable=overlap_var).grid(row=2, column=1, sticky="ew", padx=(UI_SPACING["xs"], 0), pady=(UI_SPACING["s"], 0))
        ttk.Checkbutton(ingest_tab, text="Build digest index", variable=digest_var).grid(row=3, column=0, columnspan=2, sticky="w", pady=(UI_SPACING["s"], 0))
        ttk.Checkbutton(ingest_tab, text="Build comprehension index", variable=comprehension_var).grid(row=4, column=0, columnspan=2, sticky="w", pady=(UI_SPACING["xs"], 0))
        ttk.Label(ingest_tab, text="Comprehension depth", style="Caption.TLabel").grid(row=5, column=0, sticky="w", pady=(UI_SPACING["s"], 0))
        ttk.Combobox(
            ingest_tab,
            textvariable=comprehension_depth_var,
            values=["Standard", "Deep", "Exhaustive"],
            state="readonly",
        ).grid(row=5, column=1, sticky="ew", padx=(UI_SPACING["xs"], 0), pady=(UI_SPACING["s"], 0))
        ttk.Checkbutton(ingest_tab, text="Prefer comprehension index", variable=prefer_comprehension_var).grid(row=6, column=0, columnspan=2, sticky="w", pady=(UI_SPACING["xs"], 0))
        ttk.Checkbutton(ingest_tab, text="Enable deepread (forces structure-aware ingestion)", variable=deepread_var).grid(row=7, column=0, columnspan=2, sticky="w", pady=(UI_SPACING["xs"], 0))
        ttk.Checkbutton(ingest_tab, text="Use reranker", variable=reranker_var).grid(row=8, column=0, columnspan=2, sticky="w", pady=(UI_SPACING["xs"], 0))
        ttk.Label(ingest_tab, text="Vector backend", style="Caption.TLabel").grid(row=9, column=0, sticky="w", pady=(UI_SPACING["s"], 0))
        ttk.Combobox(
            ingest_tab,
            textvariable=backend_var,
            values=["json", "chroma", "weaviate"],
            state="readonly",
        ).grid(row=9, column=1, sticky="ew", padx=(UI_SPACING["xs"], 0), pady=(UI_SPACING["s"], 0))

        provider_values = ["anthropic", "openai", "google", "xai", "local_lm_studio", "local_gguf", "mock"]
        embedding_values = ["voyage", "openai", "google", "local_huggingface", "local_sentence_transformers", "mock"]
        ttk.Label(provider_tab, text="LLM provider", style="Caption.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Combobox(provider_tab, textvariable=llm_provider_var, values=provider_values, state="readonly").grid(row=0, column=1, sticky="ew", padx=(UI_SPACING["xs"], 0))
        ttk.Label(provider_tab, text="LLM model", style="Caption.TLabel").grid(row=1, column=0, sticky="w", pady=(UI_SPACING["s"], 0))
        ttk.Entry(provider_tab, textvariable=llm_model_var).grid(row=1, column=1, sticky="ew", padx=(UI_SPACING["xs"], 0), pady=(UI_SPACING["s"], 0))
        ttk.Label(provider_tab, text="Embedding provider", style="Caption.TLabel").grid(row=2, column=0, sticky="w", pady=(UI_SPACING["s"], 0))
        ttk.Combobox(provider_tab, textvariable=embedding_provider_var, values=embedding_values, state="readonly").grid(row=2, column=1, sticky="ew", padx=(UI_SPACING["xs"], 0), pady=(UI_SPACING["s"], 0))
        ttk.Label(provider_tab, text="Embedding model", style="Caption.TLabel").grid(row=3, column=0, sticky="w", pady=(UI_SPACING["s"], 0))
        ttk.Entry(provider_tab, textvariable=embedding_model_var).grid(row=3, column=1, sticky="ew", padx=(UI_SPACING["xs"], 0), pady=(UI_SPACING["s"], 0))
        ttk.Label(provider_tab, text="Retrieval K", style="Caption.TLabel").grid(row=4, column=0, sticky="w", pady=(UI_SPACING["s"], 0))
        ttk.Entry(provider_tab, textvariable=retrieval_k_var).grid(row=4, column=1, sticky="ew", padx=(UI_SPACING["xs"], 0), pady=(UI_SPACING["s"], 0))
        ttk.Label(provider_tab, text="Final K", style="Caption.TLabel").grid(row=5, column=0, sticky="w", pady=(UI_SPACING["s"], 0))
        ttk.Entry(provider_tab, textvariable=top_k_var).grid(row=5, column=1, sticky="ew", padx=(UI_SPACING["xs"], 0), pady=(UI_SPACING["s"], 0))
        ttk.Label(provider_tab, text="MMR lambda", style="Caption.TLabel").grid(row=6, column=0, sticky="w", pady=(UI_SPACING["s"], 0))
        ttk.Entry(provider_tab, textvariable=mmr_lambda_var).grid(row=6, column=1, sticky="ew", padx=(UI_SPACING["xs"], 0), pady=(UI_SPACING["s"], 0))
        ttk.Label(provider_tab, text="Retrieval mode", style="Caption.TLabel").grid(row=7, column=0, sticky="w", pady=(UI_SPACING["s"], 0))
        ttk.Combobox(provider_tab, textvariable=retrieval_mode_var, values=["flat", "hierarchical"], state="readonly").grid(row=7, column=1, sticky="ew", padx=(UI_SPACING["xs"], 0), pady=(UI_SPACING["s"], 0))
        ttk.Checkbutton(provider_tab, text="Agentic retrieval", variable=agentic_mode_var).grid(row=8, column=0, columnspan=2, sticky="w", pady=(UI_SPACING["s"], 0))
        ttk.Label(provider_tab, text="Agentic iterations", style="Caption.TLabel").grid(row=9, column=0, sticky="w", pady=(UI_SPACING["s"], 0))
        ttk.Entry(provider_tab, textvariable=agentic_iterations_var).grid(row=9, column=1, sticky="ew", padx=(UI_SPACING["xs"], 0), pady=(UI_SPACING["s"], 0))
        ttk.Label(provider_tab, text="Output style", style="Caption.TLabel").grid(row=10, column=0, sticky="w", pady=(UI_SPACING["s"], 0))
        ttk.Combobox(
            provider_tab,
            textvariable=output_style_var,
            values=[
                "Default answer",
                "Detailed answer",
                "Brief / exec summary",
                "Script / talk track",
                "Structured report",
                "Blinkist-style summary",
            ],
            state="readonly",
        ).grid(row=10, column=1, sticky="ew", padx=(UI_SPACING["xs"], 0), pady=(UI_SPACING["s"], 0))

        for row, (label, var) in enumerate(
            (
                ("OpenAI key", openai_key_var),
                ("Anthropic key", anthropic_key_var),
                ("Google key", google_key_var),
                ("xAI key", xai_key_var),
            )
        ):
            ttk.Label(keys_tab, text=label, style="Caption.TLabel").grid(row=row, column=0, sticky="w", pady=((UI_SPACING["s"] if row else 0), 0))
            ttk.Entry(keys_tab, textvariable=var, show="*").grid(row=row, column=1, sticky="ew", padx=(UI_SPACING["xs"], 0), pady=((UI_SPACING["s"] if row else 0), 0))

        ttk.Label(mode_tab, text="Mode preset", style="Caption.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Combobox(
            mode_tab,
            textvariable=mode_var,
            values=["Q&A", "Book summary", "Tutor", "Research", "Evidence Pack"],
            state="readonly",
        ).grid(row=0, column=1, sticky="ew", padx=(UI_SPACING["xs"], 0))

        confirm_text = tk.Text(
            confirm_tab,
            wrap=tk.WORD,
            height=18,
            font=self._fonts["code"],
            bg=self._palette.get("input_bg", "#07101A"),
            fg=self._palette["text"],
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
        )
        confirm_text.grid(row=0, column=0, columnspan=2, sticky="nsew")
        confirm_tab.rowconfigure(0, weight=1)

        def _current_recommendation() -> dict:
            return recommend_auto_settings(
                file_path=file_var.get().strip() or None,
                index_path=index_label_map.get(index_var.get().strip(), "") or None,
            )

        def _apply_recommendation(rec: dict) -> None:
            chunk_size_var.set(str(rec.get("chunk_size", chunk_size_var.get())))
            overlap_var.set(str(rec.get("chunk_overlap", overlap_var.get())))
            digest_var.set(bool(rec.get("build_digest_index", digest_var.get())))
            comprehension_var.set(bool(rec.get("build_comprehension_index", comprehension_var.get())))
            comprehension_depth_var.set(
                str(rec.get("comprehension_extraction_depth", comprehension_depth_var.get()) or "Standard")
            )
            prefer_comprehension_var.set(
                bool(rec.get("prefer_comprehension_index", prefer_comprehension_var.get()))
            )
            retrieval_k_var.set(str(rec.get("retrieval_k", retrieval_k_var.get())))
            top_k_var.set(str(rec.get("final_k", top_k_var.get())))
            mmr_lambda_var.set(str(rec.get("mmr_lambda", mmr_lambda_var.get())))
            retrieval_mode_var.set(str(rec.get("retrieval_mode", retrieval_mode_var.get()) or "flat"))
            agentic_mode_var.set(bool(rec.get("agentic_mode", agentic_mode_var.get())))
            agentic_iterations_var.set(str(rec.get("agentic_max_iterations", agentic_iterations_var.get())))
            reranker_var.set(bool(rec.get("use_reranker", reranker_var.get())))
            if bool(rec.get("deepread_mode")):
                deepread_var.set(True)

        def _refresh_summary(*_args) -> None:
            current_recommendation = _current_recommendation()
            recommendation_text_var.set(describe_auto_recommendation(current_recommendation))
            summary = {
                "file_path": file_var.get().strip(),
                "selected_index_path": index_label_map.get(index_var.get().strip(), ""),
                "chunk_size": chunk_size_var.get().strip(),
                "chunk_overlap": overlap_var.get().strip(),
                "retrieval_k": retrieval_k_var.get().strip(),
                "top_k": top_k_var.get().strip(),
                "mmr_lambda": mmr_lambda_var.get().strip(),
                "retrieval_mode": retrieval_mode_var.get().strip(),
                "agentic_mode": bool(agentic_mode_var.get()),
                "agentic_max_iterations": agentic_iterations_var.get().strip(),
                "use_reranker": bool(reranker_var.get()),
                "llm_provider": llm_provider_var.get().strip(),
                "llm_model": llm_model_var.get().strip(),
                "embedding_provider": embedding_provider_var.get().strip(),
                "embedding_model": embedding_model_var.get().strip(),
                "mode_preset": mode_var.get().strip(),
                "output_style": output_style_var.get().strip(),
                "vector_db_type": backend_var.get().strip(),
                "deepread_mode": bool(deepread_var.get()),
                "cost_estimate": estimate_setup_cost(
                    current_recommendation,
                    llm_provider=llm_provider_var.get().strip(),
                    embedding_provider=embedding_provider_var.get().strip(),
                ),
            }
            confirm_text.configure(state="normal")
            confirm_text.delete("1.0", "end")
            confirm_text.insert("1.0", self._format_payload(summary))
            confirm_text.configure(state="disabled")

        for var in (
            file_var,
            index_var,
            chunk_size_var,
            overlap_var,
            retrieval_k_var,
            top_k_var,
            mmr_lambda_var,
            retrieval_mode_var,
            agentic_mode_var,
            agentic_iterations_var,
            output_style_var,
            reranker_var,
            llm_provider_var,
            llm_model_var,
            embedding_provider_var,
            embedding_model_var,
            mode_var,
            backend_var,
            deepread_var,
        ):
            try:
                var.trace_add("write", _refresh_summary)
            except Exception:
                pass
        _refresh_summary()

        result: dict | None = None

        footer = ttk.Frame(dialog, padding=(UI_SPACING["m"], 0, UI_SPACING["m"], UI_SPACING["m"]))
        footer.grid(row=1, column=0, sticky="ew")

        def _finish() -> None:
            nonlocal result
            selected_output_style = output_style_var.get().strip()
            if mode_var.get().strip() == "Book summary" and selected_output_style in {"", "Default answer"}:
                selected_output_style = "Blinkist-style summary"
            result = {
                "file_path": file_var.get().strip(),
                "selected_index_path": index_label_map.get(index_var.get().strip(), ""),
                "chunk_size": chunk_size_var.get().strip(),
                "chunk_overlap": overlap_var.get().strip(),
                "build_digest_index": digest_var.get(),
                "build_comprehension_index": comprehension_var.get(),
                "comprehension_extraction_depth": comprehension_depth_var.get().strip(),
                "prefer_comprehension_index": prefer_comprehension_var.get(),
                "llm_provider": llm_provider_var.get().strip(),
                "llm_model": llm_model_var.get().strip(),
                "embedding_provider": embedding_provider_var.get().strip(),
                "embedding_model": embedding_model_var.get().strip(),
                "retrieval_k": retrieval_k_var.get().strip(),
                "top_k": top_k_var.get().strip(),
                "mmr_lambda": mmr_lambda_var.get().strip(),
                "retrieval_mode": retrieval_mode_var.get().strip(),
                "agentic_mode": agentic_mode_var.get(),
                "agentic_max_iterations": agentic_iterations_var.get().strip(),
                "output_style": selected_output_style,
                "use_reranker": reranker_var.get(),
                "api_key_openai": openai_key_var.get().strip(),
                "api_key_anthropic": anthropic_key_var.get().strip(),
                "api_key_google": google_key_var.get().strip(),
                "api_key_xai": xai_key_var.get().strip(),
                "mode_preset": mode_var.get().strip(),
                "deepread_mode": deepread_var.get(),
                "vector_db_type": backend_var.get().strip(),
            }
            dialog.destroy()

        ttk.Button(footer, text="Cancel", style="Secondary.TButton", command=dialog.destroy).pack(side="right")
        ttk.Button(footer, text="Finish Setup", style="Primary.TButton", command=_finish).pack(
            side="right",
            padx=(0, UI_SPACING["xs"]),
        )

        dialog.wait_window()
        return result

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

    def _load_sidebar_logo(self, max_dim: int = 120) -> tk.PhotoImage | None:
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
                w = max(1, int(logo.width()))
                h = max(1, int(logo.height()))
                ds = max(1, (max(w, h) + max_dim - 1) // max_dim)
                if ds > 1:
                    logo = logo.subsample(ds, ds)
                return logo
            except Exception:
                pass
        return None
