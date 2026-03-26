"""tests/test_model_caps.py — Unit tests for model capability detection.

Pure-function tests — no network, no Tk, no ML libraries.
"""

from __future__ import annotations

from metis_app.utils.model_caps import get_capped_output_tokens, get_model_caps


# ---------------------------------------------------------------------------
# get_model_caps
# ---------------------------------------------------------------------------


class TestGetModelCaps:
    def test_unknown_provider_returns_conservative_defaults(self):
        caps = get_model_caps("unknown_provider", "some-model")
        assert caps["max_context_tokens"] == 8192
        assert caps["max_output_tokens"] == 2048

    def test_empty_provider_returns_defaults(self):
        caps = get_model_caps("", "")
        assert caps["max_context_tokens"] == 8192
        assert caps["max_output_tokens"] == 2048

    def test_none_provider_returns_defaults(self):
        caps = get_model_caps(None, None)  # type: ignore[arg-type]
        assert caps["max_context_tokens"] == 8192

    def test_anthropic_provider_defaults(self):
        caps = get_model_caps("anthropic", "unknown-model")
        assert caps["max_context_tokens"] == 200_000
        assert caps["max_output_tokens"] == 8192

    def test_openai_provider_defaults(self):
        caps = get_model_caps("openai", "unknown-model")
        assert caps["max_context_tokens"] == 128_000
        assert caps["max_output_tokens"] == 4096

    def test_google_provider_defaults(self):
        caps = get_model_caps("google", "unknown-model")
        assert caps["max_context_tokens"] == 1_000_000

    def test_xai_provider_defaults(self):
        caps = get_model_caps("xai", "grok-unknown")
        assert caps["max_context_tokens"] == 131_072

    def test_mock_provider_defaults(self):
        caps = get_model_caps("mock", "")
        assert caps["max_output_tokens"] == 1024

    def test_local_gguf_defaults(self):
        caps = get_model_caps("local_gguf", "")
        assert caps["max_context_tokens"] == 8192
        assert caps["max_output_tokens"] == 2048

    def test_claude_opus_4_override(self):
        caps = get_model_caps("anthropic", "claude-opus-4-6")
        assert caps["max_context_tokens"] == 200_000
        assert caps["max_output_tokens"] == 8192

    def test_claude_3_opus_override(self):
        caps = get_model_caps("anthropic", "claude-3-opus-20240229")
        assert caps["max_output_tokens"] == 4096

    def test_gpt4o_override(self):
        caps = get_model_caps("openai", "gpt-4o-2024-05-13")
        assert caps["max_output_tokens"] == 16_384

    def test_gpt4_turbo_override(self):
        caps = get_model_caps("openai", "gpt-4-turbo-preview")
        assert caps["max_output_tokens"] == 4096

    def test_gemini_15_pro_override(self):
        caps = get_model_caps("google", "gemini-1.5-pro-latest")
        assert caps["max_context_tokens"] == 2_000_000

    def test_grok_3_override(self):
        caps = get_model_caps("xai", "grok-3-latest")
        assert caps["max_output_tokens"] == 8192

    def test_provider_case_insensitive(self):
        caps = get_model_caps("Anthropic", "claude-opus-4")
        assert caps["max_context_tokens"] == 200_000

    def test_model_case_insensitive(self):
        caps = get_model_caps("openai", "GPT-4o")
        assert caps["max_output_tokens"] == 16_384

    def test_returns_dict_with_both_keys(self):
        caps = get_model_caps("openai", "gpt-4o")
        assert "max_context_tokens" in caps
        assert "max_output_tokens" in caps


# ---------------------------------------------------------------------------
# get_capped_output_tokens
# ---------------------------------------------------------------------------


class TestGetCappedOutputTokens:
    def test_requested_below_ceiling_returns_requested(self):
        # Mock provider ceiling is 1024; request 512 → 512
        result = get_capped_output_tokens("mock", "", 512)
        assert result == 512

    def test_requested_above_ceiling_returns_ceiling(self):
        # Mock provider ceiling is 1024; request 9999 → 1024
        result = get_capped_output_tokens("mock", "", 9999)
        assert result == 1024

    def test_requested_equals_ceiling(self):
        result = get_capped_output_tokens("mock", "", 1024)
        assert result == 1024

    def test_requested_zero_becomes_one(self):
        result = get_capped_output_tokens("mock", "", 0)
        assert result == 1

    def test_negative_becomes_one(self):
        result = get_capped_output_tokens("mock", "", -100)
        assert result == 1

    def test_anthropic_opus_capped(self):
        # Claude Opus 4 ceiling = 8192; request 16000 → 8192
        result = get_capped_output_tokens("anthropic", "claude-opus-4", 16000)
        assert result == 8192

    def test_large_request_with_unknown_provider(self):
        # Unknown provider ceiling = 2048
        result = get_capped_output_tokens("acme", "acme-xl", 100_000)
        assert result == 2048
