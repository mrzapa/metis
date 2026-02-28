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

    def switch_view(self, name: str) -> None:
        self.switched_to.append(name)



def _build_controller() -> tuple[AppController, AppModel, _FakeView]:
    model = AppModel()
    view = _FakeView()
    controller = AppController(model=model, view=view)
    return controller, model, view


def test_local_gguf_missing_model_path_shows_user_visible_error() -> None:
    controller, model, view = _build_controller()
    model.settings = {
        "llm_provider": "local_gguf",
        "local_gguf_model_path": "",
    }

    controller.on_send_prompt("hello")

    assert view.chat_messages
    assert "Local GGUF model path is not configured" in view.chat_messages[-1]
    assert model.chat_history[0] == {"role": "user", "content": "hello"}
    assert "Local GGUF model path is not configured" in model.chat_history[1]["content"]


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


def test_local_gguf_init_failure_is_logged_with_actionable_message(monkeypatch, caplog) -> None:
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

    assert "Could not initialize local GGUF backend" in view.chat_messages[-1]
    assert "Verify local_gguf_model_path exists and llama-cpp-python is installed" in caplog.text
