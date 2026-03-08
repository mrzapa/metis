"""Smoke tests for the PySide6 AppView shell."""

from __future__ import annotations

import importlib
import sys

import pytest

from axiom_app.utils.model_presets import get_llm_model_presets

qt_widgets = pytest.importorskip("PySide6.QtWidgets", reason="Qt runtime unavailable")
QScrollBar = qt_widgets.QScrollBar
QDialog = qt_widgets.QDialog
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


def _combo_items(combo) -> list[str]:
    return [combo.itemText(index) for index in range(combo.count())]


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
    assert not view._feedback_footer.isVisible()
    assert not view._evidence_tabs.isVisible()
    assert view._chat_splitter.sizes()[1] <= 0
    assert view.minimumWidth() == 1180
    assert view.minimumHeight() == 760
    assert view._rag_toggle.get_value() is True


def test_app_view_hero_heading_wraps_when_constrained(qapp, process_events) -> None:
    view = _show(process_events)

    assert view._hero_greeting_label.wordWrap() is True
    assert view._hero_greeting_label.heightForWidth(320) > view._hero_greeting_label.fontMetrics().lineSpacing()


def test_app_view_hero_labels_receive_full_wrapped_height(qapp, process_events) -> None:
    view = _show(process_events)

    for label in (view._hero_greeting_label, view._hero_copy_label):
        width = max(1, label.width())
        assert label.height() >= label.heightForWidth(width)


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
    assert not view._feedback_footer.isVisible()
    assert not view._evidence_tabs.isVisible()

    view.clear_chat()
    process_events()

    assert view._chat_has_messages is False
    assert view._chat_empty_state.isVisible()
    assert view._conversation_shell.isVisible()
    assert view._composer_shell.isVisible()
    assert view._chat_state_stack.currentWidget() is view._chat_empty_state
    assert not view._feedback_footer.isVisible()
    assert not view._evidence_tabs.isVisible()


def test_app_view_reveals_response_ui_only_for_completed_response(qapp, process_events) -> None:
    view = _show(process_events)

    view.append_chat("You: hello\n")
    view.append_chat("Axiom: response\n")
    view.set_chat_response_ui(True, True)
    process_events()

    assert view._feedback_footer.isVisible()
    assert view._evidence_tabs.isVisible()
    assert view._chat_splitter.sizes()[1] > 0

    view.set_chat_response_ui(True, False)
    process_events()

    assert not view._feedback_footer.isVisible()
    assert view._evidence_tabs.isVisible()

    view.clear_chat()
    process_events()

    assert not view._feedback_footer.isVisible()
    assert not view._evidence_tabs.isVisible()


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
    assert view._llm_status_badge.text() == ""
    assert not view._llm_status_badge.icon().isNull()
    assert "openai / gpt-test" in view._llm_status_badge.toolTip()
    assert view._mode_combo.currentText() == "Research"


def test_app_view_preserves_zero_numeric_settings_in_text_inputs(qapp, process_events) -> None:
    view = _show(process_events)

    view.populate_settings(
        {
            "llm_temperature": 0.0,
            "local_gguf_gpu_layers": 0,
            "local_gguf_threads": 0,
            "hardware_override_total_ram_gb": 0.0,
            "hardware_override_available_ram_gb": 0.0,
            "hardware_override_gpu_vram_gb": 0.0,
            "hardware_override_gpu_count": 0,
        }
    )
    view.apply_theme("light")
    process_events()

    collected = view.collect_settings()

    assert collected["llm_temperature"] == "0.0"
    assert collected["local_gguf_gpu_layers"] == "0"
    assert collected["local_gguf_threads"] == "0"
    assert collected["hardware_override_total_ram_gb"] == "0.0"
    assert collected["hardware_override_available_ram_gb"] == "0.0"
    assert collected["hardware_override_gpu_vram_gb"] == "0.0"
    assert collected["hardware_override_gpu_count"] == "0"


def test_app_view_quick_model_popup_repopulates_presets(qapp, process_events) -> None:
    view = _show(process_events)

    view.populate_settings({"llm_provider": "anthropic", "llm_model": "claude-opus-4-6"})
    view._show_quick_model_popup()
    view._quick_model_provider_combo.setCurrentText("google")
    process_events()

    assert _combo_items(view._quick_model_model_combo) == get_llm_model_presets("google")


def test_app_view_quick_model_popup_reveals_custom_editor(qapp, process_events) -> None:
    view = _show(process_events)
    payloads: list[dict[str, str]] = []
    view.quickModelChangeRequested.connect(lambda payload: payloads.append(dict(payload)))

    view.populate_settings({"llm_provider": "anthropic", "llm_model": "claude-opus-4-6"})
    view._show_quick_model_popup()
    view._quick_model_model_combo.setCurrentText("custom")
    process_events()

    assert view._quick_model_custom_row.isVisible()

    view._quick_model_custom_input.setText("claude-labs-preview")
    view._emit_quick_model_change_from_popup()
    process_events()

    assert payloads[-1] == {
        "llm_provider": "anthropic",
        "llm_model": "claude-labs-preview",
        "llm_model_custom": "claude-labs-preview",
    }


def test_app_view_model_switch_busy_state_disables_button_and_hides_popup(qapp, process_events) -> None:
    view = _show(process_events)

    view._show_quick_model_popup()
    process_events()
    assert view._quick_model_popup.isVisible()

    view.set_model_switch_enabled(False)
    process_events()

    assert not view._llm_status_badge.isEnabled()
    assert not view._quick_model_popup.isVisible()


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
    assert view.btn_import_local_gguf_recommendation.isEnabled()
    assert view.btn_apply_local_gguf_recommendation.isEnabled()
    assert view.btn_apply_local_gguf_recommendation.text() == "Apply as Local LLM"


def test_app_view_disables_apply_for_too_tight_local_gguf(qapp, process_events) -> None:
    view = _show(process_events)
    view.switch_view("settings")
    view.set_local_gguf_recommendations(
        {
            "use_case": "reasoning",
            "advisory_only": False,
            "hardware": {
                "total_ram_gb": 16.0,
                "available_ram_gb": 10.0,
                "total_cpu_cores": 8,
                "backend": "cpu_x86",
                "has_gpu": False,
            },
            "rows": [
                {
                    "model_name": "Qwen/Test-70B",
                    "parameter_count": "70B",
                    "fit_level": "too_tight",
                    "run_mode": "cpu",
                    "best_quant": "Q2_K",
                    "estimated_tps": 2.0,
                    "memory_required_gb": 48.0,
                    "memory_available_gb": 10.0,
                    "recommended_context_length": 2048,
                    "source_provider": "bartowski",
                    "source_repo": "bartowski/test",
                    "notes": ["CPU-only fallback."],
                }
            ],
        }
    )
    process_events()

    assert view.btn_import_local_gguf_recommendation.isEnabled()
    assert not view.btn_apply_local_gguf_recommendation.isEnabled()
    assert "Activation is blocked" in view._local_gguf_recommendation_notes.text()


def test_app_view_repo_file_picker_uses_structured_columns(monkeypatch, qapp, process_events) -> None:
    view = _show(process_events)
    seen_headers: list[str] = []

    def _exec(dialog):
        tree = dialog.findChild(QTreeWidget)
        assert tree is not None
        seen_headers.extend(tree.headerItem().text(index) for index in range(tree.columnCount()))
        return QDialog.Accepted

    monkeypatch.setattr(QDialog, "exec", _exec)

    selected = view.pick_local_gguf_repo_file(
        [
            {
                "filename": "Qwen-Test-Instruct-Q4_K_M.gguf",
                "quant": "Q4_K_M",
                "size_bytes": 4_000_000,
                "hint": "chat/instruct",
            }
        ],
        detail="Choose a file.",
    )

    assert selected == "Qwen-Test-Instruct-Q4_K_M.gguf"
    assert seen_headers == ["Filename", "Quant", "Size", "Hint"]


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
