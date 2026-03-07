"""axiom_app.config — Application-wide configuration constants and Config dataclass.

This module holds shared app identity and baseline runtime defaults used by the
MVC app while the legacy runtime remains available behind the default entry
path.
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
# Valid values: "pyside6" | "ttk"
# ---------------------------------------------------------------------------

UI_BACKEND_DEFAULT: str = "pyside6"

# ---------------------------------------------------------------------------
# Config dataclass
# Fields mirror the MVC runtime defaults.
# ---------------------------------------------------------------------------


@dataclass
class Config:
    """Runtime configuration for the Axiom application.

    All fields are optional with sensible defaults so the dataclass can be
    instantiated with zero arguments in non-GUI contexts.
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
    vector_db_type: str = "json"

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
