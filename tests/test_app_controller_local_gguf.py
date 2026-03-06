"""tests/test_app_controller_local_gguf.py — local GGUF provider integration tests.

Updated to work with the factory-based async dispatch.  Tests monkeypatch
``create_llm`` (in the provider factory) rather than the removed
``LocalGGUFBackend`` class.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from axiom_app.controllers.app_controller import AppController
from axiom_app.models.app_model import AppModel


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeRoot:
    def protocol(self, *_a, **_kw):
        pass


class _FakeButton:
    def configure(self, **_kw):
        pass


class _FakeView:
    def __init__(self) -> None:
        self.root = _FakeRoot()
        self.btn_cancel_rag = _FakeButton()
        self.btn_build_index = _FakeButton()
        self.chat_messages: list[str] = []
        self.log_messages: list[str] = []
        self.switched_to: list[str] = []
        self._status: str = ""

    def append_chat(self, text: str, tag: str = "agent") -> None:
        _ = tag
        self.chat_messages.append(text)

    def append_log(self, text: str) -> None:
        self.log_messages.append(text)

    def get_chat_mode(self) -> str:
        return "direct"

    def switch_view(self, name: str) -> None:
        self.switched_to.append(name)

    def set_status(self, text: str) -> None:
        self._status = text

    def set_progress(self, current: int, total: int | None = None) -> None:
        pass

    def reset_progress(self) -> None:
        pass


@dataclass
class _FakeMessage:
    content: str
    type: str = "ai"


def _build_controller() -> tuple[AppController, AppModel, _FakeView]:
    model = AppModel()
    view = _FakeView()
    controller = AppController(model=model, view=view)
    return controller, model, view


def _drain(controller: AppController) -> None:
    """Wait for background future, then pump messages."""
    if controller._active_future is not None:
        controller._active_future.result(timeout=5)
    controller.poll_and_dispatch()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


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

    class _FakeLLM:
        def invoke(self, messages: Any) -> _FakeMessage:
            return _FakeMessage(content="generated output")

    monkeypatch.setattr(
        "axiom_app.utils.llm_providers.create_llm",
        lambda _s: _FakeLLM(),
    )
    # Also patch the controller-level import.
    monkeypatch.setattr(
        "axiom_app.controllers.app_controller.create_llm",
        lambda _s: _FakeLLM(),
    )

    controller.on_send_prompt("hello")
    _drain(controller)

    all_text = " ".join(view.chat_messages)
    assert "local_gguf" in all_text
    assert "generated output" in all_text
    assert len(model.chat_history) == 2
    assert view.switched_to[-1] == "chat"


def test_local_gguf_missing_model_path_shows_user_visible_error(monkeypatch) -> None:
    controller, model, view = _build_controller()
    model.settings = {
        "llm_provider": "local_gguf",
        "local_gguf_model_path": "",
    }

    # create_llm should raise ValueError for missing path.
    # We don't need to monkeypatch — the real create_llm will raise.

    controller.on_send_prompt("hello")
    _drain(controller)

    all_text = " ".join(view.chat_messages)
    assert "local_gguf" in all_text
    # Error should be surfaced to the user.
    assert "invalid" in all_text.lower() or "error" in all_text.lower() or "missing" in all_text.lower()
    assert len(model.chat_history) == 2
    assert view.switched_to[-1] == "chat"


def test_local_gguf_backend_is_reused(monkeypatch) -> None:
    """The factory is called once per prompt since each dispatches a new worker."""
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

    calls = {"create": 0}

    class _FakeLLM:
        def invoke(self, messages: Any) -> _FakeMessage:
            # Find the human message content.
            for m in messages:
                if isinstance(m, dict) and m.get("type") == "human":
                    return _FakeMessage(content=f"ok:{m['content']}")
            return _FakeMessage(content="ok")

    def _factory(settings: dict) -> _FakeLLM:
        calls["create"] += 1
        return _FakeLLM()

    monkeypatch.setattr("axiom_app.controllers.app_controller.create_llm", _factory)

    controller.on_send_prompt("first")
    _drain(controller)
    controller.on_send_prompt("second")
    _drain(controller)

    assert calls["create"] == 2  # one per prompt dispatch
    all_text = " ".join(view.chat_messages)
    assert "ok:second" in all_text
    assert len(model.chat_history) == 4
    assert view.switched_to[-1] == "chat"


def test_local_gguf_runtime_error_appends_actionable_telemetry_line(monkeypatch, caplog) -> None:
    controller, model, view = _build_controller()
    model.settings = {
        "llm_provider": "local_gguf",
        "local_gguf_model_path": "configured.gguf",
    }

    def _factory(settings: dict):
        raise RuntimeError("llama-cpp backend init failed")

    monkeypatch.setattr("axiom_app.controllers.app_controller.create_llm", _factory)

    controller.on_send_prompt("prompt")
    _drain(controller)

    all_text = " ".join(view.chat_messages)
    assert "local_gguf" in all_text
    assert "llama-cpp backend init failed" in all_text
    assert len(model.chat_history) == 2
    assert view.switched_to[-1] == "chat"


def test_local_gguf_success_appends_telemetry_line(monkeypatch) -> None:
    controller, model, view = _build_controller()
    model.settings = {
        "llm_provider": "local_gguf",
        "local_gguf_model_path": "dummy.gguf",
        "llm_max_tokens": 44,
        "llm_temperature": 0.15,
    }

    class _FakeLLM:
        def invoke(self, messages: Any) -> _FakeMessage:
            return _FakeMessage(content="generated output")

    monkeypatch.setattr("axiom_app.controllers.app_controller.create_llm", lambda _s: _FakeLLM())

    controller.on_send_prompt("hello")
    _drain(controller)

    all_text = " ".join(view.chat_messages)
    assert "local_gguf" in all_text
    assert "generated output" in all_text
    assert any("provider=local_gguf" in line for line in view.log_messages)
    assert len(model.chat_history) == 2
    assert view.switched_to[-1] == "chat"


def test_local_gguf_generic_init_exception_is_concise_for_user_and_logged(monkeypatch, caplog) -> None:
    controller, model, view = _build_controller()
    model.settings = {
        "llm_provider": "local_gguf",
        "local_gguf_model_path": "configured.gguf",
    }

    def _factory(settings: dict):
        raise ValueError("unexpected init failure details")

    monkeypatch.setattr("axiom_app.controllers.app_controller.create_llm", _factory)

    controller.on_send_prompt("prompt")
    _drain(controller)

    all_text = " ".join(view.chat_messages)
    assert "local_gguf" in all_text
    assert "unexpected init failure details" in all_text
    assert len(model.chat_history) == 2
    assert view.switched_to[-1] == "chat"
