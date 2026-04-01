"""metis_app.utils.embedding_providers — Embedding model factory.

``create_embeddings(settings)`` returns an object with
``embed_documents(texts)`` and ``embed_query(text)`` methods (LangChain
``Embeddings`` protocol).  Heavy provider packages are lazily imported.

No Tk objects, no UI — purely driven by a plain settings dict.
"""

from __future__ import annotations

import logging
from typing import Any

from metis_app.utils.llm_providers import _require_key

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Local sentence-transformers backend (no LangChain dependency)
# ---------------------------------------------------------------------------

class LocalSentenceTransformerEmbeddings:
    """Batched embedding via ``sentence-transformers`` on local CPU/GPU."""

    def __init__(
        self,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        cache_folder: str | None = None,
        batch_size: int = 32,
    ) -> None:
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "sentence-transformers is not installed. "
                "Install it from Settings."
            ) from exc

        self.model_name = (model_name or "sentence-transformers/all-MiniLM-L6-v2").strip()
        self.cache_folder = (cache_folder or "").strip() or None
        self.batch_size = max(1, int(batch_size))
        self._model = SentenceTransformer(self.model_name, cache_folder=self.cache_folder)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        safe_texts = [t or "" for t in (texts or [])]
        for i in range(0, len(safe_texts), self.batch_size):
            batch = safe_texts[i : i + self.batch_size]
            encoded = self._model.encode(
                batch,
                batch_size=self.batch_size,
                show_progress_bar=False,
                convert_to_numpy=True,
            )
            vectors.extend(encoded.tolist())
        return vectors

    def embed_query(self, text: str) -> list[float]:
        encoded = self._model.encode(
            [text or ""],
            batch_size=1,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return encoded[0].tolist()


# ---------------------------------------------------------------------------
# Public factory
# ---------------------------------------------------------------------------

def create_embeddings(settings: dict[str, Any]) -> Any:
    """Construct and return an embedding model from *settings*.

    Parameters
    ----------
    settings:
        Flat settings dict (as stored in ``AppModel.settings``).
        Required keys: ``embedding_provider``.

    Returns
    -------
    An object with ``embed_documents(texts)`` → ``list[list[float]]``
    and ``embed_query(text)`` → ``list[float]``.

    Raises
    ------
    ValueError
        Missing API key or unknown provider.
    ImportError
        Provider-specific package not installed.
    """
    provider = str(settings.get("embedding_provider", "mock") or "mock").strip().lower()
    model_name = _resolve_embedding_model(settings, provider)

    _log.info("create_embeddings: provider=%s model=%s", provider, model_name)

    if provider == "openai":
        return _create_openai_embeddings(settings, model_name)

    if provider == "google":
        return _create_google_embeddings(settings, model_name)

    if provider == "voyage":
        return _create_voyage_embeddings(settings, model_name)

    if provider == "local_huggingface":
        return _create_hf_embeddings(model_name)

    if provider == "local_sentence_transformers":
        return _create_st_embeddings(settings, model_name)

    if provider == "mock":
        from metis_app.utils.mock_embeddings import MockEmbeddings
        return MockEmbeddings()

    raise ValueError(f"Unknown embedding provider: {provider}")


# ---------------------------------------------------------------------------
# Per-provider constructors
# ---------------------------------------------------------------------------

def _create_openai_embeddings(settings: dict[str, Any], model: str) -> Any:
    from langchain_openai import OpenAIEmbeddings  # type: ignore[import-untyped]

    api_key = _require_key(settings, "api_key_openai", "OpenAI")
    return OpenAIEmbeddings(openai_api_key=api_key, model=model)


def _create_google_embeddings(settings: dict[str, Any], model: str) -> Any:
    from langchain_google_genai import GoogleGenerativeAIEmbeddings  # type: ignore[import-untyped]

    api_key = _require_key(settings, "api_key_google", "Google")
    return GoogleGenerativeAIEmbeddings(google_api_key=api_key, model=model)


def _create_voyage_embeddings(settings: dict[str, Any], model: str) -> Any:
    api_key = _require_key(settings, "api_key_voyage", "Voyage")

    # VoyageAI renamed their class across versions — handle both.
    try:
        from langchain_voyageai import VoyageAIEmbeddings  # type: ignore[import-untyped]
        cls = VoyageAIEmbeddings
    except ImportError:
        try:
            module = __import__("langchain_voyageai", fromlist=["VoyageEmbeddings"])
            cls = getattr(module, "VoyageEmbeddings", None)
            if cls is None:
                raise ImportError(
                    "langchain-voyageai is installed but exports neither "
                    "VoyageAIEmbeddings nor VoyageEmbeddings."
                )
        except ImportError as exc:
            raise ImportError(
                "langchain-voyageai is not installed. "
                "Install it to use Voyage embeddings."
            ) from exc

    try:
        return cls(voyage_api_key=api_key, model=model, truncation=True)
    except TypeError:
        # Older versions don't support the truncation kwarg.
        return cls(voyage_api_key=api_key, model=model)


def _create_hf_embeddings(model: str) -> Any:
    try:
        from langchain_community.embeddings import HuggingFaceEmbeddings  # type: ignore[import-untyped]
    except (ImportError, AttributeError) as exc:
        raise ImportError(
            "langchain-community is not installed. "
            "Install it to use local HuggingFace embeddings."
        ) from exc

    resolved = model or "all-MiniLM-L6-v2"
    _log.info("Loading local HuggingFace embeddings (%s)", resolved)
    return HuggingFaceEmbeddings(model_name=resolved)


def _create_st_embeddings(settings: dict[str, Any], model: str) -> LocalSentenceTransformerEmbeddings:
    resolved = model or "sentence-transformers/all-MiniLM-L6-v2"
    cache_dir = str(settings.get("local_st_cache_dir", "") or "").strip()
    batch_size = max(1, int(settings.get("local_st_batch_size", 32)))
    _log.info(
        "Loading local sentence-transformers (%s, batch_size=%d)",
        resolved, batch_size,
    )
    return LocalSentenceTransformerEmbeddings(
        model_name=resolved,
        cache_folder=cache_dir or None,
        batch_size=batch_size,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_embedding_model(settings: dict[str, Any], provider: str) -> str:
    """Pick the effective embedding model name, preferring a custom override."""
    base = str(settings.get("embedding_model", "") or "").strip()
    custom = str(settings.get("embedding_model_custom", "") or "").strip()
    if base.lower() == "custom" and custom:
        return custom

    # For local sentence-transformers, use the dedicated setting.
    if provider == "local_sentence_transformers":
        st_model = str(settings.get("sentence_transformers_model", "") or "").strip()
        return st_model or base or "sentence-transformers/all-MiniLM-L6-v2"

    return base or "voyage-4-large"



