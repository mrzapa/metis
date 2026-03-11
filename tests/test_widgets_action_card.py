from __future__ import annotations

import pytest

from axiom_app.views.styles import get_palette
from axiom_app.views.widgets import ActionCard

qt_core = pytest.importorskip("PySide6.QtCore", reason="Qt runtime unavailable")
qt_test = pytest.importorskip("PySide6.QtTest", reason="Qt runtime unavailable")

QEvent = qt_core.QEvent
QPoint = qt_core.QPoint
Qt = qt_core.Qt
QApplication = pytest.importorskip("PySide6.QtWidgets", reason="Qt runtime unavailable").QApplication
QTest = qt_test.QTest


def test_action_card_height_for_width_grows_as_width_shrinks(qapp) -> None:
    card = ActionCard(
        "Research",
        "Fan out across the workspace, compare evidence, and keep the answer grounded.",
        palette=get_palette("space_dust"),
    )

    wide_height = card.heightForWidth(320)
    narrow_height = card.heightForWidth(180)

    assert wide_height >= 72
    assert narrow_height > wide_height


def test_action_card_update_palette_refreshes_idle_styles(qapp) -> None:
    dark_palette = get_palette("space_dust")
    light_palette = get_palette("light")
    card = ActionCard(
        "Ask Documents",
        "Ground answers in your indexed files with citations.",
        palette=dark_palette,
    )

    assert dark_palette["surface_alt"] in card._surface.styleSheet()
    assert dark_palette["border"] in card._surface.styleSheet()
    assert dark_palette["text"] in card._title_label.styleSheet()
    assert dark_palette["muted_text"] in card._affordance_label.styleSheet()

    card.update_palette(light_palette)

    assert light_palette["surface_alt"] in card._surface.styleSheet()
    assert light_palette["border"] in card._surface.styleSheet()
    assert light_palette["text"] in card._title_label.styleSheet()
    assert light_palette["muted_text"] in card._affordance_label.styleSheet()


def test_action_card_hover_and_pressed_states_update_styles(qapp, process_events) -> None:
    palette = get_palette("space_dust")
    card = ActionCard(
        "Summarize",
        "Condense a source into the most important ideas.",
        palette=palette,
    )
    card.resize(280, card.heightForWidth(280))
    card.show()
    process_events()

    QTest.mouseMove(card, QPoint(12, 12))
    process_events()

    assert card._visual_state == "hover"
    assert palette["nav_hover_bg"] in card._surface.styleSheet()
    assert palette["primary"] in card._affordance_label.styleSheet()

    QTest.mousePress(
        card,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        QPoint(12, 12),
    )
    process_events()

    pressed_border = palette.get("primary_pressed", palette["primary"])
    assert card._visual_state == "pressed"
    assert palette["nav_active_bg"] in card._surface.styleSheet()
    assert pressed_border in card._surface.styleSheet()

    QTest.mouseRelease(
        card,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        QPoint(12, 12),
    )
    process_events()

    assert card._visual_state == "hover"

    QApplication.sendEvent(card, QEvent(QEvent.Type.Leave))
    process_events()

    assert card._visual_state == "idle"
    assert palette["surface_alt"] in card._surface.styleSheet()
