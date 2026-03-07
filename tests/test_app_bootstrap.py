"""Bootstrap helper tests for the Qt desktop runtime."""

from __future__ import annotations

from axiom_app import app as app_module


class _FakeUser32:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def SetProcessDpiAwarenessContext(self, value) -> int:
        self.calls.append(("context", value))
        return 1

    def SetProcessDPIAware(self) -> int:
        self.calls.append(("legacy", None))
        return 1


class _FakeShcore:
    def __init__(self) -> None:
        self.calls: list[int] = []

    def SetProcessDpiAwareness(self, value: int) -> int:
        self.calls.append(value)
        return 0


def test_enable_windows_dpi_awareness_prefers_modern_context_api() -> None:
    fake_user32 = _FakeUser32()
    fake_ctypes = type(
        "FakeCtypes",
        (),
        {"windll": type("FakeWindll", (), {"user32": fake_user32, "shcore": _FakeShcore()})()},
    )()

    enabled = app_module._enable_windows_dpi_awareness(platform_name="win32", ctypes_module=fake_ctypes)

    assert enabled is True
    assert fake_user32.calls == [("context", -4)]


def test_enable_windows_dpi_awareness_is_noop_off_windows() -> None:
    enabled = app_module._enable_windows_dpi_awareness(platform_name="linux", ctypes_module=object())

    assert enabled is False
