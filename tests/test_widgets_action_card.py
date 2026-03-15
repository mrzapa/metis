from __future__ import annotations

import pytest

qt_core = pytest.importorskip(
    "PySide6.QtCore",
    reason="Qt runtime unavailable",
    exc_type=ImportError,
)
qt_test = pytest.importorskip(
    "PySide6.QtTest",
    reason="Qt runtime unavailable",
    exc_type=ImportError,
)
qt_widgets = pytest.importorskip(
    "PySide6.QtWidgets",
    reason="Qt runtime unavailable",
    exc_type=ImportError,
)
styles_module = pytest.importorskip(
    "axiom_app.views.styles",
    reason="Qt runtime unavailable",
    exc_type=ImportError,
)
widgets_module = pytest.importorskip(
    "axiom_app.views.widgets",
    reason="Qt runtime unavailable",
    exc_type=ImportError,
)

get_palette = styles_module.get_palette
ActionCard = widgets_module.ActionCard

QEvent = qt_core.QEvent
QPoint = qt_core.QPoint
Qt = qt_core.Qt
QApplication = qt_widgets.QApplication
QTest = qt_test.QTest


def test_action_card_height_for_width_grows_as_width_shrinks(qapp) -> None:
    card = ActionCard(
        "Research",
        "Fan out across the workspace, compare evidence, and keep the answer grounded.",
        palette=get_palette("space_dust"),
        icon_key="research",
    )

    wide_height = card.heightForWidth(320)
    narrow_height = card.heightForWidth(180)

    assert card._icon_widget is not None
    assert card._icon_widget._icon_key == "research"
    assert wide_height >= 72
    assert narrow_height > wide_height


def test_action_card_update_palette_refreshes_idle_styles(qapp) -> None:
    dark_palette = get_palette("space_dust")
    light_palette = get_palette("light")
    card = ActionCard(
        "Ask Documents",
        "Ground answers in your indexed files with citations.",
        palette=dark_palette,
        icon_key="document",
    )

    assert card._icon_widget is not None
    assert dark_palette["surface_alt"] in card._surface.styleSheet()
    assert dark_palette["border"] in card._surface.styleSheet()
    assert dark_palette["text"] in card._title_label.styleSheet()
    assert card._icon_widget._badge_background_color == dark_palette["surface"]
    assert card._icon_widget._badge_border_color == dark_palette["border"]
    assert card._icon_widget._icon_color == dark_palette["status"]

    card.update_palette(light_palette)

    assert light_palette["surface_alt"] in card._surface.styleSheet()
    assert light_palette["border"] in card._surface.styleSheet()
    assert light_palette["text"] in card._title_label.styleSheet()
    assert card._icon_widget._badge_background_color == light_palette["surface"]
    assert card._icon_widget._badge_border_color == light_palette["border"]
    assert card._icon_widget._icon_color == light_palette["status"]


def test_action_card_without_icon_key_omits_icon_slot(qapp) -> None:
    card = ActionCard(
        "Chat Freely",
        "Talk directly to the model without retrieval.",
        palette=get_palette("space_dust"),
    )

    assert card._icon_widget is None
    assert card.heightForWidth(240) >= 72


@pytest.mark.parametrize("theme_name", ["space_dust", "light"])
def test_action_card_hover_and_pressed_states_update_styles(
    qapp,
    process_events,
    theme_name: str,
) -> None:
    palette = get_palette(theme_name)
    card = ActionCard(
        "Summarize",
        "Condense a source into the most important ideas.",
        palette=palette,
        icon_key="summary",
    )
    card.resize(280, card.heightForWidth(280))
    card.show()
    process_events()
    assert card._icon_widget is not None

    QTest.mouseMove(card, QPoint(12, 12))
    process_events()

    assert card._visual_state == "hover"
    assert palette["nav_hover_bg"] in card._surface.styleSheet()
    assert card._icon_widget._badge_border_color == palette["primary"]
    assert card._icon_widget._icon_color == palette["primary"]

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
    assert card._icon_widget._badge_border_color == pressed_border
    assert card._icon_widget._icon_color == pressed_border

    QTest.mouseRelease(
        card,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        QPoint(12, 12),
    )
    process_events()

    assert card._visual_state == "hover"
    assert card._icon_widget._icon_color == palette["primary"]

    QApplication.sendEvent(card, QEvent(QEvent.Type.Leave))
    process_events()

    assert card._visual_state == "idle"
    assert palette["surface_alt"] in card._surface.styleSheet()
    assert card._icon_widget._badge_border_color == palette["border"]
    assert card._icon_widget._icon_color == palette["status"]
