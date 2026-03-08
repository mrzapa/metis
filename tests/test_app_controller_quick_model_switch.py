from __future__ import annotations

from dataclasses import dataclass, field

from axiom_app.controllers.app_controller import AppController
from axiom_app.models.app_model import AppModel
from axiom_app.services.session_repository import SessionRepository


class _FakeButton:
    def setEnabled(self, _enabled: bool) -> None:
        pass


@dataclass
class _FakeView:
    btn_cancel_rag: _FakeButton = field(default_factory=_FakeButton)
    btn_build_index: _FakeButton = field(default_factory=_FakeButton)
    populated_settings: list[dict] = field(default_factory=list)
    status_messages: list[str] = field(default_factory=list)
    refresh_calls: int = 0

    def set_chat_response_ui(self, _has_completed_response: bool, _feedback_pending: bool) -> None:
        pass

    def set_history_rows(self, _rows) -> None:
        pass

    def populate_settings(self, settings: dict) -> None:
        self.populated_settings.append(dict(settings))

    def refresh_llm_status_badge(self) -> None:
        self.refresh_calls += 1

    def set_status(self, text: str) -> None:
        self.status_messages.append(str(text))

    def get_selected_profile_label(self) -> str:
        return "Built-in: Default"


def _build_controller(tmp_path, monkeypatch) -> tuple[AppController, AppModel, _FakeView, list[dict]]:
    model = AppModel()
    model.session_db_path = tmp_path / "rag_sessions.db"
    model.settings = {
        "llm_provider": "anthropic",
        "llm_model": "claude-opus-4-6",
        "llm_model_custom": "",
        "selected_mode": "Q&A",
        "retrieval_k": 25,
        "top_k": 5,
        "mmr_lambda": 0.5,
        "agentic_max_iterations": 2,
    }
    view = _FakeView()
    controller = AppController(
        model=model,
        view=view,
        session_repository=SessionRepository(model.session_db_path),
    )
    saved_payloads: list[dict] = []

    def _save(settings: dict) -> None:
        saved_payloads.append(dict(settings))
        model.settings = dict(settings)

    monkeypatch.setattr(model, "save_settings", _save)
    monkeypatch.setattr(controller, "_show_error_dialog", lambda *_args, **_kwargs: None)
    return controller, model, view, saved_payloads


def test_quick_model_switch_persists_preset_and_refreshes_session_metadata(tmp_path, monkeypatch) -> None:
    controller, model, view, saved_payloads = _build_controller(tmp_path, monkeypatch)
    summary = controller.session_repository.create_session(
        title="Test",
        summary="Before switch",
        active_profile="Built-in: Default",
        mode="Q&A",
        llm_provider="anthropic",
        llm_model="claude-opus-4-6",
    )
    model.current_session_id = summary.session_id

    controller.on_quick_model_change(
        {
            "llm_provider": "openai",
            "llm_model": "gpt-5.2",
            "llm_model_custom": "",
        }
    )

    assert saved_payloads
    assert model.settings["llm_provider"] == "openai"
    assert model.settings["llm_model"] == "gpt-5.2"
    assert model.settings["llm_model_custom"] == ""
    assert view.populated_settings[-1]["llm_model"] == "gpt-5.2"
    assert view.refresh_calls == 1

    detail = controller.session_repository.get_session(summary.session_id)
    assert detail is not None
    assert detail.summary.llm_provider == "openai"
    assert detail.summary.llm_model == "gpt-5.2"


def test_quick_model_switch_preserves_custom_model_value(tmp_path, monkeypatch) -> None:
    controller, model, _view, _saved_payloads = _build_controller(tmp_path, monkeypatch)

    controller.on_quick_model_change(
        {
            "llm_provider": "anthropic",
            "llm_model": "claude-labs-preview",
            "llm_model_custom": "claude-labs-preview",
        }
    )

    assert model.settings["llm_provider"] == "anthropic"
    assert model.settings["llm_model"] == "claude-labs-preview"
    assert model.settings["llm_model_custom"] == "claude-labs-preview"


def test_quick_model_switch_rejects_local_gguf_without_valid_path(tmp_path, monkeypatch) -> None:
    controller, model, view, saved_payloads = _build_controller(tmp_path, monkeypatch)

    controller.on_quick_model_change(
        {
            "llm_provider": "local_gguf",
            "llm_model": "mistral-local",
            "llm_model_custom": "mistral-local",
        }
    )

    assert not saved_payloads
    assert model.settings["llm_provider"] == "anthropic"
    assert any("blocked" in message.lower() for message in view.status_messages)
