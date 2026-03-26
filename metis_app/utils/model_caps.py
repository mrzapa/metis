"""metis_app.utils.model_caps — LLM model capability detection.

Pure-function lookup for context-window sizes and output-token limits.
No Tk, no network — suitable for unit testing and headless CLI use.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Provider-level defaults (fallback when no model-specific override matches)
# ---------------------------------------------------------------------------

_PROVIDER_DEFAULTS: dict[str, dict[str, int]] = {
    "openai":          {"max_context_tokens": 128_000, "max_output_tokens": 4096},
    "anthropic":       {"max_context_tokens": 200_000, "max_output_tokens": 8192},
    "google":          {"max_context_tokens": 1_000_000, "max_output_tokens": 8192},
    "xai":             {"max_context_tokens": 131_072, "max_output_tokens": 8192},
    "local_lm_studio": {"max_context_tokens": 8192, "max_output_tokens": 2048},
    "local_gguf":      {"max_context_tokens": 8192, "max_output_tokens": 2048},
    "mock":            {"max_context_tokens": 8192, "max_output_tokens": 1024},
}

# ---------------------------------------------------------------------------
# Model-specific overrides  (pattern, max_context, max_output)
# First match wins within a provider.
# ---------------------------------------------------------------------------

_MODEL_OVERRIDES: dict[str, list[tuple[str, int, int]]] = {
    "openai": [
        (r"gpt-5\.2-pro",               400_000, 32_768),
        (r"gpt-5\.2",                    400_000, 32_768),
        (r"gpt-5\.1-codex",             400_000, 32_768),
        (r"gpt-5\.1",                    400_000, 32_768),
        (r"gpt-5-mini|gpt-5-nano",      400_000, 32_768),
        (r"gpt-5$|gpt-5-",              400_000, 32_768),
        (r"gpt-4\.1$|gpt-4\.1-mini|gpt-4\.1-nano", 1_000_000, 32_768),
        (r"gpt-4o|o4-mini",             128_000, 16_384),
        (r"o3-pro|o3$",                 200_000, 100_000),
        (r"gpt-4-turbo",                128_000, 4096),
        (r"gpt-4",                      8192,    2048),
        (r"gpt-3\.5-turbo",             16_384,  4096),
    ],
    "anthropic": [
        (r"claude-(opus|sonnet|haiku)-4", 200_000, 8192),
        (r"claude-3\.7-sonnet",           200_000, 8192),
        (r"claude-3\.5-(sonnet|haiku)",   200_000, 8192),
        (r"claude-3-(opus|sonnet|haiku)", 200_000, 4096),
    ],
    "google": [
        (r"gemini-3",            1_000_000, 8192),
        (r"gemini-2\.5-pro",     1_000_000, 8192),
        (r"gemini-2\.5-flash",   1_000_000, 8192),
        (r"gemini-2\.0-flash",   1_000_000, 8192),
        (r"gemini-1\.5-pro",     2_000_000, 8192),
        (r"gemini-1\.5-flash",   1_000_000, 8192),
    ],
    "xai": [
        (r"grok-4-heavy", 131_072, 8192),
        (r"grok-4$",      131_072, 8192),
        (r"grok-3",       131_072, 8192),
    ],
}


def get_model_caps(provider: str, model: str) -> dict[str, int]:
    """Return ``{"max_context_tokens": …, "max_output_tokens": …}`` for a
    provider/model pair.

    Falls back to conservative defaults (8192 / 2048) when the provider or
    model is unknown.
    """
    provider_name = (provider or "").strip().lower()
    model_name = (model or "").strip().lower()

    caps: dict[str, int] = {
        "max_context_tokens": 8192,
        "max_output_tokens": 2048,
    }
    caps.update(_PROVIDER_DEFAULTS.get(provider_name, {}))

    for pattern, ctx, out in _MODEL_OVERRIDES.get(provider_name, []):
        if re.search(pattern, model_name):
            caps["max_context_tokens"] = ctx
            caps["max_output_tokens"] = out
            break

    return caps


def get_capped_output_tokens(
    provider: str,
    model: str,
    requested_max_tokens: int,
) -> int:
    """Clamp *requested_max_tokens* to the model's known output ceiling."""
    requested = max(1, int(requested_max_tokens))
    caps = get_model_caps(provider, model)
    ceiling = max(1, int(caps.get("max_output_tokens", requested)))
    return min(requested, ceiling)
