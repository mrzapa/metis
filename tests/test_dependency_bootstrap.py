from __future__ import annotations

from axiom_app.utils import dependency_bootstrap as bootstrap


def test_get_missing_startup_packages_reports_only_missing(monkeypatch):
    modules_present = {"langchain", "llama_cpp"}

    def fake_find_spec(module_name: str):
        if module_name in modules_present:
            return object()
        return None

    monkeypatch.setattr(bootstrap.importlib.util, "find_spec", fake_find_spec)

    missing = bootstrap.get_missing_startup_packages()

    assert "llama-cpp-python" not in missing
    assert "langchain>=0.3.0" not in missing
    assert "sentence-transformers" in missing


def test_ensure_startup_dependencies_skips_install_when_not_needed(monkeypatch):
    monkeypatch.setattr(bootstrap, "get_missing_startup_packages", lambda: [])

    called = {"ran": False}

    def fake_run(*_args, **_kwargs):
        called["ran"] = True
        raise AssertionError("pip should not be called when no dependencies are missing")

    monkeypatch.setattr(bootstrap.subprocess, "run", fake_run)

    class DummyLogger:
        def info(self, *_args, **_kwargs):
            return None

        def warning(self, *_args, **_kwargs):
            return None

        def error(self, *_args, **_kwargs):
            return None

    bootstrap.ensure_startup_dependencies(DummyLogger())
    assert called["ran"] is False
