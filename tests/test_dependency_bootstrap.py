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

    def fake_popen(*_args, **_kwargs):
        called["ran"] = True
        raise AssertionError("pip should not be called when no dependencies are missing")

    monkeypatch.setattr(bootstrap.subprocess, "Popen", fake_popen)

    class DummyLogger:
        def info(self, *_args, **_kwargs):
            return None

        def warning(self, *_args, **_kwargs):
            return None

        def error(self, *_args, **_kwargs):
            return None

    installed = bootstrap.ensure_startup_dependencies(DummyLogger())
    assert installed is False
    assert called["ran"] is False


def test_ensure_startup_dependencies_reports_progress(monkeypatch):
    monkeypatch.setattr(bootstrap, "get_missing_startup_packages", lambda: ["llama-cpp-python"])

    class FakeProc:
        def __init__(self):
            self.stdout = iter(["Collecting llama-cpp-python\n", "Installing collected packages\n"])
            self.returncode = 0

        def wait(self):
            return 0

    monkeypatch.setattr(bootstrap.subprocess, "Popen", lambda *_args, **_kwargs: FakeProc())

    progress: list[str] = []

    class DummyLogger:
        def info(self, *_args, **_kwargs):
            return None

        def warning(self, *_args, **_kwargs):
            return None

        def error(self, *_args, **_kwargs):
            return None

    installed = bootstrap.ensure_startup_dependencies(
        DummyLogger(),
        progress_callback=progress.append,
    )

    assert installed is True
    assert any("Missing dependencies detected" in line for line in progress)
    assert any("Collecting llama-cpp-python" in line for line in progress)
    assert progress[-1] == "Dependencies installed successfully."
