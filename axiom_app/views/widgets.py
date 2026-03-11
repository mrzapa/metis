"""axiom_app.views.widgets — Reusable custom PySide6 widget classes.

Classes
-------
AnimationEngine      — QVariantAnimation-based smooth value interpolation with easing
IOSSegmentedToggle   — QPainter-rendered iOS-style two-option pill toggle
CollapsibleFrame     — animated accordion section with height transitions
MetricAwareWrapLabel — QLabel with better wrapped size hints
RoundedCard          — QFrame with border-radius + QGraphicsDropShadowEffect
ActionCard          — Clickable card button with hover and pressed states
TooltipManager       — hover tooltips with fade-in animation
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QRect,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QMouseEvent,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from axiom_app.views.styles import STYLE_CONFIG, UI_SPACING, _pal

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# AnimationEngine
# ---------------------------------------------------------------------------


class AnimationEngine(QObject):
    """Smooth value interpolation using QVariantAnimation."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._animations: dict[str, QVariantAnimation] = {}

    def cancel(self, anim_id: str) -> None:
        anim = self._animations.pop(anim_id, None)
        if anim is not None and anim.state() == QVariantAnimation.Running:
            anim.stop()
            anim.deleteLater()

    def animate_value(
        self,
        anim_id: str,
        start: float,
        end: float,
        duration_ms: int,
        steps: int,  # ignored — Qt handles interpolation natively
        callback: Callable[[float], Any],
        on_complete: Callable[[], Any] | None = None,
    ) -> None:
        self.cancel(anim_id)
        anim = QVariantAnimation(self)
        anim.setStartValue(float(start))
        anim.setEndValue(float(end))
        anim.setDuration(max(1, int(duration_ms)))
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.valueChanged.connect(lambda val: callback(val))
        if on_complete:
            anim.finished.connect(on_complete)
        anim.finished.connect(lambda: self._animations.pop(anim_id, None))
        self._animations[anim_id] = anim
        anim.start()


# ---------------------------------------------------------------------------
# IOSSegmentedToggle
# ---------------------------------------------------------------------------


class IOSSegmentedToggle(QWidget):
    """iOS-style segmented two-option toggle rendered with QPainter.

    Parameters
    ----------
    parent   : QWidget parent
    options  : sequence of exactly 2 label strings, e.g. ["RAG", "Direct"]
    value    : True selects options[0], False selects options[1]
    palette  : colour-dict (same shape as STYLE_CONFIG theme palettes)
    command  : optional callable invoked after each toggle
    height   : pixel height of the pill (default 28)
    font     : QFont instance (default Segoe UI 9 bold)
    """

    toggled = Signal(bool)

    def __init__(
        self,
        parent: QWidget | None,
        options: list[str] | tuple[str, str],
        value: bool = True,
        palette: dict | None = None,
        *,
        command: Callable[[], Any] | None = None,
        height: int = 28,
        font: QFont | None = None,
    ) -> None:
        super().__init__(parent)
        self._opts = list(options)
        self._value = value
        self._palette = dict(palette) if palette else {}
        self._command = command
        self._h = height
        self._font = font or QFont("Segoe UI", 9, QFont.Bold)
        self._seg_w = max(68, max(len(o) for o in options) * 9 + 28)
        total_w = self._seg_w * 2 + 2
        self.setFixedSize(total_w, height)
        self.setCursor(Qt.PointingHandCursor)

    def get_value(self) -> bool:
        return self._value

    def set_value(self, val: bool) -> None:
        self._value = val
        self.update()

    def update_palette(self, palette: dict) -> None:
        self._palette = dict(palette)
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._command:
            self._command()
        else:
            self._value = not self._value
            self.toggled.emit(self._value)
            self.update()

    def paintEvent(self, event: Any) -> None:
        pal = self._palette
        track = QColor(pal.get("surface_alt", "#1A2B40"))
        border_col = QColor(pal.get("outline", "#2A3E58"))
        primary = QColor(pal.get("primary", "#4D9EFF"))
        text_on = QColor(pal.get("text", "#EAF0FF"))
        text_off = QColor(pal.get("muted_text", "#8A9DC0"))

        w = self.width()
        h = self._h
        r = h / 2.0
        sw = self._seg_w
        pad = 3
        left_active = self._value

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        # Track background
        painter.setPen(QPen(border_col, 1))
        painter.setBrush(QBrush(track))
        painter.drawRoundedRect(QRectF(0, 0, w, h), r, r)

        # Active segment
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(primary))
        if left_active:
            painter.drawRoundedRect(QRectF(pad, pad, sw - 2 * pad, h - 2 * pad), r - pad, r - pad)
        else:
            painter.drawRoundedRect(QRectF(sw + pad, pad, sw - 2 * pad, h - 2 * pad), r - pad, r - pad)

        # Text
        painter.setFont(self._font)

        painter.setPen(text_on if left_active else text_off)
        painter.drawText(QRectF(0, 0, sw, h), Qt.AlignCenter, self._opts[0])

        painter.setPen(text_off if left_active else text_on)
        painter.drawText(QRectF(sw, 0, sw, h), Qt.AlignCenter, self._opts[1])

        painter.end()


# ---------------------------------------------------------------------------
# CollapsibleFrame
# ---------------------------------------------------------------------------


class CollapsibleFrame(QWidget):
    """Animated accordion section.

    Parameters
    ----------
    parent    : QWidget parent
    title     : header label text
    expanded  : initial state (default False = collapsed)
    animator  : AnimationEngine instance for smooth height transitions, or
                None to skip animation
    """

    def __init__(
        self,
        parent: QWidget | None,
        title: str,
        expanded: bool = False,
        animator: AnimationEngine | None = None,
    ) -> None:
        super().__init__(parent)
        self._animator = animator
        self._expanded = expanded
        self._animating = False
        self._animation_id = f"collapsible_{id(self)}"
        self._content_pad = UI_SPACING["s"]

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(
            UI_SPACING["s"], UI_SPACING["s"], UI_SPACING["s"], UI_SPACING["s"]
        )
        main_layout.setSpacing(0)

        # Header
        self.header = QWidget(self)
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(UI_SPACING["xs"])

        self.arrow_label = QLabel("▾" if expanded else "▸", self.header)
        self.arrow_label.setFixedWidth(18)
        self.arrow_label.setAlignment(Qt.AlignCenter)
        self.arrow_label.setProperty("cssClass", "muted")
        header_layout.addWidget(self.arrow_label)

        self.title_label = QLabel(title, self.header)
        self.title_label.setProperty("cssClass", "bold")
        header_layout.addWidget(self.title_label, 1)

        self.header.setCursor(Qt.PointingHandCursor)
        self.header.mousePressEvent = lambda _e: self.toggle()
        main_layout.addWidget(self.header)

        # Content wrapper
        self.content = QWidget(self)
        self.content.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self._content_layout = QVBoxLayout(self.content)
        self._content_layout.setContentsMargins(0, self._content_pad, 0, self._content_pad)
        self._content_layout.setSpacing(UI_SPACING["s"])
        main_layout.addWidget(self.content)

        if not expanded:
            self.content.setMaximumHeight(0)
            self.content.setVisible(False)

    def _measure_content_height(self) -> int:
        self.content.setMaximumHeight(16777215)  # QWIDGETSIZE_MAX
        self.content.adjustSize()
        h = max(1, self.content.sizeHint().height())
        if not self._expanded and not self._animating:
            self.content.setMaximumHeight(0)
        return h

    @property
    def content_layout(self) -> QVBoxLayout:
        """Public layout API for adding content widgets to the accordion body."""
        return self._content_layout

    def _set_clip_height(self, value: float) -> None:
        self.content.setMaximumHeight(max(0, int(value)))

    def _expand(self) -> None:
        if self._animating:
            return
        self._animating = True
        self.content.setVisible(True)
        target = self._measure_content_height()
        self.content.setMaximumHeight(0)

        def _done() -> None:
            self.content.setMaximumHeight(16777215)
            self.arrow_label.setText("▾")
            self._expanded = True
            self._animating = False

        duration = int(STYLE_CONFIG.get("animation", {}).get("collapse_duration_ms", 200))
        if self._animator:
            self._animator.animate_value(
                self._animation_id, 0, target, duration, 10,
                lambda v: self._set_clip_height(v),
                on_complete=_done,
            )
        else:
            self._set_clip_height(target)
            _done()

    def _collapse(self) -> None:
        if self._animating:
            return
        self._animating = True
        start = max(1, self.content.height())

        def _done() -> None:
            self._set_clip_height(0)
            self.content.setVisible(False)
            self.arrow_label.setText("▸")
            self._expanded = False
            self._animating = False

        duration = int(STYLE_CONFIG.get("animation", {}).get("collapse_duration_ms", 200))
        if self._animator:
            self._animator.animate_value(
                self._animation_id, start, 0, duration, 10,
                lambda v: self._set_clip_height(v),
                on_complete=_done,
            )
        else:
            _done()

    def set_expanded(self, expanded: bool) -> None:
        if bool(expanded) != self._expanded:
            self.toggle()

    def toggle(self) -> None:
        if self._animating:
            return
        if self._expanded:
            self._collapse()
        else:
            self._expand()


# ---------------------------------------------------------------------------
# MetricAwareWrapLabel
# ---------------------------------------------------------------------------


class MetricAwareWrapLabel(QLabel):
    """QLabel that reports wrapped size hints using the best available width."""

    _MAX_WIDGET_DIMENSION = 16_777_215

    def event(self, event: QEvent | None) -> bool:
        if event is not None and event.type() in (
            QEvent.FontChange,
            QEvent.Polish,
            QEvent.PolishRequest,
            QEvent.StyleChange,
        ):
            self.updateGeometry()
        return super().event(event)

    def minimumSizeHint(self) -> QSize:
        return self._resolve_wrapped_hint(super().minimumSizeHint())

    def sizeHint(self) -> QSize:
        return self._resolve_wrapped_hint(super().sizeHint())

    def _resolve_wrapped_hint(self, hint: QSize) -> QSize:
        if not self.wordWrap():
            return hint
        width = self.width()
        maximum_width = self.maximumWidth()
        if width <= 0 and 0 < maximum_width < self._MAX_WIDGET_DIMENSION:
            width = maximum_width
        if width <= 0:
            width = max(hint.width(), 1)
        height = self.heightForWidth(width)
        if height > 0:
            hint.setWidth(width)
            hint.setHeight(max(hint.height(), height))
        return hint


# ---------------------------------------------------------------------------
# RoundedCard
# ---------------------------------------------------------------------------


class RoundedCard(QFrame):
    """QFrame with rounded corners and optional drop shadow.

    Children should be placed inside ``card.inner`` (a plain ``QFrame``).
    """

    def __init__(
        self,
        parent: QWidget | None,
        radius: int = 12,
        bg: str = "#161B22",
        outer_bg: str | None = None,
        border_color: str = "#33465F",
        border_width: int = 1,
        shadow_color: str | None = None,
        shadow_offset: int = 0,
        inner_padding: int | None = None,
    ) -> None:
        super().__init__(parent)
        self._radius = max(2, int(radius))
        self._card_bg = bg
        self._border_color = border_color
        self._border_width = border_width
        self._shadow_offset = max(0, int(shadow_offset))
        inner_pad = max(0, int(inner_padding)) if inner_padding is not None else max(10, self._radius - 4)

        self._apply_card_style()

        # Drop shadow effect
        if shadow_color and self._shadow_offset > 0:
            shadow = QGraphicsDropShadowEffect(self)
            shadow.setBlurRadius(self._shadow_offset * 4)
            shadow.setOffset(0, self._shadow_offset)
            shadow.setColor(QColor(shadow_color))
            self.setGraphicsEffect(shadow)

        # Inner frame for content
        layout = QVBoxLayout(self)
        layout.setContentsMargins(inner_pad, inner_pad, inner_pad, inner_pad)
        layout.setSpacing(0)
        self.inner = QFrame(self)
        self.inner.setStyleSheet("background: transparent;")
        layout.addWidget(self.inner)

    def _apply_card_style(self) -> None:
        bw = self._border_width
        border = f"{bw}px solid {self._border_color}" if bw > 0 else "none"
        self.setStyleSheet(
            f"RoundedCard {{ background-color: {self._card_bg}; "
            f"border: {border}; "
            f"border-radius: {self._radius}px; }}"
        )

    def configure_colors(
        self,
        bg: str | None = None,
        border_color: str | None = None,
        outer_bg: str | None = None,
        shadow_color: str | None = None,
    ) -> None:
        """Update colors and restyle; safe to call after theme changes."""
        if bg is not None:
            self._card_bg = bg
        if border_color is not None:
            self._border_color = border_color
        self._apply_card_style()


# ---------------------------------------------------------------------------
# ActionCard
# ---------------------------------------------------------------------------


class ActionCard(QPushButton):
    """Reusable clickable starter card with consistent spacing and theme states."""

    _TEXT_MEASURE_HEIGHT = 4096
    _MIN_HEIGHT = 72
    _H_PADDING = 18
    _V_PADDING = 16
    _ROW_SPACING = UI_SPACING["xs"]
    _SECTION_SPACING = UI_SPACING["xs"] // 2
    _AFFORDANCE_WIDTH = 18
    _RADIUS = 18

    def __init__(
        self,
        title: str,
        description: str,
        parent: QWidget | None = None,
        *,
        palette: dict,
        affordance_text: str = "▸",
    ) -> None:
        super().__init__(parent)
        self._palette = dict(palette)
        self._visual_state = "idle"

        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(self._MIN_HEIGHT)
        self.setText("")
        self.setStyleSheet(
            "QPushButton { background: transparent; border: none; padding: 0px; }"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._surface = RoundedCard(
            self,
            radius=self._RADIUS,
            bg=self._palette.get("surface_alt", "#171F29"),
            border_color=self._palette.get("border", "#2B3542"),
            inner_padding=0,
        )
        self._surface.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._surface.inner.setAttribute(Qt.WA_TransparentForMouseEvents)
        root.addWidget(self._surface)

        content = QVBoxLayout(self._surface.inner)
        content.setContentsMargins(
            self._H_PADDING,
            self._V_PADDING,
            self._H_PADDING,
            self._V_PADDING,
        )
        content.setSpacing(self._SECTION_SPACING)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(self._ROW_SPACING)
        content.addLayout(title_row)

        self._title_label = MetricAwareWrapLabel(title, self._surface.inner)
        self._title_label.setObjectName("actionCardTitle")
        self._title_label.setWordWrap(True)
        self._title_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self._title_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        title_row.addWidget(self._title_label, 1)

        self._affordance_label = QLabel(affordance_text, self._surface.inner)
        self._affordance_label.setObjectName("actionCardAffordance")
        self._affordance_label.setFixedWidth(self._AFFORDANCE_WIDTH)
        self._affordance_label.setAlignment(Qt.AlignCenter)
        self._affordance_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        title_row.addWidget(self._affordance_label, 0, Qt.AlignTop)

        self._description_label = MetricAwareWrapLabel(description, self._surface.inner)
        self._description_label.setObjectName("actionCardDescription")
        self._description_label.setWordWrap(True)
        self._description_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self._description_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        content.addWidget(self._description_label)

        self._apply_type_styles()
        self.update_palette(self._palette)

    def event(self, event: QEvent | None) -> bool:
        if event is not None and event.type() in (
            QEvent.FontChange,
            QEvent.Polish,
            QEvent.PolishRequest,
            QEvent.StyleChange,
        ) and hasattr(self, "_title_label"):
            self._sync_label_widths(self.width())
            self.updateGeometry()
        return super().event(event)

    def resizeEvent(self, event: Any) -> None:
        if hasattr(self, "_title_label"):
            self._sync_label_widths(self.width())
        super().resizeEvent(event)

    def enterEvent(self, event: Any) -> None:
        if self.isEnabled() and self._visual_state != "pressed":
            self._apply_visual_state("hover")
        super().enterEvent(event)

    def leaveEvent(self, event: Any) -> None:
        if self.isEnabled():
            self._apply_visual_state("idle")
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton and self.isEnabled():
            self._apply_visual_state("pressed")
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        super().mouseReleaseEvent(event)
        if not self.isEnabled():
            self._apply_visual_state("idle")
            return
        local_pos = event.position().toPoint()
        if self.rect().contains(local_pos):
            self._apply_visual_state("hover")
        else:
            self._apply_visual_state("idle")

    def update_palette(self, palette: dict) -> None:
        self._palette = dict(palette)
        self._apply_visual_state(self._visual_state)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        content_width, title_width = self._sync_label_widths(width)
        spacing = max(self._SECTION_SPACING, 0)
        title_height = self._wrapped_label_height(self._title_label, title_width)
        title_row_height = max(title_height, self._affordance_label.sizeHint().height())
        description_height = self._wrapped_label_height(
            self._description_label,
            content_width,
        )
        total_height = (
            self._V_PADDING
            + title_row_height
            + spacing
            + description_height
            + self._V_PADDING
        )
        return max(self._MIN_HEIGHT, total_height)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def sizeHint(self) -> QSize:
        title_hint = self._title_label.sizeHint()
        description_hint = self._description_label.sizeHint()
        content_width = max(
            title_hint.width() + self._AFFORDANCE_WIDTH + self._ROW_SPACING,
            description_hint.width(),
            1,
        )
        width = content_width + self._H_PADDING * 2
        return QSize(width, self.heightForWidth(width))

    def _apply_type_styles(self) -> None:
        self._title_label.setStyleSheet(
            "background: transparent; font-size: 14px; font-weight: 600;"
        )
        self._description_label.setStyleSheet(
            "background: transparent; font-size: 13px;"
        )
        self._affordance_label.setStyleSheet(
            "background: transparent; font-size: 14px; font-weight: 700;"
        )

    def _resolved_width(self, width: int) -> int:
        if width > 0:
            return width
        if self.width() > 0:
            return self.width()
        return max(QPushButton.sizeHint(self).width(), 1)

    def _content_width_for_button_width(self, width: int) -> int:
        return max(1, self._resolved_width(width) - self._H_PADDING * 2)

    def _title_width_for_content_width(self, content_width: int) -> int:
        return max(1, content_width - self._AFFORDANCE_WIDTH - self._ROW_SPACING)

    def _sync_label_widths(self, width: int) -> tuple[int, int]:
        content_width = self._content_width_for_button_width(width)
        title_width = self._title_width_for_content_width(content_width)
        self._title_label.setMaximumWidth(title_width)
        self._description_label.setMaximumWidth(content_width)
        self._title_label.updateGeometry()
        self._description_label.updateGeometry()
        return content_width, title_width

    def _wrapped_label_height(self, label: QLabel, width: int) -> int:
        height = label.heightForWidth(width)
        if height > 0:
            return height
        text_rect = label.fontMetrics().boundingRect(
            QRect(0, 0, width, self._TEXT_MEASURE_HEIGHT),
            int(Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop),
            label.text(),
        )
        return max(1, text_rect.height())

    def _apply_visual_state(self, state: str) -> None:
        self._visual_state = state
        state_colors = self._colors_for_state(state)
        self._surface.configure_colors(
            bg=state_colors["bg"],
            border_color=state_colors["border"],
        )
        self._title_label.setStyleSheet(
            "background: transparent; "
            f"color: {state_colors['title']}; "
            "font-size: 14px; font-weight: 600;"
        )
        self._description_label.setStyleSheet(
            "background: transparent; "
            f"color: {state_colors['description']}; "
            "font-size: 13px;"
        )
        self._affordance_label.setStyleSheet(
            "background: transparent; "
            f"color: {state_colors['affordance']}; "
            "font-size: 14px; font-weight: 700;"
        )

    def _colors_for_state(self, state: str) -> dict[str, str]:
        palette = self._palette
        primary = palette.get("primary", "#45C2FF")
        pressed_border = palette.get("primary_pressed", primary)
        colors = {
            "idle": {
                "bg": palette.get("surface_alt", "#171F29"),
                "border": palette.get("border", "#2B3542"),
                "title": palette.get("text", "#F6FAFD"),
                "description": palette.get("muted_text", "#95A2B3"),
                "affordance": palette.get("muted_text", "#95A2B3"),
            },
            "hover": {
                "bg": palette.get("nav_hover_bg", "#1D2632"),
                "border": primary,
                "title": palette.get("text", "#F6FAFD"),
                "description": palette.get("muted_text", "#95A2B3"),
                "affordance": primary,
            },
            "pressed": {
                "bg": palette.get("nav_active_bg", "#202D3D"),
                "border": pressed_border,
                "title": palette.get("text", "#F6FAFD"),
                "description": palette.get("muted_text", "#95A2B3"),
                "affordance": primary,
            },
        }
        return colors.get(state, colors["idle"])


# ---------------------------------------------------------------------------
# TooltipManager
# ---------------------------------------------------------------------------


class _TooltipEventFilter(QObject):
    """Event filter that intercepts hover/destroy events for tooltip management."""

    def __init__(self, manager: TooltipManager) -> None:
        super().__init__()
        self._manager = manager

    def eventFilter(self, obj: QObject, event: Any) -> bool:
        from PySide6.QtCore import QEvent

        t = event.type()
        if t == QEvent.Enter:
            self._manager._on_enter(obj, event)
        elif t == QEvent.Leave:
            self._manager._on_leave(obj)
        elif t == QEvent.HoverMove:
            self._manager._on_motion(obj, event)
        elif t == QEvent.Destroy:
            self._manager._on_destroy(obj)
        return False


class TooltipManager:
    """Hover tooltips with fade-in animation.

    Parameters
    ----------
    parent_widget : the root QWidget
    get_palette   : callable returning the active palette dict (for live theming)
    delay_ms      : hover delay before tooltip appears
    wrap_px       : maximum tooltip width in pixels
    fade_ms       : fade-in duration (defaults to STYLE_CONFIG animation setting)
    """

    def __init__(
        self,
        parent_widget: QWidget,
        get_palette: Callable[[], dict],
        *,
        delay_ms: int = 350,
        wrap_px: int = 340,
        fade_ms: int | None = None,
    ) -> None:
        self._parent = parent_widget
        self.get_palette = get_palette
        self.delay_ms = delay_ms
        self.wrap_px = wrap_px
        if fade_ms is None:
            fade_ms = STYLE_CONFIG.get("animation", {}).get("tooltip_fade_ms", 150)
        self.fade_ms = max(1, int(fade_ms))
        self._widget_text: dict[int, str] = {}  # id(widget) -> text
        self._widget_refs: dict[int, QWidget] = {}  # id(widget) -> widget
        self._tooltip_widget: QWidget | None = None
        self._tooltip_label: QLabel | None = None
        self._active_widget_id: int | None = None
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._show_tooltip)
        self._fade_anim: QPropertyAnimation | None = None
        self._last_pointer = (0, 0)
        self._event_filter = _TooltipEventFilter(self)

    def register(self, widget: QWidget, text: str) -> None:
        if widget is None:
            return
        message = (text or "").strip()
        if not message:
            return
        wid = id(widget)
        self._widget_text[wid] = message
        self._widget_refs[wid] = widget
        widget.setAttribute(Qt.WA_Hover, True)
        widget.installEventFilter(self._event_filter)

    def hide(self) -> None:
        self._timer.stop()
        if self._fade_anim is not None:
            self._fade_anim.stop()
        self._active_widget_id = None
        if self._tooltip_widget is not None:
            self._tooltip_widget.hide()

    def _on_enter(self, widget: QObject, event: Any) -> None:
        wid = id(widget)
        self._active_widget_id = wid
        try:
            self._last_pointer = (event.globalPosition().x(), event.globalPosition().y())
        except AttributeError:
            self._last_pointer = (0, 0)
        self._timer.start(self.delay_ms)

    def _on_leave(self, widget: QObject) -> None:
        if id(widget) == self._active_widget_id:
            self.hide()

    def _on_motion(self, widget: QObject, event: Any) -> None:
        try:
            self._last_pointer = (event.globalPosition().x(), event.globalPosition().y())
        except AttributeError:
            pass
        if id(widget) == self._active_widget_id and self._tooltip_widget is not None and self._tooltip_widget.isVisible():
            self._position_window(*self._last_pointer)

    def _on_destroy(self, widget: QObject) -> None:
        wid = id(widget)
        self._widget_text.pop(wid, None)
        self._widget_refs.pop(wid, None)
        if wid == self._active_widget_id:
            self.hide()

    def _show_tooltip(self) -> None:
        if self._active_widget_id is None:
            return
        text = self._widget_text.get(self._active_widget_id, "").strip()
        if not text:
            return
        widget = self._widget_refs.get(self._active_widget_id)
        if widget is None:
            return

        if self._tooltip_widget is None:
            self._create_tooltip_widget()

        palette = self.get_palette() or STYLE_CONFIG["themes"].get("space_dust", {})
        bg = _pal(palette, "surface_alt", fallback_key="surface", default="#161B22")
        fg = _pal(palette, "text", default="#E8EEF8")
        border = _pal(palette, "border", default="#2A3A4F")

        self._tooltip_widget.setStyleSheet(
            f"background-color: {bg}; color: {fg}; border: 1px solid {border}; "
            f"border-radius: 6px; padding: 7px 10px;"
        )
        self._tooltip_label.setText(text)
        self._tooltip_label.setWordWrap(True)
        self._tooltip_label.setMaximumWidth(self.wrap_px)
        self._tooltip_widget.adjustSize()
        self._position_window(*self._last_pointer)
        self._tooltip_widget.show()
        self._fade_in()

    def _create_tooltip_widget(self) -> None:
        self._tooltip_widget = QWidget(None, Qt.ToolTip | Qt.FramelessWindowHint)
        self._tooltip_widget.setAttribute(Qt.WA_TranslucentBackground, False)
        layout = QVBoxLayout(self._tooltip_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        self._tooltip_label = QLabel(self._tooltip_widget)
        self._tooltip_label.setFont(QFont("Segoe UI", 9))
        layout.addWidget(self._tooltip_label)

    def _position_window(self, x_root: float, y_root: float) -> None:
        if self._tooltip_widget is None:
            return
        self._tooltip_widget.adjustSize()
        tip_w = self._tooltip_widget.width()
        tip_h = self._tooltip_widget.height()
        screen = self._parent.screen()
        if screen is None:
            return
        screen_rect = screen.availableGeometry()
        x = min(max(int(x_root) + 16, 4), max(4, screen_rect.width() - tip_w - 4))
        y = int(y_root) + 20
        if y + tip_h > screen_rect.height() - 4:
            y = int(y_root) - tip_h - 14
        y = min(max(y, 4), max(4, screen_rect.height() - tip_h - 4))
        self._tooltip_widget.move(x, y)

    def _fade_in(self) -> None:
        if self._tooltip_widget is None:
            return
        self._tooltip_widget.setWindowOpacity(0.0)
        self._fade_anim = QPropertyAnimation(self._tooltip_widget, b"windowOpacity")
        self._fade_anim.setDuration(self.fade_ms)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(0.97)
        self._fade_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._fade_anim.start()
