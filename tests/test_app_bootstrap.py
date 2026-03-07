"""Bootstrap helper tests for the MVC desktop runtime."""

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


class _FakeTkBridge:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    def call(self, *args) -> None:
        self.calls.append(args)


class _FakeRoot:
    def __init__(self, dpi: float) -> None:
        self._dpi = dpi
        self.tk = _FakeTkBridge()

    def winfo_fpixels(self, value: str) -> float:
        assert value == "1i"
        return self._dpi


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


def test_apply_tk_scaling_uses_effective_display_dpi() -> None:
    root = _FakeRoot(dpi=144.0)

    scaling = app_module._apply_tk_scaling(root, platform_name="win32")

    assert scaling == 2.0
    assert root.tk.calls == [("tk", "scaling", 2.0)]


def test_apply_tk_scaling_is_noop_off_windows() -> None:
    root = _FakeRoot(dpi=144.0)

    scaling = app_module._apply_tk_scaling(root, platform_name="darwin")

    assert scaling is None
    assert root.tk.calls == []
