"""
theme.py — Color palettes, theme switching, and widget registry.

The palette is an ink surface with a single mint accent. Text colors are
chosen so body copy and captions stay above a 4.5:1 contrast ratio on the
surfaces they sit on. Bright fills use dark ink for their label.

``border`` is the quiet outline of a card. ``border_strong`` is for anything the
user interacts with (inputs, ghost buttons, switch tracks): at least 3:1 against
the card, as WCAG 1.4.11 asks for UI components.
"""

import tkinter as tk

# ─────────────────────────────────────────────────────────────────────────────
# PALETTES
# ─────────────────────────────────────────────────────────────────────────────

DARK: dict[str, str] = {
    "bg":          "#0c1210",
    "bg2":         "#111916",
    "card":        "#16211c",
    "card2":       "#1c2923",
    "input":       "#0f1613",
    "border":      "#2c433b",
    "border2":     "#3e5c50",
    "border_strong": "#4f7a6a",
    "accent":      "#3dcc8e",
    "accent_dk":   "#1f8f62",
    "green":       "#3dcc8e",
    "green_dk":    "#1f8f62",
    "violet":      "#9aa7ff",
    "violet_dk":   "#7e8ef5",
    "amber":       "#f5b942",
    "red":         "#f07178",
    "text":        "#f4fbf7",
    "text2":       "#c9e0d6",
    "text3":       "#93b3a6",
    "tag_bg":      "#17382c",
    "tag_fg":      "#8ee7bf",
    "white":       "#ffffff",
    "ink":         "#10211a",
    "danger_soft": "#3a2226",
    "warn_soft":   "#3a3018",
    "ok_soft":     "#17382c",
    "mode":        "dark",
}

LIGHT: dict[str, str] = {
    "bg":          "#f3f6f4",
    "bg2":         "#e7eeea",
    "card":        "#ffffff",
    "card2":       "#f7faf8",
    "input":       "#ffffff",
    "border":      "#d5e2db",
    "border2":     "#b7c9c0",
    "border_strong": "#728a7d",
    "accent":      "#0d7a4e",
    "accent_dk":   "#0b6842",
    "green":       "#0d7a4e",
    "green_dk":    "#0b6842",
    "violet":      "#3c4cad",
    "violet_dk":   "#313e90",
    "amber":       "#8a5a00",
    "red":         "#b42318",
    "text":        "#12241c",
    "text2":       "#3c564b",
    "text3":       "#4f675c",
    "tag_bg":      "#e5f6ee",
    "tag_fg":      "#0b6842",
    "white":       "#ffffff",
    "ink":         "#10211a",
    "danger_soft": "#fdecea",
    "warn_soft":   "#fbf3df",
    "ok_soft":     "#e5f6ee",
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


def _channel(value: float) -> float:
    if value <= 0.04045:
        return value / 12.92
    return ((value + 0.055) / 1.055) ** 2.4


def luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r = _channel(int(h[0:2], 16) / 255)
    g = _channel(int(h[2:4], 16) / 255)
    b = _channel(int(h[4:6], 16) / 255)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(foreground: str, background: str) -> float:
    lighter = max(luminance(foreground), luminance(background))
    darker = min(luminance(foreground), luminance(background))
    return (lighter + 0.05) / (darker + 0.05)


def readable_fg(background: str) -> str:
    """Pick ink or white, whichever is more readable on *background*."""
    ink = C.get("ink", "#10211a")
    white = C.get("white", "#ffffff")
    return ink if contrast_ratio(ink, background) >= contrast_ratio(white, background) else white


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

# Defaults work before a Tk root exists. App startup replaces them with the
# first installed family so Linux, macOS, and Windows share one stack.
FH  = ("Segoe UI", 20, "bold")
FL  = ("Segoe UI", 12, "bold")
FS  = ("Segoe UI", 10)
FM  = ("Cascadia Mono", 10)
FB  = ("Segoe UI", 10, "bold")
FBS = ("Segoe UI", 9, "bold")
FT  = ("Segoe UI", 9)

_SANS = ("Inter", "Segoe UI Variable Text", "Segoe UI", "Cantarell", "Noto Sans", "DejaVu Sans")
_MONO = ("JetBrains Mono", "Cascadia Mono", "Cascadia Code", "SF Mono", "DejaVu Sans Mono")


def bind_fonts(root) -> None:
    """Point the shared font tuples at families that exist on this machine."""
    global FH, FL, FS, FM, FB, FBS, FT
    try:
        import tkinter.font as tkfont

        families = set(tkfont.families(root))
    except Exception:
        return
    sans = next((name for name in _SANS if name in families), "TkDefaultFont")
    mono = next((name for name in _MONO if name in families), "TkFixedFont")
    FH = (sans, 20, "bold")
    FL = (sans, 12, "bold")
    FS = (sans, 10)
    FT = (sans, 9)
    FB = (sans, 10, "bold")
    FBS = (sans, 9, "bold")
    FM = (mono, 10)
