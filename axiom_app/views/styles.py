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
        padding=(12, 7),
        borderwidth=1,
        relief="flat",
    )
    style.configure("Sidebar.Title.TLabel", background=sidebar_bg, foreground=text, font=fonts["body_bold"])
    style.configure("Sidebar.Caption.TLabel", background=sidebar_bg, foreground=muted, font=fonts["caption"])
    style.configure("CollapsibleArrow.TLabel", background=surface, foreground=muted, font=fonts["body_bold"])
    style.configure("CollapsibleTitle.TLabel", background=surface, foreground=text, font=fonts["body_bold"])

    style.configure(
        "TButton",
        padding=(15, 11),
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
        padding=(17, 11),
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
        padding=(15, 11),
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
        padding=(12, 14),
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
        padding=(12, 14),
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
        rowheight=38,
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
        background=outline,
        troughcolor=surface_alt,
        bordercolor=surface_alt,
        arrowcolor=outline,
        relief="flat",
        width=12,
        arrowsize=0,
    )
    style.map(
        "Vertical.TScrollbar",
        background=[("active", primary), ("!active", outline)],
    )
    style.configure(
        "Horizontal.TScrollbar",
        background=outline,
        troughcolor=surface_alt,
        bordercolor=surface_alt,
        arrowcolor=outline,
        relief="flat",
        width=12,
        arrowsize=0,
    )
    style.map(
        "Horizontal.TScrollbar",
        background=[("active", primary), ("!active", outline)],
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
