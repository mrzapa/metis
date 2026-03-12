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


def _widget_top_in(widget, ancestor) -> int:
    return widget.mapTo(ancestor, widget.rect().topLeft()).y()


def _widget_bottom_in(widget, ancestor) -> int:
    return _widget_top_in(widget, ancestor) + widget.height()


def _widget_center_y_in(widget, ancestor) -> int:
    return widget.mapTo(ancestor, widget.rect().center()).y()


def _vertical_gap_in(upper, lower, ancestor) -> int:
    return _widget_top_in(lower, ancestor) - _widget_bottom_in(upper, ancestor)


def _bottom_gap_in(widget, ancestor) -> int:
    return ancestor.rect().height() - _widget_bottom_in(widget, ancestor)


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


def _complete_chat_response(view, process_events, *, feedback_pending: bool = True) -> None:
    view.append_chat("You: hello\n")
    view.append_chat("Axiom: here is the evidence\n")
    view.render_evidence_sources([_sample_source()])
    view.set_chat_response_ui(True, feedback_pending)
    process_events()


def test_app_view_constructs_with_hidden_drawers_and_prompt_first_empty_state(qapp, process_events) -> None:
    module, view = _show(process_events)
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
    assert view._chat_empty_value_label.parentWidget() is view._chat_empty_text_column
    assert view._chat_empty_text_column.layout().indexOf(view._chat_empty_value_label) == 0
    assert empty_inner_layout.count() == 7
    assert empty_inner_layout.indexOf(view._chat_empty_text_row) < empty_inner_layout.indexOf(
        view._chat_empty_composer_slot
    )
    assert empty_inner_layout.indexOf(view._chat_empty_composer_slot) < empty_inner_layout.indexOf(
        view._chat_preset_grid_host
    )
    assert len(view._chat_preset_buttons) == len(module._CHAT_PRESETS)
    assert all(isinstance(button, module.ActionCard) for button in view._chat_preset_buttons)
    assert all(button._icon_widget is not None for button in view._chat_preset_buttons)
    assert [button._icon_widget._icon_key for button in view._chat_preset_buttons] == [
        preset["icon_key"] for preset in module._CHAT_PRESETS
    ]
    assert view._workspace_splitter.sizes()[0] == 0
    assert view._workspace_splitter.sizes()[2] == 0
    assert view._activity_tray.isVisible() is False
    assert view._session_drawer.isVisible() is False
    assert view._chat_context_hint.isVisible() is False
    assert view._chat_context_summary.isVisible() is False
    assert view._chat_footer_composer_slot.isVisible() is False
    assert view._rail_buttons["inspect"].isEnabled() is False
    assert view._chat_context_summary.text() == "Q&A · Use Sources · No skill selected · unset"


def test_app_view_empty_state_scroll_area_expands_horizontally(qapp, process_events) -> None:
    module, view = _show(process_events)

    view.resize(1400, 960)
    for _ in range(6):
        process_events()

    empty_layout = view._chat_empty_state.layout()
    scroll_item = empty_layout.itemAt(0)

    assert scroll_item is not None
    assert scroll_item.widget() is view._chat_empty_scroll
    assert int(scroll_item.alignment()) == 0
    assert empty_layout.count() == 1
    assert view._chat_empty_body_row.height() == view._chat_empty_scroll.viewport().height()
    assert view._chat_empty_scroll.width() > view._chat_empty_state.width() * 0.85
    assert view._chat_empty_scroll.height() > view._chat_empty_state.height() * 0.85
    assert view._chat_empty_inner.width() <= 880
    assert view._chat_empty_inner.width() >= 860
    assert abs(
        view._chat_empty_inner.geometry().center().x() - view._chat_empty_body_row.rect().center().x()
    ) <= 2
    assert view._chat_empty_text_column.width() <= 720
    assert view._chat_empty_text_column.width() >= 680
    assert view._chat_empty_value_label.width() >= view._chat_empty_text_column.width() - 2
    assert (
        abs(
            _widget_center_y_in(view._chat_empty_composer_slot, view._chat_empty_scroll.viewport())
            - view._chat_empty_scroll.viewport().rect().center().y()
        )
        <= module.UI_SPACING["xl"]
    )
    assert _widget_top_in(view._chat_empty_text_row, view._chat_empty_scroll.viewport()) >= module.UI_SPACING["l"]
    assert (
        _vertical_gap_in(
            view._chat_empty_text_row,
            view._chat_empty_composer_slot,
            view._chat_empty_scroll.viewport(),
        )
        <= module.UI_SPACING["xxl"] + module.UI_SPACING["xl"]
    )
    assert (
        _vertical_gap_in(
            view._chat_empty_composer_slot,
            view._chat_preset_grid_host,
            view._chat_empty_scroll.viewport(),
        )
        > 0
    )
    assert _bottom_gap_in(view._chat_preset_grid_host, view._chat_empty_scroll.viewport()) >= 0


def test_app_view_empty_state_balances_tall_windows_without_dead_space_bands(qapp, process_events) -> None:
    module, view = _show(process_events)

    view.resize(1480, 1200)
    for _ in range(6):
        process_events()

    viewport = view._chat_empty_scroll.viewport()
    top_gap = _widget_top_in(view._chat_empty_text_row, viewport)
    intro_gap = _vertical_gap_in(view._chat_empty_text_row, view._chat_empty_composer_slot, viewport)
    composer_gap = _vertical_gap_in(view._chat_empty_composer_slot, view._chat_preset_grid_host, viewport)
    bottom_gap = _bottom_gap_in(view._chat_preset_grid_host, viewport)

    assert top_gap >= module.UI_SPACING["xxl"]
    assert intro_gap <= module.UI_SPACING["xxl"] + module.UI_SPACING["xl"]
    assert abs(_widget_center_y_in(view._chat_empty_composer_slot, viewport) - viewport.rect().center().y()) <= (
        module.UI_SPACING["l"]
    )
    assert composer_gap > 0
    assert bottom_gap > 0
    assert view._chat_empty_scroll.verticalScrollBar().value() == 0


def test_app_view_empty_state_text_column_rewraps_when_center_stage_narrows(qapp, process_events) -> None:
    module, view = _show(process_events)

    view.resize(1400, 960)
    for _ in range(6):
        process_events()

    wide_text_width = view._chat_empty_text_column.width()
    wide_label_height = view._chat_empty_value_label.height()
    wide_inner_width = view._chat_empty_inner.width()

    view.resize(1180, 760)
    view._set_library_visible(True)
    for _ in range(6):
        process_events()

    narrow_text_width = view._chat_empty_text_column.width()
    narrow_label_height = view._chat_empty_value_label.height()
    narrow_inner_width = view._chat_empty_inner.width()

    assert narrow_inner_width < wide_inner_width
    assert narrow_text_width < wide_text_width
    assert narrow_text_width >= 400
    assert narrow_label_height > wide_label_height
    assert abs(
        view._chat_empty_inner.geometry().center().x() - view._chat_empty_body_row.rect().center().x()
    ) <= 2
    assert view._chat_empty_scroll.verticalScrollBar().value() == 0
    assert _widget_top_in(view._chat_empty_text_row, view._chat_empty_scroll.viewport()) <= module.UI_SPACING["xl"]
    assert (
        _widget_top_in(view._chat_empty_text_row, view._chat_empty_scroll.viewport())
        < _widget_top_in(view._chat_empty_composer_slot, view._chat_empty_scroll.viewport())
        < _widget_top_in(view._chat_preset_grid_host, view._chat_empty_scroll.viewport())
    )
    assert (
        _widget_top_in(view._chat_empty_text_row, view._chat_empty_scroll.viewport())
        + view._chat_empty_text_row.height()
        <= _widget_top_in(view._chat_empty_composer_slot, view._chat_empty_scroll.viewport())
    )
    assert (
        _vertical_gap_in(
            view._chat_empty_composer_slot,
            view._chat_preset_grid_host,
            view._chat_empty_scroll.viewport(),
        )
        >= 0
    )
    assert (
        _widget_top_in(view._chat_empty_composer_slot, view._chat_empty_scroll.viewport())
        + view._chat_empty_composer_slot.height()
        <= _widget_top_in(view._chat_preset_grid_host, view._chat_empty_scroll.viewport())
    )


def test_app_view_starter_cards_click_through_existing_preset_handler(qapp, process_events) -> None:
    module, view = _show(process_events)
    emitted: list[str] = []
    target_preset = module._CHAT_PRESETS[2]

    view.newChatRequested.connect(lambda: emitted.append("new-chat"))
    view._chat_preset_buttons[2].click()
    process_events()

    assert view._mode_combo.currentText() == target_preset["mode"]
    assert view._rag_toggle.get_value() is True
    assert emitted == ["new-chat"]


def test_app_view_starter_cards_retheme_without_breaking_empty_state_layout(qapp, process_events) -> None:
    _module, view = _show(process_events)
    first_card = view._chat_preset_buttons[0]
    dark_surface_style = first_card._surface.styleSheet()
    assert first_card._icon_widget is not None
    dark_icon_color = first_card._icon_widget._icon_color
    dark_badge_background = first_card._icon_widget._badge_background_color

    view.apply_theme("light")
    for _ in range(4):
        process_events()

    assert view._theme_name == "light"
    assert first_card._surface.styleSheet() != dark_surface_style
    assert first_card._icon_widget._icon_color != dark_icon_color
    assert first_card._icon_widget._badge_background_color != dark_badge_background
    assert view._chat_state_stack.currentWidget() is view._chat_empty_state
    assert view._chat_empty_inner.width() <= 880
    assert len(view._chat_preset_buttons) > 0


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

    chips = view._session_chip_buttons
    assert chips["mode"].text() == "Mode · Research"
    assert chips["sources"].text() == "Sources · Direct"
    assert chips["skill"].text().startswith("Skill · evidence-pack")
    assert chips["skill"].toolTip() == "Skill · evidence-pack-timeline"
    assert chips["model"].text().startswith("Model · openai")
    assert chips["model"].toolTip() == "Model · openai / gpt-5.4-mini"
    assert len({button.width() for button in chips.values()}) == 1
    assert len({button.height() for button in chips.values()}) == 1
    assert view._chat_context_summary.text() == "Research · Direct · evidence-pack-timeline · openai / gpt-5.4-mini"
    assert view._chat_context_summary.isVisible() is False

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
    assert view._chat_context_summary.isVisible() is True

    view.clear_chat()
    process_events()

    assert view._chat_state_stack.currentWidget() is view._chat_empty_state
    assert view._chat_has_messages is False
    assert view._chat_cards == []
    assert view._composer_shell.parentWidget() is view._chat_empty_composer_slot
    assert view._chat_context_hint.isVisible() is False
    assert view._chat_context_summary.isVisible() is False
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

    _complete_chat_response(view, process_events, feedback_pending=True)

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


def test_app_view_inspector_has_exactly_three_expected_tabs(qapp, process_events) -> None:
    _module, view = _show(process_events)

    assert [view._evidence_tabs.tabText(index) for index in range(view._evidence_tabs.count())] == [
        "Evidence",
        "Process",
        "Structure",
    ]


def test_app_view_sources_button_opens_evidence_tab_in_inspector(qapp, process_events) -> None:
    _module, view = _show(process_events)

    _complete_chat_response(view, process_events, feedback_pending=True)
    latest = view._chat_cards[-1]
    view._evidence_tabs.setCurrentIndex(2)

    latest._sources_button.click()
    process_events()

    assert view._inspector_visible is True
    assert view._workspace_splitter.sizes()[2] > 0
    assert view._evidence_tabs.tabText(view._evidence_tabs.currentIndex()) == "Evidence"


def test_app_view_inspector_renderers_map_to_expected_widgets(qapp, process_events, tmp_path) -> None:
    _module, view = _show(process_events)
    grounding_html_path = tmp_path / "grounding.html"
    grounding_html_path.write_text("<html><body>Grounded</body></html>", encoding="utf-8")

    view.render_evidence_sources([_sample_source()])
    view.render_events([{"timestamp": "10:00", "stage": "retrieve", "event_type": "search", "detail": "ok"}])
    view.render_trace_events([{"timestamp": "10:01", "stage": "answer", "event_type": "emit", "payload": {"ok": True}}])
    view.render_grounding_info("Inline grounding note")
    view.render_document_outline([{"heading": "Introduction", "path": "1"}], str(grounding_html_path))
    view.render_semantic_regions([{"document": "doc.txt", "region": "Intro", "summary": "Summary"}])
    process_events()

    assert not hasattr(view, "_regions_tree")
    assert view._evidence_sources_tree.topLevelItemCount() == 1
    assert view._events_tree.topLevelItemCount() == 1
    assert view._trace_tree.topLevelItemCount() == 1
    assert view._outline_tree.topLevelItemCount() == 1
    assert view._grounding_browser.toPlainText() == str(grounding_html_path)
    assert "href=" in view._grounding_browser.toHtml()


def test_app_view_user_closed_inspector_stays_closed_on_later_completions(qapp, process_events) -> None:
    _module, view = _show(process_events)

    _complete_chat_response(view, process_events, feedback_pending=True)

    view._toggle_inspector()
    process_events()

    assert view._inspector_visible is False
    assert view._user_closed_since_last_completion is True
    assert view._workspace_splitter.sizes()[2] == 0

    view.set_chat_response_ui(True, False)
    process_events()

    assert view._inspector_visible is False
    assert view._user_closed_since_last_completion is True
    assert view._workspace_splitter.sizes()[2] == 0
    assert view._rail_buttons["inspect"].isEnabled() is True


def test_app_view_manual_inspector_open_does_not_reenable_auto_open(qapp, process_events) -> None:
    _module, view = _show(process_events)

    _complete_chat_response(view, process_events, feedback_pending=True)
    latest = view._chat_cards[-1]

    view._toggle_inspector()
    process_events()
    latest._sources_button.click()
    process_events()

    assert view._inspector_visible is True
    assert view._user_closed_since_last_completion is True

    view._toggle_inspector()
    process_events()
    view.set_chat_response_ui(True, False)
    process_events()

    assert view._inspector_visible is False
    assert view._user_closed_since_last_completion is True


def test_app_view_clearing_chat_resets_inspector_auto_open_suppression(qapp, process_events) -> None:
    _module, view = _show(process_events)

    _complete_chat_response(view, process_events, feedback_pending=True)
    view._toggle_inspector()
    process_events()

    assert view._user_closed_since_last_completion is True

    view.clear_chat()
    process_events()

    assert view._inspector_visible is False
    assert view._user_closed_since_last_completion is False
    assert view._rail_buttons["inspect"].isEnabled() is False

    _complete_chat_response(view, process_events, feedback_pending=False)

    assert view._inspector_visible is True
    assert view._workspace_splitter.sizes()[2] > 0


def test_app_view_loading_transcript_resets_inspector_auto_open_suppression(qapp, process_events) -> None:
    _module, view = _show(process_events)

    _complete_chat_response(view, process_events, feedback_pending=True)
    view._toggle_inspector()
    process_events()

    assert view._user_closed_since_last_completion is True

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

    assert view._inspector_visible is False
    assert view._user_closed_since_last_completion is False

    view.set_chat_response_ui(True, False)
    process_events()

    assert view._inspector_visible is True
    assert view._workspace_splitter.sizes()[2] > 0


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
