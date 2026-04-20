"""metis_app.utils.embedding_providers — Embedding model factory.

``create_embeddings(settings)`` returns an object with
``embed_documents(texts)`` and ``embed_query(text)`` methods (LangChain
``Embeddings`` protocol).  Heavy provider packages are lazily imported.

No Tk objects, no UI — purely driven by a plain settings dict.

M17 Phase 4 note: every concrete embeddings-model construction path
below (``_create_openai_embeddings``, ``_create_google_embeddings``,
``_create_voyage_embeddings``, ``_create_hf_embeddings`` — rows F-I in
the plan's call-site inventory) is wrapped in a
``_EmbeddingsAuditWrapper`` proxy so every ``embed_documents`` /
``embed_query`` call emits a ``source="sdk_invocation"`` audit event and
consults the kill switch. Local sentence-transformers is left unwrapped
— its :class:`LocalSentenceTransformerEmbeddings` class is pure-Python
in-process inference with no outbound traffic and is not classified as a
network provider in :data:`KNOWN_PROVIDERS`. See ADR 0010.
"""

from __future__ import annotations

import logging
from typing import Any

from metis_app.network_audit.sdk_events import audit_sdk_call
from metis_app.network_audit.trigger_features import (
    TRIGGER_EMBEDDING_DOCUMENTS,
    TRIGGER_EMBEDDING_QUERY,
)
from metis_app.utils.llm_providers import _require_key

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Provider → (provider_key, url_host) map for SDK-invocation audit events
# ---------------------------------------------------------------------------
# As with ``_SDK_HOST_MAP`` in ``llm_providers.py``: ``url_host`` is the
# declared primary host, not an observed wire host. See ADR 0010.
# ``huggingface_local`` resolves to loopback — first-run downloads hit
# huggingface.co but that goes through a separate stdlib path that is
# Phase 3's concern; steady-state embed calls are in-process.
_SDK_EMBEDDINGS_HOST_MAP: dict[str, tuple[str, str]] = {
    "openai": ("openai_embeddings", "api.openai.com"),
    "google": ("google_embeddings", "generativelanguage.googleapis.com"),
    "voyage": ("voyage", "api.voyageai.com"),
    "local_huggingface": ("huggingface_local", "localhost"),
}


class _EmbeddingsAuditWrapper:
    """Thin ``embed_documents`` / ``embed_query`` proxy with audit hooks.

    Mirrors ``_ProviderAuditWrapper`` in ``llm_providers.py``. Each
    call opens an :func:`audit_sdk_call` context with a coarse
    ``/embeddings`` path prefix. As with the LLM wrapper, the kill
    switch is honoured (airplane mode in Phase 4; per-provider
    settings in Phase 5), and any transparent attribute access
    forwards to the wrapped object so existing integrations keep
    working.
    """

    __slots__ = ("_inner", "_provider_key", "_url_host", "_user_initiated")

    def __init__(
        self,
        inner: Any,
        *,
        provider_key: str,
        url_host: str,
        user_initiated: bool = False,
    ) -> None:
        self._inner = inner
        self._provider_key = provider_key
        self._url_host = url_host
        # TODO(Phase 4b): thread real user-vs-agent context. Embedding
        # calls happen during indexing (agent-initiated) and during
        # query (user-initiated at the top of the call chain). The
        # distinction is not available here today; Phase 5+ wires it.
        self._user_initiated = user_initiated

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        with audit_sdk_call(
            provider_key=self._provider_key,
            trigger_feature=TRIGGER_EMBEDDING_DOCUMENTS,
            url_host=self._url_host,
            url_path_prefix="/embeddings",
            method="POST",
            user_initiated=self._user_initiated,
        ):
            return self._inner.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        with audit_sdk_call(
            provider_key=self._provider_key,
            trigger_feature=TRIGGER_EMBEDDING_QUERY,
            url_host=self._url_host,
            url_path_prefix="/embeddings",
            method="POST",
            user_initiated=self._user_initiated,
        ):
            return self._inner.embed_query(text)

    def __getattr__(self, item: str) -> Any:
        # Transparent forwarding for any non-audited attribute. This
        # keeps the wrapper a drop-in replacement for the underlying
        # LangChain Embeddings instance.
        return getattr(self._inner, item)


def _wrap_embeddings_for_audit(embeddings: Any, provider_label: str) -> Any:
    """Wrap a concrete embeddings object in the SDK-audit proxy.

    ``provider_label`` is the ``embedding_provider`` setting value
    (``"openai"`` / ``"google"`` / ``"voyage"`` / ``"local_huggingface"``).
    It indexes :data:`_SDK_EMBEDDINGS_HOST_MAP` to produce the
    ``(provider_key, url_host)`` pair for the audit event.
    """
    provider_key, url_host = _SDK_EMBEDDINGS_HOST_MAP[provider_label]
    return _EmbeddingsAuditWrapper(
        embeddings,
        provider_key=provider_key,
        url_host=url_host,
    )


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
    inner = OpenAIEmbeddings(openai_api_key=api_key, model=model)
    return _wrap_embeddings_for_audit(inner, "openai")


def _create_google_embeddings(settings: dict[str, Any], model: str) -> Any:
    from langchain_google_genai import GoogleGenerativeAIEmbeddings  # type: ignore[import-untyped]

    api_key = _require_key(settings, "api_key_google", "Google")
    inner = GoogleGenerativeAIEmbeddings(google_api_key=api_key, model=model)
    return _wrap_embeddings_for_audit(inner, "google")


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
        inner = cls(voyage_api_key=api_key, model=model, truncation=True)
    except TypeError:
        # Older versions don't support the truncation kwarg.
        inner = cls(voyage_api_key=api_key, model=model)
    return _wrap_embeddings_for_audit(inner, "voyage")


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
    inner = HuggingFaceEmbeddings(model_name=resolved)
    # Loopback once the model cache is populated; first-run downloads
    # hit huggingface.co via the vendor SDK (separate audit surface).
    # We still wrap here so airplane mode can block even loopback
    # embed calls — the audit panel shows "zero loopback too" during
    # verification, which is load-bearing for the privacy pitch.
    return _wrap_embeddings_for_audit(inner, "local_huggingface")


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



