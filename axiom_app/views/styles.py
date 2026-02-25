"""axiom_app.views.styles — Design tokens and ttk theme application.

Extracted verbatim from agentic_rag_gui.py (STYLE_CONFIG, UI_SPACING, _pal helper)
and adapted into standalone functions that the MVC AppView can call without coupling
to the monolithic AgenticRAGApp class.

Public API
----------
STYLE_CONFIG  : dict  — fonts, palettes (space_dust / light / dark), animation timings
UI_SPACING    : dict  — xs/s/m/l/xl/xxl pixel constants
get_palette(name) -> dict
resolve_fonts(root) -> dict
apply_ttk_theme(root, palette, fonts) -> None
"""

from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

# ---------------------------------------------------------------------------
# Design tokens
# ---------------------------------------------------------------------------

STYLE_CONFIG: dict = {
    "font_family": "SF Pro Text",
    "fallback_font": "Segoe UI",
    "mono_font": "SF Mono",
    "fallback_mono_font": "Consolas",
    "radius": 12,
    "radius_sm": 6,
    "radius_lg": 16,
    "padding": {"sm": 12, "md": 16, "lg": 24},
    "type_scale": {
        "h1": {"size": 24, "weight": "bold"},
        "h2": {"size": 18, "weight": "bold"},
        "h3": {"size": 15, "weight": "bold"},
        "body": {"size": 13, "weight": "normal"},
        "body_bold": {"size": 13, "weight": "bold"},
        "caption": {"size": 11, "weight": "normal"},
        "code": {"size": 11, "weight": "normal"},
        "overline": {"size": 10, "weight": "bold"},
    },
    "animation": {
        "collapse_duration_ms": 180,
        "tooltip_fade_ms": 120,
        "theme_fade_ms": 220,
        "message_fade_ms": 80,
        "progress_pulse_ms": 40,
    },
    "themes": {
        "space_dust": {
            "bg": "#090E15",
            "surface": "#111827",
            "surface_elevated": "#1A2535",
            "surface_alt": "#1E2D42",
            "sidebar_bg": "#0D1520",
            "content_bg": "#141E2D",
            "text": "#EAF0FF",
            "muted_text": "#8A9DC0",
            "primary": "#4D9EFF",
            "primary_hover": "#70B5FF",
            "primary_pressed": "#2E80E8",
            "secondary": "#2E7ED4",
            "tertiary": "#7B8FFF",
            "border": "#1D2E45",
            "outline": "#2A3E58",
            "status": "#A0B8D8",
            "danger": "#FF6B7A",
            "danger_hover": "#FF8A96",
            "success": "#3ECFA0",
            "success_hover": "#5EDBB5",
            "warning": "#F0B84A",
            "selection_bg": "#1F3F66",
            "selection_fg": "#EAF0FF",
            "chat_user_bg": "#13304F",
            "chat_agent_bg": "#141E2D",
            "chat_system_bg": "#252515",
            "input_bg": "#07101A",
            "badge_bg": "#162438",
            "stripe_alt": "#0D1725",
            "focus_ring": "#70B5FF",
            "tab_indicator": "#4D9EFF",
            "progress_pulse": "#7DC5FF",
            "link": "#6BD4FF",
            "source": "#6A7F9E",
            "supporting_bg": "#18405E",
            "nav_hover_bg": "#1A2B40",
            "sidebar_border": "#142030",
            "chat_user_border": "#1D4674",
            "chat_agent_border": "#1D2E45",
        },
        "light": {
            "bg": "#F3F6FB",
            "surface": "#FFFFFF",
            "surface_elevated": "#EDF1F7",
            "surface_alt": "#E6EBF4",
            "sidebar_bg": "#E4EAF4",
            "content_bg": "#FAFCFF",
            "text": "#0D1117",
            "muted_text": "#4A5568",
            "primary": "#0868D5",
            "primary_hover": "#1478E6",
            "primary_pressed": "#0556B5",
            "secondary": "#2563C8",
            "tertiary": "#5457C2",
            "border": "#D0D8E8",
            "outline": "#BCC5D8",
            "status": "#2A3248",
            "danger": "#C0373B",
            "danger_hover": "#D44A4E",
            "success": "#1C7A45",
            "success_hover": "#248D52",
            "warning": "#8A5C00",
            "selection_bg": "#C5DCFF",
            "selection_fg": "#0D1117",
            "chat_user_bg": "#D5E8FF",
            "chat_agent_bg": "#EEF2FA",
            "chat_system_bg": "#FFFAE6",
            "input_bg": "#FFFFFF",
            "badge_bg": "#DDE5F2",
            "stripe_alt": "#F7FAFD",
            "focus_ring": "#1F7AEA",
            "tab_indicator": "#0868D5",
            "progress_pulse": "#5CA0F0",
            "link": "#0A52A0",
            "source": "#58677E",
            "supporting_bg": "#FFF1C8",
            "nav_hover_bg": "#D8E3F2",
            "sidebar_border": "#CBD5E8",
            "chat_user_border": "#A8CCFF",
            "chat_agent_border": "#D0D8E8",
        },
        "dark": {
            "bg": "#0A0F18",
            "surface": "#131B27",
            "surface_elevated": "#1C2638",
            "surface_alt": "#222E42",
            "sidebar_bg": "#0F1A2A",
            "content_bg": "#161F30",
            "text": "#F0F4FF",
            "muted_text": "#8DA3C0",
            "primary": "#4D9EFF",
            "primary_hover": "#70B5FF",
            "primary_pressed": "#2E80E8",
            "secondary": "#3EA8D5",
            "tertiary": "#8C95F2",
            "border": "#1E2E44",
            "outline": "#28405C",
            "status": "#BFC8DA",
            "danger": "#FF7A7A",
            "danger_hover": "#FF9A9A",
            "success": "#55C990",
            "success_hover": "#70D8A5",
            "warning": "#D9A820",
            "selection_bg": "#1E3B5E",
            "selection_fg": "#F0F4FF",
            "chat_user_bg": "#163556",
            "chat_agent_bg": "#161F30",
            "chat_system_bg": "#25250F",
            "input_bg": "#070D18",
            "badge_bg": "#1A2A3E",
            "stripe_alt": "#0C1520",
            "focus_ring": "#70B5FF",
            "tab_indicator": "#4D9EFF",
            "progress_pulse": "#7DC5FF",
            "link": "#7ADAFF",
            "source": "#8095B2",
            "supporting_bg": "#1D3E5A",
            "nav_hover_bg": "#1C2E44",
            "sidebar_border": "#102030",
            "chat_user_border": "#1D4270",
            "chat_agent_border": "#1E2E44",
        },
    },
}

UI_SPACING: dict[str, int] = {"xs": 6, "s": 10, "m": 15, "l": 22, "xl": 30, "xxl": 40}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pal(palette: dict, key: str, fallback_key: str | None = None, default=None):
    """Look up *key* in *palette* with optional fallback key and default."""
    if not isinstance(palette, dict):
        return default
    if key in palette:
        return palette[key]
    if fallback_key is not None:
        return palette.get(fallback_key, default)
    return default


def get_palette(name: str = "space_dust") -> dict:
    """Return a merged palette (always based on space_dust as the base)."""
    base = STYLE_CONFIG["themes"]["space_dust"]
    selected = STYLE_CONFIG["themes"].get(name, base)
    return {**base, **selected}


# ---------------------------------------------------------------------------
# Font resolution
# ---------------------------------------------------------------------------


def resolve_fonts(root: tk.Misc | None = None) -> dict:  # noqa: ARG001
    """Return a font dict keyed by type-scale names.

    Picks the best available font families from the system's installed fonts.
    ``root`` is accepted but unused — tkfont.families() works without a live Tk root
    as long as Tk is initialised.
    """
    try:
        families = set(tkfont.families())
    except Exception:
        families = set()

    base_family = (
        STYLE_CONFIG["font_family"]
        if STYLE_CONFIG["font_family"] in families
        else STYLE_CONFIG["fallback_font"]
    )

    mono_candidates = (
        STYLE_CONFIG.get("mono_font", "SF Mono"),
        STYLE_CONFIG.get("fallback_mono_font", "Consolas"),
        "Cascadia Code",
        "Menlo",
        "Courier New",
        "TkFixedFont",
    )
    code_family = next(
        (f for f in mono_candidates if f in families), base_family
    )

    type_scale = STYLE_CONFIG.get("type_scale", {})

    def _font_for(name: str, family: str) -> tuple:
        spec = type_scale.get(name, {})
        if not isinstance(spec, dict):
            spec = {}
        size = int(spec.get("size", 10))
        weight = str(spec.get("weight", "normal") or "normal").strip().lower()
        if weight == "bold":
            return (family, size, "bold")
        return (family, size)

    return {
        "h1":        _font_for("h1",        base_family),
        "h2":        _font_for("h2",        base_family),
        "h3":        _font_for("h3",        base_family),
        "body":      _font_for("body",      base_family),
        "body_bold": _font_for("body_bold", base_family),
        "caption":   _font_for("caption",   base_family),
        "code":      _font_for("code",      code_family),
        "overline":  _font_for("overline",  base_family),
    }


# ---------------------------------------------------------------------------
# TTK theme application
# ---------------------------------------------------------------------------


def apply_ttk_theme(root: tk.Tk, palette: dict, fonts: dict) -> None:
    """Configure all ttk style names using *palette* and *fonts*.

    Mirrors AgenticRAGApp._apply_ttk_theme() but as a free function so
    AppView can call it without inheritance from the monolith.
    """
    def get(key, fallback=None, default=None):
        value = palette.get(key)
        if value is not None:
            return value
        if isinstance(fallback, str) and fallback in palette:
            fv = palette.get(fallback)
            if fv is not None:
                return fv
        elif fallback is not None:
            return fallback
        if default is not None:
            return default
        return STYLE_CONFIG["themes"].get("space_dust", {}).get(key)

    style = ttk.Style()
    if "clam" in style.theme_names():
        style.theme_use("clam")

    root.configure(bg=palette["bg"])

    style.configure(".", background=palette["bg"], foreground=palette["text"],
                    fieldbackground=palette["surface_alt"])
    style.configure("TFrame", background=palette["bg"], borderwidth=0, relief="flat")
    style.configure("Card.TFrame", background=palette["surface"], borderwidth=0, relief="flat")
    style.configure("Sidebar.TFrame",
                    background=get("sidebar_bg", fallback="surface_alt",
                                   default=palette["surface_alt"]),
                    borderwidth=0, relief="flat")
    style.configure("MainContent.TFrame",
                    background=get("content_bg", fallback="surface",
                                   default=palette["surface"]),
                    borderwidth=0, relief="flat")
    style.configure("Card.Elevated.TFrame", background=palette["surface"],
                    borderwidth=1, bordercolor=palette["outline"], relief="flat")
    style.configure("Card.Flat.TFrame", background=palette["surface_alt"],
                    borderwidth=0, relief="flat")
    style.configure("StatusBar.TFrame", background=palette["surface"],
                    borderwidth=0, relief="flat")
    style.configure("CollapsibleHeader.TFrame", background=palette["surface"],
                    borderwidth=0, relief="flat")

    style.configure("TLabelframe", background=palette["surface"],
                    bordercolor=palette["outline"], borderwidth=1, relief="flat",
                    padding=(12, 10))
    style.configure("TLabelframe.Label", background=palette["surface"],
                    foreground=palette["primary"], font=fonts["body_bold"])

    style.configure("TLabel",
                    background=get("content_bg", fallback="surface",
                                   default=palette["surface"]),
                    foreground=palette["text"], font=fonts["body"])
    style.configure("Bold.TLabel", background=palette["surface"],
                    foreground=palette["text"], font=fonts["body_bold"])
    style.configure("Header.TLabel",
                    background=get("sidebar_bg", fallback="surface_alt",
                                   default=palette["surface_alt"]),
                    foreground=palette["text"], font=fonts["h2"])
    style.configure("Title.TLabel", background=palette["surface"],
                    foreground=palette["text"], font=fonts["h1"])
    style.configure("Muted.TLabel", background=palette["surface"],
                    foreground=palette["muted_text"], font=fonts["body"])
    style.configure("Caption.TLabel", background=palette["surface"],
                    foreground=palette["muted_text"], font=fonts["caption"])
    style.configure("Overline.TLabel", background=palette["surface"],
                    foreground=palette["muted_text"], font=fonts["overline"])
    style.configure("Code.TLabel", background=palette["surface"],
                    foreground=palette["source"], font=fonts["code"])
    style.configure("Danger.TLabel", background=palette["surface"],
                    foreground=palette["danger"], font=fonts["body_bold"])
    style.configure("Success.TLabel", background=palette["surface"],
                    foreground=palette["success"], font=fonts["body_bold"])
    style.configure("Warning.TLabel", background=palette["surface"],
                    foreground=palette["tertiary"], font=fonts["body_bold"])
    style.configure("Status.TLabel", background=palette["surface"],
                    foreground=palette["status"], font=fonts["caption"])
    style.configure("Badge.TLabel",
                    background=get("badge_bg", fallback="surface_alt",
                                   default=palette["surface_alt"]),
                    foreground=palette["primary"], font=fonts["caption"],
                    padding=(12, 5), relief="flat")
    style.configure("CollapsibleArrow.TLabel", background=palette["surface"],
                    foreground=palette["muted_text"], font=fonts["body_bold"])
    style.configure("CollapsibleTitle.TLabel", background=palette["surface"],
                    foreground=palette["text"], font=fonts["body_bold"])

    # Sidebar-specific labels
    _sidebar_bg = get("sidebar_bg", fallback="surface_alt", default=palette["surface_alt"])
    _sidebar_hover = _pal(palette, "nav_hover_bg", fallback_key="surface_elevated",
                           default=palette["surface_elevated"])
    style.configure("Sidebar.Title.TLabel", background=_sidebar_bg,
                    foreground=palette["text"], font=fonts["h2"])
    style.configure("Sidebar.Caption.TLabel", background=_sidebar_bg,
                    foreground=palette["muted_text"], font=fonts["caption"])

    # Buttons
    style.configure("TButton", padding=(14, 9), relief="flat", borderwidth=0,
                    background=palette["surface_alt"], foreground=palette["text"],
                    focuscolor=palette["surface_alt"])
    style.map("TButton",
              background=[("active", _sidebar_hover), ("pressed", palette["outline"])],
              foreground=[("active", palette["text"])])
    style.configure("Primary.TButton", padding=(16, 9), relief="flat", borderwidth=0,
                    background=palette["primary"], foreground="#FFFFFF")
    style.map("Primary.TButton",
              background=[("active", _pal(palette, "primary_hover",
                                          fallback_key="primary", default="#70B5FF")),
                          ("pressed", _pal(palette, "primary_pressed",
                                           fallback_key="primary", default="#2E80E8")),
                          ("disabled", palette["outline"])],
              foreground=[("active", "#FFFFFF"), ("disabled", palette["muted_text"])])
    style.configure("Secondary.TButton", padding=(14, 9), relief="flat", borderwidth=0,
                    background=palette["surface_alt"], foreground=palette["text"])
    style.map("Secondary.TButton",
              background=[("active", _sidebar_hover),
                          ("pressed", palette["outline"]),
                          ("disabled", palette["surface_alt"])],
              foreground=[("active", palette["text"]),
                          ("disabled", palette["muted_text"])])
    style.configure("Danger.TButton", padding=(14, 9), relief="flat", borderwidth=0,
                    background=palette["danger"], foreground="#FFFFFF")
    style.map("Danger.TButton",
              background=[("active", _pal(palette, "danger_hover",
                                          fallback_key="danger", default="#FF5555")),
                          ("disabled", palette["outline"])],
              foreground=[("active", "#FFFFFF"), ("disabled", palette["muted_text"])])
    style.configure("Sidebar.TButton", padding=(14, 11), relief="flat", borderwidth=0,
                    background=_sidebar_bg, foreground=palette["muted_text"],
                    anchor="w", font=fonts["body"])
    style.map("Sidebar.TButton",
              background=[("active", _sidebar_hover), ("pressed", _sidebar_hover)],
              foreground=[("active", palette["text"]), ("pressed", palette["text"])])
    style.configure("Sidebar.Active.TButton", padding=(14, 11), relief="flat", borderwidth=0,
                    background=_sidebar_hover, foreground=palette["primary"],
                    anchor="w", font=fonts["body_bold"])
    style.map("Sidebar.Active.TButton",
              background=[("active", _sidebar_hover), ("pressed", _sidebar_hover)],
              foreground=[("active", palette["primary"]), ("pressed", palette["primary"])])

    # Checkbutton / Radiobutton
    style.configure("TCheckbutton", background=palette["surface"],
                    foreground=palette["text"], indicatorcolor=palette["surface_alt"],
                    relief="flat")
    style.map("TCheckbutton",
              background=[("active", palette["surface"]), ("!active", palette["surface"])],
              foreground=[("active", palette["text"]), ("disabled", palette["muted_text"])],
              indicatorcolor=[("selected", palette["primary"]),
                              ("!selected", palette["surface_alt"])])

    # Entry / Combobox
    _input_bg = _pal(palette, "input_bg", fallback_key="surface_alt",
                     default=palette["surface_alt"])
    style.configure("TEntry", fieldbackground=_input_bg, foreground=palette["text"],
                    bordercolor=palette["outline"], insertcolor=palette["primary"],
                    borderwidth=1, relief="flat", padding=(10, 8))
    style.map("TEntry", bordercolor=[("focus", palette["primary"])])
    style.configure("TCombobox", fieldbackground=_input_bg, background=_input_bg,
                    foreground=palette["text"], arrowcolor=palette["muted_text"],
                    bordercolor=palette["outline"], relief="flat",
                    insertcolor=palette["primary"], padding=(10, 8))
    style.map("TCombobox",
              fieldbackground=[("readonly", _input_bg)],
              selectbackground=[("readonly", palette["selection_bg"])],
              selectforeground=[("readonly", palette["selection_fg"])],
              foreground=[("readonly", palette["text"])])

    # Fix TCombobox popup listbox colors (plain tk.Listbox bypasses ttk)
    root.option_add("*TCombobox*Listbox.background", _input_bg)
    root.option_add("*TCombobox*Listbox.foreground", palette["text"])
    root.option_add("*TCombobox*Listbox.selectBackground", palette["selection_bg"])
    root.option_add("*TCombobox*Listbox.selectForeground", palette["selection_fg"])
    root.option_add("*TCombobox*Listbox.relief", "flat")
    root.option_add("*TCombobox*Listbox.borderWidth", "0")

    # Treeview
    style.configure("Treeview", background=palette["surface"],
                    fieldbackground=palette["surface"], foreground=palette["text"],
                    bordercolor=palette["border"], borderwidth=0, rowheight=34,
                    relief="flat")
    style.map("Treeview",
              background=[("selected", palette["selection_bg"]),
                          ("active", palette["surface_alt"])],
              foreground=[("selected", palette["selection_fg"]),
                          ("active", palette["text"])])
    style.configure("Treeview.Heading", background=palette["surface_elevated"],
                    foreground=palette["muted_text"], borderwidth=0, relief="flat",
                    font=fonts["caption"], padding=(8, 6))
    style.map("Treeview.Heading",
              background=[("active", palette["surface_alt"])],
              foreground=[("active", palette["text"])])

    # Scrollbars
    style.configure("Vertical.TScrollbar", background=palette["surface_alt"],
                    troughcolor=palette["bg"], bordercolor=palette["bg"],
                    arrowcolor=palette["surface_alt"], relief="flat", width=6, arrowsize=0)
    style.map("Vertical.TScrollbar",
              background=[("active", palette["outline"]),
                          ("!active", _pal(palette, "border",
                                           fallback_key="surface_alt",
                                           default=palette["surface_alt"]))])
    style.configure("Horizontal.TScrollbar", background=palette["surface_alt"],
                    troughcolor=palette["bg"], bordercolor=palette["bg"],
                    arrowcolor=palette["surface_alt"], relief="flat", width=6, arrowsize=0)
    style.map("Horizontal.TScrollbar",
              background=[("active", palette["outline"]),
                          ("!active", _pal(palette, "border",
                                           fallback_key="surface_alt",
                                           default=palette["surface_alt"]))])

    # Progress bar
    style.configure("TProgressbar", troughcolor=palette["surface_alt"],
                    background=palette["primary"], bordercolor=palette["bg"],
                    lightcolor=_pal(palette, "primary_hover",
                                    fallback_key="primary", default=palette["primary"]),
                    darkcolor=palette["primary"], relief="flat")

    # Separator
    style.configure("TSeparator", background=palette["border"])
