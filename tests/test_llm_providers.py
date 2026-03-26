"""tests/test_llm_providers.py — Unit tests for the LLM provider factory.

Tests the mock path end-to-end and the factory's error handling / routing
logic.  Real provider constructors (OpenAI, Anthropic, etc.) are tested
only for argument validation — we don't make real API calls.
"""

from __future__ import annotations

import pytest

from metis_app.utils.llm_providers import (
    MockChatModel,
    _ChatMessage,
    _msg_content,
    _msg_type,
    _resolve_model,
    create_llm,
)


# ---------------------------------------------------------------------------
# _resolve_model
# ---------------------------------------------------------------------------


class TestResolveModel:
    def test_returns_base_model(self):
        assert _resolve_model({"llm_model": "gpt-4o"}) == "gpt-4o"

    def test_custom_override_when_base_is_custom(self):
        s = {"llm_model": "custom", "llm_model_custom": "my-fine-tune"}
        assert _resolve_model(s) == "my-fine-tune"

    def test_custom_not_used_when_base_is_normal(self):
        s = {"llm_model": "gpt-4o", "llm_model_custom": "ignored"}
        assert _resolve_model(s) == "gpt-4o"

    def test_empty_base_falls_back_to_default(self):
        assert _resolve_model({}) == "claude-opus-4-6"

    def test_custom_case_insensitive(self):
        s = {"llm_model": "Custom", "llm_model_custom": "my-model"}
        assert _resolve_model(s) == "my-model"


# ---------------------------------------------------------------------------
# _msg_type / _msg_content
# ---------------------------------------------------------------------------


class TestMessageHelpers:
    def test_msg_type_from_dict_with_type(self):
        assert _msg_type({"type": "system", "content": "hi"}) == "system"

    def test_msg_type_from_dict_with_role(self):
        assert _msg_type({"role": "user", "content": "hi"}) == "user"

    def test_msg_type_from_object(self):
        msg = _ChatMessage(content="hi", type="ai")
        assert _msg_type(msg) == "ai"

    def test_msg_content_from_dict(self):
        assert _msg_content({"content": "hello"}) == "hello"

    def test_msg_content_from_object(self):
        msg = _ChatMessage(content="world")
        assert _msg_content(msg) == "world"

    def test_msg_content_none_returns_empty(self):
        assert _msg_content({"content": None}) == "None"

    def test_msg_type_empty_dict(self):
        assert _msg_type({}) == ""


# ---------------------------------------------------------------------------
# MockChatModel
# ---------------------------------------------------------------------------


class TestMockChatModel:
    def test_invoke_returns_chat_message(self):
        model = MockChatModel()
        result = model.invoke([{"type": "human", "content": "hello"}])
        assert isinstance(result, _ChatMessage)
        assert result.type == "ai"

    def test_invoke_contains_prompt_echo(self):
        model = MockChatModel()
        result = model.invoke([{"type": "human", "content": "test prompt"}])
        assert "test prompt" in result.content

    def test_invoke_json_request(self):
        import json

        model = MockChatModel()
        messages = [
            {"type": "system", "content": "Return strict JSON with keys."},
            {"type": "human", "content": "plan retrieval"},
        ]
        result = model.invoke(messages)
        parsed = json.loads(result.content)
        assert "checklist_review" in parsed
        assert "retrieval_queries" in parsed

    def test_invoke_with_context(self):
        model = MockChatModel()
        messages = [
            {"type": "system", "content": "CONTEXT: This is some document text."},
            {"type": "human", "content": "What does it say?"},
        ]
        result = model.invoke(messages)
        assert "document text" in result.content.lower() or "context" in result.content.lower()

    def test_invoke_empty_messages(self):
        model = MockChatModel()
        result = model.invoke([])
        assert "no user prompt" in result.content.lower()


# ---------------------------------------------------------------------------
# create_llm
# ---------------------------------------------------------------------------


class TestCreateLlm:
    def test_mock_provider(self):
        model = create_llm({"llm_provider": "mock"})
        assert isinstance(model, MockChatModel)

    def test_empty_provider_defaults_to_mock(self):
        model = create_llm({})
        assert isinstance(model, MockChatModel)

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            create_llm({"llm_provider": "acme_corp"})

    def test_openai_missing_key_raises(self):
        with pytest.raises((ValueError, ImportError)):
            create_llm({"llm_provider": "openai", "api_key_openai": ""})

    def test_anthropic_missing_key_raises(self):
        with pytest.raises((ValueError, ImportError)):
            create_llm({"llm_provider": "anthropic", "api_key_anthropic": ""})

    def test_google_missing_key_raises(self):
        with pytest.raises((ValueError, ImportError)):
            create_llm({"llm_provider": "google", "api_key_google": ""})

    def test_xai_missing_key_raises(self):
        with pytest.raises((ValueError, ImportError)):
            create_llm({"llm_provider": "xai", "api_key_xai": ""})

    def test_local_gguf_missing_path_raises(self):
        with pytest.raises((ValueError, RuntimeError)):
            create_llm({
                "llm_provider": "local_gguf",
                "local_gguf_model_path": "",
            })

    def test_local_gguf_nonexistent_path_raises(self):
        with pytest.raises((ValueError, RuntimeError)):
            create_llm({
                "llm_provider": "local_gguf",
                "local_gguf_model_path": "/nonexistent/model.gguf",
            })

    def test_mock_invoke_round_trip(self):
        model = create_llm({"llm_provider": "mock"})
        result = model.invoke([{"type": "human", "content": "ping"}])
        assert result.content
        assert result.type == "ai"
