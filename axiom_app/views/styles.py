"""axiom_app.views.styles — Shared design tokens and ttk theme configuration."""

from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk


STYLE_CONFIG: dict = {
    "font_family": "Aptos",
    "fallback_font": "Segoe UI",
    "mono_font": "Cascadia Code",
    "fallback_mono_font": "Consolas",
    "radius": 18,
    "radius_sm": 10,
    "radius_lg": 28,
    "padding": {"sm": 12, "md": 18, "lg": 28},
    "type_scale": {
        "h1": {"size": 31, "weight": "bold"},
        "h2": {"size": 21, "weight": "bold"},
        "h3": {"size": 15, "weight": "bold"},
        "body": {"size": 12, "weight": "normal"},
        "body_bold": {"size": 12, "weight": "bold"},
        "caption": {"size": 10, "weight": "normal"},
        "code": {"size": 10, "weight": "normal"},
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
        "light": {
            "app_bg": "#ECEAEC",
            "bg": "#ECEAEC",
            "workspace_bg": "#FFFFFF",
            "workspace_border": "#D9D4E3",
            "workspace_shadow": "#E3DEE9",
            "surface": "#FFFFFF",
            "surface_elevated": "#FBFAFD",
            "surface_alt": "#F4F1F8",
            "sidebar_bg": "#FFFFFF",
            "content_bg": "#FFFFFF",
            "text": "#17141F",
            "muted_text": "#706A7C",
            "primary": "#8C5AF7",
            "primary_hover": "#9F72FF",
            "primary_pressed": "#7345DD",
            "secondary": "#272332",
            "tertiary": "#B78EFF",
            "border": "#E5E0EA",
            "outline": "#D6D0E0",
            "status": "#5E576B",
            "danger": "#D05263",
            "danger_hover": "#DD6A79",
            "success": "#2F8A68",
            "success_hover": "#42A07C",
            "warning": "#A06A14",
            "selection_bg": "#E5D7FF",
            "selection_fg": "#17141F",
            "chat_user_bg": "#F1EAFE",
            "chat_agent_bg": "#FFFFFF",
            "chat_system_bg": "#F8F5FC",
            "input_bg": "#FBFAFD",
            "badge_bg": "#F4F1F8",
            "stripe_alt": "#F8F6FB",
            "focus_ring": "#8C5AF7",
            "tab_indicator": "#8C5AF7",
            "progress_pulse": "#B38AFF",
            "link": "#8452F2",
            "source": "#6B6478",
            "supporting_bg": "#F7F4FB",
            "nav_hover_bg": "#F5F2FA",
            "nav_active_bg": "#F1ECFB",
            "sidebar_border": "#E7E2EC",
            "chat_user_border": "#D9C7FF",
            "chat_agent_border": "#E5E0EA",
            "accent_glow": "#E8D9FF",
        },
        "dark": {
            "app_bg": "#1E1B24",
            "bg": "#1E1B24",
            "workspace_bg": "#24212C",
            "workspace_border": "#342F3F",
            "workspace_shadow": "#17141C",
            "surface": "#2A2633",
            "surface_elevated": "#312C3B",
            "surface_alt": "#363142",
            "sidebar_bg": "#25212D",
            "content_bg": "#24212C",
            "text": "#F4F1F8",
            "muted_text": "#B0A8BC",
            "primary": "#A87BFF",
            "primary_hover": "#BA97FF",
            "primary_pressed": "#8A5CF5",
            "secondary": "#F4F1F8",
            "tertiary": "#C9AEFF",
            "border": "#3A3447",
            "outline": "#443D52",
            "status": "#CAC2D8",
            "danger": "#EE7B88",
            "danger_hover": "#F299A4",
            "success": "#67C39A",
            "success_hover": "#81D7AE",
            "warning": "#D2A45D",
            "selection_bg": "#4A3A73",
            "selection_fg": "#F4F1F8",
            "chat_user_bg": "#3B3055",
            "chat_agent_bg": "#2A2633",
            "chat_system_bg": "#332C3A",
            "input_bg": "#312C3B",
            "badge_bg": "#363142",
            "stripe_alt": "#292531",
            "focus_ring": "#A87BFF",
            "tab_indicator": "#A87BFF",
            "progress_pulse": "#C9AEFF",
            "link": "#C9AEFF",
            "source": "#B3AAC2",
            "supporting_bg": "#322C3C",
            "nav_hover_bg": "#312C3B",
            "nav_active_bg": "#3A3247",
            "sidebar_border": "#3A3447",
            "chat_user_border": "#58457F",
            "chat_agent_border": "#3A3447",
            "accent_glow": "#47386E",
        },
        "space_dust": {
            "app_bg": "#F1EFF4",
            "bg": "#F1EFF4",
            "workspace_bg": "#FCFBFE",
            "workspace_border": "#DDD6E8",
            "workspace_shadow": "#E6E0EE",
            "surface": "#FCFBFE",
            "surface_elevated": "#FFFFFF",
            "surface_alt": "#F5F2FA",
            "sidebar_bg": "#FCFBFE",
            "content_bg": "#FCFBFE",
            "text": "#1A1722",
            "muted_text": "#756F83",
            "primary": "#7C5CFA",
            "primary_hover": "#9478FF",
            "primary_pressed": "#6241E8",
            "secondary": "#1F1A2C",
            "tertiary": "#B59DFF",
            "border": "#E3DDED",
            "outline": "#D5CEE1",
            "status": "#635C71",
            "danger": "#D85A6A",
            "danger_hover": "#E47281",
            "success": "#3C9A76",
            "success_hover": "#4FB18A",
            "warning": "#B07A1B",
            "selection_bg": "#E9E0FF",
            "selection_fg": "#1A1722",
            "chat_user_bg": "#F0E8FF",
            "chat_agent_bg": "#FFFFFF",
            "chat_system_bg": "#F7F3FD",
            "input_bg": "#FFFFFF",
            "badge_bg": "#F2EEFA",
            "stripe_alt": "#F7F4FB",
            "focus_ring": "#7C5CFA",
            "tab_indicator": "#7C5CFA",
            "progress_pulse": "#B7A2FF",
            "link": "#7C5CFA",
            "source": "#706987",
            "supporting_bg": "#F6F1FD",
            "nav_hover_bg": "#F4F0FB",
            "nav_active_bg": "#EEE8FB",
            "sidebar_border": "#E6E0EE",
            "chat_user_border": "#D8CBF7",
            "chat_agent_border": "#E3DDED",
            "accent_glow": "#EADFFF",
        },
    },
}

UI_SPACING: dict[str, int] = {
    "xs": 6,
    "s": 10,
    "m": 16,
    "l": 24,
    "xl": 34,
    "xxl": 46,
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


def resolve_fonts(root: tk.Misc | None = None) -> dict:  # noqa: ARG001
    """Return a font dict keyed by the shared type-scale names."""
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
        STYLE_CONFIG.get("mono_font", "Cascadia Code"),
        STYLE_CONFIG.get("fallback_mono_font", "Consolas"),
        "SF Mono",
        "Courier New",
        "TkFixedFont",
    )
    code_family = next((family for family in mono_candidates if family in families), base_family)

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
        "h1": _font_for("h1", base_family),
        "h2": _font_for("h2", base_family),
        "h3": _font_for("h3", base_family),
        "body": _font_for("body", base_family),
        "body_bold": _font_for("body_bold", base_family),
        "caption": _font_for("caption", base_family),
        "code": _font_for("code", code_family),
        "overline": _font_for("overline", base_family),
    }


def apply_ttk_theme(root: tk.Tk, palette: dict, fonts: dict) -> None:
    """Configure the shared ttk styles for the active palette."""

    def get(key: str, fallback=None, default=None):
        value = palette.get(key)
        if value is not None:
            return value
        if isinstance(fallback, str):
            value = palette.get(fallback)
            if value is not None:
                return value
        elif fallback is not None:
            return fallback
        if default is not None:
            return default
        return STYLE_CONFIG["themes"]["light"].get(key)

    style = ttk.Style()
    if "clam" in style.theme_names():
        style.theme_use("clam")

    root.configure(bg=get("app_bg", "bg"))

    app_bg = get("app_bg", "bg")
    surface = get("surface")
    surface_elevated = get("surface_elevated", "surface")
    surface_alt = get("surface_alt", "surface")
    sidebar_bg = get("sidebar_bg", "surface")
    text = get("text")
    muted = get("muted_text")
    border = get("border", default="#E5E0EA")
    outline = get("outline", "border")
    primary = get("primary")
    primary_hover = get("primary_hover", "primary")
    primary_pressed = get("primary_pressed", "primary")
    nav_hover = get("nav_hover_bg", "surface_alt")
    nav_active = get("nav_active_bg", "surface_alt")
    input_bg = get("input_bg", "surface_alt")
    badge_bg = get("badge_bg", "surface_alt")

    style.configure(".", background=app_bg, foreground=text, fieldbackground=input_bg)
    style.configure("TFrame", background=app_bg, borderwidth=0, relief="flat")
    style.configure("Card.TFrame", background=surface, borderwidth=0, relief="flat")
    style.configure("Card.Elevated.TFrame", background=surface_elevated, borderwidth=0, relief="flat")
    style.configure("Card.Flat.TFrame", background=surface_alt, borderwidth=0, relief="flat")
    style.configure("Workspace.TFrame", background=get("workspace_bg", "surface"), borderwidth=0, relief="flat")
    style.configure("Sidebar.TFrame", background=sidebar_bg, borderwidth=0, relief="flat")
    style.configure("MainContent.TFrame", background=get("workspace_bg", "surface"), borderwidth=0, relief="flat")
    style.configure("Utility.TFrame", background=surface, borderwidth=0, relief="flat")
    style.configure("MutedPanel.TFrame", background=surface_alt, borderwidth=0, relief="flat")
    style.configure("StatusBar.TFrame", background=surface, borderwidth=0, relief="flat")
    style.configure("CollapsibleHeader.TFrame", background=surface, borderwidth=0, relief="flat")

    style.configure(
        "TLabelframe",
        background=surface,
        bordercolor=border,
        borderwidth=1,
        relief="flat",
        padding=(14, 12),
    )
    style.configure("TLabelframe.Label", background=surface, foreground=text, font=fonts["body_bold"])

    style.configure("TLabel", background=surface, foreground=text, font=fonts["body"])
    style.configure("Header.TLabel", background=surface, foreground=text, font=fonts["h2"])
    style.configure("Title.TLabel", background=surface, foreground=text, font=fonts["h1"])
    style.configure("Bold.TLabel", background=surface, foreground=text, font=fonts["body_bold"])
    style.configure("Muted.TLabel", background=surface, foreground=muted, font=fonts["body"])
    style.configure("Caption.TLabel", background=surface, foreground=muted, font=fonts["caption"])
    style.configure("Overline.TLabel", background=surface, foreground=muted, font=fonts["overline"])
    style.configure("Code.TLabel", background=surface, foreground=get("source", "muted_text"), font=fonts["code"])
    style.configure("Danger.TLabel", background=surface, foreground=get("danger"), font=fonts["body_bold"])
    style.configure("Success.TLabel", background=surface, foreground=get("success"), font=fonts["body_bold"])
    style.configure("Warning.TLabel", background=surface, foreground=get("warning"), font=fonts["body_bold"])
    style.configure("Status.TLabel", background=surface, foreground=get("status", "muted_text"), font=fonts["caption"])
    style.configure(
        "Badge.TLabel",
        background=badge_bg,
        foreground=primary,
        font=fonts["caption"],
        padding=(12, 6),
        borderwidth=0,
        relief="flat",
    )
    style.configure("Sidebar.Title.TLabel", background=sidebar_bg, foreground=text, font=fonts["body_bold"])
    style.configure("Sidebar.Caption.TLabel", background=sidebar_bg, foreground=muted, font=fonts["caption"])
    style.configure("CollapsibleArrow.TLabel", background=surface, foreground=muted, font=fonts["body_bold"])
    style.configure("CollapsibleTitle.TLabel", background=surface, foreground=text, font=fonts["body_bold"])

    style.configure(
        "TButton",
        padding=(14, 10),
        borderwidth=1,
        relief="flat",
        background=surface,
        foreground=text,
        bordercolor=border,
        focuscolor=surface,
        font=fonts["body"],
    )
    style.map(
        "TButton",
        background=[("active", surface_alt), ("pressed", nav_hover)],
        foreground=[("disabled", muted), ("active", text)],
        bordercolor=[("focus", primary), ("active", outline)],
    )

    style.configure(
        "Primary.TButton",
        padding=(16, 10),
        borderwidth=0,
        relief="flat",
        background=primary,
        foreground="#FFFFFF",
        focuscolor=primary,
        font=fonts["body_bold"],
    )
    style.map(
        "Primary.TButton",
        background=[
            ("active", primary_hover),
            ("pressed", primary_pressed),
            ("disabled", outline),
        ],
        foreground=[("disabled", muted), ("active", "#FFFFFF")],
    )

    style.configure(
        "Secondary.TButton",
        padding=(14, 10),
        borderwidth=1,
        relief="flat",
        background=surface,
        foreground=text,
        bordercolor=border,
        focuscolor=surface,
        font=fonts["body"],
    )
    style.map(
        "Secondary.TButton",
        background=[
            ("active", surface_alt),
            ("pressed", nav_hover),
            ("disabled", surface),
        ],
        foreground=[("disabled", muted), ("active", text)],
        bordercolor=[("focus", primary), ("active", outline)],
    )

    style.configure(
        "Sidebar.TButton",
        padding=(11, 11),
        borderwidth=0,
        relief="flat",
        background=sidebar_bg,
        foreground=muted,
        anchor="center",
        focuscolor=sidebar_bg,
        font=fonts["body_bold"],
    )
    style.map(
        "Sidebar.TButton",
        background=[("active", nav_hover), ("pressed", nav_hover)],
        foreground=[("active", text), ("pressed", text)],
    )

    style.configure(
        "Sidebar.Active.TButton",
        padding=(11, 11),
        borderwidth=0,
        relief="flat",
        background=nav_active,
        foreground=primary,
        anchor="center",
        focuscolor=nav_active,
        font=fonts["body_bold"],
    )
    style.map(
        "Sidebar.Active.TButton",
        background=[("active", nav_active), ("pressed", nav_active)],
        foreground=[("active", primary), ("pressed", primary)],
    )

    style.configure(
        "TCheckbutton",
        background=surface,
        foreground=text,
        indicatorcolor=surface_alt,
        relief="flat",
    )
    style.map(
        "TCheckbutton",
        background=[("active", surface), ("!active", surface)],
        foreground=[("active", text), ("disabled", muted)],
        indicatorcolor=[("selected", primary), ("!selected", surface_alt)],
    )

    style.configure(
        "TEntry",
        fieldbackground=input_bg,
        foreground=text,
        bordercolor=border,
        insertcolor=primary,
        borderwidth=1,
        relief="flat",
        padding=(12, 9),
    )
    style.map("TEntry", bordercolor=[("focus", primary), ("active", outline)])

    style.configure(
        "TCombobox",
        fieldbackground=input_bg,
        background=input_bg,
        foreground=text,
        arrowcolor=muted,
        bordercolor=border,
        relief="flat",
        insertcolor=primary,
        padding=(12, 9),
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", input_bg)],
        selectbackground=[("readonly", get("selection_bg"))],
        selectforeground=[("readonly", get("selection_fg"))],
        foreground=[("readonly", text)],
        bordercolor=[("focus", primary), ("active", outline)],
    )

    root.option_add("*TCombobox*Listbox.background", input_bg)
    root.option_add("*TCombobox*Listbox.foreground", text)
    root.option_add("*TCombobox*Listbox.selectBackground", get("selection_bg"))
    root.option_add("*TCombobox*Listbox.selectForeground", get("selection_fg"))
    root.option_add("*TCombobox*Listbox.relief", "flat")
    root.option_add("*TCombobox*Listbox.borderWidth", "0")

    style.configure(
        "Treeview",
        background=surface,
        fieldbackground=surface,
        foreground=text,
        bordercolor=border,
        borderwidth=0,
        rowheight=34,
        relief="flat",
    )
    style.map(
        "Treeview",
        background=[("selected", get("selection_bg")), ("active", surface_alt)],
        foreground=[("selected", get("selection_fg")), ("active", text)],
    )
    style.configure(
        "Treeview.Heading",
        background=surface_alt,
        foreground=muted,
        borderwidth=0,
        relief="flat",
        font=fonts["caption"],
        padding=(8, 7),
    )
    style.map(
        "Treeview.Heading",
        background=[("active", surface_elevated)],
        foreground=[("active", text)],
    )

    style.configure(
        "TNotebook",
        background=surface,
        borderwidth=0,
        tabmargins=(0, 0, 0, 0),
    )
    style.configure(
        "TNotebook.Tab",
        background=surface_alt,
        foreground=muted,
        padding=(14, 8),
        borderwidth=0,
        font=fonts["caption"],
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", surface), ("active", surface_elevated)],
        foreground=[("selected", text), ("active", text)],
    )

    style.configure(
        "Vertical.TScrollbar",
        background=surface_alt,
        troughcolor=app_bg,
        bordercolor=app_bg,
        arrowcolor=surface_alt,
        relief="flat",
        width=8,
        arrowsize=0,
    )
    style.map(
        "Vertical.TScrollbar",
        background=[("active", outline), ("!active", border)],
    )
    style.configure(
        "Horizontal.TScrollbar",
        background=surface_alt,
        troughcolor=app_bg,
        bordercolor=app_bg,
        arrowcolor=surface_alt,
        relief="flat",
        width=8,
        arrowsize=0,
    )
    style.map(
        "Horizontal.TScrollbar",
        background=[("active", outline), ("!active", border)],
    )

    style.configure(
        "TProgressbar",
        troughcolor=surface_alt,
        background=primary,
        bordercolor=app_bg,
        lightcolor=primary_hover,
        darkcolor=primary,
        relief="flat",
    )
    style.configure("TSeparator", background=border)
