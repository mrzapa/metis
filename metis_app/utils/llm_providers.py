"""metis_app.utils.llm_providers — LLM chat-model factory.

``create_llm(settings)`` returns an object with an ``.invoke(messages)``
method (LangChain ``BaseChatModel`` protocol).  All heavy dependencies are
lazily imported so the module itself stays lightweight.

No Tk objects, no UI — purely driven by a plain settings dict.

M17 Phase 4 note: every concrete chat-model construction path below
(``_create_openai``, ``_create_anthropic``, etc. — rows A-E in the
plan's call-site inventory) is wrapped in a ``_ProviderAuditWrapper``
proxy so every ``invoke`` / ``stream`` call emits a
``source="sdk_invocation"`` audit event and consults the kill switch.
See ``metis_app/network_audit/sdk_events.py`` and ADR 0010.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from metis_app.network_audit.sdk_events import audit_sdk_call
from metis_app.network_audit.trigger_features import (
    TRIGGER_LLM_INVOKE,
    TRIGGER_LLM_STREAM,
)
from metis_app.utils.model_caps import get_capped_output_tokens
from metis_app.utils.credential_pool import CredentialPool as _CredentialPool

_log = logging.getLogger(__name__)

_llm_cache: dict[tuple, Any] = {}


# ---------------------------------------------------------------------------
# Provider → (url_host, provider_key) map for SDK-invocation audit events
# ---------------------------------------------------------------------------
# ``url_host`` is the provider's *declared* primary API host — not an
# observed wire host. See ADR 0010: these events are labelled
# ``source="sdk_invocation"`` precisely so the panel can caveat them
# as intent-level (we don't wrap LangChain's httpx client). The
# ``provider_key`` matches the entry in
# ``metis_app/network_audit/providers.py:KNOWN_PROVIDERS``.
_SDK_HOST_MAP: dict[str, tuple[str, str]] = {
    "openai": ("openai", "api.openai.com"),
    "anthropic": ("anthropic", "api.anthropic.com"),
    "google": ("google", "generativelanguage.googleapis.com"),
    "xai": ("xai", "api.x.ai"),
    "local_lm_studio": ("local_lm_studio", "localhost"),
}


class _ProviderAuditWrapper:
    """Thin invoke/stream proxy that emits SDK-invocation audit events.

    Wraps any object with ``invoke(messages)`` and ``stream(messages)``
    methods (a LangChain ``BaseChatModel`` or the matching interface).
    Each call opens an :func:`audit_sdk_call` context with the
    provider-specific ``url_host`` and ``/chat`` or ``/stream`` path
    prefix. If the provider's kill switch is active (airplane mode in
    Phase 4 — per-LLM-provider switches are Phase 5), the call raises
    :class:`NetworkBlockedError` instead of touching the wrapped model.

    The wrapper is intentionally dumb: it does not reimplement the
    retry / pool-rotate behaviour from ``PooledLLM`` — that wrapper
    composes *around* this one (``PooledLLM`` calls ``factory(key)``
    which returns a wrapped model, so every retry attempt is also
    audited).
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
        # TODO(Phase 4b): thread real user-vs-agent context from the
        # call site. For now every SDK invocation is recorded with
        # ``user_initiated=False``; the Phase 7 coordination hooks
        # (M06 / M09) re-audit this.
        self._user_initiated = user_initiated

    def invoke(self, messages: list[Any]) -> Any:
        with audit_sdk_call(
            provider_key=self._provider_key,
            trigger_feature=TRIGGER_LLM_INVOKE,
            url_host=self._url_host,
            url_path_prefix="/chat",
            method="POST",
            user_initiated=self._user_initiated,
        ):
            return self._inner.invoke(messages)

    def stream(self, messages: list[Any]) -> Any:
        # Keep lazy streaming intact: yield chunks as they arrive rather
        # than materialising the full response before the caller sees
        # the first token. ``engine/streaming.py`` iterates this output
        # chunk-by-chunk to render incremental tokens to the UI;
        # collecting into a list would buffer the whole response first
        # (regression). The ``audit_sdk_call`` context manager stays
        # open for the whole stream, so the recorded ``latency_ms``
        # reflects end-to-end stream time — matches wall-clock
        # experience, which is what the panel should show.
        with audit_sdk_call(
            provider_key=self._provider_key,
            trigger_feature=TRIGGER_LLM_STREAM,
            url_host=self._url_host,
            url_path_prefix="/stream",
            method="POST",
            user_initiated=self._user_initiated,
        ):
            yield from self._inner.stream(messages)

    def __getattr__(self, item: str) -> Any:
        # Transparent forwarding for any non-audited attribute (e.g.
        # ``batch``, configuration properties) so existing integrations
        # that poke at the underlying model still work.
        #
        # Known audit gap: LangChain's ``with_structured_output``,
        # ``bind_tools``, ``with_retry``, and ``with_fallbacks`` each
        # return a NEW model instance; invoking that new model
        # BYPASSES this wrapper. No production call site in metis_app
        # uses those methods today (grep-verified on 2026-04-20);
        # Phase 4b or 5 should either override them to re-wrap the
        # return value or migrate to LangChain callback handlers,
        # which hook the model lifecycle more cleanly.
        return getattr(self._inner, item)


# ---------------------------------------------------------------------------
# PooledLLM — retries with the next pool key on 401/429 errors
# ---------------------------------------------------------------------------

class PooledLLM:
    """LLM wrapper that retries with the next pool key on 401/429 errors.

    Matches the invoke() / stream() interface of LangChain BaseChatModel.
    Ported from Hermes Agent v0.7.0 credential_pool pattern.
    """

    _AUTH_KEYWORDS = ("401", "unauthorized", "authentication", "invalid api key", "ratelimit", "429")

    def __init__(
        self,
        pool: _CredentialPool,
        factory: Any,  # Callable[[str], LLM]
        initial_key: str,
    ) -> None:
        self._pool = pool
        self._factory = factory
        self._current_key = initial_key
        self._llm = factory(initial_key)

    def _is_auth_error(self, exc: Exception) -> bool:
        msg = str(exc).lower()
        return any(kw in msg for kw in self._AUTH_KEYWORDS)

    def _rotate(self) -> None:
        self._pool.report_failure(self._current_key)
        self._current_key = self._pool.get_key()  # raises RuntimeError if pool empty
        self._llm = self._factory(self._current_key)

    def invoke(self, messages: list[Any]) -> Any:
        try:
            result = self._llm.invoke(messages)
            self._pool.report_success(self._current_key)
            return result
        except Exception as exc:
            if self._is_auth_error(exc):
                self._rotate()
                result = self._llm.invoke(messages)
                self._pool.report_success(self._current_key)
                return result
            raise

    def stream(self, messages: list[Any]) -> Any:
        try:
            yield from self._llm.stream(messages)
            self._pool.report_success(self._current_key)
        except Exception as exc:
            if self._is_auth_error(exc):
                self._rotate()
                yield from self._llm.stream(messages)
                self._pool.report_success(self._current_key)
            else:
                raise


# ---------------------------------------------------------------------------
# Lightweight mock chat model (no external deps)
# ---------------------------------------------------------------------------

@dataclass
class _ChatMessage:
    """Minimal stand-in for a LangChain AI message."""
    content: str
    type: str = "ai"


class MockChatModel:
    """Deterministic mock — returns a templated response summarising the
    prompt and any context found in the system message.  Useful for test
    mode and offline development.
    """

    def invoke(self, messages: list[Any]) -> _ChatMessage:
        import json as _json
        import re as _re

        system_text = ""
        user_text = ""
        for msg in reversed(messages or []):
            msg_type = _msg_type(msg)
            if not system_text and msg_type == "system":
                system_text = _msg_content(msg)
            if not user_text and msg_type in {"human", "user"}:
                user_text = _msg_content(msg).strip()
            if system_text and user_text:
                break
        if not user_text:
            user_text = "(no user prompt provided)"

        # JSON-schema requests (sub-query planner, etc.) get an empty-but-valid JSON.
        if "Return strict JSON" in system_text:
            return _ChatMessage(
                content=_json.dumps(
                    {"checklist_review": [], "retrieval_queries": []},
                    ensure_ascii=False,
                )
            )

        ctx_match = _re.search(r"CONTEXT:\s*(.+)", system_text, flags=_re.DOTALL)
        ctx_preview = (
            _re.sub(r"\s+", " ", ctx_match.group(1).strip())[:220]
            if ctx_match
            else "(no context block found)"
        )
        return _ChatMessage(
            content=(
                "[Mock/Test Backend]\n"
                "Short answer: Local mock backend executed successfully "
                "with deterministic output.\n\n"
                "Citations:\n- [S1] chunk_ids: [1]\n\n"
                "Debug retrieved:\n"
                f"- prompt: {user_text}\n"
                f"- context_preview: {ctx_preview}"
            )
        )


# ---------------------------------------------------------------------------
# Local GGUF chat model (llama-cpp-python)
# ---------------------------------------------------------------------------

class LocalLlamaCppChatModel:
    """Thin ``invoke(messages)`` adapter around ``llama-cpp-python``.

    Unlike ``llm_backends.LocalGGUFBackend`` (raw completions), this class
    uses the chat-completion API expected by the RAG pipeline.
    """

    def __init__(
        self,
        *,
        model_path: str,
        n_ctx: int = 2048,
        temperature: float = 0.0,
        max_tokens: int = 512,
        n_gpu_layers: int = 0,
        n_threads: int = 0,
    ) -> None:
        try:
            from llama_cpp import Llama  # type: ignore[import-untyped]
        except ImportError as exc:
            raise RuntimeError(
                "llama-cpp-python is not installed. "
                "Install it to use llm_provider=local_gguf."
            ) from exc

        kwargs: dict[str, Any] = {
            "model_path": model_path,
            "n_ctx": max(256, int(n_ctx)),
            "verbose": False,
        }
        if int(n_gpu_layers) > 0:
            kwargs["n_gpu_layers"] = int(n_gpu_layers)
        if int(n_threads) > 0:
            kwargs["n_threads"] = int(n_threads)

        self._llm = Llama(**kwargs)
        self._temperature = float(temperature)
        self._max_tokens = max(1, int(max_tokens))

    def invoke(self, messages: list[Any]) -> _ChatMessage:
        payload: list[dict[str, str]] = []
        for msg in messages or []:
            mt = _msg_type(msg)
            if mt == "system":
                role = "system"
            elif mt in {"ai", "assistant"}:
                role = "assistant"
            else:
                role = "user"
            payload.append({"role": role, "content": _msg_content(msg)})

        result = self._llm.create_chat_completion(
            messages=payload,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
        )
        content = ""
        try:
            content = result["choices"][0]["message"]["content"]  # type: ignore[index]
        except Exception:
            content = ""
        return _ChatMessage(content=content or "")


# ---------------------------------------------------------------------------
# Public factory
# ---------------------------------------------------------------------------

def create_llm(settings: dict[str, Any]) -> Any:
    """Construct and return an LLM chat model from *settings*.

    Parameters
    ----------
    settings:
        Flat settings dict (as stored in ``AppModel.settings``).
        Required keys: ``llm_provider``.
        Optional keys vary by provider — see ``default_settings.json``.

    Returns
    -------
    An object with ``.invoke(messages)`` returning an AI-message object
    whose ``.content`` attribute is the response text.

    Raises
    ------
    ValueError
        Missing API key or unknown provider.
    ImportError
        Provider-specific LangChain package is not installed.
    """
    provider = str(settings.get("llm_provider", "mock") or "mock").strip().lower()
    model_name = _resolve_model(settings)
    temperature = float(settings.get("llm_temperature", 0.0))
    requested_max = int(settings.get("llm_max_tokens", 1024))
    output_max = get_capped_output_tokens(provider, model_name, requested_max)

    _log.info(
        "create_llm: provider=%s model=%s temp=%.2f max_tokens=%d",
        provider, model_name, temperature, output_max,
    )

    # --- Credential pool rotation ---
    _pool_keys = list(
        (settings.get("credential_pool") or {}).get(provider) or []
    )
    _POOL_KEY_MAP: dict[str, str] = {
        "openai": "api_key_openai",
        "anthropic": "api_key_anthropic",
        "google": "api_key_google",
        "xai": "api_key_xai",
    }
    if _pool_keys and provider in _POOL_KEY_MAP:
        _pool = _CredentialPool(_pool_keys)
        _initial_key = _pool.get_key()

        def _llm_factory(
            key: str,
            _p: str = provider,
            _m: str = model_name,
            _t: float = temperature,
            _o: int = output_max,
            _s: dict = settings,
            _km: dict = _POOL_KEY_MAP,
        ) -> Any:
            _settings_copy = dict(_s)
            _settings_copy[_km[_p]] = key
            if _p == "openai":
                return _create_openai(_settings_copy, _m, _t, _o)
            if _p == "anthropic":
                return _create_anthropic(_settings_copy, _m, _t, _o)
            if _p == "google":
                return _create_google(_settings_copy, _m, _t, _o)
            if _p == "xai":
                return _create_xai(_settings_copy, _m, _t, _o)
            raise ValueError(f"Credential pool not supported for provider: {_p}")

        _pool.report_success(_initial_key)
        return PooledLLM(pool=_pool, factory=_llm_factory, initial_key=_initial_key)

    _UNCACHED = frozenset({"local_gguf", "mock"})
    if provider not in _UNCACHED:
        _key = (
            provider,
            model_name,
            temperature,
            output_max,
            settings.get("api_key_openai") or "",
            settings.get("api_key_anthropic") or "",
            settings.get("api_key_google") or "",
            settings.get("api_key_xai") or "",
            settings.get("local_llm_url") or "",
        )
        if _key in _llm_cache:
            _log.debug("create_llm: cache hit for %s/%s", provider, model_name)
            return _llm_cache[_key]

    if provider == "openai":
        llm = _create_openai(settings, model_name, temperature, output_max)
    elif provider == "anthropic":
        llm = _create_anthropic(settings, model_name, temperature, output_max)
    elif provider == "google":
        llm = _create_google(settings, model_name, temperature, output_max)
    elif provider == "xai":
        llm = _create_xai(settings, model_name, temperature, output_max)
    elif provider == "local_lm_studio":
        llm = _create_lm_studio(settings, model_name, temperature, output_max)
    elif provider == "local_gguf":
        llm = _create_local_gguf(settings, temperature, output_max)
    elif provider == "mock":
        llm = MockChatModel()
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")

    if provider not in _UNCACHED:
        _llm_cache[_key] = llm
    return llm


def create_smart_llm(settings: dict[str, Any]) -> Any:
    """Construct and return an LLM for intelligence-sensitive workflows.

    Uses ``smart_llm_provider`` / ``smart_llm_model`` from *settings* when
    set, falling back transparently to ``create_llm(settings)`` otherwise.
    Intended for Research-mode final synthesis and Evidence Pack output.

    Parameters
    ----------
    settings:
        Same flat settings dict as accepted by ``create_llm``.

    Returns
    -------
    An object with ``.invoke(messages)`` — same protocol as ``create_llm``.
    """
    smart_provider = str(settings.get("smart_llm_provider", "") or "").strip()
    smart_model = str(settings.get("smart_llm_model", "") or "").strip()

    if not smart_provider and not smart_model:
        _log.info("create_smart_llm: no smart model configured, using primary")
        return create_llm(settings)

    smart_settings = dict(settings)
    if smart_provider:
        smart_settings["llm_provider"] = smart_provider
    if smart_model:
        smart_settings["llm_model"] = smart_model
        smart_settings["llm_model_custom"] = ""

    raw_temp = settings.get("smart_llm_temperature")
    smart_settings["llm_temperature"] = (
        float(raw_temp) if raw_temp is not None
        else float(settings.get("llm_temperature", 0.0))
    )
    raw_max = settings.get("smart_llm_max_tokens")
    smart_settings["llm_max_tokens"] = (
        int(raw_max) if raw_max is not None
        else int(settings.get("llm_max_tokens", 2048))
    )

    _log.info(
        "create_smart_llm: using smart model %s/%s",
        smart_settings["llm_provider"], smart_settings["llm_model"],
    )
    return create_llm(smart_settings)


# ---------------------------------------------------------------------------
# Private per-provider constructors
# ---------------------------------------------------------------------------

def _wrap_for_audit(llm: Any, provider_key_label: str) -> Any:
    """Wrap a concrete LangChain LLM in the SDK-audit proxy.

    ``provider_key_label`` is the internal llm_providers.py routing
    label (``"openai"`` / ``"anthropic"`` / ``"google"`` / ``"xai"`` /
    ``"local_lm_studio"``). It indexes :data:`_SDK_HOST_MAP` to produce
    the ``(provider_key, url_host)`` pair for the audit event.
    """
    provider_key, url_host = _SDK_HOST_MAP[provider_key_label]
    return _ProviderAuditWrapper(
        llm,
        provider_key=provider_key,
        url_host=url_host,
    )


def _create_openai(
    settings: dict[str, Any], model: str, temperature: float, max_tokens: int,
) -> Any:
    from langchain_openai import ChatOpenAI  # type: ignore[import-untyped]

    api_key = _require_key(settings, "api_key_openai", "OpenAI")
    llm = ChatOpenAI(
        api_key=api_key,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return _wrap_for_audit(llm, "openai")


def _create_anthropic(
    settings: dict[str, Any], model: str, temperature: float, max_tokens: int,
) -> Any:
    from langchain_anthropic import ChatAnthropic  # type: ignore[import-untyped]

    api_key = _require_key(settings, "api_key_anthropic", "Anthropic")
    llm = ChatAnthropic(
        api_key=api_key,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return _wrap_for_audit(llm, "anthropic")


def _create_google(
    settings: dict[str, Any], model: str, temperature: float, max_tokens: int,
) -> Any:
    from langchain_google_genai import ChatGoogleGenerativeAI  # type: ignore[import-untyped]

    api_key = _require_key(settings, "api_key_google", "Google")
    llm = ChatGoogleGenerativeAI(
        google_api_key=api_key,
        model=model,
        temperature=temperature,
        max_output_tokens=max_tokens,
    )
    return _wrap_for_audit(llm, "google")


def _create_xai(
    settings: dict[str, Any], model: str, temperature: float, max_tokens: int,
) -> Any:
    from langchain_openai import ChatOpenAI  # type: ignore[import-untyped]

    api_key = _require_key(settings, "api_key_xai", "xAI")
    llm = ChatOpenAI(
        base_url="https://api.x.ai/v1",
        api_key=api_key,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return _wrap_for_audit(llm, "xai")


def _create_lm_studio(
    settings: dict[str, Any], model: str, temperature: float, max_tokens: int,
) -> Any:
    from langchain_openai import ChatOpenAI  # type: ignore[import-untyped]

    url = str(settings.get("local_llm_url", "http://localhost:1234/v1") or "").strip()
    _log.info("Connecting to Local LLM at %s", url)
    llm = ChatOpenAI(
        base_url=url,
        api_key="lm-studio",
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return _wrap_for_audit(llm, "local_lm_studio")


def _create_local_gguf(
    settings: dict[str, Any], temperature: float, max_tokens: int,
) -> LocalLlamaCppChatModel:
    import os

    model_path = str(settings.get("local_gguf_model_path", "") or "").strip()
    if not model_path or not os.path.isfile(model_path):
        raise ValueError(
            "local_gguf model path is invalid. "
            "Choose a valid .gguf file in Settings."
        )
    return LocalLlamaCppChatModel(
        model_path=model_path,
        n_ctx=max(256, int(settings.get("local_gguf_context_length", 2048))),
        temperature=temperature,
        max_tokens=max_tokens,
        n_gpu_layers=max(0, int(settings.get("local_gguf_gpu_layers", 0))),
        n_threads=max(0, int(settings.get("local_gguf_threads", 0))),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_model(settings: dict[str, Any]) -> str:
    """Pick the effective model name from settings, preferring a custom
    override when the base ``llm_model`` field is ``custom``."""
    base = str(settings.get("llm_model", "") or "").strip()
    custom = str(settings.get("llm_model_custom", "") or "").strip()
    if base.lower() == "custom" and custom:
        return custom
    return base or "claude-opus-4-6"


def _require_key(settings: dict[str, Any], key_name: str, label: str) -> str:
    """Extract a non-empty API key from *settings* or raise."""
    val = str(settings.get(key_name, "") or "").strip()
    if not val:
        raise ValueError(f"{label} API key is missing (settings key: {key_name})")
    return val


def _msg_type(msg: Any) -> str:
    """Extract the role/type string from a message (LangChain or dict)."""
    if isinstance(msg, dict):
        return str(msg.get("type", msg.get("role", ""))).strip().lower()
    return str(getattr(msg, "type", getattr(msg, "role", ""))).strip().lower()


def _msg_content(msg: Any) -> str:
    """Extract the content string from a message (LangChain or dict)."""
    if isinstance(msg, dict):
        return str(msg.get("content", ""))
    return str(getattr(msg, "content", "") or "")


def clear_llm_cache() -> None:
    """Invalidate the module-level LLM client cache.

    Call this after settings changes to force fresh client construction on
    the next ``create_llm`` call.  The ``local_gguf`` and ``mock`` providers
    are never cached, so this has no effect on them.
    """
    _llm_cache.clear()
