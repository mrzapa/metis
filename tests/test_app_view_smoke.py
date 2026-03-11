"""Smoke tests for the redesigned PySide6 AppView workspace shell."""

from __future__ import annotations

import importlib
import pathlib
import sys
from types import SimpleNamespace

import pytest

from axiom_app.models.session_types import EvidenceSource

qt_widgets = pytest.importorskip("PySide6.QtWidgets", reason="Qt runtime unavailable")
qt_gui = pytest.importorskip("PySide6.QtGui", reason="Qt runtime unavailable")
QApplication = qt_widgets.QApplication
QTabWidget = qt_widgets.QTabWidget


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
    module = importlib.import_module("axiom_app.views.app_view")
    view = module.AppView(theme_name="space_dust")
    view.show()
    process_events()
    process_events()
    return module, view


def _settings_tabs(view) -> QTabWidget:
    tabs = view._settings_dialog.findChildren(QTabWidget)
    assert tabs
    return tabs[0]


def _sample_source() -> EvidenceSource:
    return EvidenceSource(
        sid="src-1",
        source="doc.txt",
        snippet="Grounded evidence",
        title="Doc",
        file_path="C:/tmp/doc.txt",
        score=0.82,
    )


def test_app_view_constructs_with_hidden_drawers_and_prompt_first_empty_state(qapp, process_events) -> None:
    _module, view = _show(process_events)
    empty_inner_layout = view._chat_empty_inner.layout()

    assert view._active_view == "chat"
    assert view._theme_name == "space_dust"
    assert view._chat_state_stack.currentWidget() is view._chat_empty_state
    assert view._chat_has_messages is False
    assert view.prompt_entry.isVisible()
    assert view.prompt_entry.placeholderText().startswith("Ask a question")
    assert view._chat_empty_value_label.text() == (
        "Start with plain language. Sources and setup stay out of the way until you need them."
    )
    assert view._chat_empty_value_label.isVisible()
    assert view._composer_shell.parentWidget() is view._chat_empty_composer_slot
    assert view._chat_empty_composer_slot.layout().indexOf(view._composer_shell) == 0
    assert empty_inner_layout.indexOf(view._chat_empty_value_label) < empty_inner_layout.indexOf(
        view._chat_empty_composer_slot
    )
    assert empty_inner_layout.indexOf(view._chat_empty_composer_slot) < empty_inner_layout.indexOf(
        view._chat_preset_grid_host
    )
    assert len(view._chat_preset_buttons) >= 5
    assert view._workspace_splitter.sizes()[0] == 0
    assert view._workspace_splitter.sizes()[2] == 0
    assert view._activity_tray.isVisible() is False
    assert view._session_drawer.isVisible() is False
    assert view._chat_context_hint.isVisible() is False
    assert view._chat_footer_composer_slot.isVisible() is False
    assert view._rail_buttons["inspect"].isEnabled() is False
    assert view._chat_context_summary.text() == "Q&A · Use Sources · No skill selected · unset"


def test_app_view_empty_state_scroll_area_expands_horizontally(qapp, process_events) -> None:
    _module, view = _show(process_events)

    view.resize(1400, 960)
    for _ in range(6):
        process_events()

    empty_layout = view._chat_empty_state.layout()
    scroll_item = empty_layout.itemAt(1)

    assert scroll_item is not None
    assert scroll_item.widget() is view._chat_empty_scroll
    assert int(scroll_item.alignment()) == 0
    assert view._chat_empty_scroll.width() > view._chat_empty_state.width() * 0.75
    assert view._chat_empty_inner.width() > view._chat_empty_scroll.viewport().width() * 0.55


def test_app_view_session_chips_reflect_context_and_open_the_session_drawer(qapp, process_events) -> None:
    _module, view = _show(process_events)

    view.set_profile_options(["No skill", "evidence-pack-timeline"], "evidence-pack-timeline")
    view.populate_settings(
        {
            "selected_mode": "Research",
            "chat_path": "Direct",
            "llm_provider": "openai",
            "llm_model": "gpt-5.4-mini",
        }
    )
    process_events()

    chips = {key: button.text() for key, button in view._session_chip_buttons.items()}
    assert chips == {
        "mode": "Mode · Research",
        "sources": "Sources · Direct",
        "skill": "Skill · evidence-pack-timeline",
        "model": "Model · openai / gpt-5.4-mini",
    }
    assert view._chat_context_summary.text() == "Research · Direct · evidence-pack-timeline · openai / gpt-5.4-mini"

    view._session_chip_buttons["model"].click()
    process_events()
    assert view._session_drawer.isVisible()
    assert view._session_tabs.tabText(view._session_tabs.currentIndex()) == "Model"

    view._session_chip_buttons["sources"].click()
    process_events()
    assert view._session_tabs.tabText(view._session_tabs.currentIndex()) == "Sources"

    view._show_conversation_setup_popup()
    process_events()
    assert view._session_tabs.tabText(view._session_tabs.currentIndex()) == "Mode"

    view._show_quick_model_popup()
    process_events()
    assert view._session_tabs.tabText(view._session_tabs.currentIndex()) == "Model"

    view._hide_quick_model_popup()
    process_events()
    assert view._session_drawer.isVisible() is False


def test_app_view_switches_between_empty_state_and_timeline_cards(qapp, process_events) -> None:
    _module, view = _show(process_events)

    view.append_chat("You: hello\n")
    view.append_chat("Axiom: hi there\n")
    process_events()

    assert view._chat_state_stack.currentWidget() is view._chat_transcript_state
    assert view._chat_has_messages is True
    assert [card._role_label.text() for card in view._chat_cards] == ["You", "Axiom"]
    assert [card._content_label.text() for card in view._chat_cards] == ["hello", "hi there"]
    assert view._composer_shell.parentWidget() is view._chat_footer_composer_slot
    assert view._chat_context_hint.isVisible() is True

    view.clear_chat()
    process_events()

    assert view._chat_state_stack.currentWidget() is view._chat_empty_state
    assert view._chat_has_messages is False
    assert view._chat_cards == []
    assert view._composer_shell.parentWidget() is view._chat_empty_composer_slot
    assert view._chat_context_hint.isVisible() is False
    assert view._workspace_splitter.sizes()[2] == 0


def test_app_view_preserves_prompt_focus_and_cursor_during_composer_relocation(qapp, process_events) -> None:
    _module, view = _show(process_events)

    view.set_prompt_text("hello world")
    cursor = view.prompt_entry.textCursor()
    cursor.setPosition(5)
    view.prompt_entry.setTextCursor(cursor)
    view.prompt_entry.setFocus()
    process_events()

    assert QApplication.focusWidget() is view.prompt_entry

    view.append_chat("You: hello\n")
    process_events()
    process_events()

    assert view._composer_shell.parentWidget() is view._chat_footer_composer_slot
    assert QApplication.focusWidget() is view.prompt_entry
    assert view.prompt_entry.textCursor().position() == 5

    view.clear_chat()
    process_events()
    process_events()

    assert view._composer_shell.parentWidget() is view._chat_empty_composer_slot
    assert QApplication.focusWidget() is view.prompt_entry
    assert view.prompt_entry.textCursor().position() == 5


def test_app_view_composer_relocation_does_not_steal_focus(qapp, process_events) -> None:
    _module, view = _show(process_events)

    view.btn_new_chat.setFocus()
    process_events()

    assert QApplication.focusWidget() is view.btn_new_chat

    view.append_chat("You: hello\n")
    process_events()
    process_events()

    assert view._composer_shell.parentWidget() is view._chat_footer_composer_slot
    assert QApplication.focusWidget() is view.btn_new_chat

    view.clear_chat()
    process_events()
    process_events()

    assert view._composer_shell.parentWidget() is view._chat_empty_composer_slot
    assert QApplication.focusWidget() is view.btn_new_chat


def test_app_view_completed_response_reveals_inspector_and_feedback_on_latest_assistant_card(qapp, process_events) -> None:
    _module, view = _show(process_events)

    view.append_chat("You: hello\n")
    view.append_chat("Axiom: here is the evidence\n")
    view.render_evidence_sources([_sample_source()])
    view.set_chat_response_ui(True, True)
    process_events()

    latest = view._chat_cards[-1]

    assert view._inspector_visible is True
    assert view._workspace_splitter.sizes()[2] > 0
    assert view._rail_buttons["inspect"].isEnabled() is True
    assert latest._sources_button.isVisible() is True
    assert latest._sources_button.text() == "1 source"
    assert latest._feedback_row.isVisible() is True
    assert latest._feedback_up.text() == "Useful"
    assert latest._feedback_down.text() == "Needs work"
    assert view._evidence_sources_tree.topLevelItemCount() == 1


def test_app_view_library_drawer_switches_between_sources_sessions_and_graph(qapp, process_events) -> None:
    _module, view = _show(process_events)

    view.switch_view("brain")
    process_events()

    assert view._library_visible is True
    assert [view._library_tabs.tabText(index) for index in range(view._library_tabs.count())] == [
        "Sources",
        "Sessions",
        "Graph",
    ]
    assert view._library_tabs.currentWidget() is view._library_graph_tab

    view._library_tabs.setCurrentWidget(view._library_sources_tab)
    view.set_active_index_summary("Indexed 14 files", index_path="C:/indexes/workspace")
    view.set_available_indexes(
        [
            {"label": "Workspace Index", "path": "C:/indexes/workspace"},
            {"label": "Archive Index", "path": "C:/indexes/archive"},
        ],
        selected_path="C:/indexes/workspace",
    )
    process_events()
    assert view._library_tabs.currentWidget() is view._library_sources_tab
    assert "Indexed 14 files" in view._active_index_summary.text()
    assert view.get_selected_available_index_path() == "C:/indexes/workspace"

    rows = [
        SimpleNamespace(
            session_id="session-1",
            title="Q1 recap",
            updated_at="2026-03-10 09:00",
            mode="Q&A",
            primary_skill_id="timeline",
            skill_ids=["timeline"],
        ),
        SimpleNamespace(
            session_id="session-2",
            title="Evidence pack",
            updated_at="2026-03-10 10:00",
            mode="Research",
            primary_skill_id="evidence-pack",
            skill_ids=["evidence-pack"],
        ),
    ]
    view._library_tabs.setCurrentWidget(view._library_sessions_tab)
    view.set_history_rows(rows)
    view.select_history_session("session-2")
    view.set_history_detail(
        SimpleNamespace(
            summary=rows[1],
            messages=[SimpleNamespace(role="assistant", content="Evidence pack ready.")],
            feedback=[],
        )
    )
    process_events()

    assert view._library_tabs.currentWidget() is view._library_sessions_tab
    assert view._history_tree.topLevelItemCount() == 2
    assert view.get_selected_history_session_id() == "session-2"
    assert "Evidence pack ready." in view._history_detail_browser.toPlainText()


def test_app_view_settings_dialog_round_trip_preserves_values(qapp, process_events) -> None:
    _module, view = _show(process_events)

    view.switch_view("settings")
    process_events()

    tabs = _settings_tabs(view)
    assert view._settings_dialog.isVisible() is True
    assert [tabs.tabText(index) for index in range(tabs.count())] == [
        "General",
        "Models",
        "Retrieval",
        "Privacy",
        "Developer",
        "Local Models",
    ]

    view.populate_settings(
        {
            "theme": "dark",
            "llm_provider": "anthropic",
            "llm_model": "claude-opus-4-6",
            "selected_mode": "Research",
            "llm_temperature": 0.0,
            "local_gguf_gpu_layers": 0,
            "log_dir": "axiom-logs",
        }
    )
    process_events()

    view._settings_widgets["llm_model"].setText("gpt-5.4-mini")
    view._settings_widgets["log_dir"].setText("custom-logs")
    collected = view.collect_settings()

    assert collected["theme"] == "dark"
    assert collected["llm_provider"] == "anthropic"
    assert collected["llm_model"] == "gpt-5.4-mini"
    assert collected["selected_mode"] == "Research"
    assert collected["llm_temperature"] == "0.0"
    assert collected["local_gguf_gpu_layers"] == "0"
    assert collected["log_dir"] == "custom-logs"


def test_app_view_activity_tray_filters_logs_and_supports_copy_and_open_folder(
    monkeypatch, qapp, process_events
) -> None:
    module, view = _show(process_events)
    opened_urls: list[str] = []

    monkeypatch.setattr(
        module.QDesktopServices,
        "openUrl",
        lambda url: opened_urls.append(url.toLocalFile()) or True,
    )

    view.populate_settings({"log_dir": "test-logs"})
    view.switch_view("logs")
    view.append_log("[status] indexed")
    view.append_log("[error] missing source")
    view._logs_search.setText("error")
    process_events()

    assert view._activity_visible is True
    assert "missing source" in view._logs_view.toPlainText()
    assert "indexed" not in view._logs_view.toPlainText()

    view._logs_copy_button.click()
    process_events()
    assert QApplication.clipboard().text() == "[error] missing source"

    view._logs_open_folder_button.click()
    process_events()
    assert opened_urls
    assert pathlib.Path(opened_urls[-1]).name == "test-logs"


def test_app_view_append_chat_compatibility_parses_legacy_prefixes(qapp, process_events) -> None:
    _module, view = _show(process_events)

    view.append_chat("System: reindexing\n")
    view.append_chat("You: compare the drafts\n")
    view.append_chat("Axiom: the newer one is more complete\n")
    process_events()

    assert [item.role for item in view._chat_items] == ["system", "user", "assistant"]
    assert [card._role_label.text() for card in view._chat_cards] == ["System", "You", "Axiom"]
    assert view._chat_cards[-1]._content_label.text() == "the newer one is more complete"


def test_app_view_set_chat_transcript_compatibility_renders_structured_messages(qapp, process_events) -> None:
    _module, view = _show(process_events)

    messages = [
        {"role": "user", "content": "Where is the evidence?"},
        SimpleNamespace(
            role="assistant",
            content="In the appendix.",
            run_id="run-42",
            sources=[_sample_source()],
        ),
    ]
    view.set_chat_transcript(messages)
    process_events()

    assert view._chat_state_stack.currentWidget() is view._chat_transcript_state
    assert len(view._chat_items) == 2
    assert len(view._chat_cards) == 2
    assert view._composer_shell.parentWidget() is view._chat_footer_composer_slot
    assert view._chat_cards[-1]._role_label.text() == "Axiom"
    assert view._chat_cards[-1]._sources_button.isVisible() is True
    assert view._chat_cards[-1]._sources_button.text() == "1 source"


def test_app_view_local_gguf_recommendations_render_in_the_settings_dialog(qapp, process_events) -> None:
    _module, view = _show(process_events)

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
    assert "RTX 4090" in view._local_gguf_hardware_label.text()
    assert view.btn_import_local_gguf_recommendation.isEnabled() is True
    assert view.btn_apply_local_gguf_recommendation.isEnabled() is True
