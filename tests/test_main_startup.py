"""Startup routing tests for main.py."""

from __future__ import annotations

import sys
import types

import main as main_module


def test_main_uses_mvc_runtime_by_default(monkeypatch) -> None:
    calls: list[str] = []
    fake_module = types.ModuleType("metis_app.app")

    def _run_app() -> None:
        calls.append("mvc")

    fake_module.run_app = _run_app  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "metis_app.app", fake_module)
    monkeypatch.setattr(sys, "argv", ["main.py"])

    main_module.main()

    assert calls == ["mvc"]
