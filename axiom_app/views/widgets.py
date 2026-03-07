"""axiom_app.views.widgets — Reusable custom tkinter widget classes.

Extracted from agentic_rag_gui.py (the legacy monolith) and adapted for use
inside the clean MVC package.  All classes are pure-tkinter and have no
dependency on AgenticRAGApp or any model/controller code.

Classes
-------
AnimationEngine      — root.after-based smooth value interpolation with easing
IOSSegmentedToggle   — iOS-style two-option pill toggle (tk.Canvas)
CollapsibleFrame     — animated accordion section (ttk.Frame)
RoundedCard          — canvas-backed card with rounded corners
TooltipManager       — hover tooltips with fade-in animation
"""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk

from axiom_app.views.styles import STYLE_CONFIG, UI_SPACING, _pal

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# AnimationEngine
# ---------------------------------------------------------------------------


class AnimationEngine:
    """Smooth value interpolation for tkinter widgets using root.after()."""

    def __init__(self, root: tk.Misc) -> None:
        self.root = root
        self._animations: dict = {}
        self._token_counter = 0

    def cancel(self, anim_id: str) -> None:
        state = self._animations.pop(anim_id, None)
        if not state:
            return
        after_id = state.get("after_id")
        if after_id is not None and self._root_alive():
            try:
                self.root.after_cancel(after_id)
            except tk.TclError:
                pass

    def animate_value(
        self,
        anim_id: str,
        start: float,
        end: float,
        duration_ms: int,
        steps: int,
        callback,
        on_complete=None,
    ) -> None:
        self.cancel(anim_id)
        if not self._root_alive():
            return
        try:
            duration = max(1, int(duration_ms))
            total_steps = max(1, int(steps))
        except (TypeError, ValueError):
            duration = 1
            total_steps = 1

        self._token_counter += 1
        token = self._token_counter
        self._animations[anim_id] = {"token": token, "after_id": None}
        step_delay = max(1, int(round(duration / total_steps)))

        def _run(step_index: int) -> None:
            state = self._animations.get(anim_id)
            if state is None or state.get("token") != token:
                return
            if not self._root_alive():
                self._animations.pop(anim_id, None)
                return
            t = min(1.0, max(0.0, step_index / total_steps))
            eased = 1.0 - ((1.0 - t) ** 3)
            value = float(start) + (float(end) - float(start)) * eased
            try:
                callback(value)
            except Exception:
                self._animations.pop(anim_id, None)
                raise
            if step_index >= total_steps:
                self._animations.pop(anim_id, None)
                if callable(on_complete):
                    try:
                        on_complete()
                    except Exception:
                        logger.exception("Animation completion callback failed for %s", anim_id)
                return
            try:
                after_id = self.root.after(step_delay, lambda: _run(step_index + 1))
            except tk.TclError:
                self._animations.pop(anim_id, None)
                return
            state = self._animations.get(anim_id)
            if state is not None and state.get("token") == token:
                state["after_id"] = after_id

        _run(0)

    def _root_alive(self) -> bool:
        try:
            return bool(self.root) and bool(self.root.winfo_exists())
        except tk.TclError:
            return False


# ---------------------------------------------------------------------------
# IOSSegmentedToggle
# ---------------------------------------------------------------------------


class IOSSegmentedToggle(tk.Canvas):
    """iOS-style segmented two-option toggle rendered on a tk.Canvas.

    Shows both option labels side-by-side inside a rounded pill.  The active
    segment is filled with the primary colour so both options are always
    visible and new users can immediately see which mode is selected.

    Parameters
    ----------
    parent   : tk parent widget
    options  : sequence of exactly 2 label strings, e.g. ["RAG", "Direct"]
    variable : tk.BooleanVar – True selects options[0], False selects options[1]
    palette  : colour-dict (same shape as STYLE_CONFIG theme palettes)
    command  : optional callable invoked after each toggle
    height   : pixel height of the pill (default 28)
    font     : tkinter font tuple (default Segoe UI 9 bold)
    """

    def __init__(
        self,
        parent,
        options,
        variable: tk.BooleanVar,
        palette: dict,
        *,
        command=None,
        height: int = 28,
        font=None,
        **kwargs,
    ) -> None:
        self._opts = list(options)
        self._var = variable
        self._palette = dict(palette)
        self._command = command
        self._h = height
        self._font = font or ("Segoe UI", 9, "bold")
        self._seg_w = max(68, max(len(o) for o in options) * 9 + 28)
        total_w = self._seg_w * 2 + 2
        kwargs.setdefault("highlightthickness", 0)
        kwargs.setdefault("borderwidth", 0)
        bg = palette.get("bg", "#141E2D")
        super().__init__(parent, width=total_w, height=height, bg=bg, **kwargs)
        self.configure(cursor="hand2")
        self.bind("<Button-1>", self._on_click)
        self._draw()

    def update_palette(self, palette: dict) -> None:
        """Re-colour the widget when the application theme changes."""
        self._palette = dict(palette)
        self._draw()

    def _on_click(self, _event) -> None:
        if self._command:
            self._command()
        else:
            self._var.set(not self._var.get())
            self._draw()

    def _rounded_rect(self, x1, y1, x2, y2, r, **kw) -> None:
        r = min(r, (x2 - x1) // 2, (y2 - y1) // 2)
        pts = [
            x1 + r, y1,    x2 - r, y1,
            x2,     y1,    x2,     y1 + r,
            x2,     y2 - r, x2,   y2,
            x2 - r, y2,    x1 + r, y2,
            x1,     y2,    x1,     y2 - r,
            x1,     y1 + r, x1,   y1,
        ]
        self.create_polygon(pts, smooth=True, **kw)

    def _draw(self) -> None:
        pal        = self._palette
        bg         = pal.get("bg",          "#141E2D")
        track      = pal.get("surface_alt", "#1A2B40")
        border_col = pal.get("outline",     "#2A3E58")
        primary    = pal.get("primary",     "#4D9EFF")
        text_on    = pal.get("text",        "#EAF0FF")
        text_off   = pal.get("muted_text",  "#8A9DC0")

        self.delete("all")
        self.configure(bg=bg)

        w   = self._seg_w * 2 + 2
        h   = self._h
        r   = h // 2
        sw  = self._seg_w
        pad = 3
        left_active = self._var.get()

        self._rounded_rect(0, 0, w, h, r, fill=track, outline=border_col)

        if left_active:
            self._rounded_rect(pad, pad, sw - pad + 1, h - pad, r - pad,
                               fill=primary, outline="")
        else:
            self._rounded_rect(sw + pad - 1, pad, w - pad, h - pad, r - pad,
                               fill=primary, outline="")

        mid_y = h // 2
        self.create_text(sw // 2, mid_y,
                         text=self._opts[0],
                         fill=text_on if left_active else text_off,
                         font=self._font, anchor="center")
        self.create_text(sw + sw // 2, mid_y,
                         text=self._opts[1],
                         fill=text_off if left_active else text_on,
                         font=self._font, anchor="center")


# ---------------------------------------------------------------------------
# CollapsibleFrame
# ---------------------------------------------------------------------------


class CollapsibleFrame(ttk.Frame):
    """Animated accordion section.

    Parameters
    ----------
    parent    : tk parent widget
    title     : header label text
    expanded  : initial state (default False = collapsed)
    animator  : AnimationEngine instance for smooth height transitions, or
                None to skip animation
    """

    def __init__(
        self,
        parent,
        title: str,
        expanded: bool = False,
        animator: AnimationEngine | None = None,
        **kwargs,
    ) -> None:
        kwargs.setdefault("style", "Card.Elevated.TFrame")
        super().__init__(parent, **kwargs)
        self._animator = animator
        self._expanded = tk.BooleanVar(value=expanded)
        self._animating = False
        self._animation_id = f"collapsible_{id(self)}"
        self._content_pad = (UI_SPACING["s"], UI_SPACING["s"])

        self.header = ttk.Frame(self, style="CollapsibleHeader.TFrame")
        self.header.pack(fill="x", padx=UI_SPACING["s"], pady=(UI_SPACING["s"], 0))
        self.arrow_label = ttk.Label(
            self.header,
            text="▾" if expanded else "▸",
            style="CollapsibleArrow.TLabel",
            width=2,
            anchor="center",
        )
        self.arrow_label.pack(side="left")
        self.title_label = ttk.Label(
            self.header, text=title, style="CollapsibleTitle.TLabel"
        )
        self.title_label.pack(side="left", padx=(UI_SPACING["xs"], 0), fill="x", expand=True)

        for widget in (self.header, self.arrow_label, self.title_label):
            widget.bind("<Button-1>", lambda _e: self.toggle(), add="+")

        self._content_clip = ttk.Frame(self, style="Card.Elevated.TFrame", height=0)
        self._content_clip.pack_propagate(False)
        self.content = ttk.Frame(self._content_clip, style="Card.Elevated.TFrame")
        self.content.pack(fill="x")
        self.content.bind("<Configure>", self._on_content_configure, add="+")
        if expanded:
            self._content_clip.pack(fill="x", padx=UI_SPACING["s"], pady=self._content_pad)
            self.after_idle(lambda: self._set_clip_height(self._measure_content_height()))

    def _on_content_configure(self, _event=None) -> None:
        if self._expanded.get() and not self._animating:
            self._set_clip_height(self._measure_content_height())

    def _measure_content_height(self) -> int:
        self.update_idletasks()
        return max(1, int(self.content.winfo_reqheight()))

    def _set_clip_height(self, value: float) -> None:
        try:
            self._content_clip.configure(height=max(0, int(value)))
        except tk.TclError:
            return

    def _animate_height(
        self, start: float, end: float, duration_ms: int, on_complete=None
    ) -> None:
        if self._animator is None:
            self._set_clip_height(end)
            if callable(on_complete):
                on_complete()
            return
        self._animator.animate_value(
            self._animation_id,
            start,
            end,
            duration_ms,
            10,
            lambda value: self._set_clip_height(value),
            on_complete=on_complete,
        )

    def _expand(self) -> None:
        if self._animating:
            return
        self._animating = True
        self._content_clip.pack(fill="x", padx=UI_SPACING["s"], pady=self._content_pad)
        self._set_clip_height(0)
        target_height = self._measure_content_height()

        def _done() -> None:
            self._set_clip_height(target_height)
            self.arrow_label.config(text="▾")
            self._expanded.set(True)
            self._animating = False
            self.after_idle(lambda: self._set_clip_height(self._measure_content_height()))

        collapse_duration = int(
            STYLE_CONFIG.get("animation", {}).get("collapse_duration_ms", 200)
        )
        self._animate_height(0, target_height, collapse_duration, on_complete=_done)

    def _collapse(self) -> None:
        if self._animating:
            return
        self._animating = True
        start_height = max(
            1, self._content_clip.winfo_height(), self._measure_content_height()
        )

        def _done() -> None:
            self._set_clip_height(0)
            self._content_clip.pack_forget()
            self.arrow_label.config(text="▸")
            self._expanded.set(False)
            self._animating = False

        collapse_duration = int(
            STYLE_CONFIG.get("animation", {}).get("collapse_duration_ms", 200)
        )
        self._animate_height(start_height, 0, collapse_duration, on_complete=_done)

    def set_expanded(self, expanded: bool) -> None:
        expanded = bool(expanded)
        if expanded != bool(self._expanded.get()):
            self.toggle()

    def toggle(self) -> None:
        if self._animating:
            return
        if self._expanded.get():
            self._collapse()
        else:
            self._expand()


# ---------------------------------------------------------------------------
# RoundedCard
# ---------------------------------------------------------------------------


class RoundedCard(tk.Canvas):
    """Canvas-backed card widget with rounded corners.

    Children should be placed inside ``card.inner`` (a plain ``tk.Frame``).

    Example::

        card = RoundedCard(parent, radius=16, bg=palette["surface"],
                           border_color=palette["outline"], border_width=1)
        ttk.Label(card.inner, text="Title").pack(anchor="w", padx=12, pady=(10, 4))
        card.pack(fill="x", padx=8, pady=4)
    """

    def __init__(
        self,
        parent,
        radius: int = 12,
        bg: str = "#161B22",
        outer_bg: str | None = None,
        border_color: str = "#33465F",
        border_width: int = 1,
        shadow_color: str | None = None,
        shadow_offset: int = 0,
        inner_padding: int | None = None,
        **kwargs,
    ) -> None:
        kwargs.setdefault("highlightthickness", 0)
        kwargs.setdefault("bd", 0)
        kwargs.setdefault("relief", "flat")
        if outer_bg is None:
            try:
                outer_bg = parent.cget("background")
            except Exception:
                outer_bg = "#0D1117"
        super().__init__(parent, bg=outer_bg, **kwargs)
        self._radius = max(2, int(radius))
        self._card_bg = bg
        self._border_color = border_color
        self._border_width = border_width
        self._shadow_color = shadow_color or ""
        self._shadow_offset = max(0, int(shadow_offset))
        self._inner_padding = max(0, int(inner_padding)) if inner_padding is not None else max(10, self._radius - 4)
        self._rect_tag = "card_bg"
        self._shadow_tag = "card_shadow"
        self.inner = tk.Frame(self, bg=bg, bd=0, highlightthickness=0)
        self._win_id = self.create_window(
            self._inner_padding, self._inner_padding, anchor="nw", window=self.inner
        )
        self.bind("<Configure>", self._redraw)

    def _smooth_pts(self, x0, y0, x1, y1) -> list:
        r = self._radius
        return [
            x0 + r, y0,   x1 - r, y0,
            x1,     y0,   x1,     y0 + r,
            x1,     y1 - r, x1,   y1,
            x1 - r, y1,   x0 + r, y1,
            x0,     y1,   x0,     y1 - r,
            x0,     y0 + r, x0,   y0,
        ]

    def _redraw(self, _event=None) -> None:
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 4 or h < 4:
            return
        bw = self._border_width
        shadow = self._shadow_offset
        self.delete(self._rect_tag)
        self.delete(self._shadow_tag)
        if self._shadow_color and shadow:
            self.create_polygon(
                self._smooth_pts(bw + shadow, bw + shadow, w - bw, h - bw),
                smooth=True,
                fill=self._shadow_color,
                outline="",
                tags=self._shadow_tag,
            )
            self.tag_lower(self._shadow_tag)
        self.create_polygon(
            self._smooth_pts(bw, bw, w - bw - shadow, h - bw - shadow),
            smooth=True,
            fill=self._card_bg,
            outline=self._border_color if bw else "",
            width=bw,
            tags=self._rect_tag,
        )
        self.tag_lower(self._rect_tag)
        inner_pad = self._inner_padding
        self.coords(self._win_id, inner_pad, inner_pad)
        self.itemconfig(
            self._win_id,
            width=max(1, w - (2 * inner_pad) - shadow),
            height=max(1, h - (2 * inner_pad) - shadow),
        )

    def configure_colors(
        self,
        bg: str | None = None,
        border_color: str | None = None,
        outer_bg: str | None = None,
        shadow_color: str | None = None,
    ) -> None:
        """Update colors and redraw; safe to call after theme changes."""
        if bg is not None:
            self._card_bg = bg
            self.inner.configure(bg=bg)
        if border_color is not None:
            self._border_color = border_color
        if outer_bg is not None:
            self.configure(bg=outer_bg)
        if shadow_color is not None:
            self._shadow_color = shadow_color
        self._redraw()


# ---------------------------------------------------------------------------
# TooltipManager
# ---------------------------------------------------------------------------


class TooltipManager:
    """Hover tooltips with fade-in animation.

    Parameters
    ----------
    root        : the Tk root window
    get_palette : callable returning the active palette dict (for live theming)
    delay_ms    : hover delay before tooltip appears
    wrap_px     : maximum tooltip width in pixels
    fade_ms     : fade-in duration (defaults to STYLE_CONFIG animation setting)
    """

    def __init__(
        self,
        root: tk.Tk,
        get_palette,
        *,
        delay_ms: int = 350,
        wrap_px: int = 340,
        fade_ms: int | None = None,
    ) -> None:
        self.root = root
        self.get_palette = get_palette
        self.delay_ms = delay_ms
        self.wrap_px = wrap_px
        if fade_ms is None:
            fade_ms = STYLE_CONFIG.get("animation", {}).get("tooltip_fade_ms", 150)
        self.fade_ms = max(1, int(fade_ms))
        self._widget_text: dict = {}
        self._tooltip_window: tk.Toplevel | None = None
        self._tooltip_label: tk.Label | None = None
        self._active_widget = None
        self._after_id = None
        self._fade_after_id = None
        self._last_pointer = (0, 0)

    def register(self, widget, text: str) -> None:
        if widget is None:
            return
        message = (text or "").strip()
        if not message:
            return
        self._widget_text[widget] = message
        widget.bind("<Enter>",   lambda e, w=widget: self._on_enter(w, e),   add="+")
        widget.bind("<Leave>",   lambda _e, w=widget: self._on_leave(w),     add="+")
        widget.bind("<Motion>",  lambda e, w=widget: self._on_motion(w, e),  add="+")
        widget.bind("<Destroy>", lambda _e, w=widget: self._on_destroy(w),   add="+")

    def hide(self) -> None:
        self._cancel_pending()
        self._cancel_fade()
        self._active_widget = None
        if self._tooltip_window is not None and self._tooltip_window.winfo_exists():
            self._tooltip_window.withdraw()

    def _on_enter(self, widget, event) -> None:
        self._active_widget = widget
        self._last_pointer = (event.x_root, event.y_root)
        self._schedule_show(widget)

    def _on_leave(self, widget) -> None:
        if widget == self._active_widget:
            self.hide()

    def _on_motion(self, widget, event) -> None:
        self._last_pointer = (event.x_root, event.y_root)
        if (
            widget == self._active_widget
            and self._tooltip_window is not None
            and self._tooltip_window.winfo_viewable()
        ):
            self._position_window(event.x_root, event.y_root)

    def _on_destroy(self, widget) -> None:
        self._widget_text.pop(widget, None)
        if widget == self._active_widget:
            self.hide()

    def _schedule_show(self, widget) -> None:
        self._cancel_pending()
        self._after_id = self.root.after(
            self.delay_ms, lambda w=widget: self._show(w)
        )

    def _cancel_pending(self) -> None:
        if self._after_id is not None:
            try:
                self.root.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None

    def _show(self, widget) -> None:
        self._after_id = None
        if widget != self._active_widget or not widget.winfo_exists():
            return
        text = self._widget_text.get(widget, "").strip()
        if not text:
            return
        if self._tooltip_window is None or not self._tooltip_window.winfo_exists():
            self._create_tooltip_window()
        palette = self.get_palette() or STYLE_CONFIG["themes"].get("space_dust", {})
        self._tooltip_window.configure(
            bg=_pal(palette, "border", default="#2A3A4F")
        )
        self._tooltip_label.configure(
            text=text,
            bg=_pal(palette, "surface_alt", fallback_key="surface", default="#161B22"),
            fg=_pal(palette, "text", default="#E8EEF8"),
            wraplength=self.wrap_px,
            padx=10, pady=7,
            relief="flat", bd=0,
            justify="left",
        )
        self._tooltip_window.deiconify()
        self._tooltip_window.lift()
        self._position_window(*self._last_pointer)
        self._fade_in_tooltip()

    def _create_tooltip_window(self) -> None:
        self._tooltip_window = tk.Toplevel(self.root)
        self._tooltip_window.withdraw()
        self._tooltip_window.overrideredirect(True)
        self._tooltip_window.attributes("-topmost", True)
        self._tooltip_window.attributes("-alpha", 0.0)
        try:
            self._tooltip_window.attributes("-type", "tooltip")
        except tk.TclError:
            pass
        shell = tk.Frame(self._tooltip_window, borderwidth=1, relief="flat")
        shell.pack(fill="both", expand=True)
        self._tooltip_label = tk.Label(shell, font=("Segoe UI", 9))
        self._tooltip_label.pack(fill="both", expand=True, padx=1, pady=1)

    def _position_window(self, x_root: int, y_root: int) -> None:
        if self._tooltip_window is None or not self._tooltip_window.winfo_exists():
            return
        self._tooltip_window.update_idletasks()
        tip_w = self._tooltip_window.winfo_reqwidth()
        tip_h = self._tooltip_window.winfo_reqheight()
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = min(max(x_root + 16, 4), max(4, screen_w - tip_w - 4))
        y = y_root + 20
        if y + tip_h > screen_h - 4:
            y = y_root - tip_h - 14
        y = min(max(y, 4), max(4, screen_h - tip_h - 4))
        self._tooltip_window.geometry(f"+{x}+{y}")

    def _cancel_fade(self) -> None:
        if self._fade_after_id is not None:
            try:
                self.root.after_cancel(self._fade_after_id)
            except tk.TclError:
                pass
            self._fade_after_id = None

    def _fade_in_tooltip(self) -> None:
        if self._tooltip_window is None or not self._tooltip_window.winfo_exists():
            return
        self._cancel_fade()
        steps = 8
        interval = max(1, int(self.fade_ms / steps))

        def _tick(step: int = 0) -> None:
            if self._tooltip_window is None or not self._tooltip_window.winfo_exists():
                self._fade_after_id = None
                return
            t = min(1.0, step / steps)
            eased = 1.0 - ((1.0 - t) ** 3)
            try:
                self._tooltip_window.attributes("-alpha", 0.97 * eased)
            except tk.TclError:
                self._fade_after_id = None
                return
            if step >= steps:
                self._fade_after_id = None
                return
            self._fade_after_id = self.root.after(interval, lambda: _tick(step + 1))

        _tick(0)
