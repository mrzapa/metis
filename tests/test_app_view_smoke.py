"""Smoke tests for the redesigned MVC AppView shell."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import pytest

from axiom_app.views.app_view import AppView


def _make_root() -> tk.Tk:
    try:
        root = tk.Tk()
    except tk.TclError as exc:  # pragma: no cover - depends on CI display availability
        pytest.skip(f"Tk unavailable in test environment: {exc}")
    root.withdraw()
    return root


def _assert_child_fits(parent: tk.Misc, child: tk.Misc) -> None:
    parent.update_idletasks()
    assert child.winfo_height() > 0
    assert child.winfo_y() >= 0
    assert child.winfo_y() + child.winfo_height() <= parent.winfo_height()


def test_app_view_constructs_with_empty_chat_state() -> None:
    root = _make_root()
    try:
        view = AppView(root, theme_name="space_dust")
        root.update_idletasks()

        assert view._active_view == "chat"
        assert view._theme_name == "space_dust"
        assert view._chat_has_messages is False
        assert view._chat_empty_state.winfo_manager() == "grid"
        assert view._conversation_shell.winfo_manager() == ""
        assert view._sidebar_logo_photo is not None
        assert root.minsize() == (1180, 760)
        assert int(ttk.Style(root).lookup("Vertical.TScrollbar", "width")) == 12

        for geometry in ("1180x760", "1280x800", "1440x960"):
            root.geometry(geometry)
            root.update_idletasks()
            _assert_child_fits(view._chat_empty_inner, view._hero_greeting_label)
            _assert_child_fits(view._chat_empty_inner, view._hero_copy_label)
    finally:
        root.destroy()


def test_app_view_switches_between_empty_and_conversation_states() -> None:
    root = _make_root()
    try:
        view = AppView(root, theme_name="space_dust")
        root.update_idletasks()

        view.append_chat("Hello from a smoke test.\n")
        root.update_idletasks()

        assert view._chat_has_messages is True
        assert view._chat_empty_state.winfo_manager() == ""
        assert view._conversation_shell.winfo_manager() == "grid"
        assert view._chat_transcript_scrollbar.winfo_manager() == "grid"
        assert view._prompt_scrollbar.winfo_manager() == "grid"

        view.clear_chat()
        root.update_idletasks()

        assert view._chat_has_messages is False
        assert view._chat_empty_state.winfo_manager() == "grid"
        assert view._conversation_shell.winfo_manager() == ""
    finally:
        root.destroy()


def test_app_view_lazy_builds_tabs_and_rethemes_raw_widgets() -> None:
    root = _make_root()
    try:
        view = AppView(root, theme_name="space_dust")
        for key in ("library", "history", "settings", "logs"):
            view.switch_view(key)
            root.update_idletasks()
            assert view._tab_built[key] is True

        assert view._library_page_canvas.winfo_exists()
        assert view._library_page_scrollbar.winfo_manager() == "grid"
        assert view._settings_scrollbar.winfo_manager() == "grid"
        assert view._logs_view_scrollbar.winfo_manager() == "grid"

        view.apply_theme("dark")
        root.update_idletasks()

        assert view.txt_input.cget("bg") == view._palette["input_bg"]
        assert view._file_listbox.cget("bg") == view._palette["surface_alt"]
        assert view._rag_toggle._palette["primary"] == view._palette["primary"]
        assert int(ttk.Style(root).lookup("Vertical.TScrollbar", "width")) == 12
    finally:
        root.destroy()
