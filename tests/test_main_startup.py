"""Startup routing tests for main.py."""

from __future__ import annotations

import sys
import types

import main as main_module


def test_main_uses_mvc_runtime_by_default(monkeypatch) -> None:
    calls: list[str] = []
    fake_module = types.ModuleType("axiom_app.app")

    def _run_app() -> None:
        calls.append("mvc")

    fake_module.run_app = _run_app  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "axiom_app.app", fake_module)
    monkeypatch.delenv("AXIOM_NEW_APP", raising=False)
    monkeypatch.setattr(sys, "argv", ["main.py"])

    main_module.main()

    assert calls == ["mvc"]


def test_main_allows_explicit_legacy_opt_out(monkeypatch) -> None:
    calls: list[str] = []

    fake_legacy = types.ModuleType("agentic_rag_gui")

    class _FakeApp:
        def __init__(self, _root) -> None:
            calls.append("legacy-app")

    fake_legacy.AgenticRAGApp = _FakeApp  # type: ignore[attr-defined]

    class _FakeRoot:
        def withdraw(self) -> None:
            calls.append("withdraw")

        def mainloop(self) -> None:
            calls.append("mainloop")

    fake_tk = types.ModuleType("tkinter")
    fake_tk.Tk = _FakeRoot  # type: ignore[attr-defined]
    fake_tk.messagebox = types.SimpleNamespace(showerror=lambda *args, **kwargs: None)

    monkeypatch.setitem(sys.modules, "agentic_rag_gui", fake_legacy)
    monkeypatch.setitem(sys.modules, "tkinter", fake_tk)
    monkeypatch.setenv("AXIOM_NEW_APP", "0")
    monkeypatch.setattr(sys, "argv", ["main.py"])

    main_module.main()

    assert calls == ["withdraw", "legacy-app", "mainloop"]
