"""axiom_app.config — Application-wide configuration constants and Config dataclass.

This module will become the single source of truth for app identity, theming
defaults, and runtime configuration once constants are migrated out of
agentic_rag_gui.py.

Migration status: PLACEHOLDER — values here are not yet used by the running app.
All live constants still reside in agentic_rag_gui.py.  Each constant below
will be wired up and the duplicate in agentic_rag_gui.py removed in a
subsequent refactor step.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# App identity
# ---------------------------------------------------------------------------

APP_NAME: str = "Axiom"
APP_VERSION: str = "1.0"
APP_SUBTITLE: str = "Personal RAG Assistant"

# ---------------------------------------------------------------------------
# UI backend
# Resolved at runtime in agentic_rag_gui.py; mirrored here as the future
# canonical location.  Valid values: "ctk" | "ttkbootstrap" | "ttk"
# ---------------------------------------------------------------------------

UI_BACKEND_DEFAULT: str = "ttk"

# ---------------------------------------------------------------------------
# Config dataclass
# Fields will be populated as settings are migrated from AgenticRAGApp.__init__
# ---------------------------------------------------------------------------


@dataclass
class Config:
    """Runtime configuration for the Axiom application.

    All fields are optional with sensible defaults so the dataclass can be
    instantiated with zero arguments before full migration is complete.

    TODO: migrate fields from AgenticRAGApp.__init__ tk.*Var declarations:
      - llm_provider, embedding_provider, vector_db_type
      - chunk_size, chunk_overlap
      - retrieval_k, final_k, mmr_lambda
      - agentic_mode, agentic_max_iterations
      - theme selection
      - api_keys (store as plain str, not tk.StringVar)
    """

    # App identity (read-only at runtime)
    app_name: str = APP_NAME
    app_version: str = APP_VERSION
    ui_backend: str = UI_BACKEND_DEFAULT

    # LLM / embedding providers
    llm_provider: str = "anthropic"
    llm_model: str = "claude-opus-4-6"
    embedding_provider: str = "voyage"
    embedding_model: str = "voyage-4-large"
    vector_db_type: str = "chroma"

    # Ingestion defaults
    chunk_size: int = 1000
    chunk_overlap: int = 200
    structure_aware_ingestion: bool = False
    build_digest_index: bool = True
    build_comprehension_index: bool = False

    # Retrieval defaults
    retrieval_k: int = 25
    final_k: int = 5
    mmr_lambda: float = 0.5
    retrieval_mode: str = "flat"
    agentic_mode: bool = False
    agentic_max_iterations: int = 2

    # UI defaults
    theme: str = "space_dust"
    output_style: str = "Default answer"
    selected_mode: str = "Q&A"

    # API keys (populated from config file or env; never hard-coded)
    api_keys: dict[str, str] = field(default_factory=dict)
