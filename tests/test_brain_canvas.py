from __future__ import annotations

import pytest

from axiom_app.models.brain_graph import BrainNode

qt_core = pytest.importorskip("PySide6.QtCore", reason="Qt runtime unavailable")
qt_gui = pytest.importorskip("PySide6.QtGui", reason="Qt runtime unavailable")
brain_canvas = pytest.importorskip("axiom_app.views.brain_canvas", reason="Qt runtime unavailable")

Qt = qt_core.Qt
QFontMetricsF = qt_gui.QFontMetricsF
BrainNodeItem = brain_canvas.BrainNodeItem


def test_brain_root_label_layout_fits_wrapped_text_inside_node(qapp) -> None:
    item = BrainNodeItem(
        BrainNode(
            node_id="category:brain",
            node_type="category",
            label="Axiom Brain",
            metadata={"category_kind": "root"},
        ),
        {},
    )

    label, font, text_rect = item.label_layout()
    metrics = QFontMetricsF(font)
    bounds = metrics.boundingRect(text_rect, int(Qt.AlignCenter | Qt.TextWordWrap), label)

    assert label == "Axiom Brain"
    assert bounds.height() <= text_rect.height() + 0.5
    assert bounds.width() <= text_rect.width() + 0.5
