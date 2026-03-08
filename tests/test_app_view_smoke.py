"""Smoke tests for the PySide6 AppView shell."""

from __future__ import annotations

import importlib
import sys

import pytest

qt_widgets = pytest.importorskip("PySide6.QtWidgets", reason="Qt runtime unavailable")
QScrollBar = qt_widgets.QScrollBar
QTreeWidget = qt_widgets.QTreeWidget


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


def _is_descendant(widget, ancestor) -> bool:
    current = widget
    while current is not None:
        if current is ancestor:
            return True
        current = current.parentWidget()
    return False


def test_app_view_constructs_with_empty_chat_state(qapp, process_events) -> None:
    view = _show(process_events)

    assert view._active_view == "chat"
    assert view._theme_name == "space_dust"
    assert view._chat_has_messages is False
    assert view._chat_empty_state.isVisible()
    assert view._conversation_shell.isVisible()
    assert view._composer_shell.isVisible()
    assert view._chat_state_stack.currentWidget() is view._chat_empty_state
    assert not view._chat_transcript_state.isVisible()
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
    assert view._composer_shell.isVisible()
    assert view._chat_state_stack.currentWidget() is view._chat_transcript_state
    assert view._chat_transcript_state.isVisible()

    view.clear_chat()
    process_events()

    assert view._chat_has_messages is False
    assert view._chat_empty_state.isVisible()
    assert view._conversation_shell.isVisible()
    assert view._composer_shell.isVisible()
    assert view._chat_state_stack.currentWidget() is view._chat_empty_state


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


def test_app_view_settings_widgets_are_owned_by_settings_page(qapp, process_events) -> None:
    view = _show(process_events)
    settings_page = view._pages["settings"]
    view.switch_view("settings")
    process_events()

    for widget in view._settings_widgets.values():
        assert _is_descendant(widget, settings_page)
    assert _is_descendant(view._local_model_tree, settings_page)
    assert not [tree for tree in view.findChildren(QTreeWidget) if tree.parentWidget() is view]
    assert not [bar for bar in view.findChildren(QScrollBar) if bar.parentWidget() is view]


def test_app_view_renders_local_gguf_recommendations(qapp, process_events) -> None:
    view = _show(process_events)
    view.switch_view("settings")
    view.set_local_gguf_recommendations(
        {
            "use_case": "chat",
            "advisory_only": False,
            "hardware": {
                "total_ram_gb": 32.0,
                "available_ram_gb": 24.0,
                "total_cpu_cores": 12,
                "backend": "cuda",
                "has_gpu": True,
                "gpu_name": "RTX 4090",
                "gpu_vram_gb": 24.0,
            },
            "rows": [
                {
                    "model_name": "Qwen/Test-7B-Instruct",
                    "parameter_count": "7B",
                    "fit_level": "good",
                    "run_mode": "gpu",
                    "best_quant": "Q4_K_M",
                    "estimated_tps": 42.5,
                    "memory_required_gb": 4.6,
                    "memory_available_gb": 24.0,
                    "recommended_context_length": 8192,
                    "source_provider": "bartowski",
                    "notes": ["GPU: model loaded into VRAM."],
                }
            ],
        }
    )
    process_events()

    assert view._local_gguf_recommendation_tree.topLevelItemCount() == 1
    selected = view.get_selected_local_gguf_recommendation()
    assert selected is not None
    assert selected["model_name"] == "Qwen/Test-7B-Instruct"
    assert "RTX 4090" in view._local_gguf_hardware_label.text()


def test_app_view_uses_packaged_brand_logo_when_available(qapp, process_events) -> None:
    view = _show(process_events)

    assert not view._brand_logo_pixmap.isNull()
    assert not view.windowIcon().isNull()
    assert view._brand_icon_stack.currentWidget() is view._brand_logo_page
    assert view._brand_logo_label.pixmap() is not None


def test_app_view_falls_back_to_vector_brand_mark_when_logo_missing(monkeypatch, qapp, process_events) -> None:
    module = importlib.import_module("axiom_app.views.app_view")
    monkeypatch.setattr(module.AppView, "_load_packaged_brand_pixmap", lambda self: module.QPixmap())

    view = module.AppView(theme_name="space_dust")
    view.show()
    process_events()

    assert view._brand_logo_pixmap.isNull()
    assert view._brand_icon_stack.currentWidget() is view._brand_mark_page
