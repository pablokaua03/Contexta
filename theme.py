"""
theme.py — Color palettes, theme switching, and widget registry.
"""

import tkinter as tk

# ─────────────────────────────────────────────────────────────────────────────
# PALETTES
# ─────────────────────────────────────────────────────────────────────────────

DARK: dict[str, str] = {
    "bg":          "#08111f",
    "bg2":         "#0d1728",
    "card":        "#101b30",
    "card2":       "#16243d",
    "input":       "#0b1526",
    "border":      "#243552",
    "border2":     "#35507a",
    "accent":      "#38bdf8",
    "accent_dk":   "#0ea5e9",
    "green":       "#10b981",
    "green_dk":    "#059669",
    "violet":      "#f97316",
    "violet_dk":   "#ea580c",
    "amber":       "#f59e0b",
    "red":         "#ef4444",
    "text":        "#e6eefb",
    "text2":       "#aac0dd",
    "text3":       "#6f86a8",
    "tag_bg":      "#102844",
    "tag_fg":      "#7dd3fc",
    "white":       "#ffffff",
    "mode":        "dark",
}

LIGHT: dict[str, str] = {
    "bg":          "#f3f7fb",
    "bg2":         "#eaf1f8",
    "card":        "#ffffff",
    "card2":       "#f8fbff",
    "input":       "#ffffff",
    "border":      "#d5e1ee",
    "border2":     "#b8cae0",
    "accent":      "#0284c7",
    "accent_dk":   "#0369a1",
    "green":       "#059669",
    "green_dk":    "#047857",
    "violet":      "#ea580c",
    "violet_dk":   "#c2410c",
    "amber":       "#d97706",
    "red":         "#dc2626",
    "text":        "#10213a",
    "text2":       "#425874",
    "text3":       "#7d93ad",
    "tag_bg":      "#dff3ff",
    "tag_fg":      "#0369a1",
    "white":       "#ffffff",
    "mode":        "light",
}

# Active theme — mutable dict, updated in place on toggle
C: dict[str, str] = dict(DARK)


def apply_theme(theme: dict[str, str]) -> None:
    """Switch the active theme in place."""
    C.clear()
    C.update(theme)


def toggle_theme() -> None:
    """Toggle between dark and light."""
    apply_theme(LIGHT if C["mode"] == "dark" else DARK)


def darken(hex_color: str, amount: int = 25) -> str:
    """Return a darker shade of *hex_color*."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"#{max(0, r - amount):02x}{max(0, g - amount):02x}{max(0, b - amount):02x}"


# ─────────────────────────────────────────────────────────────────────────────
# WIDGET REGISTRY — live theme repaint
# ─────────────────────────────────────────────────────────────────────────────

class ThemeRegistry:
    _entries: list[tuple] = []

    @classmethod
    def register(cls, widget, cfg_fn) -> None:
        cls._entries.append((widget, cfg_fn))

    @classmethod
    def repaint(cls) -> None:
        dead = []
        for i, (w, fn) in enumerate(cls._entries):
            try:
                fn(w)
            except tk.TclError:
                dead.append(i)
        for i in reversed(dead):
            cls._entries.pop(i)

    @classmethod
    def reset(cls) -> None:
        cls._entries.clear()


def reg(widget, cfg_fn):
    """Register a widget for theme repainting and return it."""
    ThemeRegistry.register(widget, cfg_fn)
    return widget


# ─────────────────────────────────────────────────────────────────────────────
# FONTS
# ─────────────────────────────────────────────────────────────────────────────

FH  = ("Segoe UI Semibold", 18)  # hero title
FL  = ("Segoe UI Semibold", 11)  # section label
FS  = ("Segoe UI", 9)            # small / caption
FM  = ("Consolas", 9)            # mono
FB  = ("Segoe UI Semibold", 10)  # button primary
FBS = ("Segoe UI Semibold", 9)   # button secondary
FT  = ("Segoe UI", 8)            # tag / badge
