"""axiom_app.views.styles — Shared design tokens and QSS theme configuration.

Provides:
  * STYLE_CONFIG  — master design-token dictionary (palettes, type scale, radii, animation timings)
  * UI_SPACING    — semantic spacing scale (xs … xxl)
  * get_palette() — return a complete colour palette by name
  * resolve_fonts()  — return QFont objects keyed by type-scale name
  * generate_qss()   — produce a complete Qt Style Sheet for the active palette
  * apply_theme_to_app() — apply QSS + QPalette to a QApplication
"""

from __future__ import annotations

from PySide6.QtGui import QFont, QFontDatabase, QPalette, QColor
from PySide6.QtWidgets import QApplication


STYLE_CONFIG: dict = {
    "font_family": "Aptos",
    "fallback_font": "Segoe UI",
    "mono_font": "Cascadia Code",
    "fallback_mono_font": "Consolas",
    "radius": 18,
    "radius_sm": 10,
    "radius_lg": 28,
    "padding": {"sm": 12, "md": 20, "lg": 32},
    "type_scale": {
        "h1": {"size": 34, "weight": "bold"},
        "h2": {"size": 24, "weight": "bold"},
        "h3": {"size": 18, "weight": "bold"},
        "body": {"size": 13, "weight": "normal"},
        "body_bold": {"size": 13, "weight": "bold"},
        "caption": {"size": 11, "weight": "normal"},
        "code": {"size": 11, "weight": "normal"},
        "overline": {"size": 11, "weight": "bold"},
    },
    "animation": {
        "collapse_duration_ms": 180,
        "tooltip_fade_ms": 120,
        "theme_fade_ms": 220,
        "message_fade_ms": 80,
        "progress_pulse_ms": 40,
    },
    "themes": {
        "light": {
            "app_bg": "#EAF3F8",
            "bg": "#EAF3F8",
            "workspace_bg": "#FAFDFF",
            "workspace_border": "#CFE2F0",
            "workspace_shadow": "#DDEBF4",
            "surface": "#FFFFFF",
            "surface_elevated": "#F7FBFE",
            "surface_alt": "#ECF5FB",
            "sidebar_bg": "#F7FBFE",
            "content_bg": "#FAFDFF",
            "text": "#08131D",
            "muted_text": "#597089",
            "primary": "#1198E8",
            "primary_hover": "#27A9F8",
            "primary_pressed": "#0B7FC5",
            "secondary": "#082033",
            "tertiary": "#51C6FF",
            "border": "#D5E6F2",
            "outline": "#A6C7DA",
            "status": "#476076",
            "danger": "#D85C66",
            "danger_hover": "#E2707A",
            "success": "#2E9875",
            "success_hover": "#42AD88",
            "warning": "#B57C21",
            "selection_bg": "#D5EFFC",
            "selection_fg": "#08131D",
            "chat_user_bg": "#E5F5FF",
            "chat_agent_bg": "#FFFFFF",
            "chat_system_bg": "#F1F8FD",
            "input_bg": "#F8FCFF",
            "badge_bg": "#EAF5FD",
            "stripe_alt": "#F4FAFD",
            "focus_ring": "#1198E8",
            "tab_indicator": "#1198E8",
            "progress_pulse": "#63CCFF",
            "link": "#0C82D0",
            "source": "#58728B",
            "supporting_bg": "#F0F8FD",
            "nav_hover_bg": "#ECF5FB",
            "nav_active_bg": "#DFF0FB",
            "sidebar_border": "#D7E8F4",
            "chat_user_border": "#BAE2F8",
            "chat_agent_border": "#D5E6F2",
            "accent_glow": "#CFEFFF",
        },
        "dark": {
            "app_bg": "#050A11",
            "bg": "#050A11",
            "workspace_bg": "#08131D",
            "workspace_border": "#16324A",
            "workspace_shadow": "#01050A",
            "surface": "#0C1825",
            "surface_elevated": "#112132",
            "surface_alt": "#14283A",
            "sidebar_bg": "#07111A",
            "content_bg": "#08131D",
            "text": "#EAF6FF",
            "muted_text": "#91A8BD",
            "primary": "#35B7FF",
            "primary_hover": "#5AC9FF",
            "primary_pressed": "#1796E0",
            "secondary": "#DDF4FF",
            "tertiary": "#8FE7FF",
            "border": "#17344C",
            "outline": "#235476",
            "status": "#A2B8CC",
            "danger": "#F06C7A",
            "danger_hover": "#FF8793",
            "success": "#37A887",
            "success_hover": "#4EC29D",
            "warning": "#E0A95A",
            "selection_bg": "#143754",
            "selection_fg": "#EAF6FF",
            "chat_user_bg": "#0E2740",
            "chat_agent_bg": "#0C1825",
            "chat_system_bg": "#102233",
            "input_bg": "#0E1C2B",
            "badge_bg": "#0F2233",
            "stripe_alt": "#0B1724",
            "focus_ring": "#35B7FF",
            "tab_indicator": "#35B7FF",
            "progress_pulse": "#73DBFF",
            "link": "#82DDFF",
            "source": "#A0B9D1",
            "supporting_bg": "#0F1E2D",
            "nav_hover_bg": "#0F2133",
            "nav_active_bg": "#133353",
            "sidebar_border": "#16324A",
            "chat_user_border": "#1F4567",
            "chat_agent_border": "#17344C",
            "accent_glow": "#134A73",
        },
        "space_dust": {
            "app_bg": "#030912",
            "bg": "#030912",
            "workspace_bg": "#060F18",
            "workspace_border": "#143A59",
            "workspace_shadow": "#010408",
            "surface": "#091522",
            "surface_elevated": "#102032",
            "surface_alt": "#13283D",
            "sidebar_bg": "#050E17",
            "content_bg": "#060F18",
            "text": "#F2FAFF",
            "muted_text": "#8AA5BE",
            "primary": "#2EB7FF",
            "primary_hover": "#5DCCFF",
            "primary_pressed": "#138DD7",
            "secondary": "#D7F4FF",
            "tertiary": "#83F0FF",
            "border": "#17405F",
            "outline": "#1F5B85",
            "status": "#A4BED5",
            "danger": "#F2707D",
            "danger_hover": "#FF8B95",
            "success": "#35A886",
            "success_hover": "#49C09B",
            "warning": "#E0A94F",
            "selection_bg": "#103C5A",
            "selection_fg": "#F2FAFF",
            "chat_user_bg": "#0B2844",
            "chat_agent_bg": "#091522",
            "chat_system_bg": "#102132",
            "input_bg": "#0D1C2D",
            "badge_bg": "#0E2031",
            "stripe_alt": "#0C1826",
            "focus_ring": "#4CC8FF",
            "tab_indicator": "#2EB7FF",
            "progress_pulse": "#77DFFF",
            "link": "#8BE7FF",
            "source": "#9FBBD6",
            "supporting_bg": "#0D1D2E",
            "nav_hover_bg": "#0E2032",
            "nav_active_bg": "#113B5C",
            "sidebar_border": "#143A59",
            "chat_user_border": "#23547B",
            "chat_agent_border": "#17405F",
            "accent_glow": "#0F4D79",
        },
    },
}

UI_SPACING: dict[str, int] = {
    "xs": 8,
    "s": 12,
    "m": 18,
    "l": 28,
    "xl": 42,
    "xxl": 60,
}


def _pal(palette: dict, key: str, fallback_key: str | None = None, default=None):
    """Look up *key* in *palette* with optional fallback handling."""
    if not isinstance(palette, dict):
        return default
    if key in palette:
        return palette[key]
    if fallback_key is not None:
        return palette.get(fallback_key, default)
    return default


def get_palette(name: str = "light") -> dict:
    """Return a merged palette using the light theme as the baseline."""
    base = STYLE_CONFIG["themes"]["light"]
    selected = STYLE_CONFIG["themes"].get(name, base)
    return {**base, **selected}


def resolve_fonts() -> dict[str, QFont]:
    """Return a QFont dict keyed by the shared type-scale names."""
    available = set(QFontDatabase.families())

    base_family = (
        STYLE_CONFIG["font_family"]
        if STYLE_CONFIG["font_family"] in available
        else STYLE_CONFIG["fallback_font"]
    )

    mono_candidates = (
        STYLE_CONFIG.get("mono_font", "Cascadia Code"),
        STYLE_CONFIG.get("fallback_mono_font", "Consolas"),
        "SF Mono",
        "Courier New",
        "Monospace",
    )
    code_family = next(
        (family for family in mono_candidates if family in available),
        base_family,
    )

    type_scale = STYLE_CONFIG.get("type_scale", {})

    def _qfont(name: str, family: str) -> QFont:
        spec = type_scale.get(name, {})
        if not isinstance(spec, dict):
            spec = {}
        size = int(spec.get("size", 10))
        weight_str = str(spec.get("weight", "normal") or "normal").strip().lower()
        font = QFont(family, size)
        if weight_str == "bold":
            font.setBold(True)
        return font

    return {
        "h1": _qfont("h1", base_family),
        "h2": _qfont("h2", base_family),
        "h3": _qfont("h3", base_family),
        "body": _qfont("body", base_family),
        "body_bold": _qfont("body_bold", base_family),
        "caption": _qfont("caption", base_family),
        "code": _qfont("code", code_family),
        "overline": _qfont("overline", base_family),
    }


def generate_qss(palette: dict, fonts: dict[str, QFont]) -> str:
    """Produce a complete Qt Style Sheet string for the given palette and fonts."""

    def _get(key: str, fallback: str | None = None, default: str = "") -> str:
        val = palette.get(key)
        if val is not None:
            return val
        if fallback is not None:
            val = palette.get(fallback)
            if val is not None:
                return val
        return default or STYLE_CONFIG["themes"]["light"].get(key, "")

    app_bg = _get("app_bg", "bg")
    surface = _get("surface")
    surface_elevated = _get("surface_elevated", "surface")
    surface_alt = _get("surface_alt", "surface")
    sidebar_bg = _get("sidebar_bg", "surface")
    text = _get("text")
    muted = _get("muted_text")
    border = _get("border", default="#E5E0EA")
    outline = _get("outline", "border")
    primary = _get("primary")
    primary_hover = _get("primary_hover", "primary")
    primary_pressed = _get("primary_pressed", "primary")
    nav_hover = _get("nav_hover_bg", "surface_alt")
    nav_active = _get("nav_active_bg", "surface_alt")
    input_bg = _get("input_bg", "surface_alt")
    badge_bg = _get("badge_bg", "surface_alt")
    selection_bg = _get("selection_bg")
    selection_fg = _get("selection_fg")
    danger = _get("danger")
    success = _get("success")
    warning = _get("warning")
    workspace_bg = _get("workspace_bg", "surface")
    focus_ring = _get("focus_ring", "primary")
    tab_indicator = _get("tab_indicator", "primary")

    body_font = fonts.get("body")
    body_family = body_font.family() if body_font else "Segoe UI"
    body_size = body_font.pointSize() if body_font else 13
    caption_font = fonts.get("caption")
    caption_size = caption_font.pointSize() if caption_font else 11
    code_font = fonts.get("code")
    code_family = code_font.family() if code_font else "Consolas"
    code_size = code_font.pointSize() if code_font else 11

    r = STYLE_CONFIG["radius_sm"]

    return f"""
/* ======== BASE WIDGETS ======== */
QMainWindow, QWidget {{
    background-color: {app_bg};
    color: {text};
    font-family: "{body_family}";
    font-size: {body_size}pt;
}}

QWidget[cssClass="surface"] {{
    background-color: {surface};
}}
QWidget[cssClass="surface_elevated"] {{
    background-color: {surface_elevated};
}}
QWidget[cssClass="surface_alt"] {{
    background-color: {surface_alt};
}}
QWidget[cssClass="workspace"] {{
    background-color: {workspace_bg};
}}
QWidget[cssClass="sidebar"] {{
    background-color: {sidebar_bg};
}}
QWidget[cssClass="content"] {{
    background-color: {workspace_bg};
}}

/* ======== LABELS ======== */
QLabel {{
    background: transparent;
    color: {text};
    font-size: {body_size}pt;
}}
QLabel[cssClass="header"] {{
    font-size: {fonts.get("h2", body_font).pointSize() if fonts.get("h2") else 24}pt;
    font-weight: bold;
}}
QLabel[cssClass="title"] {{
    font-size: {fonts.get("h1", body_font).pointSize() if fonts.get("h1") else 34}pt;
    font-weight: bold;
}}
QLabel[cssClass="bold"] {{
    font-weight: bold;
}}
QLabel[cssClass="muted"] {{
    color: {muted};
}}
QLabel[cssClass="caption"] {{
    color: {muted};
    font-size: {caption_size}pt;
}}
QLabel[cssClass="overline"] {{
    color: {muted};
    font-size: {caption_size}pt;
    font-weight: bold;
    text-transform: uppercase;
}}
QLabel[cssClass="code"] {{
    color: {_get("source", "muted_text")};
    font-family: "{code_family}";
    font-size: {code_size}pt;
}}
QLabel[cssClass="status"] {{
    color: {_get("status", "muted_text")};
    font-size: {caption_size}pt;
}}
QLabel[cssClass="badge"] {{
    background-color: {badge_bg};
    color: {primary};
    font-size: {caption_size}pt;
    padding: 7px 12px;
    border-radius: {r}px;
}}
QLabel[cssClass="danger"] {{
    color: {danger};
    font-weight: bold;
}}
QLabel[cssClass="success"] {{
    color: {success};
    font-weight: bold;
}}
QLabel[cssClass="warning"] {{
    color: {warning};
    font-weight: bold;
}}

/* ======== BUTTONS ======== */
QPushButton {{
    background-color: {surface};
    color: {text};
    border: 1px solid {border};
    border-radius: {r}px;
    padding: 11px 15px;
    font-size: {body_size}pt;
}}
QPushButton:hover {{
    background-color: {surface_alt};
    border-color: {outline};
}}
QPushButton:pressed {{
    background-color: {nav_hover};
}}
QPushButton:disabled {{
    color: {muted};
    background-color: {surface};
    border-color: {border};
}}
QPushButton:focus {{
    border-color: {primary};
}}

QPushButton[cssClass="primary"] {{
    background-color: {primary};
    color: #FFFFFF;
    border: none;
    border-radius: {r}px;
    padding: 11px 17px;
    font-weight: bold;
}}
QPushButton[cssClass="primary"]:hover {{
    background-color: {primary_hover};
}}
QPushButton[cssClass="primary"]:pressed {{
    background-color: {primary_pressed};
}}
QPushButton[cssClass="primary"]:disabled {{
    background-color: {outline};
    color: {muted};
}}

QPushButton[cssClass="secondary"] {{
    background-color: {surface};
    color: {text};
    border: 1px solid {border};
    border-radius: {r}px;
    padding: 11px 15px;
}}
QPushButton[cssClass="secondary"]:hover {{
    background-color: {surface_alt};
    border-color: {outline};
}}
QPushButton[cssClass="secondary"]:pressed {{
    background-color: {nav_hover};
}}
QPushButton[cssClass="secondary"]:disabled {{
    color: {muted};
    background-color: {surface};
}}

QPushButton[cssClass="sidebar"] {{
    background-color: {sidebar_bg};
    color: {muted};
    border: none;
    border-radius: {r}px;
    padding: 14px 12px;
    font-weight: bold;
    text-align: center;
}}
QPushButton[cssClass="sidebar"]:hover {{
    background-color: {nav_hover};
    color: {text};
}}
QPushButton[cssClass="sidebar"]:pressed {{
    background-color: {nav_hover};
    color: {text};
}}
QPushButton[cssClass="sidebar_active"] {{
    background-color: {nav_active};
    color: {primary};
    border: none;
    border-radius: {r}px;
    padding: 14px 12px;
    font-weight: bold;
    text-align: center;
}}

/* ======== INPUTS ======== */
QLineEdit {{
    background-color: {input_bg};
    color: {text};
    border: 1px solid {border};
    border-radius: {r}px;
    padding: 9px 12px;
    selection-background-color: {selection_bg};
    selection-color: {selection_fg};
}}
QLineEdit:focus {{
    border-color: {focus_ring};
}}

QTextEdit, QPlainTextEdit {{
    background-color: {input_bg};
    color: {text};
    border: 1px solid {border};
    border-radius: {r}px;
    padding: 9px 12px;
    selection-background-color: {selection_bg};
    selection-color: {selection_fg};
}}
QTextEdit:focus, QPlainTextEdit:focus {{
    border-color: {focus_ring};
}}
QTextEdit[cssClass="chat_display"] {{
    background-color: {surface};
    border: none;
    border-radius: 0px;
    padding: {UI_SPACING['m']}px;
}}
QTextEdit[cssClass="log_display"] {{
    background-color: {surface};
    color: {muted};
    border: none;
    font-family: "{code_family}";
    font-size: {code_size}pt;
}}

/* ======== COMBOBOX ======== */
QComboBox {{
    background-color: {input_bg};
    color: {text};
    border: 1px solid {border};
    border-radius: {r}px;
    padding: 9px 12px;
    min-width: 80px;
}}
QComboBox:focus {{
    border-color: {focus_ring};
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {muted};
    margin-right: 8px;
}}
QComboBox QAbstractItemView {{
    background-color: {input_bg};
    color: {text};
    border: 1px solid {border};
    selection-background-color: {selection_bg};
    selection-color: {selection_fg};
    outline: none;
}}

/* ======== CHECKBOX ======== */
QCheckBox {{
    background: transparent;
    color: {text};
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border: 1px solid {outline};
    border-radius: 4px;
    background-color: {surface_alt};
}}
QCheckBox::indicator:checked {{
    background-color: {primary};
    border-color: {primary};
}}
QCheckBox::indicator:hover {{
    border-color: {primary_hover};
}}
QCheckBox:disabled {{
    color: {muted};
}}

/* ======== TREE / LIST ======== */
QTreeWidget, QListWidget {{
    background-color: {surface};
    color: {text};
    border: none;
    outline: none;
    font-size: {body_size}pt;
}}
QTreeWidget::item, QListWidget::item {{
    padding: 6px 8px;
    border: none;
}}
QTreeWidget::item:selected, QListWidget::item:selected {{
    background-color: {selection_bg};
    color: {selection_fg};
}}
QTreeWidget::item:hover, QListWidget::item:hover {{
    background-color: {surface_alt};
}}
QHeaderView::section {{
    background-color: {surface_alt};
    color: {muted};
    border: none;
    padding: 7px 8px;
    font-size: {caption_size}pt;
}}
QHeaderView::section:hover {{
    background-color: {surface_elevated};
    color: {text};
}}

/* ======== TAB WIDGET ======== */
QTabWidget::pane {{
    background-color: {surface};
    border: none;
}}
QTabBar::tab {{
    background-color: {surface_alt};
    color: {muted};
    border: none;
    padding: 8px 14px;
    font-size: {caption_size}pt;
}}
QTabBar::tab:selected {{
    background-color: {surface};
    color: {text};
    border-bottom: 2px solid {tab_indicator};
}}
QTabBar::tab:hover {{
    background-color: {surface_elevated};
    color: {text};
}}

/* ======== SCROLLBAR ======== */
QScrollBar:vertical {{
    background-color: {surface_alt};
    width: 12px;
    border: none;
}}
QScrollBar::handle:vertical {{
    background-color: {outline};
    border-radius: 6px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background-color: {primary};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
}}
QScrollBar:horizontal {{
    background-color: {surface_alt};
    height: 12px;
    border: none;
}}
QScrollBar::handle:horizontal {{
    background-color: {outline};
    border-radius: 6px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{
    background-color: {primary};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: none;
}}

/* ======== PROGRESS BAR ======== */
QProgressBar {{
    background-color: {surface_alt};
    border: none;
    border-radius: 5px;
    text-align: center;
    color: {text};
    max-height: 10px;
}}
QProgressBar::chunk {{
    background-color: {primary};
    border-radius: 5px;
}}

/* ======== GROUP BOX ======== */
QGroupBox {{
    background-color: {surface};
    border: 1px solid {border};
    border-radius: {r}px;
    margin-top: 12px;
    padding: 12px 14px;
    font-weight: bold;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 6px;
    color: {text};
    background-color: {surface};
}}

/* ======== TOOLTIP ======== */
QToolTip {{
    background-color: {surface_alt};
    color: {text};
    border: 1px solid {border};
    padding: 7px 10px;
    font-size: {caption_size}pt;
    border-radius: 6px;
}}

/* ======== SEPARATOR ======== */
QFrame[cssClass="separator"] {{
    background-color: {border};
    max-height: 1px;
    min-height: 1px;
}}
QFrame[cssClass="v_separator"] {{
    background-color: {border};
    max-width: 1px;
    min-width: 1px;
}}

/* ======== SCROLL AREA ======== */
QScrollArea {{
    background: transparent;
    border: none;
}}
QScrollArea > QWidget > QWidget {{
    background: transparent;
}}
"""


def apply_theme_to_app(app: QApplication, palette: dict, fonts: dict[str, QFont]) -> None:
    """Apply QSS theme and QPalette to the entire application."""
    qss = generate_qss(palette, fonts)
    app.setStyleSheet(qss)

    # Also set the QPalette for widgets that don't fully respect QSS
    qt_palette = QPalette()
    text_color = QColor(palette.get("text", "#FFFFFF"))
    bg_color = QColor(palette.get("app_bg", palette.get("bg", "#000000")))
    surface_color = QColor(palette.get("surface", "#111111"))
    primary_color = QColor(palette.get("primary", "#2EB7FF"))
    selection_bg = QColor(palette.get("selection_bg", "#103C5A"))
    selection_fg = QColor(palette.get("selection_fg", "#FFFFFF"))

    qt_palette.setColor(QPalette.Window, bg_color)
    qt_palette.setColor(QPalette.WindowText, text_color)
    qt_palette.setColor(QPalette.Base, surface_color)
    qt_palette.setColor(QPalette.AlternateBase, QColor(palette.get("surface_alt", "#222222")))
    qt_palette.setColor(QPalette.Text, text_color)
    qt_palette.setColor(QPalette.Button, surface_color)
    qt_palette.setColor(QPalette.ButtonText, text_color)
    qt_palette.setColor(QPalette.Highlight, selection_bg)
    qt_palette.setColor(QPalette.HighlightedText, selection_fg)
    qt_palette.setColor(QPalette.Link, primary_color)
    qt_palette.setColor(QPalette.PlaceholderText, QColor(palette.get("muted_text", "#888888")))
    app.setPalette(qt_palette)
