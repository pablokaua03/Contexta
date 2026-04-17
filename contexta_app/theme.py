"""
theme.py — Color palettes, theme switching, and widget registry.
"""

import tkinter as tk

# ─────────────────────────────────────────────────────────────────────────────
# PALETTES
# ─────────────────────────────────────────────────────────────────────────────

DARK: dict[str, str] = {
    "bg":          "#091512",
    "bg2":         "#0f1f1b",
    "card":        "#11231d",
    "card2":       "#173029",
    "input":       "#0d1b18",
    "border":      "#244339",
    "border2":     "#326053",
    "accent":      "#44d39a",
    "accent_dk":   "#27b27c",
    "green":       "#44d39a",
    "green_dk":    "#1fa56f",
    "violet":      "#4f6f66",
    "violet_dk":   "#435e56",
    "amber":       "#f59e0b",
    "red":         "#ef4444",
    "text":        "#eefaf5",
    "text2":       "#bdd9d0",
    "text3":       "#7aa196",
    "tag_bg":      "#173129",
    "tag_fg":      "#86e7bf",
    "white":       "#ffffff",
    "mode":        "dark",
}

LIGHT: dict[str, str] = {
    "bg":          "#eef7f3",
    "bg2":         "#e2efe9",
    "card":        "#ffffff",
    "card2":       "#f7fbf9",
    "input":       "#ffffff",
    "border":      "#d2e2db",
    "border2":     "#bdd1c8",
    "accent":      "#1f9f6d",
    "accent_dk":   "#197f57",
    "green":       "#1f9f6d",
    "green_dk":    "#197f57",
    "violet":      "#5d746c",
    "violet_dk":   "#4d615a",
    "amber":       "#d97706",
    "red":         "#dc2626",
    "text":        "#143127",
    "text2":       "#4f6d63",
    "text3":       "#7e968d",
    "tag_bg":      "#e0f2ea",
    "tag_fg":      "#1f9f6d",
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

FH  = ("Segoe UI Variable Display Semibold", 19)  # hero title
FL  = ("Segoe UI Variable Display Semibold", 12)  # section label
FS  = ("Segoe UI Variable Text", 10)              # small / caption
FM  = ("Cascadia Mono", 10)                       # mono
FB  = ("Segoe UI Variable Display Semibold", 10)  # button primary
FBS = ("Segoe UI Variable Display Semibold", 9)   # button secondary
FT  = ("Segoe UI Variable Text", 9)               # tag / badge
