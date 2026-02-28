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
        self.log_messages: list[str] = []
        self.switched_to: list[str] = []

    def append_chat(self, text: str, tag: str = "agent") -> None:
        _ = tag
        self.chat_messages.append(text)

    def append_log(self, text: str) -> None:
        self.log_messages.append(text)

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

    monkeypatch.setattr("pathlib.Path.exists", lambda _self: True)
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
    assert "Invalid local GGUF setting" in view.chat_messages[-1]
    assert "local_gguf_model_path is not configured" in view.chat_messages[-1]
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

    monkeypatch.setattr("pathlib.Path.exists", lambda _self: True)
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


def test_local_gguf_runtime_error_appends_actionable_telemetry_line(monkeypatch, caplog) -> None:
    controller, model, view = _build_controller()
    model.settings = {
        "llm_provider": "local_gguf",
        "local_gguf_model_path": "configured.gguf",
    }

    actionable = "llama-cpp backend init failed"

    class _Backend:
        def __init__(self, _config):
            raise RuntimeError(actionable)

    monkeypatch.setattr("pathlib.Path.exists", lambda _self: True)
    monkeypatch.setattr("axiom_app.controllers.app_controller.LocalGGUFBackend", _Backend)

    with caplog.at_level(logging.ERROR):
        controller.on_send_prompt("prompt")

    assert "Axiom [local_gguf, direct]" in view.chat_messages[-1]
    assert "Runtime dependency issue" in view.chat_messages[-1]
    assert actionable in view.chat_messages[-1]
    assert any(
        "verify local_gguf_model_path and llama-cpp-python install" in line
        for line in view.log_messages
    )
    assert "Local GGUF runtime initialization failed" in caplog.text
    assert model.chat_history == [
        {"role": "user", "content": "prompt"},
        {"role": "assistant", "content": view.chat_messages[-1]},
    ]
    assert view.switched_to[-1] == "chat"


def test_local_gguf_success_appends_telemetry_line(monkeypatch) -> None:
    controller, model, view = _build_controller()
    model.settings = {
        "llm_provider": "local_gguf",
        "local_gguf_model_path": "dummy.gguf",
        "llm_max_tokens": 44,
        "llm_temperature": 0.15,
    }

    class _Backend:
        def __init__(self, _config):
            return None

        def generate(self, _prompt: str, *, max_tokens: int, temperature: float) -> str:
            assert max_tokens == 44
            assert temperature == 0.15
            return "generated output"

    monkeypatch.setattr("pathlib.Path.exists", lambda _self: True)
    monkeypatch.setattr("axiom_app.controllers.app_controller.LocalGGUFBackend", _Backend)

    controller.on_send_prompt("hello")

    assert "Axiom [local_gguf, direct]" in view.chat_messages[-1]
    assert any("[direct] provider=local_gguf" in line for line in view.log_messages)
    assert model.chat_history == [
        {"role": "user", "content": "hello"},
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

    monkeypatch.setattr("pathlib.Path.exists", lambda _self: True)
    monkeypatch.setattr("axiom_app.controllers.app_controller.LocalGGUFBackend", _Backend)

    with caplog.at_level(logging.ERROR):
        controller.on_send_prompt("prompt")

    assert "Axiom [local_gguf, direct]" in view.chat_messages[-1]
    assert "Invalid local GGUF setting" in view.chat_messages[-1]
    assert "unexpected init failure details" in view.chat_messages[-1]
    assert "Invalid local GGUF setting while initializing backend" in caplog.text
    assert model.chat_history == [
        {"role": "user", "content": "prompt"},
        {"role": "assistant", "content": view.chat_messages[-1]},
    ]
    assert view.switched_to[-1] == "chat"
