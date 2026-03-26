"""Shared LLM provider/model preset helpers for the GUI."""

from __future__ import annotations

LLM_PROVIDER_OPTIONS: tuple[str, ...] = (
    "anthropic",
    "openai",
    "google",
    "xai",
    "local_lm_studio",
    "local_gguf",
    "mock",
)

_LLM_MODEL_PRESETS: dict[str, tuple[str, ...]] = {
    "openai": (
        "gpt-5.2",
        "gpt-5.2-pro",
        "gpt-5.2-codex",
        "gpt-5.1",
        "gpt-5.1-codex",
        "gpt-5.1-codex-mini",
        "gpt-5",
        "gpt-5-mini",
        "gpt-5-nano",
        "gpt-4.1",
        "gpt-4.1-mini",
        "gpt-4.1-nano",
        "gpt-4o",
        "gpt-4o-mini",
        "o3",
        "o3-pro",
        "o4-mini",
        "custom",
    ),
    "anthropic": (
        "claude-opus-4-6",
        "claude-sonnet-4-6",
        "claude-haiku-4-5",
        "claude-3-7-sonnet-20250219",
        "claude-3-5-sonnet-20240620",
        "claude-3-5-haiku-20241022",
        "custom",
    ),
    "google": (
        "gemini-3-pro-preview",
        "gemini-3-flash",
        "gemini-2.5-pro",
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-1.5-pro",
        "gemini-1.5-flash",
        "custom",
    ),
    "xai": (
        "grok-4",
        "grok-4-heavy",
        "grok-3",
        "grok-3-mini",
        "custom",
    ),
    "local_lm_studio": ("custom",),
    "local_gguf": ("custom",),
    "mock": ("mock-test-v1",),
}

_CUSTOM_ONLY_PROVIDERS = {"local_lm_studio", "local_gguf"}


def list_llm_providers() -> list[str]:
    return list(LLM_PROVIDER_OPTIONS)


def get_llm_model_presets(provider: str) -> list[str]:
    provider_name = str(provider or "").strip()
    return list(_LLM_MODEL_PRESETS.get(provider_name, ("custom",)))


def provider_requires_custom_model(provider: str) -> bool:
    return str(provider or "").strip() in _CUSTOM_ONLY_PROVIDERS


def uses_custom_model_value(provider: str, model: str) -> bool:
    provider_name = str(provider or "").strip()
    model_name = str(model or "").strip()
    return provider_requires_custom_model(provider_name) or model_name == "custom" or not model_name
