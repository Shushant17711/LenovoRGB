"""Reusable Tk widgets with a consistent dark look."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Sequence
from tkinter import ttk
from typing import Callable, List, Optional

from .. import colors as col
from . import theme


def blend(hex_a: str, hex_b: str, amount: float) -> str:
    a = col.parse_hex(hex_a)
    b = col.parse_hex(hex_b)
    return col.to_hex(col.lerp(a, b, amount))


def rounded_rect(canvas: tk.Canvas, x1: float, y1: float, x2: float, y2: float, radius: float, **kwargs):
    radius = min(radius, (x2 - x1) / 2, (y2 - y1) / 2)
    points = [
        x1 + radius, y1,
        x2 - radius, y1,
        x2, y1,
        x2, y1 + radius,
        x2, y2 - radius,
        x2, y2,
        x2 - radius, y2,
        x1 + radius, y2,
        x1, y2,
        x1, y2 - radius,
        x1, y1 + radius,
        x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, splinesteps=24, **kwargs)


class FlatButton(tk.Button):
    """A borderless button with hover styling."""

    def __init__(
        self,
        master: tk.Misc,
        text: str,
        command: Optional[Callable[[], None]] = None,
        font: object = None,
        variant: str = "ghost",
        padx: int = 14,
        pady: int = 7,
        **kwargs: object,
    ):
        if variant == "solid":
            bg, fg, hover = theme.ACCENT, "#04161A", blend(theme.ACCENT, "#FFFFFF", 0.18)
        elif variant == "danger":
            bg, fg, hover = theme.SURFACE, theme.DANGER, theme.SURFACE_HOVER
        elif variant == "quiet":
            bg, fg, hover = theme.BG, theme.TEXT_SECONDARY, theme.SURFACE
        else:
            bg, fg, hover = theme.SURFACE, theme.TEXT, theme.SURFACE_HOVER
        super().__init__(
            master,
            text=text,
            command=command,
            font=font,
            bg=bg,
            fg=fg,
            activebackground=hover,
            activeforeground=fg,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=bg,
            highlightcolor=theme.ACCENT,
            padx=padx,
            pady=pady,
            cursor="hand2",
            takefocus=True,
            **kwargs,
        )
        self._normal_bg = bg
        self._hover_bg = hover
        self.bind("<Enter>", lambda _event: self._paint(self._hover_bg))
        self.bind("<Leave>", lambda _event: self._paint(self._normal_bg))

    def _paint(self, background: str) -> None:
        self.configure(bg=background, highlightbackground=background)


class SidebarButton(tk.Frame):
    """Category selector with an accent indicator."""

    def __init__(
        self,
        master: tk.Misc,
        text: str,
        command: Callable[[], None],
        font: object,
        count: Optional[int] = None,
    ):
        super().__init__(master, bg=theme.BG, cursor="hand2")
        self.command = command
        self._selected = False
        self._accent = tk.Frame(self, bg=theme.BG, width=3)
        self._accent.pack(side="left", fill="y")
        self._label = tk.Label(
            self,
            text=text,
            font=font,
            bg=theme.BG,
            fg=theme.TEXT_SECONDARY,
            anchor="w",
            padx=10,
            pady=7,
        )
        self._label.pack(side="left", fill="x", expand=True)
        self._count = tk.Label(
            self,
            text=str(count) if count is not None else "",
            font=font,
            bg=theme.BG,
            fg=theme.MUTED,
            padx=10,
        )
        self._count.pack(side="right")
        for widget in (self, self._label, self._count, self._accent):
            widget.bind("<Button-1>", self._click)
            widget.bind("<Enter>", self._enter)
            widget.bind("<Leave>", self._leave)

    def _click(self, _event: object = None) -> None:
        self.command()

    def _enter(self, _event: object = None) -> None:
        if not self._selected:
            self._paint(theme.SURFACE, theme.TEXT)

    def _leave(self, _event: object = None) -> None:
        if not self._selected:
            self._paint(theme.BG, theme.TEXT_SECONDARY)

    def _paint(self, bg: str, fg: str, accent: Optional[str] = None) -> None:
        self.configure(bg=bg)
        self._label.configure(bg=bg, fg=fg)
        self._count.configure(bg=bg, fg=theme.MUTED if fg == theme.TEXT_SECONDARY else fg)
        self._accent.configure(bg=accent or bg)

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        if selected:
            self._paint(theme.SURFACE_ACTIVE, theme.TEXT, theme.ACCENT)
        else:
            self._paint(theme.BG, theme.TEXT_SECONDARY)


class ModeCard(tk.Frame):
    """Clickable card representing one lighting mode."""

    def __init__(
        self,
        master: tk.Misc,
        mode: type,
        command: Callable[[str], None],
        fonts: object,
        selected: bool = False,
    ):
        super().__init__(
            master,
            bg=theme.SURFACE,
            highlightthickness=1,
            highlightbackground=theme.BORDER,
            bd=0,
            cursor="hand2",
        )
        self.mode_id = mode.id
        self.command = command
        self.selected = selected
        self._widgets: List[tk.Misc] = [self]

        self._bar = tk.Frame(self, bg=mode.accent, width=3)
        self._bar.pack(side="left", fill="y")

        body = tk.Frame(self, bg=theme.SURFACE, padx=12, pady=10)
        body.pack(side="left", fill="both", expand=True)
        self._widgets.append(body)

        icon = tk.Canvas(body, width=36, height=36, bg=theme.SURFACE, highlightthickness=0, bd=0)
        icon.pack(side="left", padx=(0, 11))
        self._widgets.append(icon)
        rounded_rect(icon, 1, 1, 35, 35, 10, fill=blend(mode.accent, theme.SURFACE, 0.82), outline="")
        icon.create_text(
            18,
            18,
            text=mode.abbr,
            fill=blend(mode.accent, "#FFFFFF", 0.25),
            font=fonts.preview,
        )

        text = tk.Frame(body, bg=theme.SURFACE)
        text.pack(side="left", fill="both", expand=True)
        self._widgets.append(text)

        self._title = tk.Label(
            text,
            text=mode.name,
            font=fonts.card_title,
            bg=theme.SURFACE,
            fg=theme.TEXT,
            anchor="w",
        )
        self._title.pack(fill="x")
        self._desc = tk.Label(
            text,
            text=mode.description,
            font=fonts.card_body,
            bg=theme.SURFACE,
            fg=theme.MUTED,
            anchor="w",
            justify="left",
            wraplength=200,
        )
        self._desc.pack(fill="x", pady=(2, 0))
        self._widgets.extend([self._title, self._desc])

        for widget in self._widgets:
            widget.bind("<Button-1>", self._click)
            widget.bind("<Enter>", self._enter)
            widget.bind("<Leave>", self._leave)
        for widget in (self._bar,):
            widget.bind("<Button-1>", self._click)
            widget.bind("<Enter>", self._enter)
            widget.bind("<Leave>", self._leave)
        self._apply_selected()

    def _click(self, _event: object = None) -> None:
        self.command(self.mode_id)

    def _enter(self, _event: object = None) -> None:
        if not self.selected:
            self._paint(theme.SURFACE_HOVER)
            self.configure(highlightbackground=theme.BORDER_HOVER, highlightcolor=theme.BORDER_HOVER)

    def _leave(self, _event: object = None) -> None:
        if not self.selected:
            self._paint(theme.SURFACE)
            self.configure(highlightbackground=theme.BORDER, highlightcolor=theme.BORDER)

    def _paint(self, bg: str) -> None:
        self.configure(bg=bg)
        for widget in self._widgets:
            try:
                if isinstance(widget, (tk.Frame, tk.Label, tk.Canvas)):
                    widget.configure(bg=bg)
            except tk.TclError:
                pass

    def _apply_selected(self) -> None:
        if self.selected:
            self.configure(
                highlightbackground=theme.ACCENT,
                highlightcolor=theme.ACCENT,
                bg=theme.SURFACE_ACTIVE,
            )
            self._paint(theme.SURFACE_ACTIVE)
            self._title.configure(fg=theme.TEXT)
            self._desc.configure(fg=theme.TEXT_SECONDARY)
        else:
            self.configure(
                highlightbackground=theme.BORDER,
                highlightcolor=theme.BORDER,
                bg=theme.SURFACE,
            )
            self._paint(theme.SURFACE)
            self._title.configure(fg=theme.TEXT)
            self._desc.configure(fg=theme.MUTED)

    def set_selected(self, selected: bool) -> None:
        self.selected = selected
        self._apply_selected()


class ZonePreview(tk.Canvas):
    """Live four-zone mirror of the physical keyboard."""

    def __init__(self, master: tk.Misc, width: int = 240, height: int = 34):
        super().__init__(
            master,
            width=width,
            height=height,
            bg=theme.BG,
            highlightthickness=0,
            bd=0,
        )
        self._colors: List[Sequence[float]] = [(0, 0, 0)] * 4
        self._size = (width, height)
        self._draw()

    def set_colors(self, colors: Sequence[Sequence[float]]) -> None:
        if list(colors) == list(self._colors):
            return
        self._colors = [tuple(color) for color in colors][:4]
        while len(self._colors) < 4:
            self._colors.append((0, 0, 0))
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        width, height = self._size
        rounded_rect(self, 0, 0, width, height, 8, fill=theme.SURFACE, outline=theme.BORDER)
        gap = 6
        inner = 6
        count = 4
        segment = (width - inner * 2 - gap * (count - 1)) / count
        for index, color in enumerate(self._colors):
            x1 = inner + index * (segment + gap)
            x2 = x1 + segment
            y1 = inner
            y2 = height - inner
            base = col.to_hex(color)
            if max(color) < 6:
                base = "#161C2A"
                outline = "#222C40"
            else:
                outline = blend(base, "#FFFFFF", 0.18)
            rounded_rect(self, x1, y1, x2, y2, 5, fill=base, outline=outline, width=1)
            if max(color) >= 6:
                highlight = blend(base, "#FFFFFF", 0.35)
                self.create_line(x1 + 5, y1 + 3, x2 - 5, y1 + 3, fill=highlight, width=1)


class Switch(tk.Canvas):
    """Small iOS-style toggle bound to a BooleanVar."""

    def __init__(self, master: tk.Misc, variable: tk.BooleanVar, bg: str = theme.BG):
        super().__init__(
            master,
            width=44,
            height=24,
            bg=bg,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self._variable = variable
        self._bg = bg
        self._trace = variable.trace_add("write", lambda *_: self._draw())
        self.bind("<Button-1>", self._toggle)
        self._draw()

    def _toggle(self, _event: object = None) -> None:
        self._variable.set(not self._variable.get())

    def _draw(self) -> None:
        self.delete("all")
        on = bool(self._variable.get())
        fill = theme.ACCENT if on else theme.SURFACE_ACTIVE
        border = theme.ACCENT if on else theme.BORDER_HOVER
        rounded_rect(self, 1, 2, 43, 22, 10, fill=fill, outline=border)
        knob_x = 33 if on else 11
        self.create_oval(knob_x - 8, 4, knob_x + 8, 20, fill="#FFFFFF", outline="")

    def destroy(self) -> None:
        try:
            self._variable.trace_remove("write", self._trace)
        except Exception:
            pass
        super().destroy()


class Pill(tk.Frame):
    """Status badge (connected / demo / error)."""

    def __init__(self, master: tk.Misc, text: str, color: str, font: object, bg: str = theme.BG):
        super().__init__(master, bg=bg)
        self._bg = bg
        self._dot = tk.Canvas(self, width=10, height=10, bg=bg, highlightthickness=0, bd=0)
        self._dot.pack(side="left", padx=(10, 6), pady=7)
        self._dot_id = self._dot.create_oval(2, 2, 8, 8, fill=color, outline="")
        self._label = tk.Label(
            self,
            text=text,
            font=font,
            bg=bg,
            fg=theme.TEXT_SECONDARY,
            padx=0,
            pady=6,
        )
        self._label.pack(side="left", padx=(0, 12))
        self.configure(bg=blend(color, theme.BG, 0.86))
        self._dot.configure(bg=self.cget("bg"))
        self._label.configure(bg=self.cget("bg"))

    def set(self, text: str, color: str) -> None:
        background = blend(color, theme.BG, 0.86)
        self.configure(bg=background)
        self._dot.configure(bg=background)
        self._label.configure(bg=background, text=text)
        self._dot.itemconfigure(self._dot_id, fill=color)


class ScrollFrame(tk.Frame):
    """Vertically scrollable container with mouse-wheel support."""

    def __init__(self, master: tk.Misc, bg: str = theme.BG):
        super().__init__(master, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.scrollbar = ttk.Scrollbar(
            self,
            orient="vertical",
            command=self.canvas.yview,
            style="RGB.Vertical.TScrollbar",
        )
        self.inner = tk.Frame(self.canvas, bg=bg)
        self._window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y", padx=(10, 0))
        self.inner.bind("<Configure>", self._inner_configured)
        self.canvas.bind("<Configure>", self._canvas_configured)
        root = self.winfo_toplevel()
        self._wheel_ids = []
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self._wheel_ids.append((sequence, root.bind_all(sequence, self._wheel, add="+")))

    def _inner_configured(self, _event: object = None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _canvas_configured(self, event: object) -> None:
        self.canvas.itemconfigure(self._window, width=event.width)  # type: ignore[attr-defined]

    def _contains_pointer(self, widget: object) -> bool:
        current = widget
        while current is not None:
            if current == self:
                return True
            current = getattr(current, "master", None)
        return False

    def _wheel(self, event: object) -> None:
        try:
            if not self._contains_pointer(self.winfo_containing(event.x_root, event.y_root)):
                return
            number = getattr(event, "num", None)
            if number == 4:
                step = -2
            elif number == 5:
                step = 2
            else:
                delta = getattr(event, "delta", 0)
                step = -2 if delta > 0 else 2
            self.canvas.yview_scroll(step, "units")
        except (tk.TclError, AttributeError):
            pass

    def scroll_to_top(self) -> None:
        self.canvas.yview_moveto(0.0)

    def destroy(self) -> None:
        try:
            root = self.winfo_toplevel()
            for sequence, funcid in self._wheel_ids:
                try:
                    root.unbind(sequence, funcid)
                except tk.TclError:
                    pass
            self._wheel_ids = []
        except tk.TclError:
            pass
        super().destroy()


def separator(master: tk.Misc, bg: str = theme.BORDER) -> tk.Frame:
    return tk.Frame(master, height=1, bg=bg)
