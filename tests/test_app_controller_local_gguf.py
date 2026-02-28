from __future__ import annotations

import logging

from axiom_app.controllers.app_controller import AppController
from axiom_app.models.app_model import AppModel


class _FakeRoot:
    def protocol(self, *_args, **_kwargs):
        return None


class _FakeButton:
    def configure(self, **_kwargs):
        return None


class _FakeView:
    def __init__(self) -> None:
        self.root = _FakeRoot()
        self.btn_cancel_rag = _FakeButton()
        self.btn_build_index = _FakeButton()
        self.chat_messages: list[str] = []
        self.switched_to: list[str] = []

    def append_chat(self, text: str, tag: str = "agent") -> None:
        _ = tag
        self.chat_messages.append(text)

    def get_chat_mode(self) -> str:
        return "direct"

    def switch_view(self, name: str) -> None:
        self.switched_to.append(name)



def _build_controller() -> tuple[AppController, AppModel, _FakeView]:
    model = AppModel()
    view = _FakeView()
    controller = AppController(model=model, view=view)
    return controller, model, view


def test_local_gguf_valid_settings_generate_response(monkeypatch) -> None:
    controller, model, view = _build_controller()
    model.settings = {
        "llm_provider": "local_gguf",
        "local_gguf_model_path": "dummy.gguf",
        "local_gguf_context_length": 3072,
        "local_gguf_gpu_layers": 8,
        "local_gguf_threads": 6,
        "llm_max_tokens": 44,
        "llm_temperature": 0.15,
    }

    class _Backend:
        def __init__(self, _config):
            return None

        def generate(self, prompt: str, *, max_tokens: int, temperature: float) -> str:
            assert prompt == "hello"
            assert max_tokens == 44
            assert temperature == 0.15
            return "generated output"

    monkeypatch.setattr("axiom_app.controllers.app_controller.LocalGGUFBackend", _Backend)

    controller.on_send_prompt("hello")

    assert view.chat_messages
    assert "Axiom [local_gguf, direct]" in view.chat_messages[-1]
    assert "generated output" in view.chat_messages[-1]
    assert model.chat_history == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": view.chat_messages[-1]},
    ]
    assert view.switched_to[-1] == "chat"


def test_local_gguf_missing_model_path_shows_user_visible_error() -> None:
    controller, model, view = _build_controller()
    model.settings = {
        "llm_provider": "local_gguf",
        "local_gguf_model_path": "",
    }

    controller.on_send_prompt("hello")

    assert view.chat_messages
    assert "Axiom [local_gguf, direct]" in view.chat_messages[-1]
    assert "Local GGUF model path is not configured" in view.chat_messages[-1]
    assert model.chat_history == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": view.chat_messages[-1]},
    ]
    assert view.switched_to[-1] == "chat"


def test_local_gguf_backend_is_reused(monkeypatch) -> None:
    controller, model, view = _build_controller()
    model.settings = {
        "llm_provider": "local_gguf",
        "local_gguf_model_path": "dummy.gguf",
        "local_gguf_context_length": 4096,
        "local_gguf_gpu_layers": 12,
        "local_gguf_threads": 4,
        "llm_max_tokens": 55,
        "llm_temperature": 0.2,
    }

    calls = {"init": 0, "generate": 0}

    class _Backend:
        def __init__(self, config):
            calls["init"] += 1
            self.config = config

        def generate(self, prompt: str, *, max_tokens: int, temperature: float) -> str:
            calls["generate"] += 1
            return f"ok:{prompt}:{max_tokens}:{temperature}"

    monkeypatch.setattr("axiom_app.controllers.app_controller.LocalGGUFBackend", _Backend)

    controller.on_send_prompt("first")
    controller.on_send_prompt("second")

    assert calls == {"init": 1, "generate": 2}
    assert "Axiom [local_gguf, direct]" in view.chat_messages[-1]
    assert "ok:second:55:0.2" in view.chat_messages[-1]
    assert model.chat_history == [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": view.chat_messages[0]},
        {"role": "user", "content": "second"},
        {"role": "assistant", "content": view.chat_messages[1]},
    ]
    assert view.switched_to == ["chat", "chat"]


def test_local_gguf_runtime_error_mentions_dependency(monkeypatch, caplog) -> None:
    controller, model, view = _build_controller()
    model.settings = {
        "llm_provider": "local_gguf",
        "local_gguf_model_path": "missing.gguf",
    }

    class _Backend:
        def __init__(self, _config):
            raise RuntimeError("boom")

    monkeypatch.setattr("axiom_app.controllers.app_controller.LocalGGUFBackend", _Backend)

    with caplog.at_level(logging.ERROR):
        controller.on_send_prompt("prompt")

    assert "Axiom [local_gguf, direct]" in view.chat_messages[-1]
    assert "Could not initialize local GGUF backend" in view.chat_messages[-1]
    assert "Verify local_gguf_model_path exists and llama-cpp-python is installed" in caplog.text
    assert model.chat_history == [
        {"role": "user", "content": "prompt"},
        {"role": "assistant", "content": view.chat_messages[-1]},
    ]
    assert view.switched_to[-1] == "chat"


def test_local_gguf_generic_init_exception_is_concise_for_user_and_logged(monkeypatch, caplog) -> None:
    controller, model, view = _build_controller()
    model.settings = {
        "llm_provider": "local_gguf",
        "local_gguf_model_path": "configured.gguf",
    }

    class _Backend:
        def __init__(self, _config):
            raise ValueError("unexpected init failure details")

    monkeypatch.setattr("axiom_app.controllers.app_controller.LocalGGUFBackend", _Backend)

    with caplog.at_level(logging.ERROR):
        controller.on_send_prompt("prompt")

    assert "Axiom [local_gguf, direct]" in view.chat_messages[-1]
    assert "Could not initialize local GGUF backend" in view.chat_messages[-1]
    assert "unexpected init failure details" not in view.chat_messages[-1]
    assert "Could not initialize local GGUF backend: unexpected init failure details" in caplog.text
    assert model.chat_history == [
        {"role": "user", "content": "prompt"},
        {"role": "assistant", "content": view.chat_messages[-1]},
    ]
    assert view.switched_to[-1] == "chat"
