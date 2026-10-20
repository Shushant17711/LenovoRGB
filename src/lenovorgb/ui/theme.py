"""Visual language for the desktop app."""

from __future__ import annotations

from typing import Any, Dict

BG = "#080A0F"
BG_ELEVATED = "#0C1017"
SURFACE = "#111725"
SURFACE_HOVER = "#161F30"
SURFACE_ACTIVE = "#1A2438"
BORDER = "#202B3F"
BORDER_HOVER = "#30405C"
TEXT = "#EFF4FC"
TEXT_SECONDARY = "#A6B3C9"
MUTED = "#78869F"

ACCENT = "#22D3EE"
ACCENT_DARK = "#0B2B34"
ACCENT_SOFT = "#155E6B"
VIOLET = "#8B5CF6"
SUCCESS = "#34D399"
WARNING = "#FBBF24"
DANGER = "#F87171"

CATEGORY_COLORS: Dict[str, str] = {
    "reactive": "#22D3EE",
    "system": "#34D399",
    "ambient": "#A78BFA",
    "effects": "#F472B6",
    "utility": "#94A3B8",
}


class Fonts:
    """Resolved fonts for the current OS."""

    def __init__(self, root: Any):
        import tkinter.font as tkfont

        available = {name.lower(): name for name in tkfont.families(root)}

        def pick(*candidates: str) -> str:
            for candidate in candidates:
                if candidate.lower() in available:
                    return available[candidate.lower()]
            return "TkDefaultFont"

        family = pick(
            "Inter",
            "Segoe UI Variable Text",
            "Segoe UI",
            "SF Pro Text",
            "Ubuntu",
            "Cantarell",
            "Noto Sans",
            "DejaVu Sans",
        )
        mono = pick(
            "JetBrains Mono",
            "Cascadia Mono",
            "Consolas",
            "Ubuntu Mono",
            "DejaVu Sans Mono",
        )
        self.family = family
        self.title = (family, 17, "bold")
        self.subtitle = (family, 9)
        self.heading = (family, 12, "bold")
        self.section = (family, 8, "bold")
        self.body = (family, 10)
        self.body_strong = (family, 10, "bold")
        self.card_title = (family, 10, "bold")
        self.card_body = (family, 9)
        self.small = (family, 8)
        self.button = (family, 9, "bold")
        self.preview = (mono, 9)
        self.mono = (mono, 9)


def apply_ttk_theme(root: Any, fonts: Fonts) -> Any:
    """Dark styling for the few native widgets we use (slider, entry...)."""
    from tkinter import ttk

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass

    style.configure(
        "RGB.Horizontal.TScale",
        background=BG,
        troughcolor=SURFACE_ACTIVE,
        bordercolor=BG,
        lightcolor=ACCENT,
        darkcolor=ACCENT,
        sliderrelief="flat",
        sliderlength=18,
        gripcount=0,
    )
    style.map(
        "RGB.Horizontal.TScale",
        background=[("active", BG)],
        lightcolor=[("active", ACCENT)],
        darkcolor=[("active", ACCENT)],
    )

    style.configure(
        "RGB.TEntry",
        fieldbackground=SURFACE_ALT_FIELD,
        background=SURFACE_ALT_FIELD,
        foreground=TEXT,
        insertcolor=TEXT,
        bordercolor=BORDER,
        lightcolor=BORDER,
        darkcolor=BORDER,
        padding=6,
        font=fonts.body,
    )
    style.map(
        "RGB.TEntry",
        bordercolor=[("focus", ACCENT)],
        lightcolor=[("focus", ACCENT)],
        darkcolor=[("focus", ACCENT)],
    )

    style.configure(
        "RGB.TCombobox",
        fieldbackground=SURFACE_ALT_FIELD,
        background=SURFACE_ALT_FIELD,
        foreground=TEXT,
        arrowcolor=TEXT_SECONDARY,
        bordercolor=BORDER,
        lightcolor=BORDER,
        darkcolor=BORDER,
        padding=5,
        font=fonts.body,
    )
    style.map(
        "RGB.TCombobox",
        fieldbackground=[("readonly", SURFACE_ALT_FIELD)],
        foreground=[("readonly", TEXT)],
        selectbackground=[("readonly", SURFACE_ALT_FIELD)],
        selectforeground=[("readonly", TEXT)],
        bordercolor=[("focus", ACCENT)],
    )
    root.option_add("*TCombobox*Listbox.background", SURFACE)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT_SOFT)
    root.option_add("*TCombobox*Listbox.selectForeground", TEXT)

    style.configure(
        "RGB.Vertical.TScrollbar",
        background=SURFACE_ACTIVE,
        troughcolor=BG,
        bordercolor=BG,
        arrowcolor=MUTED,
        width=8,
    )
    style.map("RGB.Vertical.TScrollbar", background=[("active", BORDER_HOVER)])

    style.configure("RGB.TCheckbutton", background=BG, foreground=TEXT, font=fonts.body)
    return style


SURFACE_ALT_FIELD = "#0E1420"
