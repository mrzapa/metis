import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import threading
import os
import sys
import time
import json
import subprocess
import importlib.util
import re
import hashlib
import sqlite3
from datetime import datetime
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

# --- Libraries check is done inside the class to prevent instant crash ---
# Required: pip install langchain langchain-community langchain-openai langchain-anthropic langchain-google-genai langchain-cohere langchain-text-splitters chromadb beautifulsoup4 tiktoken

RAW_COLLECTION_NAME = "rag_collection"
DIGEST_COLLECTION_NAME = "rag_digest_collection"
DIGEST_WINDOW_MIN = 10
DIGEST_WINDOW_MAX = 20
DIGEST_WINDOW_TARGET = 15
MINI_DIGEST_BOOST_MULTIPLIER = 3
MINI_DIGEST_MIN_POOL = 40
MAX_DIGEST_NODES = 60
MAX_RAW_CHUNKS = 200
MAX_PACKED_CONTEXT_CHARS = 60000
TOKENS_TO_CHARS_RATIO = 4
CONTEXT_SAFETY_MARGIN_TOKENS = 512
MAX_GROUP_DOCS = 2
MIN_UNIQUE_INCIDENTS = 8
MAX_UNIQUE_INCIDENTS = 12
AGENTIC_MAX_ITERATIONS_HARD_CAP = 12
MONTH_INDEX_TO_LABEL = {
    1: "Jan",
    2: "Feb",
    3: "Mar",
    4: "Apr",
    5: "May",
    6: "Jun",
    7: "Jul",
    8: "Aug",
    9: "Sep",
    10: "Oct",
    11: "Nov",
    12: "Dec",
}
MONTH_NAME_TO_INDEX = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

class AgenticRAGApp:
    def __init__(self, root):
        import langchain

        if not hasattr(langchain, "llm_cache"):
            langchain.llm_cache = None
            if hasattr(langchain, "globals") and hasattr(
                langchain.globals, "set_llm_cache"
            ):
                langchain.globals.set_llm_cache(None)

        if not hasattr(langchain, "verbose"):
            langchain.verbose = False
            if hasattr(langchain, "globals") and hasattr(
                langchain.globals, "set_verbose"
            ):
                langchain.globals.set_verbose(False)

        if not hasattr(langchain, "debug"):
            langchain.debug = False
            if hasattr(langchain, "globals") and hasattr(
                langchain.globals, "set_debug"
            ):
                langchain.globals.set_debug(False)

        self.root = root
        self.root.title("Agentic RAG: LangChain + Chroma/Weaviate + Cohere")
        self.root.geometry("1200x900")
        self.main_thread = threading.current_thread()
        self.config_path = os.path.join(os.getcwd(), "agentic_rag_config.json")
        self.default_system_instructions = (
            "You are an expert analyst assistant. Use ONLY the provided context for factual claims. "
            "Never ask for details already present in the retrieved context. "
            "Omit unsupported claims; deepen supported ones; do not ask for more docs or missing info; "
            "do not use placeholders. If evidence is thin, you may add one short 'Scope:' note at the "
            "top describing limitations. Every paragraph with factual content must end with one or more "
            "[Chunk N] citations. Use the exact [Chunk N] format only; do not use alternative formats "
            "(e.g., (1), [1], or inline URLs). Example: \"The policy was revised in 2023.\" [Chunk 4] "
            "For Script / talk track and Structured report styles, include at least one short verbatim "
            "quote (<=25 words) per major section with a [Chunk N] citation. "
            "Coverage rule: if N items are requested, output N items, omitting unsupported claims."
        )
        self.verbose_system_instructions = (
            "You are an expert analyst assistant. Use ONLY the provided context for factual claims. "
            "Never ask for details already present in the retrieved context. "
            "Omit unsupported claims; deepen supported ones; do not ask the user for missing info; "
            "do not use placeholders. Every paragraph with factual content must end with one or more "
            "[Chunk N] citations. Use the exact [Chunk N] format only; do not use alternative formats "
            "(e.g., (1), [1], or inline URLs). Example: \"The policy was revised in 2023.\" [Chunk 4] "
            "For Script / talk track and Structured report styles, include at least one short verbatim "
            "quote (<=25 words) per major section with a [Chunk N] citation. "
            "Provide a concise summary, cite evidence from the context, list key points, "
            "and explicitly note uncertainties or gaps."
        )

        # --- State Variables ---
        self.api_keys = {
            "openai": tk.StringVar(),
            "anthropic": tk.StringVar(),
            "google": tk.StringVar(),
            "cohere": tk.StringVar(),
            "weaviate_url": tk.StringVar(value="http://localhost:8080"),
            "weaviate_key": tk.StringVar(),
            "mistral": tk.StringVar(),
            "groq": tk.StringVar(),
            "azure_openai": tk.StringVar(),
            "together": tk.StringVar(),
            "voyage": tk.StringVar(),
            "huggingface": tk.StringVar(),
            "fireworks": tk.StringVar(),
            "perplexity": tk.StringVar(),
        }

        self.llm_provider = tk.StringVar(value="anthropic")
        self.embedding_provider = tk.StringVar(value="voyage")
        self.vector_db_type = tk.StringVar(value="chroma")
        self.local_llm_url = tk.StringVar(value="http://localhost:1234/v1")
        self.chunk_size = tk.IntVar(value=1000)
        self.chunk_overlap = tk.IntVar(value=200)
        self.build_digest_index = tk.BooleanVar(value=True)

        self.llm_model = tk.StringVar(value="claude-opus-4-6")
        self.llm_model_custom = tk.StringVar()
        self.embedding_model = tk.StringVar(value="voyage-4-large")
        self.embedding_model_custom = tk.StringVar()
        self.llm_temperature = tk.DoubleVar(value=0.0)
        self.llm_max_tokens = tk.IntVar(value=1024)
        self.force_embedding_compat = tk.BooleanVar(value=False)
        self.verbose_mode = tk.BooleanVar(value=False)
        self.system_instructions = tk.StringVar(
            value=self.default_system_instructions
        )
        self.output_style_options = [
            "Default answer",
            "Detailed answer",
            "Brief / exec summary",
            "Script / talk track",
            "Structured report",
        ]
        self.output_style = tk.StringVar(value="Default answer")
        self.retrieval_k = tk.IntVar(value=25)
        self.final_k = tk.IntVar(value=5)
        self.fallback_final_k = tk.IntVar(value=self.final_k.get())
        self.search_type = tk.StringVar(value="similarity")
        self.mmr_lambda = tk.DoubleVar(value=0.5)
        self.agentic_mode = tk.BooleanVar(value=False)
        self.agentic_max_iterations = tk.IntVar(value=2)
        self.show_retrieved_context = tk.BooleanVar(value=False)
        self.use_reranker = tk.BooleanVar(value=True)
        self.use_sub_queries = tk.BooleanVar(value=True)
        self.subquery_max_docs = tk.IntVar(value=200)

        self.vector_store = None
        self.index_embedding_signature = ""
        self.chat_history = []
        self.chat_history_max_turns = 6
        self.selected_file = None
        self.last_answer = ""
        self.dependency_prompted = False
        self.existing_index_var = tk.StringVar(value="(default)")
        self.existing_index_paths = {}
        self.selected_index_path = None
        self.selected_collection_name = RAW_COLLECTION_NAME
        self.lexical_db_path = None
        self.lexical_db_available = False

        self.setup_ui()
        self.load_config()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self._sync_model_options()
        self.vector_db_type.trace_add("write", self._on_vector_db_type_change)

        # Defer dependency check slightly to allow UI to render first
        self.root.after(100, self.check_dependencies)

    def _get_required_packages(self):
        return [
            "langchain",
            "langchain-community",
            "langchain-openai",
            "langchain-anthropic",
            "langchain-google-genai",
            "langchain-cohere",
            "langchain-voyageai",
            "langchain-chroma",
            "langchain-weaviate",
            "langchain-text-splitters",
            "chromadb",
            "beautifulsoup4",
            "tiktoken",
            "weaviate-client",
        ]

    def setup_ui(self):
        # Styles
        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Bold.TLabel", font=("Segoe UI", 10, "bold"))
        style.configure("Header.TLabel", font=("Segoe UI", 12, "bold"))
        style.configure("Status.TLabel", font=("Segoe UI", 9))

        # Tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 1. Configuration Tab
        self.tab_config = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_config, text="1. Configuration")
        self.build_config_tab()

        # 2. Ingestion Tab
        self.tab_ingest = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_ingest, text="2. Data Ingestion")
        self.build_ingest_tab()

        # 3. Chat Tab
        self.tab_chat = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_chat, text="3. Agentic Chat")
        self.build_chat_tab()

        # Logs
        log_frame = ttk.LabelFrame(self.root, text="System Logs")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.log_area = scrolledtext.ScrolledText(
            log_frame, height=8, state="disabled", font=("Consolas", 9)
        )
        self.log_area.pack(fill=tk.BOTH, expand=True)

        # Status Bar
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(
            self.root, textvariable=self.status_var, style="Status.TLabel", anchor="w"
        )
        status_bar.pack(fill="x", padx=10, pady=(0, 8))

    def _run_on_ui(self, func, *args, **kwargs):
        if threading.current_thread() == self.main_thread:
            func(*args, **kwargs)
        else:
            self.root.after(0, lambda: func(*args, **kwargs))

    def _get_llm_model_options(self, provider):
        options = {
            "openai": ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini", "custom"],
            "anthropic": [
                "claude-opus-4-6",
                "claude-3-5-sonnet-20240620",
                "claude-3-5-haiku-20241022",
                "custom",
            ],
            "google": ["gemini-1.5-flash", "gemini-1.5-pro", "custom"],
            "local_lm_studio": ["custom"],
        }
        return options.get(provider, ["custom"])

    def _get_embedding_model_options(self, provider):
        options = {
            "openai": ["text-embedding-3-small", "text-embedding-3-large", "custom"],
            "google": ["models/embedding-001", "custom"],
            "local_huggingface": ["all-MiniLM-L6-v2", "custom"],
            "voyage": [
                "voyage-4-large",
                "voyage-4-lite",
                "voyage-4-nano",
                "voyage-4",
                "custom",
            ],
        }
        return options.get(provider, ["custom"])

    def _sync_model_options(self):
        llm_provider = self.llm_provider.get()
        emb_provider = self.embedding_provider.get()

        llm_options = self._get_llm_model_options(llm_provider)
        emb_options = self._get_embedding_model_options(emb_provider)

        self.cb_llm_model["values"] = llm_options
        self.cb_emb_model["values"] = emb_options

        if self.llm_model.get() not in llm_options:
            self.llm_model.set(llm_options[0])
        if self.embedding_model.get() not in emb_options:
            self.embedding_model.set(emb_options[0])

        self._toggle_custom_entries()

    def _toggle_custom_entries(self):
        llm_custom_enabled = self.llm_model.get() == "custom"
        emb_custom_enabled = self.embedding_model.get() == "custom"
        hf_enabled = self.embedding_provider.get() == "local_huggingface"

        self.llm_model_custom_entry.config(
            state="normal" if llm_custom_enabled else "disabled"
        )
        self.embedding_model_custom_entry.config(
            state="normal" if emb_custom_enabled else "disabled"
        )
        self.btn_browse_hf_model.config(state="normal" if hf_enabled else "disabled")

    def _on_llm_provider_change(self, event=None):
        self._sync_model_options()

    def _on_embedding_provider_change(self, event=None):
        self._sync_model_options()
        self._refresh_compatibility_warning()

    def _on_llm_model_change(self, event=None):
        self._toggle_custom_entries()

    def _on_embedding_model_change(self, event=None):
        self._toggle_custom_entries()
        self._refresh_compatibility_warning()

    def _on_instructions_change(self, event=None):
        self.system_instructions.set(self.instructions_box.get("1.0", tk.END).strip())

    def _on_verbose_mode_toggle(self):
        if self.verbose_mode.get():
            self._apply_instruction_template(self.verbose_system_instructions)
        else:
            self._apply_instruction_template(self.default_system_instructions)

    def _apply_instruction_template(self, template):
        self.system_instructions.set(template)
        self._run_on_ui(self._refresh_instructions_box)

    def _current_embedding_signature(self):
        provider = self.embedding_provider.get()
        try:
            model = self._resolve_embedding_model()
        except ValueError:
            model = ""
        return f"{provider}:{model}".strip(":")

    def _refresh_compatibility_warning(self):
        if not self.index_embedding_signature:
            self.compat_warning.config(text="")
            return
        current_signature = self._current_embedding_signature()
        if not current_signature or current_signature == self.index_embedding_signature:
            self.compat_warning.config(text="")
            return
        message = (
            "Embedding mismatch: this index was built with "
            f"{self.index_embedding_signature}. Re-embed or use a dual-index "
            "migration. Force to bypass warning."
        )
        self.compat_warning.config(text=message)

    def browse_hf_model(self):
        path = filedialog.askdirectory()
        if path:
            self.embedding_model.set("custom")
            self.embedding_model_custom.set(path)
            self._toggle_custom_entries()
            self._refresh_compatibility_warning()

    def load_config(self):
        if not os.path.exists(self.config_path):
            return
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return

        for key, var in self.api_keys.items():
            if key in data.get("api_keys", {}):
                var.set(data["api_keys"][key])

        self.llm_provider.set(data.get("llm_provider", self.llm_provider.get()))
        self.embedding_provider.set(
            data.get("embedding_provider", self.embedding_provider.get())
        )
        self.vector_db_type.set(data.get("vector_db_type", self.vector_db_type.get()))
        self.local_llm_url.set(data.get("local_llm_url", self.local_llm_url.get()))
        self.chunk_size.set(data.get("chunk_size", self.chunk_size.get()))
        self.chunk_overlap.set(data.get("chunk_overlap", self.chunk_overlap.get()))
        self.build_digest_index.set(
            bool(data.get("build_digest_index", self.build_digest_index.get()))
        )
        self.llm_model.set(data.get("llm_model", self.llm_model.get()))
        self.llm_model_custom.set(data.get("llm_model_custom", self.llm_model_custom.get()))
        self.embedding_model.set(data.get("embedding_model", self.embedding_model.get()))
        self.embedding_model_custom.set(
            data.get("embedding_model_custom", self.embedding_model_custom.get())
        )
        self.llm_temperature.set(data.get("llm_temperature", self.llm_temperature.get()))
        self.llm_max_tokens.set(data.get("llm_max_tokens", self.llm_max_tokens.get()))
        self.force_embedding_compat.set(
            data.get("force_embedding_compat", self.force_embedding_compat.get())
        )
        self.retrieval_k.set(data.get("retrieval_k", self.retrieval_k.get()))
        self.final_k.set(data.get("final_k", self.final_k.get()))
        self.search_type.set(data.get("search_type", self.search_type.get()))
        self.mmr_lambda.set(data.get("mmr_lambda", self.mmr_lambda.get()))
        # New config fields: agentic_mode, agentic_max_iterations, show_retrieved_context
        self.agentic_mode.set(data.get("agentic_mode", self.agentic_mode.get()))
        try:
            max_iterations = int(
                data.get("agentic_max_iterations", self.agentic_max_iterations.get())
            )
        except (TypeError, ValueError):
            max_iterations = self.agentic_max_iterations.get()
        clamped_max_iterations = max(
            1, min(AGENTIC_MAX_ITERATIONS_HARD_CAP, max_iterations)
        )
        self.agentic_max_iterations.set(clamped_max_iterations)
        self.show_retrieved_context.set(
            data.get("show_retrieved_context", self.show_retrieved_context.get())
        )
        self.use_reranker.set(data.get("use_reranker", self.use_reranker.get()))
        self.use_sub_queries.set(
            bool(data.get("use_sub_queries", self.use_sub_queries.get()))
        )
        try:
            subquery_max_docs = int(
                data.get("subquery_max_docs", self.subquery_max_docs.get())
            )
        except (TypeError, ValueError):
            subquery_max_docs = self.subquery_max_docs.get()
        self.subquery_max_docs.set(max(10, min(500, subquery_max_docs)))
        try:
            fallback_final_k = int(
                data.get("fallback_final_k", self.fallback_final_k.get())
            )
        except (TypeError, ValueError):
            fallback_final_k = self.fallback_final_k.get()
        self.fallback_final_k.set(max(1, fallback_final_k))
        self.index_embedding_signature = data.get(
            "index_embedding_signature", self.index_embedding_signature
        )
        self.selected_index_path = data.get(
            "selected_index_path", self.selected_index_path
        )
        self.selected_collection_name = data.get(
            "selected_collection_name", self.selected_collection_name
        )
        output_style = data.get("output_style", self.output_style.get())
        if output_style not in self.output_style_options:
            output_style = "Default answer"
        self.output_style.set(output_style)

        instructions = data.get("system_instructions", self.system_instructions.get())
        self.system_instructions.set(instructions or self.default_system_instructions)
        self.instructions_box.delete("1.0", tk.END)
        self.instructions_box.insert(tk.END, self.system_instructions.get())

        self._sync_model_options()
        self._refresh_compatibility_warning()
        self._refresh_existing_indexes()
        if self.selected_index_path:
            selection_label = self._format_index_label(
                self.selected_index_path, self.selected_collection_name
            )
            if selection_label in self.existing_index_paths:
                self.existing_index_var.set(selection_label)

    def save_config(self):
        try:
            subquery_max_docs = int(self.subquery_max_docs.get())
        except (TypeError, ValueError):
            subquery_max_docs = self.subquery_max_docs.get()
        try:
            max_iterations = int(self.agentic_max_iterations.get())
        except (TypeError, ValueError):
            max_iterations = self.agentic_max_iterations.get()
        max_iterations = max(1, min(AGENTIC_MAX_ITERATIONS_HARD_CAP, max_iterations))
        self.agentic_max_iterations.set(max_iterations)
        data = {
            "api_keys": {key: var.get() for key, var in self.api_keys.items()},
            "llm_provider": self.llm_provider.get(),
            "embedding_provider": self.embedding_provider.get(),
            "vector_db_type": self.vector_db_type.get(),
            "local_llm_url": self.local_llm_url.get(),
            "chunk_size": self.chunk_size.get(),
            "chunk_overlap": self.chunk_overlap.get(),
            "build_digest_index": self.build_digest_index.get(),
            "llm_model": self.llm_model.get(),
            "llm_model_custom": self.llm_model_custom.get(),
            "embedding_model": self.embedding_model.get(),
            "embedding_model_custom": self.embedding_model_custom.get(),
            "llm_temperature": self.llm_temperature.get(),
            "llm_max_tokens": self.llm_max_tokens.get(),
            "system_instructions": self.system_instructions.get(),
            "force_embedding_compat": self.force_embedding_compat.get(),
            "retrieval_k": self.retrieval_k.get(),
            "final_k": self.final_k.get(),
            "search_type": self.search_type.get(),
            "mmr_lambda": self.mmr_lambda.get(),
            # New config fields: agentic_mode, agentic_max_iterations, show_retrieved_context
            "agentic_mode": self.agentic_mode.get(),
            "agentic_max_iterations": max_iterations,
            "show_retrieved_context": self.show_retrieved_context.get(),
            "use_reranker": self.use_reranker.get(),
            "use_sub_queries": bool(self.use_sub_queries.get()),
            "subquery_max_docs": subquery_max_docs,
            "fallback_final_k": self.fallback_final_k.get(),
            "index_embedding_signature": self.index_embedding_signature,
            "selected_index_path": self.selected_index_path,
            "selected_collection_name": self.selected_collection_name,
            "output_style": self.output_style.get(),
        }
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except OSError:
            pass

    def on_close(self):
        self.save_config()
        self.root.destroy()

    def build_config_tab(self):
        frame = ttk.Frame(self.tab_config, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

        # --- LLM Provider Settings ---
        llm_frame = ttk.LabelFrame(frame, text="LLM & Embedding Provider", padding=15)
        llm_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        llm_frame.columnconfigure(1, weight=1)

        ttk.Label(llm_frame, text="Generation Provider:").grid(
            row=0, column=0, sticky="w"
        )
        cb_llm = ttk.Combobox(
            llm_frame,
            textvariable=self.llm_provider,
            values=["openai", "anthropic", "google", "local_lm_studio"],
            state="readonly",
        )
        cb_llm.grid(row=0, column=1, sticky="ew", padx=5, pady=5)
        cb_llm.bind("<<ComboboxSelected>>", self._on_llm_provider_change)

        ttk.Label(llm_frame, text="Generation Model:").grid(
            row=1, column=0, sticky="w"
        )
        self.cb_llm_model = ttk.Combobox(
            llm_frame,
            textvariable=self.llm_model,
        )
        self.cb_llm_model.grid(row=1, column=1, sticky="ew", padx=5, pady=5)
        self.cb_llm_model.bind("<<ComboboxSelected>>", self._on_llm_model_change)

        ttk.Label(llm_frame, text="Custom Generation Model (optional):").grid(
            row=2, column=0, sticky="w"
        )
        self.llm_model_custom_entry = ttk.Entry(
            llm_frame, textvariable=self.llm_model_custom
        )
        self.llm_model_custom_entry.grid(
            row=2, column=1, sticky="ew", padx=5, pady=5
        )

        ttk.Label(llm_frame, text="Embedding Provider:").grid(
            row=3, column=0, sticky="w"
        )
        cb_emb = ttk.Combobox(
            llm_frame,
            textvariable=self.embedding_provider,
            values=["voyage", "openai", "google", "local_huggingface"],
            state="readonly",
        )
        cb_emb.grid(row=3, column=1, sticky="ew", padx=5, pady=5)
        cb_emb.bind("<<ComboboxSelected>>", self._on_embedding_provider_change)

        ttk.Label(llm_frame, text="Embedding Model:").grid(
            row=4, column=0, sticky="w"
        )
        self.cb_emb_model = ttk.Combobox(
            llm_frame,
            textvariable=self.embedding_model,
        )
        self.cb_emb_model.grid(row=4, column=1, sticky="ew", padx=5, pady=5)
        self.cb_emb_model.bind("<<ComboboxSelected>>", self._on_embedding_model_change)

        ttk.Label(llm_frame, text="Custom Embedding Model (optional):").grid(
            row=5, column=0, sticky="w"
        )
        self.embedding_model_custom_entry = ttk.Entry(
            llm_frame, textvariable=self.embedding_model_custom
        )
        self.embedding_model_custom_entry.grid(
            row=5, column=1, sticky="ew", padx=5, pady=5
        )
        self.btn_browse_hf_model = ttk.Button(
            llm_frame, text="Browse Local HF Model...", command=self.browse_hf_model
        )
        self.btn_browse_hf_model.grid(row=6, column=1, sticky="w", padx=5, pady=(0, 5))

        self.compat_warning = ttk.Label(
            llm_frame,
            text="",
            foreground="#a33",
            wraplength=360,
            justify="left",
        )
        self.compat_warning.grid(row=7, column=1, sticky="w", padx=5, pady=(0, 5))
        self.force_compat_check = ttk.Checkbutton(
            llm_frame,
            text="Force embedding compatibility (skip warning)",
            variable=self.force_embedding_compat,
        )
        self.force_compat_check.grid(row=8, column=1, sticky="w", padx=5, pady=(0, 5))

        ttk.Label(llm_frame, text="Local LLM URL (if using LM Studio):").grid(
            row=9, column=0, sticky="w"
        )
        ttk.Entry(llm_frame, textvariable=self.local_llm_url).grid(
            row=9, column=1, sticky="ew", padx=5, pady=5
        )

        ttk.Label(llm_frame, text="Temperature:").grid(row=10, column=0, sticky="w")
        ttk.Entry(llm_frame, textvariable=self.llm_temperature).grid(
            row=10, column=1, sticky="ew", padx=5, pady=5
        )

        ttk.Label(llm_frame, text="Max Tokens:").grid(row=11, column=0, sticky="w")
        ttk.Entry(llm_frame, textvariable=self.llm_max_tokens).grid(
            row=11, column=1, sticky="ew", padx=5, pady=5
        )

        ttk.Label(llm_frame, text="System Instructions:").grid(
            row=12, column=0, sticky="nw"
        )
        self.instructions_box = scrolledtext.ScrolledText(
            llm_frame, height=6, font=("Segoe UI", 9)
        )
        self.instructions_box.grid(row=12, column=1, sticky="ew", padx=5, pady=5)
        self.instructions_box.insert(tk.END, self.system_instructions.get())
        self.instructions_box.bind("<KeyRelease>", self._on_instructions_change)
        ttk.Checkbutton(
            llm_frame,
            text="Verbose/Analytical mode",
            variable=self.verbose_mode,
            command=self._on_verbose_mode_toggle,
        ).grid(row=13, column=1, sticky="w", padx=5, pady=(0, 5))

        # --- Vector DB Settings ---
        db_frame = ttk.LabelFrame(frame, text="Vector Database Strategy", padding=15)
        db_frame.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)

        ttk.Radiobutton(
            db_frame,
            text="ChromaDB (Local File - Recommended)",
            variable=self.vector_db_type,
            value="chroma",
        ).pack(anchor="w", pady=2)
        ttk.Radiobutton(
            db_frame,
            text="Weaviate (Server)",
            variable=self.vector_db_type,
            value="weaviate",
        ).pack(anchor="w", pady=2)

        ttk.Label(db_frame, text="Weaviate URL:").pack(anchor="w", pady=(10, 0))
        ttk.Entry(db_frame, textvariable=self.api_keys["weaviate_url"]).pack(
            fill="x", pady=2
        )

        # --- API Keys ---
        key_frame = ttk.LabelFrame(
            frame, text="API Keys (Required for selected services)", padding=15
        )
        key_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=5, pady=10)
        key_frame.columnconfigure(1, weight=1)

        keys = [
            ("OpenAI API Key:", "openai"),
            ("Anthropic API Key:", "anthropic"),
            ("Google Gemini Key:", "google"),
            ("Cohere API Key (For Reranking):", "cohere"),
            ("Weaviate API Key (Optional):", "weaviate_key"),
            ("Voyage API Key:", "voyage"),
            ("Mistral API Key:", "mistral"),
            ("Groq API Key:", "groq"),
            ("Azure OpenAI API Key:", "azure_openai"),
            ("Together API Key:", "together"),
            ("Hugging Face Token (Optional):", "huggingface"),
            ("Fireworks API Key:", "fireworks"),
            ("Perplexity API Key:", "perplexity"),
        ]

        for i, (label, key_name) in enumerate(keys):
            ttk.Label(key_frame, text=label).grid(row=i, column=0, sticky="w", pady=2)
            ttk.Entry(
                key_frame, textvariable=self.api_keys[key_name], show="*", width=50
            ).grid(row=i, column=1, sticky="w", padx=10, pady=2)

        deps_frame = ttk.LabelFrame(frame, text="Dependencies", padding=15)
        deps_frame.grid(row=2, column=0, columnspan=2, sticky="ew", padx=5, pady=10)
        deps_frame.columnconfigure(1, weight=1)

        ttk.Label(
            deps_frame,
            text="Check for required packages or reinstall them if needed.",
            wraplength=720,
            justify="left",
        ).grid(row=0, column=0, columnspan=2, sticky="w")

        ttk.Button(
            deps_frame, text="Check Dependencies", command=self.check_dependencies
        ).grid(row=1, column=0, sticky="w", padx=(0, 10), pady=(8, 0))
        ttk.Button(
            deps_frame, text="Install / Reinstall Dependencies", command=self.reinstall_dependencies
        ).grid(row=1, column=1, sticky="w", pady=(8, 0))

    def build_ingest_tab(self):
        frame = ttk.Frame(self.tab_ingest, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)

        # File Selection
        sel_frame = ttk.Frame(frame)
        sel_frame.pack(fill="x", pady=10)

        ttk.Label(
            sel_frame,
            text="Select HTML/Text File (2M+ tokens supported):",
            style="Header.TLabel",
        ).pack(anchor="w")
        self.lbl_file = ttk.Label(sel_frame, text="No file selected", foreground="gray")
        self.lbl_file.pack(anchor="w", pady=5)
        self.lbl_file_info = ttk.Label(sel_frame, text="", foreground="#666666")
        self.lbl_file_info.pack(anchor="w")

        file_btn_frame = ttk.Frame(sel_frame)
        file_btn_frame.pack(anchor="w")
        btn_browse = ttk.Button(
            file_btn_frame, text="Browse File...", command=self.browse_file
        )
        btn_browse.pack(side="left")
        ttk.Button(
            file_btn_frame, text="Clear Selection", command=self.clear_selected_file
        ).pack(side="left", padx=8)

        # Chunking Config
        chunk_frame = ttk.LabelFrame(frame, text="Chunking Strategy", padding=10)
        chunk_frame.pack(fill="x", pady=10)

        ttk.Label(chunk_frame, text="Chunk Size (chars):").pack(side="left")
        ttk.Entry(chunk_frame, textvariable=self.chunk_size, width=10).pack(
            side="left", padx=5
        )

        ttk.Label(chunk_frame, text="Overlap (chars):").pack(side="left", padx=(20, 0))
        ttk.Entry(chunk_frame, textvariable=self.chunk_overlap, width=10).pack(
            side="left", padx=5
        )

        ttk.Checkbutton(
            chunk_frame,
            text="Build digest index",
            variable=self.build_digest_index,
        ).pack(side="left", padx=(20, 0))

        # Action
        self.btn_ingest = ttk.Button(
            frame,
            text="Start Ingestion (Process -> Chunk -> Embed -> Store)",
            command=self.start_ingestion,
        )
        self.btn_ingest.pack(fill="x", pady=20)

        self.progress = ttk.Progressbar(frame, orient="horizontal", mode="determinate")
        self.progress.pack(fill="x")

    def build_chat_tab(self):
        if not hasattr(self, "use_sub_queries"):
            self.use_sub_queries = tk.BooleanVar(value=True)
        if not hasattr(self, "subquery_max_docs"):
            self.subquery_max_docs = tk.IntVar(value=200)
        frame = ttk.Frame(self.tab_chat, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)

        # Existing Index Selection
        index_frame = ttk.LabelFrame(frame, text="Vector Store Selection", padding=10)
        index_frame.pack(fill="x", pady=(0, 10))
        index_frame.columnconfigure(1, weight=1)

        ttk.Label(index_frame, text="Existing Index (optional):").grid(
            row=0, column=0, sticky="w"
        )
        self.cb_existing_index = ttk.Combobox(
            index_frame,
            textvariable=self.existing_index_var,
            state="readonly",
        )
        self.cb_existing_index.grid(row=0, column=1, sticky="ew", padx=5)
        self.cb_existing_index.bind(
            "<<ComboboxSelected>>", self._on_existing_index_change
        )
        ttk.Button(
            index_frame, text="Refresh", command=self._refresh_existing_indexes
        ).grid(row=0, column=2, padx=(5, 0))
        self._refresh_existing_indexes()

        retrieval_frame = ttk.LabelFrame(
            frame, text="Retrieval Settings", padding=10
        )
        retrieval_frame.pack(fill="x", pady=(0, 10))
        retrieval_frame.columnconfigure(1, weight=1)
        retrieval_frame.columnconfigure(3, weight=1)

        ttk.Label(retrieval_frame, text="Retrieve K:").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Entry(retrieval_frame, textvariable=self.retrieval_k, width=8).grid(
            row=0, column=1, sticky="w", padx=(5, 15)
        )

        ttk.Label(retrieval_frame, text="Final K:").grid(
            row=0, column=2, sticky="w"
        )
        ttk.Entry(retrieval_frame, textvariable=self.final_k, width=8).grid(
            row=0, column=3, sticky="w", padx=(5, 0)
        )

        ttk.Label(retrieval_frame, text="Search Type:").grid(
            row=1, column=0, sticky="w", pady=(6, 0)
        )
        ttk.Combobox(
            retrieval_frame,
            textvariable=self.search_type,
            values=["similarity", "mmr"],
            state="readonly",
            width=12,
        ).grid(row=1, column=1, sticky="w", padx=(5, 15), pady=(6, 0))

        ttk.Label(retrieval_frame, text="MMR lambda:").grid(
            row=1, column=2, sticky="w", pady=(6, 0)
        )
        ttk.Entry(retrieval_frame, textvariable=self.mmr_lambda, width=8).grid(
            row=1, column=3, sticky="w", padx=(5, 0), pady=(6, 0)
        )

        # Chat Display
        self.chat_display = scrolledtext.ScrolledText(
            frame, state="disabled", font=("Segoe UI", 10), wrap=tk.WORD
        )
        self.chat_display.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # Tag configuration for coloring
        self.chat_display.tag_config(
            "user", foreground="blue", font=("Segoe UI", 10, "bold")
        )
        self.chat_display.tag_config("agent", foreground="green")
        self.chat_display.tag_config(
            "system", foreground="gray", font=("Segoe UI", 8, "italic")
        )
        self.chat_display.tag_config("source", foreground="#888888", font=("Consolas", 8))

        # Input
        input_frame = ttk.Frame(frame)
        input_frame.pack(fill="x")

        self.txt_input = ttk.Entry(input_frame, font=("Segoe UI", 11))
        self.txt_input.pack(side="left", fill="both", expand=True, padx=(0, 10))
        self.txt_input.bind("<Return>", lambda e: self.send_message())

        btn_send = ttk.Button(input_frame, text="Send", command=self.send_message)
        btn_send.pack(side="right")

        # Quick Actions
        action_frame = ttk.Frame(frame)
        action_frame.pack(fill="x", pady=(8, 4))
        ttk.Button(action_frame, text="Clear Chat", command=self.clear_chat).pack(
            side="left"
        )
        ttk.Button(
            action_frame, text="Save Chat Transcript", command=self.save_chat
        ).pack(side="left", padx=8)
        ttk.Button(
            action_frame, text="Copy Last Answer", command=self.copy_last_answer
        ).pack(side="left")

        # Options
        opt_frame = ttk.Frame(frame)
        opt_frame.pack(fill="x", pady=5)
        ttk.Checkbutton(
            opt_frame,
            text="Use Cohere Reranker (Higher Precision)",
            variable=self.use_reranker,
        ).pack(side="left")
        ttk.Checkbutton(
            opt_frame,
            text="Use Sub-Queries (Broader Recall)",
            variable=self.use_sub_queries,
        ).pack(side="left", padx=(12, 0))
        ttk.Label(opt_frame, text="Max Merged Docs:").pack(side="left", padx=(12, 4))
        ttk.Entry(opt_frame, textvariable=self.subquery_max_docs, width=6).pack(
            side="left"
        )
        ttk.Label(opt_frame, text="Fallback Final K:").pack(side="left", padx=(15, 4))
        ttk.Entry(opt_frame, textvariable=self.fallback_final_k, width=6).pack(
            side="left"
        )

        output_frame = ttk.Frame(frame)
        output_frame.pack(fill="x", pady=(2, 4))
        ttk.Label(output_frame, text="Output style:").pack(side="left")
        ttk.Combobox(
            output_frame,
            textvariable=self.output_style,
            values=self.output_style_options,
            state="readonly",
            width=22,
        ).pack(side="left", padx=(6, 0))

        agentic_frame = ttk.LabelFrame(frame, text="Agentic Options", padding=8)
        agentic_frame.pack(fill="x", pady=(5, 0))
        ttk.Checkbutton(
            agentic_frame,
            text="Agentic mode (iterate)",
            variable=self.agentic_mode,
        ).pack(side="left")
        ttk.Label(agentic_frame, text="Max iterations:").pack(side="left", padx=(12, 4))
        ttk.Spinbox(
            agentic_frame,
            from_=1,
            to=AGENTIC_MAX_ITERATIONS_HARD_CAP,
            textvariable=self.agentic_max_iterations,
            width=4,
        ).pack(side="left")
        ttk.Checkbutton(
            agentic_frame,
            text="Show retrieved context in chat",
            variable=self.show_retrieved_context,
        ).pack(side="left", padx=(12, 0))

    # --- Logic ---

    @staticmethod
    def _humanize_bytes(num_bytes):
        if num_bytes < 1024:
            return f"{num_bytes} B"
        for unit in ["KB", "MB", "GB", "TB"]:
            num_bytes /= 1024
            if num_bytes < 1024:
                return f"{num_bytes:.1f} {unit}"
        return f"{num_bytes:.1f} PB"

    def _append_history(self, message):
        self.chat_history.append(message)
        max_messages = self.chat_history_max_turns * 2
        if len(self.chat_history) > max_messages:
            self.chat_history = self.chat_history[-max_messages:]

    def _get_history_window(self, current_query=None):
        history = list(self.chat_history)
        if (
            current_query
            and history
            and isinstance(history[-1], HumanMessage)
            and history[-1].content == current_query
        ):
            history = history[:-1]
        max_messages = self.chat_history_max_turns * 2
        if len(history) > max_messages:
            history = history[-max_messages:]
        return history

    def _parse_subquery_response(self, text):
        cleaned = text.strip()
        if "```" in cleaned:
            parts = cleaned.split("```")
            if len(parts) >= 2:
                cleaned = parts[1].strip()
                if cleaned.lower().startswith("json"):
                    cleaned = cleaned.split("\n", 1)[-1].strip()
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
        lines = []
        for line in cleaned.splitlines():
            item = line.strip().lstrip("-*0123456789. ").strip()
            if item:
                lines.append(item)
        return lines

    def _generate_sub_queries(self, query):
        try:
            llm = self.get_llm()
            system_prompt = (
                "You generate search sub-queries for retrieval. "
                "Return 3-5 concise sub-queries as a JSON array of strings. "
                "Do not include any extra text."
            )
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=query),
            ]
            response = llm.invoke(messages)
            candidates = self._parse_subquery_response(response.content)
        except Exception as exc:
            self.log(f"Sub-query generation failed, using base query only. ({exc})")
            return []
        seen = set()
        sub_queries = []
        for candidate in candidates:
            normalized = candidate.strip()
            if not normalized or normalized.lower() == query.strip().lower():
                continue
            key = normalized.lower()
            if key in seen:
                continue
            seen.add(key)
            sub_queries.append(normalized)
        return sub_queries[:5]

    def _merge_dedupe_docs(self, docs):
        seen = set()
        merged = []
        for doc in docs:
            if doc is None:
                continue
            metadata = getattr(doc, "metadata", {}) or {}
            content = (getattr(doc, "page_content", "") or "").strip()
            chunk_id = metadata.get("chunk_id")
            ingest_id = metadata.get("ingest_id")
            if chunk_id is not None and ingest_id:
                key = (ingest_id, chunk_id)
            else:
                content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
                key = content_hash
            if key in seen:
                continue
            seen.add(key)
            merged.append(doc)
        return merged

    @staticmethod
    def _doc_identity_key(doc):
        metadata = getattr(doc, "metadata", {}) or {}
        content = (getattr(doc, "page_content", "") or "").strip()
        chunk_id = metadata.get("chunk_id")
        ingest_id = metadata.get("ingest_id")
        if chunk_id is not None and ingest_id:
            return f"{ingest_id}:{chunk_id}"
        chunk_db_id = metadata.get("chunk_db_id")
        if chunk_db_id:
            return f"chunk_db:{chunk_db_id}"
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return f"content:{content_hash}"

    def _fuse_ranked_results(self, ranked_lists, k_rrf=60, fused_pool_size=600):
        score_by_key = {}
        doc_by_key = {}
        systems_by_key = {}
        for system_name, docs in ranked_lists:
            for rank_idx, doc in enumerate(docs or [], start=1):
                if doc is None:
                    continue
                key = self._doc_identity_key(doc)
                score = 1.0 / (k_rrf + rank_idx)
                score_by_key[key] = score_by_key.get(key, 0.0) + score
                doc_by_key[key] = doc
                systems_by_key.setdefault(key, set()).add(system_name)

        ranked_items = sorted(score_by_key.items(), key=lambda item: item[1], reverse=True)
        if fused_pool_size > 0:
            ranked_items = ranked_items[:fused_pool_size]

        fused_docs = []
        for rank_idx, (key, score) in enumerate(ranked_items, start=1):
            doc = doc_by_key[key]
            metadata = (getattr(doc, "metadata", {}) or {}).copy()
            metadata["rrf_score"] = round(score, 8)
            metadata["relevance_score"] = round(score, 8)
            metadata["rrf_rank"] = rank_idx
            metadata["retrieval_systems"] = sorted(systems_by_key.get(key, set()))
            doc.metadata = metadata
            fused_docs.append(doc)
        return fused_docs

    @staticmethod
    def _doc_group_key(doc):
        metadata = getattr(doc, "metadata", {}) or {}
        for field in (
            "section",
            "section_title",
            "heading",
            "header",
            "title",
            "doc_title",
        ):
            value = metadata.get(field)
            if value:
                return f"{field}:{value}"
        digest_window = metadata.get("digest_window") or metadata.get("digest_id")
        if digest_window:
            return f"digest_window:{digest_window}"
        source = metadata.get("source") or metadata.get("file_path") or metadata.get(
            "filename"
        )
        content = (getattr(doc, "page_content", "") or "").strip()
        prefix = content[:80]
        return f"{source}:{prefix}"

    @staticmethod
    def _is_priority_doc(doc):
        metadata = getattr(doc, "metadata", {}) or {}
        if metadata.get("lexical_boost") or metadata.get("lexical_boosted"):
            return True
        if metadata.get("critic_missing") or metadata.get("critic_missing_items"):
            return True
        missing_items = metadata.get("missing_items") or metadata.get(
            "missing_coverage"
        )
        if isinstance(missing_items, (list, tuple, set)):
            return len(missing_items) > 0
        return bool(missing_items)

    @staticmethod
    def _is_must_include(doc):
        metadata = getattr(doc, "metadata", {}) or {}
        return bool(
            metadata.get("must_include")
            or metadata.get("force_include")
            or metadata.get("required_context")
        )

    @staticmethod
    def _detect_channel_hint(text, metadata):
        source = (
            str(metadata.get("source") or metadata.get("file_path") or metadata.get("filename") or "")
        )
        combined = f"{source}\n{text}".lower()
        if "teams" in combined:
            return "teams"
        if "whatsapp" in combined:
            return "whatsapp"
        if "email" in combined or "e-mail" in combined:
            return "email"
        if "call" in combined or "phone" in combined or "dial" in combined:
            return "call"
        return "unknown"

    @staticmethod
    def _extract_channel(text):
        normalized = (text or "").lower()
        if not normalized:
            return "unknown"
        if re.search(r"\b(teams|slack|discord|chat)\b", normalized):
            return "chat"
        if "whatsapp" in normalized:
            return "whatsapp"
        if re.search(r"\b(email|e-mail|mail)\b", normalized):
            return "email"
        if re.search(r"\b(call|phone|dial|voicemail|zoom|meet)\b", normalized):
            return "call"
        if re.search(r"\b(ticket|case|jira|zendesk|servicenow)\b", normalized):
            return "ticket"
        return "unknown"

    @staticmethod
    def _month_to_number(month_name):
        months = {
            "jan": 1,
            "january": 1,
            "feb": 2,
            "february": 2,
            "mar": 3,
            "march": 3,
            "apr": 4,
            "april": 4,
            "may": 5,
            "jun": 6,
            "june": 6,
            "jul": 7,
            "july": 7,
            "aug": 8,
            "august": 8,
            "sep": 9,
            "sept": 9,
            "september": 9,
            "oct": 10,
            "october": 10,
            "nov": 11,
            "november": 11,
            "dec": 12,
            "december": 12,
        }
        return months.get(month_name.lower())

    def _extract_dates(self, text):
        mentions = []
        if not text:
            return mentions
        patterns = []
        patterns.append(
            (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), "ymd")
        )
        patterns.append(
            (re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b"), "numeric")
        )
        patterns.append(
            (
                re.compile(
                    r"\b(\d{1,2})\s+"
                    r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
                    r"jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|"
                    r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+"
                    r"(\d{4})\b",
                    flags=re.I,
                ),
                "day_month_year",
            )
        )
        patterns.append(
            (
                re.compile(
                    r"\b(?:early|mid|late)\s+"
                    r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
                    r"jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|"
                    r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+"
                    r"(\d{4})\b",
                    flags=re.I,
                ),
                "month_year",
            )
        )
        patterns.append(
            (
                re.compile(
                    r"\b"
                    r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
                    r"jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|"
                    r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+"
                    r"(\d{4})\b",
                    flags=re.I,
                ),
                "month_year",
            )
        )
        for pattern, kind in patterns:
            for match in pattern.finditer(text):
                if kind == "ymd":
                    year, month, day = match.groups()
                elif kind == "numeric":
                    month, day, year = match.groups()
                elif kind == "day_month_year":
                    day, month_name, year = match.groups()
                    month = self._month_to_number(month_name) or 0
                    day = int(day)
                    year = int(year)
                    if month:
                        mentions.append((match.start(), f"{year:04d}-{month:02d}-{day:02d}"))
                    continue
                elif kind == "month_year":
                    month_name, year = match.groups()
                    month = self._month_to_number(month_name) or 0
                    year = int(year)
                    if month:
                        mentions.append((match.start(), f"{year:04d}-{month:02d}"))
                    continue
                if kind in {"ymd", "numeric"}:
                    if len(year) == 2:
                        year = int(f"20{year}")
                    else:
                        year = int(year)
                    month = int(month)
                    day = int(day)
                    mentions.append((match.start(), f"{year:04d}-{month:02d}-{day:02d}"))
        mentions.sort(key=lambda item: item[0])
        return [value for _idx, value in mentions]

    def _extract_date_mentions(self, text):
        return self._extract_dates(text)

    def _extract_incident_signature(self, text):
        date_mentions = self._extract_dates(text)
        date_key = date_mentions[0] if date_mentions else "undated"
        channel = self._extract_channel(text)
        normalized = re.sub(r"\s+", " ", (text or "").strip().lower())
        participant = ""
        participant_match = re.search(
            r"\b([A-Z][a-z]+ [A-Z][a-z]+|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})\b",
            text or "",
        )
        if participant_match:
            participant = participant_match.group(1).lower()
        digest = hashlib.sha256(normalized[:200].encode("utf-8")).hexdigest()[:12]
        return f"{date_key}|{channel}|{participant or digest}"

    @staticmethod
    def _extract_role_kind(doc):
        metadata = getattr(doc, "metadata", {}) or {}
        role = str(
            metadata.get("speaker_role") or metadata.get("role") or "unknown"
        ).strip().lower()
        if role in {"assistant", "system", "bot", "ai"}:
            return "assistant"
        if role in {"user", "human", "employee", "complainant", "reporter"}:
            return "user"
        if role in {"manager", "supervisor", "lead", "hr", "legal"}:
            return "authority"
        return "other"

    def _evidence_kind(self, doc):
        metadata = getattr(doc, "metadata", {}) or {}
        kind = str(metadata.get("evidence_kind") or "").strip().lower()
        if kind:
            return kind
        role_kind = self._extract_role_kind(doc)
        if role_kind == "user":
            return "primary"
        if role_kind == "assistant":
            return "secondary"
        return "unknown"

    def _build_incident_key(self, doc):
        content = (getattr(doc, "page_content", "") or "").strip()
        metadata = getattr(doc, "metadata", {}) or {}
        signature_text = "\n".join(
            [
                str(
                    metadata.get("source")
                    or metadata.get("file_path")
                    or metadata.get("filename")
                    or ""
                ),
                content,
            ]
        )
        return self._extract_incident_signature(signature_text)

    def _score_doc_for_selection(self, doc, evidence_pack_mode=False, evidence_thin=False):
        content = (getattr(doc, "page_content", "") or "").strip()
        metadata = getattr(doc, "metadata", {}) or {}
        base_score = metadata.get("relevance_score")
        try:
            base_score = float(base_score)
        except (TypeError, ValueError):
            base_score = 0.0

        date_mentions = self._extract_date_mentions(content)
        quote_match = re.search(r"(\"[^\"]+\"|“[^”]+”)", content)
        participant_match = re.search(
            r"\b[A-Z][a-z]+ [A-Z][a-z]+\b", content
        ) or re.search(
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", content
        )
        what_happened_match = re.search(
            r"\b(incident|issue|complaint|reported|alleged|occurred|happened|"
            r"breach|violation|harassment|grievance|escalated|confirmed|said|"
            r"stated|told|raised)\b",
            content,
            flags=re.I,
        )
        advice_match = re.search(
            r"\b(you should|we should|i recommend|recommend|suggest|consider|"
            r"best practice|steps to|how to|guidance|advice|tips|as an ai)\b",
            content,
            flags=re.I,
        )

        channel = self._extract_channel(
            "\n".join(
                [
                    str(
                        metadata.get("source")
                        or metadata.get("file_path")
                        or metadata.get("filename")
                        or ""
                    ),
                    content,
                ]
            )
        )
        month_bucket = date_mentions[0][:7] if date_mentions else "undated"
        incident_signature = self._extract_incident_signature(content)
        role_kind = self._extract_role_kind(doc)
        evidence_kind = self._evidence_kind(doc)

        score = base_score
        if date_mentions:
            score += 0.3
        if quote_match:
            score += 0.2
        if participant_match:
            score += 0.2
        if what_happened_match:
            score += 0.2
        if advice_match:
            score -= 0.2 if (evidence_pack_mode and evidence_thin) else (0.5 if evidence_pack_mode else 0.3)

        if role_kind == "assistant" and evidence_pack_mode:
            score -= 0.1 if evidence_thin else 0.25
        elif role_kind == "user":
            score += 0.15

        if evidence_kind == "primary":
            score += 0.1

        incident_key = self._build_incident_key(doc)
        metadata["incident_key"] = incident_key
        metadata["incident_signature"] = incident_signature
        metadata["month_bucket"] = month_bucket
        metadata["channel_type"] = channel
        metadata["role_kind"] = role_kind
        metadata["evidence_kind"] = evidence_kind
        metadata["selection_score"] = round(score, 4)
        metadata["date_mentions"] = date_mentions
        doc.metadata = metadata
        return score, incident_key

    def _apply_coverage_selection(self, docs, final_k, group_limit=2, evidence_pack_mode=False):
        must_include = []
        remaining = []
        for doc in docs:
            if self._is_must_include(doc):
                must_include.append(doc)
            else:
                remaining.append(doc)

        selected = list(must_include)
        selected_ids = {id(doc) for doc in selected}
        group_counts = {}
        incident_counts = {}
        month_counts = {}
        channel_counts = {}
        signature_counts = {}
        pool_non_assistant = 0
        for doc in docs:
            if self._extract_role_kind(doc) != "assistant":
                pool_non_assistant += 1
        evidence_thin = evidence_pack_mode and pool_non_assistant <= max(2, final_k // 3)

        for doc in selected:
            group_key = self._doc_group_key(doc)
            group_counts[group_key] = group_counts.get(group_key, 0) + 1
            _score, incident_key = self._score_doc_for_selection(
                doc,
                evidence_pack_mode,
                evidence_thin=evidence_thin,
            )
            incident_counts[incident_key] = incident_counts.get(incident_key, 0) + 1
            metadata = getattr(doc, "metadata", {}) or {}
            month = metadata.get("month_bucket") or "undated"
            channel = metadata.get("channel_type") or "unknown"
            signature = metadata.get("incident_signature") or incident_key
            month_counts[month] = month_counts.get(month, 0) + 1
            channel_counts[channel] = channel_counts.get(channel, 0) + 1
            signature_counts[signature] = signature_counts.get(signature, 0) + 1

        priority_docs = [doc for doc in remaining if self._is_priority_doc(doc)]
        other_docs = [doc for doc in remaining if doc not in priority_docs]

        scored_priority = []
        scored_other = []
        for doc in priority_docs:
            score, incident_key = self._score_doc_for_selection(
                doc,
                evidence_pack_mode,
                evidence_thin=evidence_thin,
            )
            scored_priority.append((score, incident_key, doc))
        for doc in other_docs:
            score, incident_key = self._score_doc_for_selection(
                doc,
                evidence_pack_mode,
                evidence_thin=evidence_thin,
            )
            scored_other.append((score, incident_key, doc))
        all_channels = {
            (getattr(doc, "metadata", {}) or {}).get("channel_type") or "unknown"
            for _score, _incident_key, doc in (scored_priority + scored_other)
        }
        all_channels.discard("unknown")
        month_pool = {
            (getattr(doc, "metadata", {}) or {}).get("month_bucket") or "undated"
            for _score, _incident_key, doc in (scored_priority + scored_other)
        }
        month_pool.discard("undated")
        min_month_buckets = min(3, len(month_pool))

        def _diversity_boost(item):
            score, incident_key, doc = item
            metadata = getattr(doc, "metadata", {}) or {}
            month = metadata.get("month_bucket") or "undated"
            channel = metadata.get("channel_type") or "unknown"
            signature = metadata.get("incident_signature") or incident_key
            boost = 0.0
            boost += 0.25 if month_counts.get(month, 0) == 0 else 0.0
            boost += 0.2 if channel != "unknown" and channel_counts.get(channel, 0) == 0 else 0.0
            boost += 0.25 if signature_counts.get(signature, 0) == 0 else 0.0
            return score + boost

        scored_priority.sort(key=_diversity_boost, reverse=True)
        scored_other.sort(key=_diversity_boost, reverse=True)
        scored_all = scored_priority + scored_other

        if final_k < MIN_UNIQUE_INCIDENTS:
            target_unique = final_k
        else:
            target_unique = min(final_k, MAX_UNIQUE_INCIDENTS)

        def _add_docs(candidates):
            nonlocal selected
            for _score, incident_key, doc in candidates:
                if len(selected) >= final_k and not self._is_must_include(doc):
                    break
                if id(doc) in selected_ids:
                    continue
                group_key = self._doc_group_key(doc)
                count = group_counts.get(group_key, 0)
                if count >= group_limit and not self._is_must_include(doc):
                    continue
                selected.append(doc)
                selected_ids.add(id(doc))
                group_counts[group_key] = count + 1
                incident_counts[incident_key] = incident_counts.get(incident_key, 0) + 1
                metadata = getattr(doc, "metadata", {}) or {}
                month = metadata.get("month_bucket") or "undated"
                channel = metadata.get("channel_type") or "unknown"
                signature = metadata.get("incident_signature") or incident_key
                month_counts[month] = month_counts.get(month, 0) + 1
                channel_counts[channel] = channel_counts.get(channel, 0) + 1
                signature_counts[signature] = signature_counts.get(signature, 0) + 1

        missing_channels = [
            channel
            for channel in sorted(all_channels)
            if channel_counts.get(channel, 0) == 0
        ]
        for channel in missing_channels:
            if len(selected) >= final_k:
                break
            for _score, incident_key, doc in scored_all:
                metadata = getattr(doc, "metadata", {}) or {}
                if (metadata.get("channel_type") or "unknown") != channel:
                    continue
                _add_docs([(_score, incident_key, doc)])
                break

        missing_months = [
            month
            for month in sorted(month_pool)
            if month_counts.get(month, 0) == 0
        ]
        for month in missing_months:
            represented_months = len([m for m, c in month_counts.items() if c > 0 and m != "undated"])
            if represented_months >= min_month_buckets or len(selected) >= final_k:
                break
            for _score, incident_key, doc in scored_all:
                metadata = getattr(doc, "metadata", {}) or {}
                if (metadata.get("month_bucket") or "undated") != month:
                    continue
                _add_docs([(_score, incident_key, doc)])
                break

        for _score, incident_key, doc in scored_all:
            if len(selected) >= final_k:
                break
            if id(doc) in selected_ids:
                continue
            if incident_counts.get(incident_key):
                continue
            if len(incident_counts) >= target_unique:
                break
            group_key = self._doc_group_key(doc)
            count = group_counts.get(group_key, 0)
            if count >= group_limit and not self._is_must_include(doc):
                continue
            _add_docs([(_score, incident_key, doc)])

        _add_docs(scored_all)

        if len(selected) > final_k and len(must_include) <= final_k:
            selected = selected[:final_k]
        return selected

    def _prioritize_must_include(self, docs):
        must_include = [doc for doc in docs if self._is_must_include(doc)]
        remainder = [doc for doc in docs if doc not in must_include]
        return [*must_include, *remainder]

    @staticmethod
    def _detect_exact_detail_cues(query):
        cues = {
            "quotes": False,
            "dates": False,
            "ids": False,
            "numeric_heavy": False,
        }
        if re.search(r"\"[^\"]+\"", query):
            cues["quotes"] = True
        if re.search(r"\b\d{4}-\d{2}-\d{2}\b", query) or re.search(
            r"\b\d{1,2}/\d{1,2}/\d{2,4}\b", query
        ):
            cues["dates"] = True
        if re.search(
            r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+\d{1,2},?\s+\d{4}\b",
            query,
            flags=re.I,
        ):
            cues["dates"] = True
        if re.search(r"\b[A-Z]{2,}-\d+\b", query) or re.search(
            r"\b(?:id|ticket|case|ref)[\s:#-]*[A-Za-z0-9-]{3,}\b",
            query,
            flags=re.I,
        ):
            cues["ids"] = True
        alnum_count = sum(ch.isalnum() for ch in query)
        digit_count = sum(ch.isdigit() for ch in query)
        if alnum_count:
            ratio = digit_count / alnum_count
            if digit_count >= 4 or ratio >= 0.2:
                cues["numeric_heavy"] = True
        return cues

    @staticmethod
    def _tokenize_for_overlap(text):
        return set(re.findall(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*", text.lower()))

    def _lexical_overlap_score(self, query, content, cues):
        query_tokens = self._tokenize_for_overlap(query)
        if not query_tokens:
            return 0.0
        content_tokens = self._tokenize_for_overlap(content)
        shared = query_tokens & content_tokens
        base = len(shared) / max(1, len(query_tokens))
        bonus = 0.0
        if cues.get("quotes"):
            for quoted in re.findall(r"\"([^\"]+)\"", query):
                if quoted and quoted.lower() in content.lower():
                    bonus += 0.2
                    break
        if cues.get("dates") or cues.get("ids") or cues.get("numeric_heavy"):
            numeric_shared = [token for token in shared if any(ch.isdigit() for ch in token)]
            if numeric_shared:
                bonus += 0.15
        return min(1.0, base + bonus)

    def _promote_lexical_overlap(self, docs, query):
        cues = self._detect_exact_detail_cues(query)
        scored = []
        for idx, doc in enumerate(docs):
            content = (getattr(doc, "page_content", "") or "").strip()
            score = self._lexical_overlap_score(query, content, cues)
            metadata = getattr(doc, "metadata", {}) or {}
            metadata["lexical_overlap"] = round(score, 4)
            if score >= 0.3 or (any(cues.values()) and score >= 0.15):
                metadata["lexical_boost"] = True
            doc.metadata = metadata
            scored.append((idx, score, doc))
        scored.sort(
            key=lambda item: (
                (item[2].metadata or {}).get("lexical_boost") is True,
                item[1],
            ),
            reverse=True,
        )
        return [doc for _idx, _score, doc in scored]

    def log(self, msg):
        def _append():
            self.log_area.config(state="normal")
            self.log_area.insert(
                tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n"
            )
            self.log_area.see(tk.END)
            self.log_area.config(state="disabled")
            self.root.update_idletasks()
            if hasattr(self, "status_var"):
                self.status_var.set(msg)

        self._run_on_ui(_append)
        self._emit_log_to_console(msg)

    @staticmethod
    def _emit_log_to_console(msg):
        stream = sys.stderr if ("ERROR" in msg or "Failed" in msg) else sys.stdout
        if not stream or not stream.isatty():
            return
        print(msg, file=stream)

    def _format_role_distribution(self, docs):
        role_counts = {}
        for doc in docs or []:
            metadata = getattr(doc, "metadata", {}) or {}
            role = metadata.get("speaker_role") or "unknown"
            role_counts[role] = role_counts.get(role, 0) + 1
        if not role_counts:
            return "none"
        parts = [f"{role}={count}" for role, count in sorted(role_counts.items())]
        return ", ".join(parts)

    def _format_selected_distribution(self, docs):
        def _fmt(counter):
            if not counter:
                return "none"
            return ", ".join(
                f"{key}={value}" for key, value in sorted(counter.items(), key=lambda kv: kv[0])
            )

        month_counts = {}
        channel_counts = {}
        role_counts = {}
        evidence_counts = {}
        for doc in docs or []:
            metadata = getattr(doc, "metadata", {}) or {}
            month = metadata.get("month_bucket")
            if not month:
                dates = self._extract_dates(getattr(doc, "page_content", "") or "")
                month = dates[0][:7] if dates else "undated"
            channel = metadata.get("channel_type") or self._extract_channel(
                "\n".join(
                    [
                        str(
                            metadata.get("source")
                            or metadata.get("file_path")
                            or metadata.get("filename")
                            or ""
                        ),
                        getattr(doc, "page_content", "") or "",
                    ]
                )
            )
            role = metadata.get("role_kind") or self._extract_role_kind(doc)
            evidence = metadata.get("evidence_kind") or self._evidence_kind(doc)
            month_counts[month] = month_counts.get(month, 0) + 1
            channel_counts[channel] = channel_counts.get(channel, 0) + 1
            role_counts[role] = role_counts.get(role, 0) + 1
            evidence_counts[evidence] = evidence_counts.get(evidence, 0) + 1
        return {
            "months": _fmt(month_counts),
            "channels": _fmt(channel_counts),
            "roles": _fmt(role_counts),
            "evidence_kind": _fmt(evidence_counts),
        }

    def _log_final_docs_selection(
        self,
        retrieve_k,
        candidate_k,
        final_k,
        trunc_used_chars,
        trunc_budget_chars,
        unique_incidents,
        role_distribution,
        rerank_top_n,
        new_incidents_added,
        selected_distribution,
    ):
        self.log(
            "Final-docs selection telemetry | "
            f"retrieve_k={retrieve_k}, candidate_k={candidate_k}, final_k={final_k}, "
            f"packed_context_chars={trunc_used_chars}/{trunc_budget_chars}, "
            f"unique_incidents={unique_incidents}, role_distribution={role_distribution}, "
            f"rerank_top_n={rerank_top_n}, new_incidents_added={new_incidents_added}, "
            f"months={selected_distribution.get('months')}, "
            f"channels={selected_distribution.get('channels')}, "
            f"roles={selected_distribution.get('roles')}, "
            f"evidence_kind={selected_distribution.get('evidence_kind')}"
        )

    def _on_vector_db_type_change(self, *_args):
        self._refresh_existing_indexes()

    def _get_chroma_persist_root(self):
        return os.path.join(os.getcwd(), "chroma_db")

    def _get_lexical_db_path(self):
        persist_root = self._get_chroma_persist_root()
        parent_dir = os.path.dirname(os.path.abspath(persist_root))
        return os.path.join(parent_dir, "rag_lexical.db")

    def _ensure_lexical_db(self):
        db_path = self._get_lexical_db_path()
        try:
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS chunks(
                        chunk_id TEXT PRIMARY KEY,
                        source TEXT,
                        role TEXT,
                        evidence_kind TEXT,
                        text TEXT,
                        meta_json TEXT
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts
                    USING fts5(text, content='chunks', content_rowid='rowid')
                    """
                )
                conn.commit()
            self.lexical_db_path = db_path
            self.lexical_db_available = True
            return True
        except Exception as exc:
            self.lexical_db_path = db_path
            self.lexical_db_available = False
            self.log(f"Lexical DB unavailable; skipping SQLite sidecar. ({exc})")
            return False

    @staticmethod
    def _chunk_pk(metadata):
        ingest_id = metadata.get("ingest_id")
        chunk_id = metadata.get("chunk_id")
        if ingest_id is None or chunk_id is None:
            return None
        return f"{ingest_id}:{chunk_id}"

    def _upsert_lexical_chunks(self, docs):
        if not self._ensure_lexical_db():
            return False
        try:
            with sqlite3.connect(self.lexical_db_path) as conn:
                for doc in docs:
                    metadata = (doc.metadata or {}).copy()
                    chunk_pk = self._chunk_pk(metadata)
                    if not chunk_pk:
                        continue
                    source = metadata.get("source") or ""
                    role = metadata.get("speaker_role") or metadata.get("role") or ""
                    evidence_kind = metadata.get("evidence_kind") or ""
                    text = doc.page_content or ""
                    meta_json = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
                    conn.execute(
                        """
                        INSERT INTO chunks(chunk_id, source, role, evidence_kind, text, meta_json)
                        VALUES(?, ?, ?, ?, ?, ?)
                        ON CONFLICT(chunk_id) DO UPDATE SET
                            source=excluded.source,
                            role=excluded.role,
                            evidence_kind=excluded.evidence_kind,
                            text=excluded.text,
                            meta_json=excluded.meta_json
                        """,
                        (chunk_pk, source, role, evidence_kind, text, meta_json),
                    )
                conn.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild')")
                conn.commit()
            self.lexical_db_available = True
            return True
        except Exception as exc:
            self.lexical_db_available = False
            self.log(f"Lexical chunk upsert skipped (SQLite/FTS5 issue). ({exc})")
            return False

    def lexical_search(self, query: str, k: int) -> list[Document]:
        if not query or k <= 0:
            return []
        if not self.lexical_db_available:
            self._ensure_lexical_db()
        if not self.lexical_db_available or not self.lexical_db_path:
            return []
        try:
            with sqlite3.connect(self.lexical_db_path) as conn:
                rows = conn.execute(
                    """
                    SELECT
                        c.chunk_id,
                        c.source,
                        c.role,
                        c.evidence_kind,
                        c.text,
                        c.meta_json,
                        bm25(chunks_fts) AS lexical_score
                    FROM chunks_fts
                    JOIN chunks c ON c.rowid = chunks_fts.rowid
                    WHERE chunks_fts MATCH ?
                    ORDER BY lexical_score ASC
                    LIMIT ?
                    """,
                    (query, int(k)),
                ).fetchall()
        except Exception as exc:
            self.lexical_db_available = False
            self.log(f"Lexical search unavailable; continuing without it. ({exc})")
            return []

        docs = []
        for chunk_id, source, role, evidence_kind, text, meta_json, score in rows:
            metadata = {}
            if meta_json:
                try:
                    metadata = json.loads(meta_json)
                except json.JSONDecodeError:
                    metadata = {}
            if source and "source" not in metadata:
                metadata["source"] = source
            if role and "speaker_role" not in metadata:
                metadata["speaker_role"] = role
            if evidence_kind and "evidence_kind" not in metadata:
                metadata["evidence_kind"] = evidence_kind
            metadata["chunk_db_id"] = chunk_id
            metadata["lexical_score"] = float(score)
            metadata["lexical_match"] = True
            docs.append(Document(page_content=text or "", metadata=metadata))
        return docs

    @staticmethod
    def _safe_file_stem(file_path):
        base_name = os.path.basename(file_path or "")
        stem = os.path.splitext(base_name)[0]
        safe_stem = re.sub(r"[^A-Za-z0-9_-]+", "_", stem).strip("_")
        return safe_stem or "ingest"

    @staticmethod
    def _compact_chunk_ids(chunk_ids):
        filtered = sorted({int(cid) for cid in chunk_ids if str(cid).isdigit()})
        if not filtered:
            return ""
        ranges = []
        start = prev = filtered[0]
        for cid in filtered[1:]:
            if cid == prev + 1:
                prev = cid
                continue
            ranges.append((start, prev))
            start = prev = cid
        ranges.append((start, prev))
        return ",".join(
            str(start) if start == end else f"{start}-{end}"
            for start, end in ranges
        )

    @staticmethod
    def _expand_compact_chunk_ids(compact_ids):
        if not compact_ids:
            return set()
        ids = set()
        for part in str(compact_ids).split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                start, end = part.split("-", 1)
                if start.strip().isdigit() and end.strip().isdigit():
                    ids.update(range(int(start), int(end) + 1))
            elif part.isdigit():
                ids.add(int(part))
        return ids

    def _split_into_digest_windows(self, docs):
        windows = []
        total = len(docs)
        if total <= DIGEST_WINDOW_MAX:
            return [docs]
        idx = 0
        while idx < total:
            remaining = total - idx
            if remaining <= DIGEST_WINDOW_MAX:
                windows.append(docs[idx:])
                break
            take = min(DIGEST_WINDOW_TARGET, DIGEST_WINDOW_MAX)
            if remaining - take < DIGEST_WINDOW_MIN:
                take = remaining - DIGEST_WINDOW_MIN
            take = max(DIGEST_WINDOW_MIN, min(DIGEST_WINDOW_MAX, take))
            windows.append(docs[idx : idx + take])
            idx += take
        return windows

    def _group_chunks_for_digest(self, docs):
        groups = []
        buffer = []
        buffer_title = None

        def _flush():
            nonlocal buffer, buffer_title
            if not buffer:
                return
            if buffer_title and len(buffer) > DIGEST_WINDOW_MAX:
                windows = self._split_into_digest_windows(buffer)
            elif buffer_title:
                windows = [buffer]
            else:
                windows = self._split_into_digest_windows(buffer)
            for window in windows:
                groups.append((window, buffer_title))
            buffer = []
            buffer_title = None

        for doc in docs:
            section_title = (doc.metadata or {}).get("section_title")
            if section_title:
                if buffer and buffer_title != section_title:
                    _flush()
                buffer_title = section_title
                buffer.append(doc)
            else:
                if buffer and buffer_title:
                    _flush()
                buffer_title = None
                buffer.append(doc)
                if len(buffer) >= DIGEST_WINDOW_MAX:
                    _flush()

        _flush()
        return groups

    def _build_digest_documents(self, docs, ingest_id, source_basename, doc_title):
        groups = self._group_chunks_for_digest(docs)
        if not groups:
            return []
        llm = self._get_llm_with_temperature(0.2)
        digest_docs = []
        system_prompt = (
            "Summarize the provided content into concise bullet points. "
            "Focus on entities, dates, decisions, and key statements. "
            "Use bullets only with no introductory text."
        )
        for digest_index, (group_docs, section_title) in enumerate(groups, start=1):
            chunk_ids = [
                (doc.metadata or {}).get("chunk_id")
                for doc in group_docs
                if (doc.metadata or {}).get("chunk_id") is not None
            ]
            compact_ids = self._compact_chunk_ids(chunk_ids)
            group_text = "\n\n".join(doc.page_content for doc in group_docs)
            if section_title:
                human_content = (
                    f"Section title: {section_title}\n\nContent:\n{group_text}"
                )
            else:
                human_content = f"Content:\n{group_text}"
            response = llm.invoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=human_content),
                ]
            )
            metadata = {
                "doc_type": "digest",
                "ingest_id": ingest_id,
                "source": source_basename,
                "digest_id": f"{ingest_id}-{digest_index}",
                "child_chunk_ids": compact_ids,
            }
            if section_title:
                metadata["section_title"] = section_title
            if doc_title:
                metadata["doc_title"] = doc_title
            digest_docs.append(
                Document(page_content=response.content.strip(), metadata=metadata)
            )
        return digest_docs

    def _build_mini_digest_documents(self, docs, query):
        groups = self._group_chunks_for_digest(docs)
        if not groups:
            return []
        llm = self._get_llm_with_temperature(0.2)
        digest_docs = []
        system_prompt = (
            "Summarize the provided content into concise bullet points for routing. "
            "Focus on entities, dates, decisions, and key statements that are useful "
            "for answering the user's query. Use bullets only with no introductory text."
        )
        for digest_index, (group_docs, section_title) in enumerate(groups, start=1):
            chunk_ids = [
                (doc.metadata or {}).get("chunk_id")
                for doc in group_docs
                if (doc.metadata or {}).get("chunk_id") is not None
            ]
            compact_ids = self._compact_chunk_ids(chunk_ids)
            group_text = "\n\n".join(doc.page_content for doc in group_docs)
            if section_title:
                human_content = (
                    f"User query: {query}\n"
                    f"Section title: {section_title}\n\nContent:\n{group_text}"
                )
            else:
                human_content = f"User query: {query}\n\nContent:\n{group_text}"
            response = llm.invoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=human_content),
                ]
            )
            metadata = {
                "doc_type": "mini_digest",
                "digest_id": f"mini-{digest_index}",
                "child_chunk_ids": compact_ids,
            }
            if section_title:
                metadata["section_title"] = section_title
            digest_docs.append(
                Document(page_content=response.content.strip(), metadata=metadata)
            )
        return digest_docs

    def _route_with_mini_digest(self, docs, query, final_k):
        if not docs:
            return []
        docs_sorted = sorted(
            docs,
            key=lambda doc: (
                (doc.metadata or {}).get("chunk_id", 0),
                (doc.metadata or {}).get("source", ""),
            ),
        )
        digest_docs = self._build_mini_digest_documents(docs_sorted, query)
        if not digest_docs:
            return docs_sorted
        embeddings = self.get_embeddings()
        digest_texts = [doc.page_content for doc in digest_docs]
        digest_vectors = embeddings.embed_documents(digest_texts)
        query_vector = embeddings.embed_query(query)

        def _cosine_similarity(a, b):
            dot = sum(x * y for x, y in zip(a, b))
            norm_a = sum(x * x for x in a) ** 0.5
            norm_b = sum(y * y for y in b) ** 0.5
            if norm_a == 0 or norm_b == 0:
                return 0.0
            return dot / (norm_a * norm_b)

        scored = [
            (idx, _cosine_similarity(vec, query_vector))
            for idx, vec in enumerate(digest_vectors)
        ]
        scored.sort(key=lambda item: item[1], reverse=True)
        target_digest_k = min(max(3, final_k), len(scored))
        selected_digest_ids = {idx for idx, _score in scored[:target_digest_k]}
        selected_chunk_ids = set()
        for idx in selected_digest_ids:
            metadata = digest_docs[idx].metadata or {}
            selected_chunk_ids.update(
                self._expand_compact_chunk_ids(metadata.get("child_chunk_ids", ""))
            )
        if not selected_chunk_ids:
            return docs_sorted
        routed_docs = [
            doc
            for doc in docs_sorted
            if (doc.metadata or {}).get("chunk_id") in selected_chunk_ids
        ]
        return routed_docs or docs_sorted

    @staticmethod
    def _is_chroma_persist_dir(path):
        if not os.path.isdir(path):
            return False
        return os.path.exists(os.path.join(path, "chroma.sqlite3")) or os.path.exists(
            os.path.join(path, "index")
        )

    def _has_digest_collection(self, persist_dir):
        if not persist_dir or not os.path.isdir(persist_dir):
            return False
        try:
            from langchain_chroma import Chroma
        except ImportError:
            return False
        try:
            digest_store = Chroma(
                collection_name=DIGEST_COLLECTION_NAME,
                embedding_function=self.get_embeddings(),
                persist_directory=persist_dir,
            )
        except Exception:
            return False
        count = None
        if hasattr(digest_store, "_collection"):
            try:
                count = digest_store._collection.count()
            except Exception:
                count = None
        if count is None and hasattr(digest_store, "count"):
            try:
                count = digest_store.count()
            except Exception:
                count = None
        return bool(count)

    @staticmethod
    def _format_index_label(path, collection_name=RAW_COLLECTION_NAME):
        try:
            label = os.path.relpath(path, os.getcwd())
        except ValueError:
            label = path
        if collection_name and collection_name != RAW_COLLECTION_NAME:
            return f"{label} (digest)"
        return label

    def _list_existing_indexes(self):
        db_type = self.vector_db_type.get()
        indexes = []
        if db_type == "chroma":
            base_dir = self._get_chroma_persist_root()
            if os.path.isdir(base_dir):
                if self._is_chroma_persist_dir(base_dir):
                    indexes.append(base_dir)
                for entry in sorted(os.listdir(base_dir)):
                    path = os.path.join(base_dir, entry)
                    if self._is_chroma_persist_dir(path):
                        indexes.append(path)
        return indexes

    def _refresh_existing_indexes(self):
        indexes = self._list_existing_indexes()
        display_values = ["(default)"]
        self.existing_index_paths = {}
        for path in indexes:
            raw_label = self._format_index_label(path, RAW_COLLECTION_NAME)
            display_values.append(raw_label)
            self.existing_index_paths[raw_label] = (path, RAW_COLLECTION_NAME)
            digest_label = self._format_index_label(path, DIGEST_COLLECTION_NAME)
            display_values.append(digest_label)
            self.existing_index_paths[digest_label] = (path, DIGEST_COLLECTION_NAME)
        if hasattr(self, "cb_existing_index"):
            self.cb_existing_index["values"] = display_values
        if self.existing_index_var.get() not in display_values:
            if self.selected_index_path:
                candidate = self._format_index_label(
                    self.selected_index_path, self.selected_collection_name
                )
                if candidate in display_values:
                    self.existing_index_var.set(candidate)
                else:
                    self.existing_index_var.set("(default)")
            else:
                self.existing_index_var.set("(default)")

    def _get_selected_index_path(self):
        selection = self.existing_index_var.get()
        if not selection or selection == "(default)":
            return self.selected_index_path, self.selected_collection_name
        return self.existing_index_paths.get(selection, (selection, RAW_COLLECTION_NAME))

    def _on_existing_index_change(self, _event=None):
        selected_path, selected_collection = self._get_selected_index_path()
        if not selected_path:
            return
        self.selected_index_path = selected_path
        self.selected_collection_name = selected_collection
        self.save_config()
        threading.Thread(
            target=self._load_existing_index,
            args=(selected_path, selected_collection),
            daemon=True,
        ).start()

    def _load_existing_index(self, selected_path, selected_collection):
        try:
            self.log(
                "Loading existing index from "
                f"{self._format_index_label(selected_path, selected_collection)}..."
            )
            db_type = self.vector_db_type.get()
            embeddings = self.get_embeddings()
            if db_type == "chroma":
                try:
                    from langchain_chroma import Chroma
                except ImportError as err:
                    self._prompt_dependency_install(
                        ["langchain-chroma", "chromadb"], "Chroma vector store", err
                    )
                    return
                self.vector_store = Chroma(
                    collection_name=selected_collection,
                    embedding_function=embeddings,
                    persist_directory=selected_path,
                )
                self._ensure_lexical_db()
                self.index_embedding_signature = self._current_embedding_signature()
                self.save_config()
                self.log(
                    "Active index set to "
                    f"{self._format_index_label(selected_path, selected_collection)}."
                )
            elif db_type == "weaviate":
                self.log(
                    "Weaviate indexes must be loaded via server connection. "
                    "Please ingest or connect first."
                )
            else:
                self.log(f"Unknown vector DB type: {db_type}")
        except Exception as exc:
            self.log(f"Failed to load existing index: {exc}")

    def check_dependencies(self):
        def has_module(module_name):
            return importlib.util.find_spec(module_name) is not None

        missing_modules = []
        missing_packages = set()
        mismatched_symbols = []

        def record_missing(module_name, packages, context=None):
            label = module_name if context is None else f"{module_name} ({context})"
            missing_modules.append(label)
            missing_packages.update(packages)

        def check_module(module_name, packages, context=None):
            if has_module(module_name):
                return True
            record_missing(module_name, packages, context=context)
            return False

        def check_symbol(module_name, symbol_name, packages, context=None):
            try:
                module = __import__(module_name, fromlist=[symbol_name])
                getattr(module, symbol_name)
                return True
            except (ImportError, AttributeError) as err:
                detail = f"{module_name}.{symbol_name}"
                detail_context = context or "import"
                record_missing(detail, packages, context=detail_context)
                self.log(f"Dependency import failed for {detail}: {err}")
                return False

        def check_any_symbol(module_name, symbol_names, packages, context=None):
            try:
                module = __import__(module_name, fromlist=symbol_names)
            except ImportError as err:
                detail_context = context or "import"
                record_missing(module_name, packages, context=detail_context)
                self.log(f"Dependency import failed for {module_name}: {err}")
                return False
            for symbol_name in symbol_names:
                if hasattr(module, symbol_name):
                    return True
            detail = f"{module_name}.[{', '.join(symbol_names)}]"
            detail_context = context or "API mismatch"
            record_missing(detail, packages, context=detail_context)
            self.log(
                f"{module_name} is installed but missing expected symbols "
                f"{', '.join(symbol_names)}. This is likely an API mismatch; "
                "please upgrade or downgrade langchain-voyageai."
            )
            return False

        core_checks = {
            "langchain": ["langchain"],
            "chromadb": ["chromadb"],
            "bs4": ["beautifulsoup4"],
            "tiktoken": ["tiktoken"],
        }
        for module_name, packages in core_checks.items():
            check_module(module_name, packages)

        llm_provider = self.llm_provider.get()
        embedding_provider = self.embedding_provider.get()
        vector_db_type = self.vector_db_type.get()

        llm_checks = {
            "openai": ("langchain_openai", "ChatOpenAI", ["langchain-openai"]),
            "anthropic": ("langchain_anthropic", "ChatAnthropic", ["langchain-anthropic"]),
            "google": (
                "langchain_google_genai",
                "ChatGoogleGenerativeAI",
                ["langchain-google-genai"],
            ),
            "local_lm_studio": ("langchain_openai", "ChatOpenAI", ["langchain-openai"]),
        }
        if llm_provider in llm_checks:
            module_name, symbol_name, packages = llm_checks[llm_provider]
            check_symbol(
                module_name,
                symbol_name,
                packages,
                context=f"LLM provider {llm_provider}",
            )

        embedding_checks = {
            "openai": ("langchain_openai", "OpenAIEmbeddings", ["langchain-openai"]),
            "google": (
                "langchain_google_genai",
                "GoogleGenerativeAIEmbeddings",
                ["langchain-google-genai"],
            ),
            "local_huggingface": (
                "langchain_community.embeddings",
                "HuggingFaceEmbeddings",
                ["langchain-community"],
            ),
        }
        if embedding_provider in embedding_checks:
            module_name, symbol_name, packages = embedding_checks[embedding_provider]
            check_symbol(
                module_name,
                symbol_name,
                packages,
                context=f"embedding provider {embedding_provider}",
            )
        if embedding_provider == "voyage":
            check_any_symbol(
                "langchain_voyageai",
                ["VoyageAIEmbeddings", "VoyageEmbeddings"],
                ["langchain-voyageai"],
                context="embedding provider voyage",
            )

        vector_checks = {
            "chroma": ("langchain_chroma", "Chroma", ["langchain-chroma", "chromadb"]),
            "weaviate": (
                "langchain_weaviate",
                "WeaviateVectorStore",
                ["langchain-weaviate", "weaviate-client"],
            ),
        }
        if vector_db_type in vector_checks:
            module_name, symbol_name, packages = vector_checks[vector_db_type]
            check_symbol(
                module_name,
                symbol_name,
                packages,
                context=f"vector DB {vector_db_type}",
            )
            if vector_db_type == "weaviate":
                check_module("weaviate", ["weaviate-client"], context="weaviate client")

        if self.use_reranker.get() and self.api_keys["cohere"].get():
            check_symbol(
                "langchain_cohere",
                "CohereRerank",
                ["langchain-cohere"],
                context="Cohere reranker",
            )

        if missing_packages:
            if missing_modules:
                self.log(
                    "Missing dependencies detected: "
                    + ", ".join(sorted(missing_modules))
                )
            self.prompt_install(sorted(missing_packages))
            return

        if mismatched_symbols:
            self.log(
                "Installed packages found, but expected symbols are missing: "
                + ", ".join(sorted(mismatched_symbols))
            )
            return

        self.log("All required dependencies found.")

    def reinstall_dependencies(self):
        packages = self._get_required_packages()
        if messagebox.askyesno(
            "Install Dependencies",
            "Install or re-install required libraries now?",
        ):
            threading.Thread(
                target=self.install_packages,
                args=(packages, ["--upgrade", "--force-reinstall"]),
                daemon=True,
            ).start()
        else:
            self.log("Dependency install canceled.")

    def prompt_install(self, packages):
        if messagebox.askyesno(
            "Missing Dependencies", "Required libraries are missing. Install them automatically now?"
        ):
            threading.Thread(
                target=self.install_packages, args=(packages,), daemon=True
            ).start()
        else:
            self.log("Dependencies missing. App may crash.")

    def _prompt_dependency_install(self, packages, label, err):
        self.log(f"{label} dependency issue: {err}")
        if not self.dependency_prompted:
            self.dependency_prompted = True
            self.prompt_install(packages)

    def install_packages(self, packages, extra_args=None):
        self.log("Starting automatic installation...")
        cmd = [sys.executable, "-m", "pip", "install"]
        if extra_args:
            cmd.extend(extra_args)
        cmd.extend(packages)

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True,
            )

            for line in process.stdout:
                self.log(line.strip())

            process.wait()

            if process.returncode == 0:
                self.log("Installation Complete! Please restart the application.")
                messagebox.showinfo(
                    "Restart Required",
                    "Dependencies installed successfully.\n\nPlease close and restart the application.",
                )
            else:
                stderr = process.stderr.read()
                self.log(f"Installation Failed: {stderr}")
                messagebox.showerror(
                    "Installation Failed", "Could not install dependencies. Check logs."
                )

        except Exception as e:
            self.log(f"Installation Error: {e}")

    def browse_file(self):
        f = filedialog.askopenfilename(filetypes=[("HTML/Text", "*.html *.htm *.txt")])
        if f:
            self.selected_file = f
            self.lbl_file.config(text=f, foreground="black")
            self._update_file_info()

    def clear_selected_file(self):
        self.selected_file = None
        self.lbl_file.config(text="No file selected", foreground="gray")
        if hasattr(self, "lbl_file_info"):
            self.lbl_file_info.config(text="")

    def _update_file_info(self):
        if not self.selected_file:
            return
        try:
            size_bytes = os.path.getsize(self.selected_file)
            size_label = self._humanize_bytes(size_bytes)
            self.lbl_file_info.config(text=f"File size: {size_label}")
        except OSError:
            self.lbl_file_info.config(text="")

    def _validate_model_settings(self):
        try:
            temperature = float(self.llm_temperature.get())
        except (TypeError, ValueError):
            self._run_on_ui(
                messagebox.showerror, "Invalid Temperature", "Temperature must be a number."
            )
            return None

        if not 0 <= temperature <= 2:
            self._run_on_ui(
                messagebox.showerror,
                "Invalid Temperature",
                "Temperature must be between 0 and 2.",
            )
            return None

        try:
            max_tokens = int(self.llm_max_tokens.get())
        except (TypeError, ValueError):
            self._run_on_ui(
                messagebox.showerror, "Invalid Max Tokens", "Max tokens must be an integer."
            )
            return None

        if max_tokens <= 0:
            self._run_on_ui(
                messagebox.showerror,
                "Invalid Max Tokens",
                "Max tokens must be a positive integer.",
            )
            return None

        return temperature, max_tokens

    def get_model_caps(self, provider: str, model: str) -> dict:
        provider_name = (provider or "").strip().lower()
        model_name = (model or "").strip().lower()

        caps = {
            "max_context_tokens": 8192,
            "max_output_tokens": 2048,
        }

        provider_defaults = {
            "openai": {"max_context_tokens": 128000, "max_output_tokens": 4096},
            "anthropic": {
                "max_context_tokens": 200000,
                "max_output_tokens": 4096,
            },
            "google": {"max_context_tokens": 32000, "max_output_tokens": 4096},
            "local_lm_studio": {
                "max_context_tokens": 8192,
                "max_output_tokens": 2048,
            },
        }
        caps.update(provider_defaults.get(provider_name, {}))

        model_overrides = {
            "openai": [
                (r"gpt-4o|o4-mini", 128000, 16384),
                (r"gpt-4\.1", 1000000, 16384),
                (r"gpt-4-turbo", 128000, 4096),
                (r"gpt-4", 8192, 2048),
                (r"gpt-3\.5-turbo", 16384, 4096),
            ],
            "anthropic": [
                (r"claude-(opus|sonnet|haiku)-4", 200000, 8192),
                (r"claude-3\.7-sonnet", 200000, 8192),
                (r"claude-3\.5-(sonnet|haiku)", 200000, 8192),
                (r"claude-3-(opus|sonnet|haiku)", 200000, 4096),
            ],
        }
        for pattern, max_context_tokens, max_output_tokens in model_overrides.get(
            provider_name, []
        ):
            if re.search(pattern, model_name):
                caps["max_context_tokens"] = max_context_tokens
                caps["max_output_tokens"] = max_output_tokens
                break

        return caps

    def _get_capped_output_tokens(self, provider: str, model_name: str, requested_max_tokens: int) -> int:
        requested = max(1, int(requested_max_tokens))
        caps = self.get_model_caps(provider, model_name)
        capped = max(1, int(caps.get("max_output_tokens", requested)))
        return min(requested, capped)

    def _get_system_instructions(self):
        instructions = self.system_instructions.get().strip()
        if not instructions:
            instructions = self.default_system_instructions
            self.system_instructions.set(instructions)
            self._run_on_ui(self._refresh_instructions_box)
        return instructions

    def _get_output_style_instruction(self):
        style = self.output_style.get().strip()
        if not style or style == "Default answer":
            return ""
        style_instructions = {
            "Detailed answer": (
                "Output style: Detailed answer. Provide a thorough, well-structured "
                "response with clear sections, concrete details, and explicit coverage "
                "of requested items. Keep formatting readable with headings and bullets "
                "as needed."
            ),
            "Brief / exec summary": (
                "Output style: Brief / exec summary. Provide a concise executive summary "
                "in 3-6 bullets or short paragraphs, focusing on key outcomes only."
            ),
            "Script / talk track": (
                "Output style: Script / talk track. Provide a short talk track or script "
                "with speaker-ready phrasing, organized as numbered beats or bullet points. "
                "Include at least one short verbatim quote (<=25 words) per major section "
                "with a [Chunk N] citation."
            ),
            "Structured report": (
                "Output style: Structured report. Use clear section headings such as "
                "Summary, Findings, Evidence, and Gaps/Unknowns. Use bullets within sections "
                "where helpful. Include at least one short verbatim quote (<=25 words) per "
                "major section with a [Chunk N] citation."
            ),
        }
        return style_instructions.get(style, "")

    """
    Evidence-pack behavior notes:
    1) Evidence-pack query flow does not cap final_k; it respects GUI iterations >3 and
       outputs an incident-led pack.
    2) Corpus includes Jan 6 + Jan 16 incidents, so retrieval includes them unless
       final_k/budget is too small.
    3) Outputs omit unsupported details, include no placeholders, and no user-supplementation requests.
    4) Grievance-export regression: ChatGPT HTML role parsing yields user evidence prioritized
       and prevents missing-key-incident scenarios.
    """
    def is_evidence_pack_query(self, query, output_style):
        normalized = f"{query} {output_style}".lower()
        keywords = [
            "evidence pack",
            "chronology",
            "timeline",
            "grievance",
            "when did it happen",
            "impact",
            "examples",
        ]
        return any(keyword in normalized for keyword in keywords)

    def _get_evidence_pack_instruction(self):
        return (
            "Evidence pack mode: Build a structured evidence pack with a clear chronology/timeline "
            "of events, explicit impacts, grievances, and concrete examples. Emphasize dates, actors, "
            "actions, outcomes, and supporting quotes. Only include claims supported by context; "
            "omit details not present in context. Write incident entries using: When; What happened; "
            "Impact; Evidence (chunk citations). Do not provide coaching or advice. Ensure the output "
            "contains no placeholders and does not ask for more docs or missing info. If evidence is "
            "thin, allow one short 'Scope:' note at the top."
        )

    def _format_month_label(self, year, month):
        month_label = MONTH_INDEX_TO_LABEL.get(month)
        if not month_label:
            return None
        return f"{month_label} {year}"

    def _month_sort_key(self, month_label):
        if not month_label:
            return (9999, 99)
        parts = month_label.split()
        if len(parts) != 2:
            return (9999, 99)
        month_part, year_part = parts
        month_index = MONTH_NAME_TO_INDEX.get(month_part.lower(), 99)
        try:
            year_value = int(year_part)
        except ValueError:
            year_value = 9999
        return (year_value, month_index)

    def _extract_month_years(self, text):
        if not text:
            return set()
        months = set()
        month_name_re = re.compile(
            r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
            r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|"
            r"Dec(?:ember)?)\s+(\d{4})\b",
            re.IGNORECASE,
        )
        for match in month_name_re.finditer(text):
            month_index = MONTH_NAME_TO_INDEX.get(match.group(1).lower())
            if not month_index:
                continue
            try:
                year_value = int(match.group(2))
            except ValueError:
                continue
            label = self._format_month_label(year_value, month_index)
            if label:
                months.add(label)
        iso_date_re = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
        for match in iso_date_re.finditer(text):
            try:
                year_value = int(match.group(1))
                month_index = int(match.group(2))
            except ValueError:
                continue
            if 1 <= month_index <= 12:
                label = self._format_month_label(year_value, month_index)
                if label:
                    months.add(label)
        year_month_re = re.compile(r"\b(\d{4})-(\d{2})\b")
        for match in year_month_re.finditer(text):
            try:
                year_value = int(match.group(1))
                month_index = int(match.group(2))
            except ValueError:
                continue
            if 1 <= month_index <= 12:
                label = self._format_month_label(year_value, month_index)
                if label:
                    months.add(label)
        slash_full_re = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
        for match in slash_full_re.finditer(text):
            try:
                month_index = int(match.group(1))
                year_value = int(match.group(3))
            except ValueError:
                continue
            if 1 <= month_index <= 12:
                label = self._format_month_label(year_value, month_index)
                if label:
                    months.add(label)
        slash_re = re.compile(r"\b(\d{1,2})/(\d{4})\b")
        for match in slash_re.finditer(text):
            try:
                month_index = int(match.group(1))
                year_value = int(match.group(2))
            except ValueError:
                continue
            if 1 <= month_index <= 12:
                label = self._format_month_label(year_value, month_index)
                if label:
                    months.add(label)
        return months

    def _extract_date_tokens(self, text):
        if not text:
            return set()
        tokens = set()
        patterns = [
            r"\b\d{4}-\d{2}-\d{2}\b",
            r"\b\d{4}-\d{2}\b",
            r"\b\d{1,2}/\d{1,2}/\d{4}\b",
            r"\b\d{1,2}/\d{4}\b",
            r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
            r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|"
            r"Dec(?:ember)?)\s+\d{4}\b",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                tokens.add(match.group(0))
        return tokens

    def _extract_channels(self, docs):
        channels = set()
        for doc in docs:
            metadata = getattr(doc, "metadata", {}) or {}
            source = str(
                metadata.get("source")
                or metadata.get("file_path")
                or metadata.get("filename")
                or ""
            )
            content = (getattr(doc, "page_content", "") or "").strip()
            channel = metadata.get("channel_type") or self._extract_channel(
                f"{source}\n{content}"
            )
            if channel:
                channels.add(channel)
        return channels

    def _compute_unique_incidents(self, docs):
        incidents = set()
        for doc in docs:
            metadata = getattr(doc, "metadata", {}) or {}
            source = (
                metadata.get("source")
                or metadata.get("file_path")
                or metadata.get("filename")
                or "unknown"
            )
            content = (doc.page_content or "").strip()
            months = sorted(self._extract_month_years(content), key=self._month_sort_key)
            date_tokens = sorted(self._extract_date_tokens(content))
            if months:
                key_basis = months[0]
            elif date_tokens:
                key_basis = date_tokens[0]
            else:
                key_basis = re.sub(r"\s+", " ", content)[:80]
            if not key_basis:
                key_basis = "unknown"
            incidents.add(f"{source}|{key_basis}".lower())
        return len(incidents)

    def _extract_months_and_tokens(self, docs):
        months = set()
        tokens = set()
        for doc in docs:
            content = doc.page_content or ""
            months.update(self._extract_month_years(content))
            tokens.update(self._extract_date_tokens(content))
        return months, tokens

    def _review_evidence_pack_coverage(self, candidate_docs, selected_docs):
        candidate_months, candidate_tokens = self._extract_months_and_tokens(
            candidate_docs
        )
        selected_months, _ = self._extract_months_and_tokens(selected_docs)
        missing_months = sorted(
            candidate_months - selected_months, key=self._month_sort_key
        )
        unique_incidents = self._compute_unique_incidents(selected_docs)
        channels = self._extract_channels(candidate_docs)
        return unique_incidents, missing_months, channels, candidate_tokens

    def _generate_follow_up_queries(
        self, base_query, missing_months, channels, date_tokens, max_queries=8
    ):
        queries = []
        channel_list = sorted(channels)
        for month in missing_months:
            if channel_list:
                for channel in channel_list[:3]:
                    queries.append(
                        f"{base_query} {month} {channel} incident timeline"
                    )
            else:
                queries.append(f"{base_query} {month} incident timeline")
        for token in sorted(date_tokens)[:4]:
            queries.append(f"{base_query} {token} incident details")
        deduped = []
        seen = set()
        for candidate in queries:
            key = candidate.lower().strip()
            if key and key not in seen:
                seen.add(key)
                deduped.append(candidate)
            if len(deduped) >= max_queries:
                break
        return deduped

    def _extract_chunks(self, context_text):
        chunks = {}
        matches = list(re.finditer(r"^\[Chunk (\d+)[^\]]*\]\n", context_text, re.M))
        for idx, match in enumerate(matches):
            chunk_num = int(match.group(1))
            start = match.end()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(context_text)
            chunks[chunk_num] = context_text[start:end].strip()
        return chunks

    def _split_major_sections(self, answer_text):
        lines = answer_text.splitlines()
        sections = []
        current = []

        def _flush():
            if current:
                section_text = "\n".join(current).strip()
                if section_text:
                    sections.append(section_text)

        for line in lines:
            if re.match(r"^\s*#{1,6}\s+\S", line) or re.match(
                r"^[A-Za-z][A-Za-z /&-]{0,50}:$", line.strip()
            ):
                _flush()
                current = [line]
            else:
                current.append(line)
        _flush()
        return sections or [answer_text.strip()]

    def _find_quotes(self, text):
        quotes = []
        paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
        for paragraph in paragraphs:
            for match in re.finditer(r"\"([^\"]+)\"", paragraph):
                quote_text = match.group(1).strip()
                if quote_text:
                    quotes.append((quote_text, paragraph))
        return quotes

    def _validate_answer(self, answer_text, context_text, output_style):
        failures = []
        citation_re = re.compile(r"\[Chunk (\d+)\]")
        heading_re = re.compile(r"^\s{0,3}#{1,6}\s+\S+")
        setext_re = re.compile(r"^[=-]{3,}\s*$")
        verb_re = re.compile(
            r"\b("
            r"is|are|was|were|be|been|being|"
            r"has|have|had|"
            r"does|do|did|"
            r"shows?|indicates?|suggests?|states?|notes?|reports?|"
            r"causes?|led|leads?|resulted|results?|"
            r"increases?|decreases?|"
            r"includes?|including|"
            r"found|finds?|observed|estimated|expected|"
            r"according"
            r")\b",
            re.IGNORECASE,
        )
        structural_labels = {
            "executive summary",
            "summary",
            "overview",
            "timeline",
            "background",
            "context",
            "approach",
            "methodology",
            "analysis",
            "findings",
            "discussion",
            "recommendations",
            "next steps",
            "conclusion",
            "appendix",
        }
        min_citation_chars = 40

        def is_structural_paragraph(paragraph_text: str) -> bool:
            lines = [line.strip() for line in paragraph_text.splitlines() if line.strip()]
            if not lines:
                return True
            if len(lines) == 1:
                line = lines[0]
                if heading_re.match(line):
                    return True
                if line.rstrip(":").strip().lower() in structural_labels:
                    return True
                if line.endswith(":") and len(line.split()) <= 5:
                    return True
            if len(lines) == 2 and setext_re.match(lines[1]):
                return True
            return False

        def needs_citation(paragraph_text: str) -> bool:
            if is_structural_paragraph(paragraph_text):
                return False
            alnum_match = re.search(r"[A-Za-z0-9]", paragraph_text)
            if not alnum_match:
                return False
            if verb_re.search(paragraph_text):
                return True
            return len(paragraph_text.strip()) >= min_citation_chars

        paragraphs = [p for p in re.split(r"\n\s*\n", answer_text) if p.strip()]
        for paragraph in paragraphs:
            if needs_citation(paragraph) and not citation_re.search(paragraph):
                failures.append(
                    "Factual paragraph missing at least one [Chunk N] citation."
                )

        if output_style in {"Script / talk track", "Structured report"}:
            chunks = self._extract_chunks(context_text)
            sections = self._split_major_sections(answer_text)
            for index, section in enumerate(sections, start=1):
                quotes = self._find_quotes(section)
                section_has_quote = False
                for quote_text, paragraph in quotes:
                    word_count = len(quote_text.split())
                    if word_count > 25:
                        continue
                    citations = citation_re.findall(paragraph)
                    for citation in citations:
                        chunk_num = int(citation)
                        chunk_text = chunks.get(chunk_num, "")
                        if quote_text in chunk_text:
                            section_has_quote = True
                            break
                    if section_has_quote:
                        break
                if not section_has_quote:
                    failures.append(
                        "Missing short verbatim quote (<=25 words) with valid citation "
                        f"in section {index}."
                    )

        return len(failures) == 0, failures

    def _repair_answer(self, draft_text, context_text, failures, output_style):
        repair_llm = self._get_llm_with_temperature(0.0)
        failure_text = "\n".join(f"- {item}" for item in failures)
        repair_prompt = (
            "You are a repair assistant. Fix the draft using ONLY the provided context. "
            "Rules: remove unsupported content, add correct [Chunk N] citations to every "
            "factual paragraph, include no placeholders, and omit unsupported content. "
            "Omit unsupported claims; deepen supported ones; do not ask for more docs or missing info; "
            "do not use placeholders. If evidence is thin, you may include one short 'Scope:' note "
            "at the top. "
            "For Script / talk track and Structured report styles, ensure at least one short "
            "verbatim quote (<=25 words) per major section with a [Chunk N] citation, and "
            "the quote must appear in the cited chunk text. "
            "Output ONLY the repaired answer."
        )
        repair_messages = [
            SystemMessage(content=repair_prompt),
            HumanMessage(
                content=(
                    f"OUTPUT_STYLE: {output_style}\n\n"
                    f"FAILURES:\n{failure_text}\n\n"
                    f"CONTEXT:\n{context_text}\n\n"
                    f"DRAFT:\n{draft_text}"
                )
            ),
        ]
        repaired = repair_llm.invoke(repair_messages)
        return repaired.content

    def _validate_and_repair(self, answer_text, context_text, iteration_id=None):
        output_style = self.output_style.get().strip()
        agentic_mode = self.agentic_mode.get()
        is_valid, failures = self._validate_answer(
            answer_text, context_text, output_style
        )
        if is_valid:
            if iteration_id is not None:
                self.log(
                    "Iter "
                    f"{iteration_id} repair | style={output_style}, "
                    f"agentic={int(agentic_mode)}, triggered=0, failures=none"
                )
            return answer_text
        self.log(
            "Validation failed; triggering repair pass. Reasons: "
            + "; ".join(failures)
        )
        if iteration_id is not None:
            self.log(
                "Iter "
                f"{iteration_id} repair | style={output_style}, "
                f"agentic={int(agentic_mode)}, triggered=1, failures="
                + "; ".join(failures)
            )
        repaired = self._repair_answer(answer_text, context_text, failures, output_style)
        repaired = self._append_missing_citations(repaired, context_text)
        return repaired

    def _append_missing_citations(self, answer_text, context_text):
        citation_re = re.compile(r"\[Chunk (\d+)\]")
        paragraphs = [p for p in re.split(r"\n\s*\n", answer_text) if p.strip()]
        missing = [
            idx
            for idx, paragraph in enumerate(paragraphs)
            if re.search(r"[A-Za-z0-9]", paragraph)
            and not citation_re.search(paragraph)
        ]
        if not missing:
            return answer_text

        chunks = self._extract_chunks(context_text)
        if not chunks:
            return answer_text

        def _tokens(text):
            return set(re.findall(r"[A-Za-z0-9]{4,}", text.lower()))

        chunk_tokens = {num: _tokens(text) for num, text in chunks.items()}
        updated = list(paragraphs)
        for idx in missing:
            paragraph = paragraphs[idx]
            paragraph_tokens = _tokens(paragraph)
            best_chunk = None
            best_score = 0
            for chunk_num in sorted(chunk_tokens):
                score = len(paragraph_tokens & chunk_tokens[chunk_num])
                if score > best_score:
                    best_score = score
                    best_chunk = chunk_num
            if best_chunk and best_score > 0:
                updated[idx] = paragraph.rstrip() + f" [Chunk {best_chunk}]"
        return "\n\n".join(updated)

    def _refresh_instructions_box(self):
        self.instructions_box.delete("1.0", tk.END)
        self.instructions_box.insert(tk.END, self.system_instructions.get())

    def _resolve_llm_model(self):
        selected = self.llm_model.get().strip()
        custom = self.llm_model_custom.get().strip()
        if selected == "custom":
            if not custom:
                raise ValueError("Custom generation model is selected but empty")
            return custom
        return selected or custom

    def _resolve_embedding_model(self):
        selected = self.embedding_model.get().strip()
        custom = self.embedding_model_custom.get().strip()
        if selected == "custom":
            if not custom:
                raise ValueError("Custom embedding model is selected but empty")
            return custom
        return selected or custom

    def get_embeddings(self):
        """Factory for embedding model"""
        provider = self.embedding_provider.get()
        api_key = self.api_keys[provider].get() if provider in self.api_keys else ""
        model_name = self._resolve_embedding_model()

        if provider == "openai":
            try:
                from langchain_openai import OpenAIEmbeddings
            except ImportError as err:
                self._prompt_dependency_install(
                    ["langchain-openai"], "OpenAI embeddings", err
                )
                raise

            if not api_key:
                raise ValueError("OpenAI API Key missing")
            return OpenAIEmbeddings(openai_api_key=api_key, model=model_name)

        if provider == "google":
            try:
                from langchain_google_genai import GoogleGenerativeAIEmbeddings
            except ImportError as err:
                self._prompt_dependency_install(
                    ["langchain-google-genai"], "Google embeddings", err
                )
                raise

            if not api_key:
                raise ValueError("Google API Key missing")
            return GoogleGenerativeAIEmbeddings(google_api_key=api_key, model=model_name)

        if provider == "voyage":
            try:
                from langchain_voyageai import VoyageAIEmbeddings
                embedding_cls = VoyageAIEmbeddings
            except ImportError as err:
                try:
                    module = __import__("langchain_voyageai", fromlist=["VoyageEmbeddings"])
                except ImportError as module_err:
                    self._prompt_dependency_install(
                        ["langchain-voyageai"], "Voyage embeddings", module_err
                    )
                    raise
                if hasattr(module, "VoyageEmbeddings"):
                    embedding_cls = module.VoyageEmbeddings
                else:
                    mismatch_msg = (
                        "langchain-voyageai is installed but does not export "
                        "VoyageAIEmbeddings or VoyageEmbeddings. This is likely an "
                        "API mismatch; please upgrade or downgrade langchain-voyageai."
                    )
                    self._prompt_dependency_install(
                        ["langchain-voyageai"], "Voyage embeddings (API mismatch)", mismatch_msg
                    )
                    raise ImportError(mismatch_msg) from err

            if not api_key:
                raise ValueError("Voyage API Key missing")
            return embedding_cls(voyage_api_key=api_key, model=model_name)

        if provider == "local_huggingface":
            # Uses local CPU/GPU via HuggingFace
            try:
                from langchain_community.embeddings import HuggingFaceEmbeddings
            except (ImportError, AttributeError) as err:
                self._prompt_dependency_install(
                    ["langchain-community"], "Local HuggingFace embeddings", err
                )
                raise

            resolved_model = model_name or "all-MiniLM-L6-v2"
            self.log(f"Loading local HuggingFace embeddings ({resolved_model})...")
            return HuggingFaceEmbeddings(model_name=resolved_model)

        raise ValueError(f"Unknown embedding provider: {provider}")

    def get_llm(self):
        """Factory for LLM"""
        validated = self._validate_model_settings()
        if not validated:
            raise ValueError("Invalid model settings")
        temperature, gui_llm_max_tokens = validated
        provider = self.llm_provider.get()
        model_name = self._resolve_llm_model()
        output_max_tokens = self._get_capped_output_tokens(
            provider, model_name, gui_llm_max_tokens
        )

        if provider == "openai":
            try:
                from langchain_openai import ChatOpenAI
            except ImportError as err:
                self._prompt_dependency_install(["langchain-openai"], "OpenAI LLM", err)
                raise

            key = self.api_keys["openai"].get()
            return ChatOpenAI(
                api_key=key,
                model=model_name,
                temperature=temperature,
                max_tokens=output_max_tokens,
            )

        if provider == "anthropic":
            try:
                from langchain_anthropic import ChatAnthropic
            except ImportError as err:
                self._prompt_dependency_install(
                    ["langchain-anthropic"], "Anthropic LLM", err
                )
                raise

            key = self.api_keys["anthropic"].get()
            return ChatAnthropic(
                api_key=key,
                model=model_name,
                temperature=temperature,
                max_tokens=output_max_tokens,
            )

        if provider == "google":
            try:
                from langchain_google_genai import ChatGoogleGenerativeAI
            except ImportError as err:
                self._prompt_dependency_install(
                    ["langchain-google-genai"], "Google LLM", err
                )
                raise

            key = self.api_keys["google"].get()
            return ChatGoogleGenerativeAI(
                google_api_key=key,
                model=model_name,
                temperature=temperature,
                max_output_tokens=output_max_tokens,
            )

        if provider == "local_lm_studio":
            try:
                from langchain_openai import ChatOpenAI
            except ImportError as err:
                self._prompt_dependency_install(
                    ["langchain-openai"], "Local LLM Studio", err
                )
                raise

            url = self.local_llm_url.get()
            self.log(f"Connecting to Local LLM at {url}...")
            # LM Studio uses OpenAI compatible endpoint
            return ChatOpenAI(
                base_url=url,
                api_key="lm-studio",
                model=model_name,
                temperature=temperature,
                max_tokens=output_max_tokens,
            )

        raise ValueError(f"Unknown LLM provider: {provider}")

    def _get_llm_with_temperature(self, temperature):
        original_temperature = self.llm_temperature.get()
        self.llm_temperature.set(temperature)
        try:
            return self.get_llm()
        finally:
            self.llm_temperature.set(original_temperature)

    def start_ingestion(self):
        if not self.selected_file:
            messagebox.showerror("Error", "Please select a file first.")
            return

        threading.Thread(target=self._ingest_process, daemon=True).start()

    def _ingest_process(self):
        try:
            self._run_on_ui(self.btn_ingest.config, state="disabled")
            self.log("Starting ingestion pipeline...")

            # 1. Load & Clean
            self.log("Step 1/4: Parsing File...")
            text_content = ""

            chatgpt_messages = None
            if self.selected_file.lower().endswith(".html"):
                from bs4 import BeautifulSoup
                from bs4 import NavigableString

                def _extract_chatgpt_messages(soup):
                    message_nodes = soup.select(
                        "div.message.user-message, div.message.assistant-message"
                    )
                    if not message_nodes:
                        return None
                    extracted = []
                    for node in message_nodes:
                        classes = node.get("class", [])
                        if "user-message" in classes:
                            role = "user"
                        elif "assistant-message" in classes:
                            role = "assistant"
                        else:
                            continue
                        timestamp = None
                        timestamp_node = node.find(class_="timestamp")
                        if timestamp_node:
                            timestamp = timestamp_node.get_text(" ", strip=True) or None
                            timestamp_node.extract()
                        content = node.get_text(" ", strip=True)
                        extracted.append(
                            {
                                "role": role,
                                "timestamp": timestamp,
                                "content": content,
                            }
                        )
                    return extracted

                def _append_text_line(lines, text):
                    clean = text.strip()
                    if clean:
                        lines.append(clean)

                def _process_table(table_tag, lines):
                    for row in table_tag.find_all("tr"):
                        cells = [
                            cell.get_text(" ", strip=True)
                            for cell in row.find_all(["th", "td"])
                        ]
                        if any(cells):
                            lines.append(" | ".join(cells))

                def _process_list(list_tag, lines):
                    for item in list_tag.find_all("li", recursive=False):
                        nested_lists = item.find_all(["ul", "ol"], recursive=False)
                        for nested in nested_lists:
                            nested.extract()
                        item_text = " ".join(item.stripped_strings)
                        if item_text:
                            lines.append(f"- {item_text}")
                        for nested in nested_lists:
                            _process_list(nested, lines)

                def _process_children(parent, lines):
                    for child in parent.children:
                        if isinstance(child, NavigableString):
                            _append_text_line(lines, str(child))
                            continue
                        if not hasattr(child, "name"):
                            continue
                        if child.name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
                            heading_text = child.get_text(" ", strip=True)
                            if heading_text:
                                lines.append(f"### {heading_text}")
                            continue
                        if child.name in {"ul", "ol"}:
                            _process_list(child, lines)
                            continue
                        if child.name == "table":
                            _process_table(child, lines)
                            continue
                        if child.name in {"p", "pre", "blockquote"}:
                            paragraph_text = child.get_text(" ", strip=True)
                            _append_text_line(lines, paragraph_text)
                            continue
                        _process_children(child, lines)

                with open(self.selected_file, "r", encoding="utf-8", errors="ignore") as f:
                    soup = BeautifulSoup(f, "html.parser")
                    doc_title = None
                    if soup.title and soup.title.string:
                        doc_title = soup.title.string.strip() or None
                    # Aggressive cleaning for RAG
                    for tag in soup(["script", "style", "svg", "path", "nav", "footer"]):
                        tag.extract()
                    chatgpt_messages = _extract_chatgpt_messages(soup)
                    if chatgpt_messages:
                        text_content = "\n".join(
                            msg["content"] for msg in chatgpt_messages if msg["content"]
                        )
                    else:
                        lines = []
                        root = soup.body or soup
                        _process_children(root, lines)
                        text_content = "\n".join(lines)
            else:
                with open(self.selected_file, "r", encoding="utf-8") as f:
                    text_content = f.read()
                doc_title = None

            self.log(f"File loaded. Raw text length: {len(text_content)} characters.")

            # 2. Split
            self.log("Step 2/4: Splitting Text...")
            try:
                from langchain.text_splitter import RecursiveCharacterTextSplitter
            except ImportError:
                from langchain_text_splitters import RecursiveCharacterTextSplitter

            chunk_ingest_id = datetime.utcnow().isoformat()
            source_basename = os.path.basename(self.selected_file)
            chatgpt_docs = None
            if chatgpt_messages:
                chatgpt_docs = []
                for index, message in enumerate(chatgpt_messages, start=1):
                    role = message["role"]
                    content = message["content"]
                    prefixed_content = f"[ROLE={role}] {content}".strip()
                    metadata = {
                        "speaker_role": role,
                        "message_index": index,
                        "evidence_kind": "primary" if role == "user" else "secondary",
                        "source": source_basename,
                        "chunk_id": index,
                        "ingest_id": chunk_ingest_id,
                    }
                    if message.get("timestamp"):
                        metadata["timestamp"] = message["timestamp"]
                    if doc_title:
                        metadata["doc_title"] = doc_title
                    chatgpt_docs.append(
                        Document(page_content=prefixed_content, metadata=metadata)
                    )

            if chatgpt_docs is not None:
                docs = chatgpt_docs
            else:
                splitter = RecursiveCharacterTextSplitter(
                    chunk_size=self.chunk_size.get(),
                    chunk_overlap=self.chunk_overlap.get(),
                    separators=["\n\n", "\n", ".", " ", ""],
                )
                docs = splitter.create_documents([text_content])

            def _last_section_title(text):
                last_heading = None
                for line in text.splitlines():
                    stripped = line.strip()
                    if stripped.startswith("### "):
                        candidate = stripped[4:].strip()
                        if candidate:
                            last_heading = candidate
                return last_heading

            if chatgpt_docs is None:
                last_section_title = None
                for chunk_id, doc in enumerate(docs, start=1):
                    section_title = _last_section_title(doc.page_content)
                    if section_title:
                        last_section_title = section_title
                    metadata = (doc.metadata or {}).copy()
                    metadata.update(
                        {
                            "source": source_basename,
                            "chunk_id": chunk_id,
                            "ingest_id": chunk_ingest_id,
                        }
                    )
                    if doc_title:
                        metadata["doc_title"] = doc_title
                    if last_section_title:
                        metadata["section_title"] = last_section_title
                    doc.metadata = metadata
            self.log(f"Created {len(docs)} text chunks.")

            db_type = self.vector_db_type.get()
            if db_type == "chroma":
                if self._upsert_lexical_chunks(docs):
                    self.log(f"Lexical sidecar updated: {self.lexical_db_path}")

            # 3. Initialize Vector DB & Embeddings
            self.log("Step 3/4: Initializing Vector Store...")
            embeddings = self.get_embeddings()

            new_index_path = None
            digest_docs = []

            if self.build_digest_index.get():
                if db_type == "chroma":
                    self.log("Building digest summaries...")
                    digest_docs = self._build_digest_documents(
                        docs, chunk_ingest_id, source_basename, doc_title
                    )
                    self.log(f"Prepared {len(digest_docs)} digest summaries.")
                else:
                    self.log("Digest indexing is only supported for Chroma. Skipping.")

            if db_type == "chroma":
                persist_root = self._get_chroma_persist_root()
                index_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                safe_stem = self._safe_file_stem(self.selected_file)
                persist_dir = os.path.join(
                    persist_root, f"{safe_stem}__{index_id}"
                )
                os.makedirs(persist_root, exist_ok=True)
                new_index_path = persist_dir
                try:
                    from langchain_chroma import Chroma
                except ImportError as err:
                    self._prompt_dependency_install(
                        ["langchain-chroma", "chromadb"], "Chroma vector store", err
                    )
                    raise

                # Using a new client per ingestion to ensure clean slate or append
                self.vector_store = Chroma(
                    collection_name=RAW_COLLECTION_NAME,
                    embedding_function=embeddings,
                    persist_directory=persist_dir,
                )
            elif db_type == "weaviate":
                try:
                    import weaviate
                    from langchain_weaviate import WeaviateVectorStore
                except ImportError as err:
                    self._prompt_dependency_install(
                        ["langchain-weaviate", "weaviate-client"],
                        "Weaviate vector store",
                        err,
                    )
                    raise

                url = self.api_keys["weaviate_url"].get()
                key = self.api_keys["weaviate_key"].get()
                auth = weaviate.auth.AuthApiKey(api_key=key) if key else None

                client = weaviate.Client(url=url, auth_client_secret=auth)
                self.vector_store = WeaviateVectorStore(
                    client=client, index_name="RagDocument", text_key="text", embedding=embeddings
                )
            else:
                raise ValueError(f"Unknown vector DB type: {db_type}")

            self.index_embedding_signature = self._current_embedding_signature()
            self.save_config()
            self._run_on_ui(self._refresh_compatibility_warning)

            # 4. Batch Embed & Upsert
            self.log("Step 4/4: Embedding & Storing (This takes time)...")
            batch_size = 100  # Adjust based on API limits
            total_docs = len(docs)

            self._run_on_ui(self.progress.config, maximum=total_docs, value=0)

            for i in range(0, total_docs, batch_size):
                batch = docs[i : i + batch_size]
                self.vector_store.add_documents(batch)
                self._run_on_ui(self.progress.config, value=i + len(batch))
                self.log(f"Indexed {min(i + batch_size, total_docs)}/{total_docs} chunks...")

            if digest_docs:
                self.log("Storing digest summaries...")
                digest_store = Chroma(
                    collection_name=DIGEST_COLLECTION_NAME,
                    embedding_function=embeddings,
                    persist_directory=persist_dir,
                )
                total_digests = len(digest_docs)
                for i in range(0, total_digests, batch_size):
                    batch = digest_docs[i : i + batch_size]
                    digest_store.add_documents(batch)
                self.log(f"Indexed {total_digests} digest summaries.")

            self.log("Ingestion Complete! You can now chat.")
            if new_index_path:
                def _select_new_index():
                    self._refresh_existing_indexes()
                    selection_label = self._format_index_label(new_index_path)
                    self.existing_index_var.set(selection_label)
                    self.selected_index_path = new_index_path
                    self.selected_collection_name = RAW_COLLECTION_NAME
                    self.save_config()
                self._run_on_ui(_select_new_index)
            else:
                self._run_on_ui(self._refresh_existing_indexes)
            self._run_on_ui(
                messagebox.showinfo,
                "Success",
                "File successfully ingested into Vector Database.",
            )

        except Exception as e:
            self.log(f"INGESTION ERROR: {str(e)}")
            self._run_on_ui(messagebox.showerror, "Error", f"Ingestion failed:\n{str(e)}")
        finally:
            self._run_on_ui(self.btn_ingest.config, state="normal")

    def send_message(self):
        query = self.txt_input.get()
        if not query:
            return

        self.txt_input.delete(0, tk.END)
        self.append_chat("user", f"You: {query}")
        self._append_history(HumanMessage(content=query))

        if self.index_embedding_signature:
            current_signature = self._current_embedding_signature()
            if (
                current_signature
                and current_signature != self.index_embedding_signature
                and not self.force_embedding_compat.get()
            ):
                self.append_chat(
                    "system",
                    "Embedding mismatch detected. Re-embed documents or enable force "
                    "compatibility to proceed.",
                )
                return

        if not self.vector_store:
            # Try to load existing DB if available
            try:
                self.log("Attempting to load existing Vector DB...")
                embeddings = self.get_embeddings()
                if self.vector_db_type.get() == "chroma":
                    selected_path, selected_collection = self._get_selected_index_path()
                    if not selected_path and self.selected_index_path:
                        if os.path.isdir(self.selected_index_path):
                            selected_path = self.selected_index_path
                    persist_dir = selected_path or self._get_chroma_persist_root()
                    collection_name = (
                        selected_collection or self.selected_collection_name or RAW_COLLECTION_NAME
                    )
                    from langchain_chroma import Chroma

                    self.vector_store = Chroma(
                        collection_name=collection_name,
                        embedding_function=embeddings,
                        persist_directory=persist_dir,
                    )
                    if selected_path:
                        self.selected_index_path = selected_path
                        self.selected_collection_name = collection_name
                        self.save_config()
                        self.log(
                            "Active index set to "
                            f"{self._format_index_label(persist_dir, collection_name)}."
                        )
                else:
                    self.append_chat(
                        "system", "Error: No Weaviate connection. Please Ingest first."
                    )
                    return
            except Exception as e:
                self.append_chat("system", f"Error: Please ingest a file first. ({e})")
                return

        threading.Thread(target=self._rag_pipeline, args=(query,), daemon=True).start()

    def _rag_pipeline(self, query):
        stage = "retrieval"
        try:
            self.log("Starting Retrieval...")

            # 1. Retrieval
            output_style = self.output_style.get().strip() or "Default answer"
            retrieve_k = max(1, int(self.retrieval_k.get()))
            final_k = max(1, int(self.final_k.get()))
            provider = self.llm_provider.get()
            model_name = self._resolve_llm_model()
            gui_llm_max_tokens = max(1, int(self.llm_max_tokens.get()))
            caps = self.get_model_caps(provider, model_name)
            output_max_tokens = self._get_capped_output_tokens(
                provider, model_name, gui_llm_max_tokens
            )
            context_budget_tokens = max(
                1024,
                int(caps.get("max_context_tokens", 8192))
                - output_max_tokens
                - CONTEXT_SAFETY_MARGIN_TOKENS,
            )
            candidate_k = max(retrieve_k, final_k)
            long_form_keywords = (
                "evidence",
                "evidence pack",
                "full report",
                "timeline",
                "all details",
                "complete",
                "extract all",
                "every",
                "required details",
            )
            normalized_query = query.lower()
            is_long_form = any(
                keyword in normalized_query for keyword in long_form_keywords
            )
            is_evidence_pack = self.is_evidence_pack_query(query, output_style)
            if is_long_form:
                boosted_final_k = max(final_k, 12)
                if boosted_final_k > final_k:
                    original_final_k = final_k
                    final_k = boosted_final_k
                    candidate_k = max(candidate_k, final_k)
                    self.log(
                        "Long-form intent detected; raised final_k from "
                        f"{original_final_k} to {final_k} "
                        "(GUI value remains authoritative with long-form floor only)."
                    )
            search_type = self.search_type.get() or "similarity"
            mmr_lambda = float(self.mmr_lambda.get())
            total_docs_cap = max(10, min(500, int(self.subquery_max_docs.get())))
            persist_dir = self.selected_index_path
            if not persist_dir:
                persist_dir = getattr(self.vector_store, "_persist_directory", None)
            if not persist_dir and self.vector_db_type.get() == "chroma":
                persist_dir = self._get_chroma_persist_root()
            digest_missing = (
                not self.build_digest_index.get()
                or (
                    self.vector_db_type.get() == "chroma"
                    and not self._has_digest_collection(persist_dir)
                )
            )
            digest_store = None
            if not digest_missing and self.vector_db_type.get() == "chroma":
                try:
                    embeddings = self.get_embeddings()
                    from langchain_chroma import Chroma

                    digest_store = Chroma(
                        collection_name=DIGEST_COLLECTION_NAME,
                        embedding_function=embeddings,
                        persist_directory=persist_dir,
                    )
                except Exception as exc:
                    self.log(f"Digest store unavailable; skipping digest tier. ({exc})")
                    digest_store = None
            use_mini_digest = (
                digest_missing and self.selected_collection_name == RAW_COLLECTION_NAME
            )
            if use_mini_digest:
                self.log(
                    "Digest layer missing; using temporary mini-digest routing for this request."
                )
            routing_candidate_k = candidate_k
            if use_mini_digest:
                routing_candidate_k = min(
                    max(candidate_k * MINI_DIGEST_BOOST_MULTIPLIER, MINI_DIGEST_MIN_POOL),
                    total_docs_cap,
                )
                if routing_candidate_k > candidate_k:
                    self.log(
                        f"Mini-digest routing enabled; boosted retrieval pool to {routing_candidate_k}."
                    )

            def _extract_json_payload(text):
                cleaned = text.strip()
                if "```" in cleaned:
                    parts = cleaned.split("```")
                    if len(parts) >= 2:
                        cleaned = parts[1].strip()
                        if cleaned.lower().startswith("json"):
                            cleaned = cleaned.split("\n", 1)[-1].strip()
                try:
                    return json.loads(cleaned)
                except json.JSONDecodeError:
                    return None

            def _build_search_kwargs(k_value):
                search_kwargs_local = {"k": k_value}
                if search_type == "mmr":
                    fetch_k = min(max(4 * k_value, 50), 200)
                    if fetch_k <= k_value:
                        fetch_k = k_value + 1
                    search_kwargs_local.update(
                        {"fetch_k": fetch_k, "lambda_mult": mmr_lambda}
                    )
                return search_kwargs_local

            def _retrieve_digest_nodes(query_list, remaining_cap, k_value, digest_store):
                if remaining_cap <= 0 or not digest_store:
                    return [], 0, True
                filtered_queries = [q for q in query_list if q]
                if not filtered_queries:
                    return [], 0, False
                digest_cap = min(MAX_DIGEST_NODES, remaining_cap)
                min_per_query_k = min(2, k_value)
                per_query_k = max(
                    min_per_query_k,
                    min(k_value, max(1, digest_cap // len(filtered_queries))),
                )
                cap_reached = False
                retrieved_count_local = 0
                docs_local = []
                for sub_query in filtered_queries:
                    if len(docs_local) >= digest_cap:
                        cap_reached = True
                        break
                    query_k = min(per_query_k, digest_cap - len(docs_local))
                    retriever = digest_store.as_retriever(
                        search_type=search_type,
                        search_kwargs=_build_search_kwargs(query_k),
                    )
                    batch = retriever.invoke(sub_query)
                    retrieved_count_local += len(batch)
                    docs_local.extend(batch)
                docs_local = self._merge_dedupe_docs(docs_local)
                if len(docs_local) > digest_cap:
                    docs_local = docs_local[:digest_cap]
                    cap_reached = True
                return docs_local, retrieved_count_local, cap_reached

            def _expand_digest_nodes(digest_docs, remaining_cap):
                if not digest_docs or remaining_cap <= 0:
                    return [], False
                if not hasattr(self.vector_store, "_collection"):
                    self.log("Digest expansion unavailable; missing raw collection handle.")
                    return [], False
                max_expand = min(MAX_RAW_CHUNKS, remaining_cap)
                chunk_requests = {}
                chunk_digest_map = {}
                for digest_doc in digest_docs:
                    metadata = getattr(digest_doc, "metadata", {}) or {}
                    ingest_id = metadata.get("ingest_id")
                    if not ingest_id:
                        continue
                    digest_id = metadata.get("digest_id") or metadata.get("section_title")
                    chunk_ids = self._expand_compact_chunk_ids(
                        metadata.get("child_chunk_ids", "")
                    )
                    if not chunk_ids:
                        continue
                    chunk_requests.setdefault(ingest_id, set()).update(chunk_ids)
                    for chunk_id in chunk_ids:
                        chunk_digest_map[(ingest_id, chunk_id)] = digest_id
                raw_docs = []
                cap_reached = False
                collection = self.vector_store._collection
                for ingest_id, chunk_ids in chunk_requests.items():
                    if len(raw_docs) >= max_expand:
                        cap_reached = True
                        break
                    remaining = max_expand - len(raw_docs)
                    batch_ids = list(chunk_ids)[:remaining]
                    if not batch_ids:
                        continue
                    try:
                        result = collection.get(
                            where={
                                "ingest_id": ingest_id,
                                "chunk_id": {"$in": batch_ids},
                            },
                            include=["documents", "metadatas"],
                        )
                    except Exception as exc:
                        self.log(f"Digest expansion failed; falling back to raw search. ({exc})")
                        return [], False
                    docs = result.get("documents") or []
                    metadatas = result.get("metadatas") or []
                    for content, metadata in zip(docs, metadatas):
                        if content is None:
                            continue
                        meta = metadata or {}
                        chunk_id = meta.get("chunk_id")
                        digest_window = chunk_digest_map.get((ingest_id, chunk_id))
                        if digest_window:
                            meta["digest_window"] = digest_window
                        raw_docs.append(Document(page_content=content, metadata=meta))
                return raw_docs, cap_reached

            def _retrieve_with_digest(query_list, remaining_cap, k_value):
                digest_retrieved = 0
                digest_selected = 0
                raw_expanded_count = 0
                if digest_store:
                    digest_docs, digest_retrieved, digest_cap_reached = (
                        _retrieve_digest_nodes(
                            query_list, remaining_cap, k_value, digest_store
                        )
                    )
                    digest_selected = len(digest_docs)
                    raw_docs, raw_cap_reached = _expand_digest_nodes(
                        digest_docs, remaining_cap
                    )
                    raw_expanded_count = len(raw_docs)
                    if raw_docs:
                        return (
                            raw_docs,
                            0,
                            digest_cap_reached or raw_cap_reached,
                            digest_docs,
                            raw_expanded_count,
                            digest_retrieved,
                            digest_selected,
                        )
                raw_docs, retrieved_count, cap_reached = _retrieve_for_queries(
                    query_list, remaining_cap, k_value
                )
                return (
                    raw_docs,
                    retrieved_count,
                    cap_reached,
                    [],
                    0,
                    digest_retrieved,
                    digest_selected,
                )

            def _retrieve_for_queries(query_list, remaining_cap, k_value):
                if remaining_cap <= 0:
                    return [], 0, True
                filtered_queries = [q for q in query_list if q]
                if not filtered_queries:
                    return [], 0, False
                cap_reached = False
                rrf_base = max(200, final_k * 20)
                dense_k = max(1, min(rrf_base, remaining_cap)) if is_evidence_pack else k_value
                lexical_k = max(1, min(rrf_base, remaining_cap)) if is_evidence_pack else max(1, min(k_value, remaining_cap))
                if len(filtered_queries) == 1:
                    retriever = self.vector_store.as_retriever(
                        search_type=search_type,
                        search_kwargs=_build_search_kwargs(dense_k),
                    )
                    docs_local = retriever.invoke(filtered_queries[0])
                else:
                    min_per_query_k = min(2, dense_k)
                    per_query_k = max(
                        min_per_query_k,
                        min(dense_k, max(1, remaining_cap) // len(filtered_queries)),
                    )
                    retriever = self.vector_store.as_retriever(
                        search_type=search_type,
                        search_kwargs=_build_search_kwargs(per_query_k),
                    )
                    docs_local = []
                    for sub_query in filtered_queries:
                        docs_local.extend(retriever.invoke(sub_query))
                vector_retrieved_count = len(docs_local)
                dense_docs = self._merge_dedupe_docs(docs_local)
                lexical_docs = []
                lexical_available = False
                if is_evidence_pack:
                    lexical_available = self.lexical_db_available or self._ensure_lexical_db()
                elif self.lexical_db_available:
                    lexical_available = True
                if lexical_available:
                    for sub_query in filtered_queries:
                        lexical_docs.extend(self.lexical_search(sub_query, lexical_k))
                    if lexical_docs:
                        self.log(f"Lexical search contributed {len(lexical_docs)} candidates.")
                retrieved_count_local = vector_retrieved_count + len(lexical_docs)
                if is_evidence_pack and lexical_docs:
                    dense_ranked = self._merge_dedupe_docs(dense_docs)
                    lexical_ranked = self._merge_dedupe_docs(lexical_docs)
                    pool_cap = min(600, remaining_cap)
                    docs_local = self._fuse_ranked_results(
                        [("dense", dense_ranked), ("lexical", lexical_ranked)],
                        k_rrf=60,
                        fused_pool_size=pool_cap,
                    )
                    self.log(
                        "Fused dense+lexical candidates via RRF "
                        f"(dense={len(dense_ranked)}, lexical={len(lexical_ranked)}, fused={len(docs_local)})."
                    )
                else:
                    docs_local = dense_docs
                    if lexical_docs:
                        docs_local = self._merge_dedupe_docs(docs_local + lexical_docs)
                if len(docs_local) > remaining_cap:
                    docs_local = docs_local[:remaining_cap]
                    cap_reached = True
                return docs_local, retrieved_count_local, cap_reached

            def _select_evidence_pack(doc_list, rerank_query, evidence_pack_mode):
                candidates = self._promote_lexical_overlap(doc_list, rerank_query)
                rerank_top_n = min(len(candidates), max(final_k * 6, 80))
                if self.use_reranker.get() and self.api_keys["cohere"].get():
                    try:
                        self.log("Reranking with Cohere...")
                        from langchain_cohere import CohereRerank

                        compressor = CohereRerank(
                            cohere_api_key=self.api_keys["cohere"].get(),
                            top_n=rerank_top_n,
                            model="rerank-english-v3.0",
                        )
                        compressed_docs = compressor.compress_documents(
                            candidates, rerank_query
                        )
                        self.log(
                            f"Reranked down to {len(compressed_docs)} high-relevance chunks."
                        )
                        candidates = compressed_docs
                    except Exception as exc:
                        self.log(f"Rerank Error (Using raw retrieval instead): {exc}")
                group_limit = 1 if evidence_pack_mode else MAX_GROUP_DOCS
                candidates = self._apply_coverage_selection(
                    candidates,
                    final_k,
                    group_limit=group_limit,
                    evidence_pack_mode=evidence_pack_mode,
                )
                if len(candidates) < final_k:
                    fallback = self._merge_dedupe_docs(candidates + doc_list)
                    candidates = fallback[:final_k]
                else:
                    candidates = candidates[:final_k]
                return candidates

            def _build_context(doc_list):
                def _clamp(value, min_value, max_value):
                    return max(min_value, min(max_value, value))

                context_budget_chars = _clamp(
                    context_budget_tokens * TOKENS_TO_CHARS_RATIO,
                    min_value=12000,
                    max_value=MAX_PACKED_CONTEXT_CHARS,
                )
                context_blocks = []
                used_chars = 0
                was_truncated = False
                packed_count = 0

                for idx, doc in enumerate(doc_list, start=1):
                    metadata = getattr(doc, "metadata", {}) or {}
                    score = metadata.get("relevance_score", "N/A")
                    source = (
                        metadata.get("source")
                        or metadata.get("file_path")
                        or metadata.get("filename")
                        or "unknown"
                    )
                    chunk_id = metadata.get("chunk_id", "N/A")
                    header = (
                        f"[Chunk {idx} | chunk_id: {chunk_id} | "
                        f"score: {score} | source: {source}]"
                    )
                    content = doc.page_content.strip()
                    chunk_text = f"{header}\n{content}"

                    remaining = context_budget_chars - used_chars
                    if remaining <= 0:
                        was_truncated = True
                        break
                    if len(chunk_text) > remaining:
                        was_truncated = True
                        if remaining > len(header) + 20:
                            truncated_content = content[
                                : remaining - len(header) - 20
                            ].rstrip()
                            chunk_text = (
                                f"{header}\n{truncated_content}\n...[truncated]"
                            )
                        else:
                            break
                    context_blocks.append(chunk_text)
                    used_chars += len(chunk_text) + 2
                    packed_count += 1

                if was_truncated:
                    self.log(
                        "Context truncated during packing: "
                        f"packed_count={packed_count}, truncated={was_truncated}, "
                        f"used_chars={used_chars}, budget_chars={context_budget_chars}."
                    )

                return (
                    "\n\n".join(context_blocks),
                    was_truncated,
                    used_chars,
                    context_budget_chars,
                )

            def _append_context_if_enabled(iteration_label, context_text, truncated_flag):
                if not self.show_retrieved_context.get():
                    return
                status = " (truncated)" if truncated_flag else ""
                self.append_chat(
                    "source",
                    f"Retrieved context {iteration_label}{status}:\n{context_text}",
                )

            def _log_iteration_telemetry(
                iteration_id,
                output_style,
                agentic_mode,
                planner_subquery_count,
                query_count,
                digest_retrieved_count,
                digest_selected_count,
                raw_expanded_count,
                raw_unique_count,
                packed_docs,
                truncated_flag,
                trunc_used_chars,
                trunc_budget_chars,
                cap_reached_flag,
                retrieved_count,
            ):
                truncation_note = (
                    f"{int(truncated_flag)} {trunc_used_chars}/{trunc_budget_chars}"
                )
                self.log(
                    "Iter "
                    f"{iteration_id} telemetry | style={output_style}, "
                    f"agentic={int(agentic_mode)}, planner_subqueries={planner_subquery_count}, "
                    f"queries={query_count}, digest={digest_retrieved_count}/"
                    f"{digest_selected_count}, raw={raw_expanded_count}/"
                    f"{raw_unique_count}/{packed_docs}, "
                    f"trunc={truncation_note}, cap_reached={int(cap_reached_flag)}, "
                    f"retrieved={retrieved_count}"
                )

            if not self.agentic_mode.get():
                queries = [query]
                if self.use_sub_queries.get():
                    sub_queries = self._generate_sub_queries(query)
                    if sub_queries:
                        queries = [query, *sub_queries]
                max_total_docs = max(1, int(self.subquery_max_docs.get()))
                (
                    docs,
                    retrieved_count,
                    cap_reached,
                    _digest_docs,
                    raw_expanded_count,
                    digest_retrieved_count,
                    digest_selected_count,
                ) = _retrieve_with_digest(
                    queries, min(total_docs_cap, max_total_docs), routing_candidate_k
                )
                self.log(
                    f"Retrieved {len(docs)} initial candidates from {len(queries)} query(s)."
                )
                if use_mini_digest:
                    routed_docs = self._route_with_mini_digest(docs, query, final_k)
                    self.log(
                        "Mini-digest routing selected "
                        f"{len(routed_docs)} candidate chunks."
                    )
                    candidate_docs = routed_docs
                    final_docs = _select_evidence_pack(
                        routed_docs, query, is_evidence_pack
                    )
                else:
                    candidate_docs = docs
                    final_docs = _select_evidence_pack(docs, query, is_evidence_pack)
                if is_evidence_pack:
                    (
                        unique_incidents,
                        missing_months,
                        channels,
                        date_tokens,
                    ) = self._review_evidence_pack_coverage(
                        candidate_docs, final_docs
                    )
                    unique_incidents_value = unique_incidents
                    coverage_floor = max(3, min(final_k, len(final_docs)))
                    coverage_low = unique_incidents < coverage_floor or bool(
                        missing_months
                    )
                    missing_months_text = (
                        ", ".join(missing_months) if missing_months else "none"
                    )
                    self.log(
                        "Evidence-pack coverage check: unique_incidents="
                        f"{unique_incidents}, missing_months={missing_months_text}."
                    )
                    if coverage_low:
                        follow_up_queries = self._generate_follow_up_queries(
                            query, missing_months, channels, date_tokens
                        )
                        if follow_up_queries:
                            remaining_cap = max(0, total_docs_cap - len(docs))
                            if remaining_cap == 0:
                                self.log(
                                    "Evidence-pack follow-up skipped; total docs cap reached."
                                )
                            else:
                                (
                                    follow_docs,
                                    follow_retrieved_count,
                                    follow_cap_reached,
                                    _follow_digest_docs,
                                    follow_raw_expanded_count,
                                    follow_digest_retrieved_count,
                                    follow_digest_selected_count,
                                ) = _retrieve_with_digest(
                                    follow_up_queries,
                                    remaining_cap,
                                    routing_candidate_k,
                                )
                                retrieved_count += follow_retrieved_count
                                raw_expanded_count += follow_raw_expanded_count
                                digest_retrieved_count += follow_digest_retrieved_count
                                digest_selected_count += follow_digest_selected_count
                                cap_reached = cap_reached or follow_cap_reached
                                if follow_docs:
                                    docs = self._merge_dedupe_docs(docs + follow_docs)
                                    if use_mini_digest:
                                        routed_docs = self._route_with_mini_digest(
                                            docs, query, final_k
                                        )
                                        candidate_docs = routed_docs
                                        self.log(
                                            "Evidence-pack follow-up routing selected "
                                            f"{len(routed_docs)} candidate chunks."
                                        )
                                    else:
                                        candidate_docs = docs
                                    final_docs = _select_evidence_pack(
                                        candidate_docs, query, is_evidence_pack
                                    )
                                    self.log(
                                        "Evidence-pack follow-up retrieval added "
                                        f"{len(follow_docs)} chunks; "
                                        f"reselected {len(final_docs)} chunks."
                                    )
                        else:
                            self.log(
                                "Evidence-pack follow-up skipped; no follow-up queries."
                            )
                else:
                    unique_incidents_value = len(final_docs)
                (
                    context_text,
                    was_truncated,
                    trunc_used_chars,
                    trunc_budget_chars,
                ) = _build_context(final_docs)
                role_distribution = self._format_role_distribution(final_docs)
                selected_distribution = self._format_selected_distribution(final_docs)
                self._log_final_docs_selection(
                    retrieve_k,
                    candidate_k,
                    final_k,
                    trunc_used_chars,
                    trunc_budget_chars,
                    unique_incidents_value,
                    role_distribution,
                    final_k,
                    unique_incidents_value,
                    selected_distribution,
                )
                planner_subquery_count = 0
                if self.use_sub_queries.get():
                    planner_subquery_count = max(0, len(queries) - 1)
                _log_iteration_telemetry(
                    1,
                    self.output_style.get(),
                    self.agentic_mode.get(),
                    planner_subquery_count,
                    len(queries),
                    digest_retrieved_count,
                    digest_selected_count,
                    raw_expanded_count,
                    len(docs),
                    len(final_docs),
                    was_truncated,
                    trunc_used_chars,
                    trunc_budget_chars,
                    cap_reached,
                    retrieved_count,
                )
                _append_context_if_enabled("(single pass)", context_text, was_truncated)

                self.log("Generating Answer...")
                llm = self.get_llm()
                style_instruction = self._get_output_style_instruction()
                evidence_instruction = (
                    self._get_evidence_pack_instruction()
                    if is_evidence_pack
                    else ""
                )
                prompt_parts = [self._get_system_instructions()]
                if style_instruction:
                    prompt_parts.append(style_instruction)
                if evidence_instruction:
                    prompt_parts.append(evidence_instruction)
                prompt_parts.append(f"CONTEXT:\n{context_text}")
                system_prompt = "\n\n".join(prompt_parts)
                history_window = self._get_history_window(current_query=query)
                messages = [
                    SystemMessage(content=system_prompt),
                    *history_window,
                    HumanMessage(content=query),
                ]
                response = llm.invoke(messages)
                validated_answer = self._validate_and_repair(
                    response.content, context_text, iteration_id=1
                )

                self.last_answer = validated_answer
                self.append_chat("agent", f"AI: {validated_answer}")
                self._append_history(AIMessage(content=validated_answer))

                sources_text = "\n".join(
                    [
                        (
                            f"- [Chunk {idx} | chunk_id: "
                            f"{getattr(d, 'metadata', {}).get('chunk_id', 'N/A')} | score: "
                            f"{getattr(d, 'metadata', {}).get('relevance_score', 'N/A')} | "
                            f"source: "
                            f"{(getattr(d, 'metadata', {}) or {}).get('source') or (getattr(d, 'metadata', {}) or {}).get('file_path') or (getattr(d, 'metadata', {}) or {}).get('filename') or 'unknown'}]"
                        )
                        for idx, d in enumerate(final_docs, start=1)
                    ]
                )
                self.append_chat("source", f"\nSources used:\n{sources_text}")
                return

            try:
                max_iterations_value = int(self.agentic_max_iterations.get())
            except (TypeError, ValueError):
                max_iterations_value = 2
            HARD_CAP = AGENTIC_MAX_ITERATIONS_HARD_CAP
            max_iterations = max(1, min(HARD_CAP, max_iterations_value))
            self.log(
                "Agentic run starting with resolved max_iterations="
                f"{max_iterations} (requested {max_iterations_value})."
            )
            total_retrieved = 0
            all_docs = []
            checklist = []
            section_plan = []
            latest_answer = ""
            latest_context_text = ""
            final_docs = []
            critic_queries = []

            last_iteration_id = 1
            planner_subquery_count = 0
            convergence_patience = 2
            stagnant_iterations = 0
            last_unique_incident_count = 0
            for iteration in range(1, max_iterations + 1):
                if iteration == 1:
                    planner_llm = self._get_llm_with_temperature(0.2)
                    if is_evidence_pack:
                        planner_prompt = (
                            "You are an evidence-pack retrieval planner. Given the user query and "
                            "output_style, return strict JSON with keys: checklist_items (array of "
                            "strings), retrieval_queries (array of 8-15 strings), section_plan "
                            "(optional array). Checklist must include: 6–12 strongest dated incidents, "
                            "2–4 supporting examples, timeline fields, impacts. Retrieval queries must be "
                            "generic coverage sweeps (not user-specified examples), including date sweeps "
                            "(months/years), channel terms (Teams/email/call/meeting/WhatsApp), and role "
                            "queries (formal grievance examples, key incidents, what happened impact "
                            "evidence). Ensure checklist and queries cover chronology/timeline, impacts, "
                            "grievances, and concrete examples. Do not include any extra text."
                        )
                    else:
                        planner_prompt = (
                            "You are a retrieval planner. Given the user query and output_style, "
                            "return strict JSON with keys: checklist_items (array of strings), "
                            "retrieval_queries (array of 4-10 strings), section_plan (optional array). "
                            "Do not include any extra text."
                        )
                    planner_messages = [
                        SystemMessage(content=planner_prompt),
                        HumanMessage(
                            content=json.dumps(
                                {
                                    "query": query,
                                    "output_style": output_style,
                                }
                            )
                        ),
                    ]
                    planner_response = planner_llm.invoke(planner_messages)
                    plan_payload = _extract_json_payload(planner_response.content) or {}
                    checklist = [
                        str(item).strip()
                        for item in plan_payload.get("checklist_items", [])
                        if str(item).strip()
                    ]
                    sub_queries = [
                        str(item).strip()
                        for item in plan_payload.get("retrieval_queries", [])
                        if str(item).strip()
                    ]
                    planner_subquery_count = len(sub_queries)
                    section_plan = [
                        str(item).strip()
                        for item in plan_payload.get("section_plan", [])
                        if str(item).strip()
                    ]
                    if not checklist:
                        checklist = [query.strip()]
                    seen_queries = set()
                    normalized_sub_queries = []
                    for candidate in [query, *sub_queries]:
                        key = candidate.lower().strip()
                        if key and key not in seen_queries:
                            seen_queries.add(key)
                            normalized_sub_queries.append(candidate)
                    if len(normalized_sub_queries) < 4:
                        fallback_queries = self._generate_sub_queries(query)
                        for candidate in fallback_queries:
                            key = candidate.lower().strip()
                            if key and key not in seen_queries:
                                seen_queries.add(key)
                                normalized_sub_queries.append(candidate)
                            if len(normalized_sub_queries) >= 4:
                                break
                    if len(normalized_sub_queries) < 4:
                        normalized_sub_queries.append(query)
                    iteration_queries = normalized_sub_queries[:10]
                else:
                    if not critic_queries:
                        self.log("No critic follow-up queries; stopping iterations.")
                        break
                    iteration_queries = critic_queries

                prev_all_docs_count = len(all_docs)
                remaining_cap = max(0, total_docs_cap - total_retrieved)
                if remaining_cap == 0:
                    self.log("Total retrieved document cap reached; stopping iterations.")
                    break
                (
                    docs,
                    retrieved_count,
                    cap_reached,
                    _digest_docs,
                    raw_expanded_count,
                    digest_retrieved_count,
                    digest_selected_count,
                ) = _retrieve_with_digest(
                    iteration_queries, remaining_cap, routing_candidate_k
                )
                total_retrieved += len(docs)
                all_docs = self._merge_dedupe_docs(all_docs + docs)
                new_incidents_added = len(all_docs) - prev_all_docs_count
                unique_incident_count = len(all_docs)
                if unique_incident_count <= last_unique_incident_count:
                    stagnant_iterations += 1
                else:
                    stagnant_iterations = 0
                    last_unique_incident_count = unique_incident_count
                stop_due_to_convergence = stagnant_iterations >= convergence_patience
                if use_mini_digest:
                    routed_docs = self._route_with_mini_digest(all_docs, query, final_k)
                    self.log(
                        "Mini-digest routing selected "
                        f"{len(routed_docs)} candidate chunks."
                    )
                    candidate_docs = routed_docs
                    final_docs = _select_evidence_pack(
                        routed_docs, query, is_evidence_pack
                    )
                else:
                    candidate_docs = all_docs
                    final_docs = _select_evidence_pack(
                        all_docs, query, is_evidence_pack
                    )
                if is_evidence_pack:
                    (
                        unique_incidents,
                        missing_months,
                        channels,
                        date_tokens,
                    ) = self._review_evidence_pack_coverage(
                        candidate_docs, final_docs
                    )
                    unique_incidents_value = unique_incidents
                    coverage_floor = max(3, min(final_k, len(final_docs)))
                    coverage_low = unique_incidents < coverage_floor or bool(
                        missing_months
                    )
                    missing_months_text = (
                        ", ".join(missing_months) if missing_months else "none"
                    )
                    self.log(
                        "Evidence-pack coverage check: unique_incidents="
                        f"{unique_incidents}, missing_months={missing_months_text}."
                    )
                    if coverage_low:
                        follow_up_queries = self._generate_follow_up_queries(
                            query, missing_months, channels, date_tokens
                        )
                        if follow_up_queries:
                            remaining_cap = max(0, total_docs_cap - total_retrieved)
                            if remaining_cap == 0:
                                self.log(
                                    "Evidence-pack follow-up skipped; total docs cap reached."
                                )
                            else:
                                (
                                    follow_docs,
                                    follow_retrieved_count,
                                    follow_cap_reached,
                                    _follow_digest_docs,
                                    follow_raw_expanded_count,
                                    follow_digest_retrieved_count,
                                    follow_digest_selected_count,
                                ) = _retrieve_with_digest(
                                    follow_up_queries,
                                    remaining_cap,
                                    routing_candidate_k,
                                )
                                retrieved_count += follow_retrieved_count
                                raw_expanded_count += follow_raw_expanded_count
                                digest_retrieved_count += follow_digest_retrieved_count
                                digest_selected_count += follow_digest_selected_count
                                cap_reached = cap_reached or follow_cap_reached
                                if follow_docs:
                                    total_retrieved += len(follow_docs)
                                    all_docs = self._merge_dedupe_docs(
                                        all_docs + follow_docs
                                    )
                                    if use_mini_digest:
                                        routed_docs = self._route_with_mini_digest(
                                            all_docs, query, final_k
                                        )
                                        candidate_docs = routed_docs
                                        self.log(
                                            "Evidence-pack follow-up routing selected "
                                            f"{len(routed_docs)} candidate chunks."
                                        )
                                    else:
                                        candidate_docs = all_docs
                                    final_docs = _select_evidence_pack(
                                        candidate_docs, query, is_evidence_pack
                                    )
                                    self.log(
                                        "Evidence-pack follow-up retrieval added "
                                        f"{len(follow_docs)} chunks; "
                                        f"reselected {len(final_docs)} chunks."
                                    )
                        else:
                            self.log(
                                "Evidence-pack follow-up skipped; no follow-up queries."
                            )
                else:
                    unique_incidents_value = len(final_docs)
                (
                    context_text,
                    was_truncated,
                    trunc_used_chars,
                    trunc_budget_chars,
                ) = _build_context(final_docs)
                role_distribution = self._format_role_distribution(final_docs)
                selected_distribution = self._format_selected_distribution(final_docs)
                self._log_final_docs_selection(
                    retrieve_k,
                    candidate_k,
                    final_k,
                    trunc_used_chars,
                    trunc_budget_chars,
                    unique_incidents_value,
                    role_distribution,
                    final_k,
                    new_incidents_added,
                    selected_distribution,
                )
                _log_iteration_telemetry(
                    iteration,
                    self.output_style.get(),
                    self.agentic_mode.get(),
                    planner_subquery_count,
                    len(iteration_queries),
                    digest_retrieved_count,
                    digest_selected_count,
                    raw_expanded_count,
                    len(all_docs),
                    len(final_docs),
                    was_truncated,
                    trunc_used_chars,
                    trunc_budget_chars,
                    cap_reached,
                    retrieved_count,
                )
                _append_context_if_enabled(
                    f"(iteration {iteration})", context_text, was_truncated
                )

                self.log("Generating Answer...")
                llm = self.get_llm()
                checklist_text = "\n".join(f"- {item}" for item in checklist)
                coverage_note = ""
                if iteration > 1:
                    coverage_note = (
                        "\nIf helpful, include a compact coverage table mapping checklist "
                        "items to evidence or omitted due to missing support."
                    )
                style_instruction = self._get_output_style_instruction()
                evidence_instruction = (
                    self._get_evidence_pack_instruction()
                    if is_evidence_pack
                    else ""
                )
                prompt_parts = [self._get_system_instructions()]
                if style_instruction:
                    prompt_parts.append(style_instruction)
                if evidence_instruction:
                    prompt_parts.append(evidence_instruction)
                if section_plan:
                    prompt_parts.append(
                        "SECTION PLAN:\n" + "\n".join(f"- {item}" for item in section_plan)
                    )
                prompt_parts.append(
                    "Strict rules: Use ONLY the context. Omit unsupported claims; deepen supported ones; "
                    "do not ask for more docs or missing info; do not use placeholders. If evidence "
                    "is thin, you may add one short 'Scope:' note at the top."
                )
                prompt_parts.append(f"CHECKLIST:\n{checklist_text}")
                prompt_parts.append(f"CONTEXT:\n{context_text}{coverage_note}")
                system_prompt = "\n\n".join(prompt_parts)
                history_window = self._get_history_window(current_query=query)
                messages = [
                    SystemMessage(content=system_prompt),
                    *history_window,
                    HumanMessage(content=query),
                ]
                response = llm.invoke(messages)
                latest_answer = response.content
                latest_context_text = context_text
                last_iteration_id = iteration

                if stop_due_to_convergence:
                    self.log(
                        "Unique incident count stalled at "
                        f"{unique_incident_count} for {stagnant_iterations} "
                        "iteration(s); stopping early."
                    )
                    break
                if iteration < max_iterations:
                    critic_llm = self._get_llm_with_temperature(0.2)
                    critic_prompt = (
                        "You are a critic. Review the answer against the checklist. "
                        "For each checklist item, mark it as FOUND with citations or "
                        "UNSUPPORTED. Unsupported means the answer should omit those details "
                        "(no placeholders) rather than request more docs, except one short "
                        "'Scope:' note at top when evidence is thin. If any items are UNSUPPORTED, propose new "
                        "retrieval_queries. Return strict JSON with keys: "
                        "checklist_review (array of {item, status, citations}), "
                        "retrieval_queries (array). Do not include extra text."
                    )
                    critic_messages = [
                        SystemMessage(content=critic_prompt),
                        HumanMessage(
                            content=(
                                f"Checklist:\n{checklist_text}\n\n"
                                f"Answer:\n{latest_answer}"
                            )
                        ),
                    ]
                    critic_response = critic_llm.invoke(critic_messages)
                    critic_payload = _extract_json_payload(critic_response.content) or {}
                    review_items = critic_payload.get("checklist_review", [])
                    missing_items = []
                    for review in review_items:
                        status = str(review.get("status", "")).strip().upper()
                        item = str(review.get("item", "")).strip()
                        if status == "UNSUPPORTED" and item:
                            missing_items.append(item)
                    critic_queries = [
                        str(item).strip()
                        for item in critic_payload.get("retrieval_queries", [])
                        if str(item).strip()
                    ][:3]
                    if not missing_items:
                        critic_queries = []

            if latest_answer:
                validated_answer = self._validate_and_repair(
                    latest_answer, latest_context_text, iteration_id=last_iteration_id
                )
                self.last_answer = validated_answer
                self.append_chat("agent", f"AI: {validated_answer}")
                self._append_history(AIMessage(content=validated_answer))

            sources_text = "\n".join(
                [
                    (
                        f"- [Chunk {idx} | chunk_id: "
                        f"{getattr(d, 'metadata', {}).get('chunk_id', 'N/A')} | score: "
                        f"{getattr(d, 'metadata', {}).get('relevance_score', 'N/A')} | "
                        f"source: "
                        f"{(getattr(d, 'metadata', {}) or {}).get('source') or (getattr(d, 'metadata', {}) or {}).get('file_path') or (getattr(d, 'metadata', {}) or {}).get('filename') or 'unknown'}]"
                    )
                    for idx, d in enumerate(final_docs, start=1)
                ]
            )
            self.append_chat("source", f"\nSources used:\n{sources_text}")

        except Exception as e:
            self.log(f"RAG Error ({stage} failure): {e}")
            self.append_chat("system", f"Error ({stage} failure): {e}")

    def append_chat(self, tag, message):
        def _append():
            self.chat_display.config(state="normal")
            self.chat_display.insert(tk.END, message + "\n\n", tag)
            self.chat_display.see(tk.END)
            self.chat_display.config(state="disabled")

        self._run_on_ui(_append)

    def clear_chat(self):
        self.chat_display.config(state="normal")
        self.chat_display.delete("1.0", tk.END)
        self.chat_display.config(state="disabled")
        self.last_answer = ""
        self.chat_history = []

    def save_chat(self):
        transcript = self.chat_display.get("1.0", tk.END).strip()
        if not transcript:
            messagebox.showinfo("No Chat History", "There is no chat transcript to save.")
            return
        save_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text Files", "*.txt")],
            title="Save Chat Transcript",
        )
        if not save_path:
            return
        try:
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(transcript + "\n")
            self.log(f"Chat transcript saved to {save_path}")
        except OSError as exc:
            messagebox.showerror("Save Failed", f"Could not save transcript: {exc}")

    def copy_last_answer(self):
        if not self.last_answer:
            messagebox.showinfo("No Answer", "There is no AI answer to copy yet.")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(self.last_answer)
        self.root.update()
        self.log("Last answer copied to clipboard.")


if __name__ == "__main__":
    try:
        root = tk.Tk()
        app = AgenticRAGApp(root)
        root.mainloop()
    except Exception as e:
        print(f"Startup Error: {e}")
