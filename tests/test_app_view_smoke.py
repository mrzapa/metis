"""Smoke tests for the redesigned MVC AppView shell."""

from __future__ import annotations

import tkinter as tk

import pytest

from axiom_app.views.app_view import AppView


def _make_root() -> tk.Tk:
    try:
        root = tk.Tk()
    except tk.TclError as exc:  # pragma: no cover - depends on CI display availability
        pytest.skip(f"Tk unavailable in test environment: {exc}")
    root.withdraw()
    return root


def test_app_view_constructs_with_empty_chat_state() -> None:
    root = _make_root()
    try:
        view = AppView(root, theme_name="light")
        root.update_idletasks()

        assert view._active_view == "chat"
        assert view._chat_has_messages is False
        assert view._chat_empty_state.winfo_manager() == "grid"
        assert view._conversation_shell.winfo_manager() == ""
    finally:
        root.destroy()


def test_app_view_switches_between_empty_and_conversation_states() -> None:
    root = _make_root()
    try:
        view = AppView(root, theme_name="light")
        root.update_idletasks()

        view.append_chat("Hello from a smoke test.\n")
        root.update_idletasks()

        assert view._chat_has_messages is True
        assert view._chat_empty_state.winfo_manager() == ""
        assert view._conversation_shell.winfo_manager() == "grid"

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
        view = AppView(root, theme_name="light")
        for key in ("library", "history", "settings", "logs"):
            view.switch_view(key)
            root.update_idletasks()
            assert view._tab_built[key] is True

        view.apply_theme("dark")
        root.update_idletasks()

        assert view.txt_input.cget("bg") == view._palette["input_bg"]
        assert view._file_listbox.cget("bg") == view._palette["surface_alt"]
        assert view._rag_toggle._palette["primary"] == view._palette["primary"]
    finally:
        root.destroy()
