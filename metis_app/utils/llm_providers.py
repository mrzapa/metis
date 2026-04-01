"""metis_app.utils.llm_providers — LLM chat-model factory.

``create_llm(settings)`` returns an object with an ``.invoke(messages)``
method (LangChain ``BaseChatModel`` protocol).  All heavy dependencies are
lazily imported so the module itself stays lightweight.

No Tk objects, no UI — purely driven by a plain settings dict.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from metis_app.utils.model_caps import get_capped_output_tokens

_log = logging.getLogger(__name__)

_llm_cache: dict[tuple, Any] = {}


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


# ---------------------------------------------------------------------------
# Private per-provider constructors
# ---------------------------------------------------------------------------

def _create_openai(
    settings: dict[str, Any], model: str, temperature: float, max_tokens: int,
) -> Any:
    from langchain_openai import ChatOpenAI  # type: ignore[import-untyped]

    api_key = _require_key(settings, "api_key_openai", "OpenAI")
    return ChatOpenAI(
        api_key=api_key,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def _create_anthropic(
    settings: dict[str, Any], model: str, temperature: float, max_tokens: int,
) -> Any:
    from langchain_anthropic import ChatAnthropic  # type: ignore[import-untyped]

    api_key = _require_key(settings, "api_key_anthropic", "Anthropic")
    return ChatAnthropic(
        api_key=api_key,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def _create_google(
    settings: dict[str, Any], model: str, temperature: float, max_tokens: int,
) -> Any:
    from langchain_google_genai import ChatGoogleGenerativeAI  # type: ignore[import-untyped]

    api_key = _require_key(settings, "api_key_google", "Google")
    return ChatGoogleGenerativeAI(
        google_api_key=api_key,
        model=model,
        temperature=temperature,
        max_output_tokens=max_tokens,
    )


def _create_xai(
    settings: dict[str, Any], model: str, temperature: float, max_tokens: int,
) -> Any:
    from langchain_openai import ChatOpenAI  # type: ignore[import-untyped]

    api_key = _require_key(settings, "api_key_xai", "xAI")
    return ChatOpenAI(
        base_url="https://api.x.ai/v1",
        api_key=api_key,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def _create_lm_studio(
    settings: dict[str, Any], model: str, temperature: float, max_tokens: int,
) -> Any:
    from langchain_openai import ChatOpenAI  # type: ignore[import-untyped]

    url = str(settings.get("local_llm_url", "http://localhost:1234/v1") or "").strip()
    _log.info("Connecting to Local LLM at %s", url)
    return ChatOpenAI(
        base_url=url,
        api_key="lm-studio",
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )


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
