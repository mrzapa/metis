from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest


@pytest.fixture(scope="session")
def qapp():
    qt_widgets = pytest.importorskip("PySide6.QtWidgets", reason="Qt runtime unavailable")
    app = qt_widgets.QApplication.instance() or qt_widgets.QApplication([])
    return app


@pytest.fixture
def process_events(qapp):
    def _process() -> None:
        qapp.processEvents()

    return _process
