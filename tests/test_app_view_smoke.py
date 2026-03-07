"""Smoke tests for the PySide6 AppView shell."""

from __future__ import annotations

import importlib
import sys

import pytest


pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="Qt smoke runs on Windows CI only.",
)


@pytest.fixture(autouse=True)
def _cleanup_qt_widgets(qapp):
    yield
    for widget in list(qapp.topLevelWidgets()):
        try:
            widget.close()
        except Exception:
            pass
    qapp.processEvents()


def _show(process_events):
    view = importlib.import_module("axiom_app.views.app_view").AppView(theme_name="space_dust")
    view.show()
    process_events()
    return view


def test_app_view_constructs_with_empty_chat_state(qapp, process_events) -> None:
    view = _show(process_events)

    assert view._active_view == "chat"
    assert view._theme_name == "space_dust"
    assert view._chat_has_messages is False
    assert view._chat_empty_state.isVisible()
    assert not view._conversation_shell.isVisible()
    assert view.minimumWidth() == 1180
    assert view.minimumHeight() == 760
    assert view._rag_toggle.get_value() is True


def test_app_view_switches_between_empty_and_conversation_states(qapp, process_events) -> None:
    view = _show(process_events)

    view.append_chat("Hello from a smoke test.\n")
    process_events()

    assert view._chat_has_messages is True
    assert not view._chat_empty_state.isVisible()
    assert view._conversation_shell.isVisible()

    view.clear_chat()
    process_events()

    assert view._chat_has_messages is False
    assert view._chat_empty_state.isVisible()
    assert not view._conversation_shell.isVisible()


def test_app_view_switches_between_all_pages(qapp, process_events) -> None:
    view = _show(process_events)

    for key in ("chat", "library", "history", "settings", "logs"):
        view.switch_view(key)
        process_events()
        assert view._active_view == key
        assert view._stack.currentWidget() is view._pages[key]

    assert view.btn_open_files is not None
    assert view.btn_build_index is not None
    assert view.btn_save_settings is not None
    assert view._logs_view is not None


def test_app_view_applies_theme_and_updates_runtime_widgets(qapp, process_events) -> None:
    view = _show(process_events)

    view.populate_settings({"llm_provider": "openai", "llm_model": "gpt-test", "selected_mode": "Research"})
    view.apply_theme("dark")
    process_events()

    assert view._theme_name == "dark"
    assert view._palette["primary"] == view._rag_toggle._palette["primary"]
    assert "openai" in view._llm_status_badge.text()
    assert view._mode_combo.currentText() == "Research"
