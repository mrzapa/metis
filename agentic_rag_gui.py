import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import threading
import os
import sys
import time
import json
import subprocess
import importlib.util
from datetime import datetime
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

# --- Libraries check is done inside the class to prevent instant crash ---
# Required: pip install langchain langchain-community langchain-openai langchain-anthropic langchain-google-genai langchain-cohere langchain-text-splitters chromadb beautifulsoup4 tiktoken


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
            "You are an expert analyst assistant. Use the provided context to answer the "
            "user's question. If the answer is not in the context, say you don't know. "
            "Cite specific sections if possible, and be clear about any assumptions."
        )
        self.verbose_system_instructions = (
            "You are an expert analyst assistant. Use the provided context to answer the "
            "user's question. If the answer is not in the context, say you don't know. "
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
        self.retrieval_k = tk.IntVar(value=25)
        self.final_k = tk.IntVar(value=5)
        self.fallback_final_k = tk.IntVar(value=self.final_k.get())
        self.search_type = tk.StringVar(value="similarity")
        self.mmr_lambda = tk.DoubleVar(value=0.5)

        self.vector_store = None
        self.index_embedding_signature = ""
        self.chat_history = []
        self.chat_history_max_turns = 6
        self.selected_file = None
        self.last_answer = ""
        self.dependency_prompted = False
        self.existing_index_var = tk.StringVar(value="(default)")
        self.existing_index_paths = {}

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
        self.index_embedding_signature = data.get(
            "index_embedding_signature", self.index_embedding_signature
        )

        instructions = data.get("system_instructions", self.system_instructions.get())
        self.system_instructions.set(instructions or self.default_system_instructions)
        self.instructions_box.delete("1.0", tk.END)
        self.instructions_box.insert(tk.END, self.system_instructions.get())

        self._sync_model_options()
        self._refresh_compatibility_warning()

    def save_config(self):
        data = {
            "api_keys": {key: var.get() for key, var in self.api_keys.items()},
            "llm_provider": self.llm_provider.get(),
            "embedding_provider": self.embedding_provider.get(),
            "vector_db_type": self.vector_db_type.get(),
            "local_llm_url": self.local_llm_url.get(),
            "chunk_size": self.chunk_size.get(),
            "chunk_overlap": self.chunk_overlap.get(),
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
            "index_embedding_signature": self.index_embedding_signature,
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

        ttk.Label(chunk_frame, text="Chunk Size (Tokens):").pack(side="left")
        ttk.Entry(chunk_frame, textvariable=self.chunk_size, width=10).pack(
            side="left", padx=5
        )

        ttk.Label(chunk_frame, text="Overlap:").pack(side="left", padx=(20, 0))
        ttk.Entry(chunk_frame, textvariable=self.chunk_overlap, width=10).pack(
            side="left", padx=5
        )

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
        self.use_reranker = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            opt_frame,
            text="Use Cohere Reranker (Higher Precision)",
            variable=self.use_reranker,
        ).pack(side="left")
        ttk.Label(opt_frame, text="Fallback Final K:").pack(side="left", padx=(15, 4))
        ttk.Entry(opt_frame, textvariable=self.fallback_final_k, width=6).pack(
            side="left"
        )

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

    def _on_vector_db_type_change(self, *_args):
        self._refresh_existing_indexes()

    def _get_chroma_persist_root(self):
        return os.path.join(os.getcwd(), "chroma_db")

    @staticmethod
    def _is_chroma_persist_dir(path):
        if not os.path.isdir(path):
            return False
        return os.path.exists(os.path.join(path, "chroma.sqlite3")) or os.path.exists(
            os.path.join(path, "index")
        )

    @staticmethod
    def _format_index_label(path):
        try:
            return os.path.relpath(path, os.getcwd())
        except ValueError:
            return path

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
        display_values = ["(default)"] + [
            self._format_index_label(path) for path in indexes
        ]
        self.existing_index_paths = {
            self._format_index_label(path): path for path in indexes
        }
        if hasattr(self, "cb_existing_index"):
            self.cb_existing_index["values"] = display_values
        if self.existing_index_var.get() not in display_values:
            self.existing_index_var.set("(default)")

    def _get_selected_index_path(self):
        selection = self.existing_index_var.get()
        if not selection or selection == "(default)":
            return None
        return self.existing_index_paths.get(selection, selection)

    def _on_existing_index_change(self, _event=None):
        selected_path = self._get_selected_index_path()
        if not selected_path:
            return
        threading.Thread(
            target=self._load_existing_index, args=(selected_path,), daemon=True
        ).start()

    def _load_existing_index(self, selected_path):
        try:
            self.log(f"Loading existing index from {self._format_index_label(selected_path)}...")
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
                    collection_name="rag_collection",
                    embedding_function=embeddings,
                    persist_directory=selected_path,
                )
                self.index_embedding_signature = self._current_embedding_signature()
                self.save_config()
                self.log(
                    f"Active index set to {self._format_index_label(selected_path)}."
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

    def _get_system_instructions(self):
        instructions = self.system_instructions.get().strip()
        if not instructions:
            instructions = self.default_system_instructions
            self.system_instructions.set(instructions)
            self._run_on_ui(self._refresh_instructions_box)
        return instructions

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
        temperature, max_tokens = validated
        provider = self.llm_provider.get()
        model_name = self._resolve_llm_model()

        if provider == "openai":
            try:
                from langchain_openai import ChatOpenAI
            except ImportError as err:
                self._prompt_dependency_install(["langchain-openai"], "OpenAI LLM", err)
                raise

            key = self.api_keys["openai"].get()
            return ChatOpenAI(
                api_key=key, model=model_name, temperature=temperature, max_tokens=max_tokens
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
                api_key=key, model=model_name, temperature=temperature, max_tokens=max_tokens
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
                max_output_tokens=max_tokens,
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
                max_tokens=max_tokens,
            )

        raise ValueError(f"Unknown LLM provider: {provider}")

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

            if self.selected_file.lower().endswith(".html"):
                from bs4 import BeautifulSoup

                with open(self.selected_file, "r", encoding="utf-8", errors="ignore") as f:
                    soup = BeautifulSoup(f, "html.parser")
                    # Aggressive cleaning for RAG
                    for tag in soup(["script", "style", "svg", "path", "nav", "footer"]):
                        tag.extract()
                    text_content = soup.get_text(separator="\n")
            else:
                with open(self.selected_file, "r", encoding="utf-8") as f:
                    text_content = f.read()

            self.log(f"File loaded. Raw text length: {len(text_content)} characters.")

            # 2. Split
            self.log("Step 2/4: Splitting Text...")
            try:
                from langchain.text_splitter import RecursiveCharacterTextSplitter
            except ImportError:
                from langchain_text_splitters import RecursiveCharacterTextSplitter

            splitter = RecursiveCharacterTextSplitter(
                chunk_size=self.chunk_size.get(),
                chunk_overlap=self.chunk_overlap.get(),
                separators=["\n\n", "\n", ".", " ", ""],
            )
            docs = splitter.create_documents([text_content])
            self.log(f"Created {len(docs)} text chunks.")

            # 3. Initialize Vector DB & Embeddings
            self.log("Step 3/4: Initializing Vector Store...")
            embeddings = self.get_embeddings()

            db_type = self.vector_db_type.get()

            if db_type == "chroma":
                persist_dir = self._get_chroma_persist_root()
                try:
                    from langchain_chroma import Chroma
                except ImportError as err:
                    self._prompt_dependency_install(
                        ["langchain-chroma", "chromadb"], "Chroma vector store", err
                    )
                    raise

                # Using a new client per ingestion to ensure clean slate or append
                self.vector_store = Chroma(
                    collection_name="rag_collection",
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

            self.log("Ingestion Complete! You can now chat.")
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
                    selected_path = self._get_selected_index_path()
                    persist_dir = selected_path or self._get_chroma_persist_root()
                    from langchain_chroma import Chroma

                    self.vector_store = Chroma(
                        collection_name="rag_collection",
                        embedding_function=embeddings,
                        persist_directory=persist_dir,
                    )
                    if selected_path:
                        self.log(
                            "Active index set to "
                            f"{self._format_index_label(persist_dir)}."
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
        try:
            self.log("Starting Retrieval...")

            # 1. Retrieval
            retrieve_k = max(1, int(self.retrieval_k.get()))
            final_k = max(1, int(self.final_k.get()))
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
            if any(keyword in normalized_query for keyword in long_form_keywords):
                boosted_final_k = min(candidate_k, max(final_k, 12))
                if boosted_final_k > 20:
                    boosted_final_k = min(candidate_k, 20)
                final_k = boosted_final_k
                self.log(f"Long-form intent detected; adjusted final_k to {final_k}.")
            search_type = self.search_type.get() or "similarity"
            mmr_lambda = float(self.mmr_lambda.get())
            search_kwargs = {"k": candidate_k}
            if search_type == "mmr":
                search_kwargs.update(
                    {"fetch_k": candidate_k, "lambda_mult": mmr_lambda}
                )
            retriever = self.vector_store.as_retriever(
                search_type=search_type, search_kwargs=search_kwargs
            )
            docs = retriever.invoke(query)

            self.log(f"Retrieved {len(docs)} initial candidates.")

            # 2. Reranking (Cohere)
            final_docs = docs
            if self.use_reranker.get() and self.api_keys["cohere"].get():
                try:
                    self.log("Reranking with Cohere...")
                    from langchain_cohere import CohereRerank
                    compressor = CohereRerank(
                        cohere_api_key=self.api_keys["cohere"].get(),
                        top_n=final_k,
                        model="rerank-english-v3.0",
                    )
                    # We manually compress because we already have docs
                    compressed_docs = compressor.compress_documents(docs, query)
                    final_docs = compressed_docs
                    self.log(
                        f"Reranked down to {len(final_docs)} high-relevance chunks."
                    )
                except Exception as e:
                    self.log(f"Rerank Error (Using raw retrieval instead): {e}")
                    final_docs = docs[:final_k]  # Fallback to top K raw
            else:
                final_docs = docs[:final_k]  # No reranker, just take top K

            # 3. Context Construction
            context_budget_chars = max(2000, int(self.llm_max_tokens.get() * 4))
            context_budget_tokens = context_budget_chars // 4
            context_blocks = []
            used_chars = 0

            for idx, doc in enumerate(final_docs, start=1):
                metadata = getattr(doc, "metadata", {}) or {}
                score = metadata.get("relevance_score", "N/A")
                source = (
                    metadata.get("source")
                    or metadata.get("file_path")
                    or metadata.get("filename")
                    or "unknown"
                )
                header = f"[Chunk {idx} | score: {score} | source: {source}]"
                content = doc.page_content.strip()
                chunk_text = f"{header}\n{content}"

                remaining = context_budget_chars - used_chars
                if remaining <= 0:
                    break
                if len(chunk_text) > remaining:
                    if remaining > len(header) + 20:
                        truncated_content = content[: remaining - len(header) - 20].rstrip()
                        chunk_text = f"{header}\n{truncated_content}\n...[truncated]"
                    else:
                        break
                context_blocks.append(chunk_text)
                used_chars += len(chunk_text) + 2

            context_text = "\n\n".join(context_blocks)

            # 4. Generation
            self.log("Generating Answer...")
            llm = self.get_llm()

            # Prompt
            system_prompt = (
                f"{self._get_system_instructions()}\n\n"
                f"CONTEXT:\n{context_text}"
            )
            history_window = self._get_history_window(current_query=query)
            messages = [
                SystemMessage(content=system_prompt),
                *history_window,
                HumanMessage(content=query),
            ]

            response = llm.invoke(messages)

            self.last_answer = response.content
            self.append_chat("agent", f"AI: {response.content}")
            self._append_history(AIMessage(content=response.content))

            # Show sources
            sources_text = "\n".join(
                [
                    (
                        f"- [Chunk {idx} | score: "
                        f"{getattr(d, 'metadata', {}).get('relevance_score', 'N/A')} | "
                        f"source: "
                        f"{(getattr(d, 'metadata', {}) or {}).get('source') or (getattr(d, 'metadata', {}) or {}).get('file_path') or (getattr(d, 'metadata', {}) or {}).get('filename') or 'unknown'}]"
                    )
                    for idx, d in enumerate(final_docs, start=1)
                ]
            )
            self.append_chat("source", f"\nSources used:\n{sources_text}")

        except Exception as e:
            self.log(f"RAG Error: {e}")
            self.append_chat("system", f"Error: {e}")

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
