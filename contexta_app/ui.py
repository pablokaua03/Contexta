"""
ui.py - Premium Tkinter GUI for Contexta.
"""

from __future__ import annotations

import base64
import struct
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from contexta_app.context_engine import (
    AI_PROFILE_OPTIONS,
    APP_NAME,
    COMPRESSION_OPTIONS,
    CONTEXT_MODE_OPTIONS,
    MODEL_PROMPT_GUIDANCE,
    PACK_DEFAULTS,
    PACK_OPTIONS,
    TASK_PROFILE_OPTIONS,
)
from contexta_app.renderer import __version__, generate_markdown, section_titles_for_preview
from contexta_app.scanner import build_tree, count_files, get_git_changed_files, load_gitignore_patterns
from contexta_app.theme import C, FB, FBS, FH, FL, FM, FS, FT, ThemeRegistry, contrast_ratio, darken, readable_fg, reg, toggle_theme
from contexta_app.utils import get_desktop, safe_project_name

try:
    from contexta_app.embedded_icon_data import EMBEDDED_ICON_PNG_BASE64 as EMBEDDED_ICON_PNG_BASE64_FALLBACK
except Exception:
    EMBEDDED_ICON_PNG_BASE64_FALLBACK = ""


PACK_HELP = {
    "custom": "Leaves every control in your hands without forcing a workflow.",
    "chatgpt": "Good general-purpose preset for everyday ChatGPT-assisted work.",
    "onboarding": "Best first stop to understand a new codebase fast.",
    "debug": "Pushes changed and suspicious files to the top for bug hunting.",
    "bugfix": "Daily bug-fix pack for a coding agent: failing area, nearby code, and related tests.",
    "pr_review": "Shapes the pack around code review, risk spotting, and recent changes.",
    "risk_review": "Highlights likely weak spots, regression surfaces, missing test coverage, and shared modules with broader impact.",
    "frontend": "Biases the selection toward interface flows, views, widgets, and user-facing assets.",
    "backend": "Biases the selection toward non-UI application logic, data flow, and integration-heavy modules.",
    "changes_related": "Starts from recent changes and expands outward to the most relevant nearby files.",
    "refactor": "Collects the modules to change and the files connected to them.",
    "raw_files": "Dumps the most important files with path + full content. Clean and simple — ideal for pasting into any AI.",
}

MODE_HELP = {
    "full": "Includes as much useful project context as possible.",
    "debug": "Prefers hotspots, recent edits, and files near the reported issue.",
    "feature": "Curates files around the feature or area named in Focus.",
    "diff": "Starts from git changes and expands only where it adds context.",
    "onboarding": "Builds a clean project tour with architecture and entry points.",
    "refactor": "Collects core modules plus the files they are connected to.",
}

AI_HELP = {key: str(entry["summary"]) for key, entry in MODEL_PROMPT_GUIDANCE.items()}


def format_model_guidance(profile: str) -> str:
    guidance = MODEL_PROMPT_GUIDANCE.get(profile, MODEL_PROMPT_GUIDANCE["generic"])
    lines = [
        str(guidance["label"]),
        "- Usually works well:",
    ]
    lines.extend(f"  - {entry}" for entry in guidance["works_well"])
    lines.append("- Usually avoid:")
    lines.extend(f"  - {entry}" for entry in guidance["avoid"])
    lines.append("- Rough usage profile:")
    lines.extend(f"  - {entry}" for entry in guidance["usage"])
    return "\n".join(lines)

TASK_HELP = {
    "general": "Keeps the export broadly useful for follow-up questions and implementation work.",
    "ai_handoff": "Prepares a pack that another AI can pick up quickly with minimal extra prompting.",
    "explain_project": "Prioritizes architecture, purpose, and how the project fits together.",
    "bug_report": "Emphasizes suspicious files, flows, and recent changes tied to a bug.",
    "code_review": "Frames the export for quality, risk, and code review feedback.",
    "refactor_request": "Emphasizes central modules and coupling for refactor ideas.",
    "write_tests": "Highlights behaviors, entry points, and related tests for test generation.",
    "find_dead_code": "Pushes utilities, disconnected modules, and unused-looking files higher.",
    "pr_summary": "Shapes the pack so an AI can summarize a PR or a set of changes quickly.",
    "risk_analysis": "Highlights likely regression hotspots, broad-impact modules, maintenance weak spots, and missing coverage.",
}

COMPRESSION_HELP = {
    "full": "Keep full file payloads and add guidance around them. Best when fidelity matters more than token cost.",
    "balanced": "Mix summaries, key excerpts, and full payloads for the most important files.",
    "focused": "Trim aggressively and keep only the parts most likely to matter for the task.",
    "signatures": "Prefer structural summaries and signatures when you need a rapid, low-token project map.",
    "lean": "Minimum token usage: metadata and up to 5 signatures per file. Inline blobs and large literals are always omitted. Best for quick orientation or API budget constraints.",
}

OPTION_GUIDE = (
    "Hidden files: include dotfiles and hidden folders like .env or .github.\n"
    "Unknown extensions: include files with uncommon or extensionless names.\n"
    "Prefer recent git changes: prioritize modified files during selection.\n"
    "Staged only: when diff mode is on, use only git staged changes.\n"
    "Copy latest pack: automatically copy the generated Markdown to the clipboard."
)

SCROLL_TARGET_ATTR = "_contexta_scroll_target"
EMBEDDED_ICON_PNG_BASE64 = "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"


def resolve_pack_focus(current_focus: str, previous_auto_focus: str, preset_focus: str) -> tuple[str, str]:
    current = current_focus.strip()
    previous = previous_auto_focus.strip()
    preset = preset_focus.strip()

    if not current or current == previous:
        return preset, preset
    return current, previous


def normalize_mousewheel_units(event) -> int:
    num = getattr(event, "num", None)
    if num == 4:
        return -1
    if num == 5:
        return 1

    delta = int(getattr(event, "delta", 0) or 0)
    if delta == 0:
        return 0
    if abs(delta) >= 120:
        units = int(-delta / 120)
        if units:
            return units
    return -1 if delta > 0 else 1


def walk_widget_ancestors(widget):
    current = widget
    while current is not None:
        yield current
        try:
            parent_name = current.winfo_parent()
        except Exception:
            return
        if not parent_name:
            return
        try:
            current = current.nametowidget(parent_name)
        except Exception:
            return


def can_scroll_target(target, units: int) -> bool:
    if units == 0 or not hasattr(target, "yview"):
        return False
    try:
        first, last = target.yview()
    except Exception:
        return True
    if units < 0:
        return first > 0.0
    return last < 1.0


def resolve_scroll_target(widget, units: int = 0):
    fallback = None
    for candidate in walk_widget_ancestors(widget):
        target = getattr(candidate, SCROLL_TARGET_ATTR, None)
        if target is None:
            continue
        if fallback is None:
            fallback = target
        if units == 0 or can_scroll_target(target, units):
            return target
    return fallback


def estimate_selected_files(total_files: int, changed_files: int, mode_key: str, has_focus: bool) -> int:
    if total_files <= 0:
        return 0
    if mode_key == "full":
        return total_files
    if mode_key == "diff":
        return min(max(changed_files * 2, changed_files or 0), min(total_files, 20))
    if mode_key == "debug":
        return min(max((changed_files * 3) if changed_files else 8, 8), min(total_files, 20))
    if mode_key == "feature":
        return min(12 if has_focus else 10, min(total_files, 20))
    if mode_key == "refactor":
        return min(16, min(total_files, 20))
    if mode_key == "onboarding":
        return min(10, min(total_files, 12))
    return min(12, min(total_files, 20))


def estimate_tokens_for_preview(selected_files: int, compression_key: str) -> int:
    per_file = {
        "full": 900,
        "balanced": 430,
        "focused": 230,
        "signatures": 130,
        "lean": 65,
    }.get(compression_key, 430)
    overhead = 1400
    return max(0, overhead + (selected_files * per_file))


def format_token_k(tokens: int) -> str:
    return f"~{tokens / 1000:.1f}k"


def _icon_path() -> Path | None:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    candidates = [root / "icon.ico", root / "assets" / "icon.ico"]
    for icon in candidates:
        if icon.is_file():
            return icon
    return None


def _window_icon_source() -> str | None:
    icon = _icon_path()
    if icon:
        return str(icon)
    if sys.platform == "win32" and getattr(sys, "frozen", False):
        return str(Path(sys.executable))
    return None


def _enable_windows_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def _set_windows_app_id() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Contexta.Contexta")
    except Exception:
        pass


def _extract_icon_png(icon_path: Path) -> bytes | None:
    try:
        data = icon_path.read_bytes()
    except OSError:
        return None

    if len(data) < 6:
        return None

    reserved, icon_type, count = struct.unpack_from("<HHH", data, 0)
    if reserved != 0 or icon_type != 1 or count < 1:
        return None

    best_entry: tuple[int, bytes] | None = None
    for index in range(count):
        offset = 6 + index * 16
        if offset + 16 > len(data):
            continue
        width, height, _colors, _reserved, _planes, _bitcount, size, data_offset = struct.unpack_from("<BBBBHHII", data, offset)
        if data_offset + size > len(data):
            continue
        blob = data[data_offset : data_offset + size]
        if not blob.startswith(b"\x89PNG\r\n\x1a\n"):
            continue
        edge = max(width or 256, height or 256)
        if best_entry is None or edge > best_entry[0]:
            best_entry = (edge, blob)

    return best_entry[1] if best_entry else None


def _load_icon_photo(target_px: int | None = None) -> tk.PhotoImage | None:
    icon = _icon_path()
    png_bytes = _extract_icon_png(icon) if icon else None
    png_b64 = base64.b64encode(png_bytes).decode("ascii") if png_bytes else (EMBEDDED_ICON_PNG_BASE64_FALLBACK or EMBEDDED_ICON_PNG_BASE64)
    try:
        photo = tk.PhotoImage(data=png_b64, format="png")
    except tk.TclError:
        return None
    if target_px and photo.width() > target_px:
        factor = max(1, round(photo.width() / target_px))
        if factor > 1:
            photo = photo.subsample(factor, factor)
    return photo


def _apply_window_icon(window: tk.Misc, icon_photo: tk.PhotoImage | None) -> None:
    if icon_photo:
        try:
            window.iconphoto(True, icon_photo)
        except Exception:
            pass
    icon_source = _window_icon_source()
    if icon_source:
        try:
            window.wm_iconbitmap(icon_source)
        except Exception:
            pass
        try:
            window.iconbitmap(default=icon_source)
        except Exception:
            pass
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            source = Path(sys.executable if getattr(sys, "frozen", False) else (icon_source or ""))
            if source.is_file():
                large = wintypes.HICON()
                small = wintypes.HICON()
                extracted = ctypes.windll.shell32.ExtractIconExW(str(source), 0, ctypes.byref(large), ctypes.byref(small), 1)
                if extracted:
                    window._contexta_hicon_big = large.value
                    window._contexta_hicon_small = small.value
                    ctypes.windll.user32.SendMessageW(window.winfo_id(), 0x0080, 1, large.value)
                    ctypes.windll.user32.SendMessageW(window.winfo_id(), 0x0080, 0, small.value)
        except Exception:
            pass


class BrandMark(tk.Canvas):
    SIZE = 40

    def __init__(self, parent):
        super().__init__(parent, width=self.SIZE, height=self.SIZE, highlightthickness=0, bd=0, bg=C["card"])
        reg(self, lambda w: w._draw())
        self._draw()

    def _draw(self):
        self.delete("all")
        self.configure(bg=C["card"])
        self.create_oval(1, 1, self.SIZE - 1, self.SIZE - 1, fill=C["tag_bg"], outline=C["tag_bg"])
        self.create_rectangle(13, 11, 28, 30, outline=C["accent"], width=2)
        self.create_line(16, 17, 25, 17, fill=C["accent"], width=1.6, capstyle="round")
        self.create_line(16, 21, 23, 21, fill=C["accent"], width=1.6, capstyle="round")
        self.create_line(16, 25, 24, 25, fill=C["accent"], width=1.6, capstyle="round")


class FlatBtn(tk.Frame):
    def __init__(self, parent, text: str, color_key: str, command, font=None, padx: int = 16, pady: int = 8, surface_key: str = "bg", variant: str = "solid"):
        super().__init__(parent, bg=C[surface_key], highlightthickness=0, bd=0)
        self._color_key = color_key
        self._surface_key = surface_key
        self._variant = variant
        self._enabled = True
        self._hover = False
        self._btn = tk.Button(
            self,
            text=text,
            font=font or FB,
            relief="flat",
            bd=0,
            padx=padx,
            pady=pady,
            cursor="hand2",
            command=command,
            takefocus=1,
        )
        self._btn.pack(fill="both", expand=True)
        self._btn.bind("<Enter>", self._hover_on)
        self._btn.bind("<Leave>", self._hover_off)
        reg(self, lambda w: w._repaint())
        self._repaint()

    def _palette(self):
        if not self._enabled:
            return C["card2"], C["text3"], C["border"]
        if self._variant == "ghost":
            bg = C["card2"] if self._hover else C[self._surface_key]
            return bg, C["text"], C["border"]
        if self._variant == "soft":
            bg = C["accent"] if self._hover else C["tag_bg"]
            fg = readable_fg(bg) if self._hover else C["tag_fg"]
            return bg, fg, C["tag_bg"]
        bg = darken(C[self._color_key], 14) if self._hover else C[self._color_key]
        return bg, readable_fg(bg), bg

    def _repaint(self):
        bg, fg, border = self._palette()
        super().configure(bg=C[self._surface_key], highlightthickness=1 if self._variant == "ghost" else 0, highlightbackground=border)
        self._btn.configure(
            bg=bg,
            fg=fg,
            activebackground=bg,
            activeforeground=fg,
            highlightthickness=1,
            highlightbackground=bg,
            highlightcolor=C["accent"],
            disabledforeground=C["text3"],
            cursor="hand2" if self._enabled else "arrow",
        )

    def _hover_on(self, _=None):
        self._hover = True
        if self._enabled:
            self._repaint()

    def _hover_off(self, _=None):
        self._hover = False
        if self._enabled:
            self._repaint()

    def configure(self, **kw):
        if "state" in kw:
            self._enabled = kw.pop("state") != "disabled"
            self._btn.configure(state="normal" if self._enabled else "disabled")
            self._repaint()
        if "text" in kw:
            self._btn.configure(text=kw.pop("text"))
        if kw:
            super().configure(**kw)


class Card(tk.Frame):
    def __init__(self, parent, pad: int = 16):
        super().__init__(parent, bg=C["card"], highlightthickness=1, highlightbackground=C["border"], bd=0)
        self._pad = pad
        reg(self, lambda w: w.configure(bg=C["card"], highlightbackground=C["border"]))

    def inner(self):
        frame = tk.Frame(self, bg=C["card"])
        frame.pack(fill="both", expand=True, padx=self._pad, pady=self._pad)
        reg(frame, lambda w: w.configure(bg=C["card"]))
        return frame


class ScrollArea(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=C["bg"])
        reg(self, lambda w: w._repaint())

        self._canvas = tk.Canvas(self, bg=C["bg"], highlightthickness=0, bd=0)
        self._canvas.pack(side="left", fill="both", expand=True)
        reg(self._canvas, lambda w: w.configure(bg=C["bg"]))

        self._scrollbar = ttk.Scrollbar(self, orient="vertical", command=self._canvas.yview)
        self._scrollbar.pack(side="right", fill="y")
        self._canvas.configure(yscrollcommand=self._scrollbar.set)

        self.content = tk.Frame(self._canvas, bg=C["bg"])
        reg(self.content, lambda w: w.configure(bg=C["bg"]))
        self._window = self._canvas.create_window((0, 0), window=self.content, anchor="nw")

        self.content.bind("<Configure>", self._on_content_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)

    def _repaint(self):
        self.configure(bg=C["bg"])
        self._canvas.configure(bg=C["bg"])
        self.content.configure(bg=C["bg"])

    def _on_content_configure(self, _event=None):
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))
        self._sync_scrollbar()

    def _sync_scrollbar(self):
        bbox = self._canvas.bbox("all")
        if not bbox:
            return
        content_height = bbox[3] - bbox[1]
        needs_scroll = content_height > self._canvas.winfo_height() + 2
        mapped = bool(self._scrollbar.winfo_ismapped())
        if needs_scroll and not mapped:
            self._scrollbar.pack(side="right", fill="y")
        elif mapped and not needs_scroll:
            self._scrollbar.pack_forget()

    def _on_canvas_configure(self, event):
        self._canvas.itemconfigure(self._window, width=event.width)
        self._sync_scrollbar()


class Toggle(tk.Frame):
    WIDTH = 40
    HEIGHT = 24

    def __init__(self, parent, text: str, variable: tk.BooleanVar):
        super().__init__(parent, bg=C["card"])
        self._var = variable
        self._enabled = True
        self._canvas = tk.Canvas(
            self,
            width=self.WIDTH,
            height=self.HEIGHT,
            highlightthickness=1,
            highlightbackground=C["card"],
            highlightcolor=C["accent"],
            bg=C["card"],
            cursor="hand2",
            takefocus=1,
        )
        self._canvas.pack(side="left")
        self._label = tk.Label(self, text=text, font=FS, bg=C["card"], fg=C["text2"], cursor="hand2")
        self._label.pack(side="left", padx=(10, 0))
        for widget in (self, self._canvas, self._label):
            widget.bind("<Button-1>", self._toggle)
        self._canvas.bind("<space>", self._toggle)
        self._canvas.bind("<Return>", self._toggle)
        reg(self, lambda w: w._repaint())
        self._draw()

    def _repaint(self):
        self.configure(bg=C["card"])
        self._canvas.configure(
            bg=C["card"],
            highlightbackground=C["card"],
            highlightcolor=C["accent"],
            cursor="hand2" if self._enabled else "arrow",
        )
        self._label.configure(bg=C["card"], fg=C["text"] if self._enabled else C["text3"], cursor="hand2" if self._enabled else "arrow")
        self._draw()

    def _draw(self):
        self._canvas.delete("all")
        radius = self.HEIGHT // 2
        track = C["accent"] if self._var.get() and self._enabled else C["border2"]
        if not self._enabled:
            track = C["border"]
        self._canvas.create_oval(0, 0, self.HEIGHT, self.HEIGHT, fill=track, outline=track)
        self._canvas.create_oval(self.WIDTH - self.HEIGHT, 0, self.WIDTH, self.HEIGHT, fill=track, outline=track)
        self._canvas.create_rectangle(radius, 0, self.WIDTH - radius, self.HEIGHT, fill=track, outline=track)
        knob_x = self.WIDTH - radius if self._var.get() else radius
        self._canvas.create_oval(knob_x - radius + 3, 3, knob_x + radius - 3, self.HEIGHT - 3, fill=C["white"], outline="")

    def _toggle(self, _=None):
        if not self._enabled:
            return
        self._var.set(not self._var.get())
        self._draw()

    def configure(self, **kw):
        if "state" in kw:
            self._enabled = kw.pop("state") != "disabled"
            self._repaint()
        if kw:
            super().configure(**kw)


class ThemeToggleBtn(tk.Canvas):
    SIZE = 34

    def __init__(self, parent, command):
        super().__init__(
            parent,
            width=self.SIZE,
            height=self.SIZE,
            highlightthickness=1,
            highlightbackground=C["card"],
            highlightcolor=C["accent"],
            bd=0,
            bg=C["card"],
            cursor="hand2",
            takefocus=1,
        )
        self._command = command
        self.bind("<Button-1>", lambda _: self._command())
        self.bind("<Return>", lambda _: self._command())
        self.bind("<space>", lambda _: self._command())
        self.bind("<Enter>", lambda _: self._draw(True))
        self.bind("<Leave>", lambda _: self._draw(False))
        reg(self, lambda w: w._draw(False))
        self._draw(False)

    def _draw(self, hover: bool):
        self.delete("all")
        self.configure(bg=C["card"], highlightbackground=C["card"], highlightcolor=C["accent"])
        color = C["accent"] if hover else C["text2"]
        center = self.SIZE // 2
        self.create_oval(2, 2, self.SIZE - 2, self.SIZE - 2, fill=C["bg2"], outline=C["border"])
        if C["mode"] == "dark":
            self.create_oval(center - 4, center - 4, center + 4, center + 4, fill=color, outline=color)
            for x1, y1, x2, y2 in (
                (center, 4, center, 7),
                (center, self.SIZE - 4, center, self.SIZE - 7),
                (4, center, 7, center),
                (self.SIZE - 4, center, self.SIZE - 7, center),
                (7, 7, 9, 9),
                (self.SIZE - 7, 7, self.SIZE - 9, 9),
                (7, self.SIZE - 7, 9, self.SIZE - 9),
                (self.SIZE - 7, self.SIZE - 7, self.SIZE - 9, self.SIZE - 9),
            ):
                self.create_line(x1, y1, x2, y2, fill=color, width=1.6, capstyle="round")
        else:
            self.create_oval(center - 6, center - 6, center + 6, center + 6, fill=color, outline=color)
            self.create_oval(center - 2, center - 7, center + 7, center + 5, fill=C["bg2"], outline=C["bg2"])


class Segmented(tk.Frame):
    """Two-option switch used by the preview and result panes."""

    def __init__(self, parent, choices: list[tuple[str, str]], on_change):
        super().__init__(parent, bg=C["bg2"], highlightthickness=1, highlightbackground=C["border"], bd=0)
        self._on_change = on_change
        self._current = choices[0][0]
        self._buttons: dict[str, tk.Button] = {}
        for key, label in choices:
            button = tk.Button(
                self,
                text=label,
                font=FBS,
                relief="flat",
                bd=0,
                padx=12,
                pady=5,
                cursor="hand2",
                takefocus=1,
                command=lambda selected=key: self.set(selected, notify=True),
            )
            button.pack(side="left")
            self._buttons[key] = button
        reg(self, lambda w: w._repaint())
        self._repaint()

    def set(self, key: str, notify: bool = False):
        if key not in self._buttons:
            return
        self._current = key
        self._repaint()
        if notify:
            self._on_change(key)

    def _repaint(self):
        self.configure(bg=C["bg2"], highlightbackground=C["border"])
        for key, button in self._buttons.items():
            active = key == self._current
            bg = C["card"] if active else C["bg2"]
            fg = C["text"] if active else C["text3"]
            button.configure(bg=bg, fg=fg, activebackground=bg, activeforeground=fg, highlightthickness=0)


class StatChip(tk.Frame):
    def __init__(self, parent, label: str):
        super().__init__(parent, bg=C["bg2"], highlightthickness=1, highlightbackground=C["border"], bd=0)
        inner = tk.Frame(self, bg=C["bg2"])
        inner.pack(fill="both", expand=True, padx=12, pady=8)
        self._inner = inner
        self._value = tk.Label(inner, text="—", font=FL, bg=C["bg2"], fg=C["text"], anchor="w")
        self._value.pack(anchor="w")
        self._caption = tk.Label(inner, text=label, font=FT, bg=C["bg2"], fg=C["text3"], anchor="w")
        self._caption.pack(anchor="w", pady=(2, 0))
        reg(self, lambda w: w._repaint())

    def set(self, value: str):
        self._value.configure(text=value)

    def _repaint(self):
        self.configure(bg=C["bg2"], highlightbackground=C["border"])
        self._inner.configure(bg=C["bg2"])
        self._value.configure(bg=C["bg2"], fg=C["text"])
        self._caption.configure(bg=C["bg2"], fg=C["text3"])


class App(tk.Tk):
    def __init__(self):
        _set_windows_app_id()
        _enable_windows_dpi_awareness()
        super().__init__()
        self.title(f"{APP_NAME} v{__version__}")
        self.configure(bg=C["bg"])
        self.geometry("1200x820")
        self.minsize(1040, 700)
        self.resizable(True, True)
        self._bind_runtime_fonts()

        self._project_path: Path | None = None
        self._running = False
        self._last_md = ""
        self._last_output: Path | None = None
        self._help_window: tk.Toplevel | None = None
        self._status_pair = ("tag_bg", "tag_fg")
        self._banner_tone: str | None = None
        self._icon_photo = _load_icon_photo()
        self._brand_logo = _load_icon_photo(40)
        _apply_window_icon(self, self._icon_photo)

        self._setup_ttk()
        self._init_vars()
        self._build_ui()
        self._setup_scroll_routing()
        self._configure_scaling()
        self._apply_pack_profile()
        self._sync_option_states()
        self._refresh_preview()
        self._center()

    def _init_vars(self):
        self._combo_widgets: dict[str, tuple[tk.Variable, ttk.Combobox, dict[str, str]]] = {}
        self._last_auto_focus = ""
        self._preview_snapshot: dict[str, int] | None = None
        self._path_var = tk.StringVar()
        self._focus_var = tk.StringVar()
        self._pack_var = tk.StringVar(value="onboarding")
        self._mode_var = tk.StringVar(value="onboarding")
        self._ai_var = tk.StringVar(value="generic")
        self._task_var = tk.StringVar(value="explain_project")
        self._compression_var = tk.StringVar(value="balanced")
        self._hidden_var = tk.BooleanVar()
        self._unknown_var = tk.BooleanVar()
        self._diff_var = tk.BooleanVar()
        self._staged_var = tk.BooleanVar()
        self._copy_var = tk.BooleanVar(value=True)

    def _bind_runtime_fonts(self):
        import contexta_app.theme as theme_mod

        theme_mod.bind_fonts(self)
        global FH, FL, FS, FM, FB, FBS, FT
        FH = theme_mod.FH
        FL = theme_mod.FL
        FS = theme_mod.FS
        FM = theme_mod.FM
        FB = theme_mod.FB
        FBS = theme_mod.FBS
        FT = theme_mod.FT

    def _setup_ttk(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "TCombobox",
            padding=(8, 7),
            font=FS,
            fieldbackground=C["input"],
            background=C["card"],
            foreground=C["text"],
            bordercolor=C["border"],
            arrowcolor=C["text2"],
            lightcolor=C["input"],
            darkcolor=C["input"],
            insertcolor=C["accent"],
            relief="flat",
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", C["input"])],
            foreground=[("readonly", C["text"])],
            selectbackground=[("readonly", C["input"])],
            selectforeground=[("readonly", C["text"])],
        )
        style.configure("TProgressbar", troughcolor=C["bg2"], background=C["accent"], bordercolor=C["bg2"], lightcolor=C["accent"], darkcolor=C["accent"], thickness=6)
        style.configure("TScrollbar", troughcolor=C["bg"], background=C["border2"], arrowcolor=C["text3"], bordercolor=C["bg"], relief="flat")

    def _refresh_ttk(self):
        self._setup_ttk()

    def _configure_scaling(self):
        try:
            dpi_scale = max(self.winfo_fpixels("1i") / 72.0, 1.0)
            self.tk.call("tk", "scaling", dpi_scale)
        except Exception:
            pass

    def _build_ui(self):
        ThemeRegistry.reset()

        header = tk.Frame(self, bg=C["card"])
        header.pack(fill="x")
        reg(header, lambda w: w.configure(bg=C["card"]))

        header_inner = tk.Frame(header, bg=C["card"])
        header_inner.pack(fill="both", expand=True, padx=20, pady=(14, 14))
        reg(header_inner, lambda w: w.configure(bg=C["card"]))

        left = tk.Frame(header_inner, bg=C["card"])
        left.pack(side="left", fill="x", expand=True)
        reg(left, lambda w: w.configure(bg=C["card"]))

        if self._brand_logo:
            brand = tk.Label(left, image=self._brand_logo, bg=C["card"])
            brand.pack(side="left", padx=(0, 12))
            reg(brand, lambda w: w.configure(bg=C["card"]))
        else:
            BrandMark(left).pack(side="left", padx=(0, 12))

        titles = tk.Frame(left, bg=C["card"])
        titles.pack(side="left", fill="x", expand=True)
        reg(titles, lambda w: w.configure(bg=C["card"]))

        title = tk.Label(titles, text=APP_NAME, font=FH, bg=C["card"], fg=C["text"])
        title.pack(anchor="w")
        reg(title, lambda w: w.configure(bg=C["card"], fg=C["text"]))

        subtitle = tk.Label(
            titles,
            text="Context packs for debugging, reviews, onboarding, and AI handoffs.",
            font=FS,
            bg=C["card"],
            fg=C["text2"],
            wraplength=640,
            justify="left",
        )
        subtitle.pack(anchor="w", pady=(2, 0))
        reg(subtitle, lambda w: w.configure(bg=C["card"], fg=C["text2"]))

        right = tk.Frame(header_inner, bg=C["card"])
        right.pack(side="right")
        reg(right, lambda w: w.configure(bg=C["card"]))

        self._version_badge = tk.Label(right, text=f"v{__version__}", font=FT, bg=C["tag_bg"], fg=C["tag_fg"], padx=10, pady=4)
        self._version_badge.pack(side="right", padx=(12, 0))
        reg(self._version_badge, lambda w: w.configure(bg=C["tag_bg"], fg=C["tag_fg"]))
        self._help_btn = FlatBtn(right, "Guide", "violet", self._open_help, font=FBS, padx=12, pady=6, surface_key="card", variant="ghost")
        self._help_btn.pack(side="right", padx=(8, 0))
        theme_box = tk.Frame(right, bg=C["card"])
        theme_box.pack(side="right")
        reg(theme_box, lambda w: w.configure(bg=C["card"]))
        ThemeToggleBtn(theme_box, self._toggle_theme).pack(side="left")
        self._theme_caption = tk.Label(theme_box, text="Dark", font=FT, bg=C["card"], fg=C["text3"])
        self._theme_caption.pack(side="left", padx=(6, 0))
        reg(self._theme_caption, lambda w: w.configure(bg=C["card"], fg=C["text3"], text="Dark" if C["mode"] == "dark" else "Light"))

        rule = tk.Frame(self, bg=C["border"], height=1)
        rule.pack(fill="x")
        reg(rule, lambda w: w.configure(bg=C["border"]))

        body = tk.Frame(self, bg=C["bg"])
        reg(body, lambda w: w.configure(bg=C["bg"]))
        body.grid_columnconfigure(0, weight=5, minsize=420)
        body.grid_columnconfigure(1, weight=6, minsize=460)
        body.grid_rowconfigure(0, weight=1)

        self._controls_scroll = ScrollArea(body)
        self._controls_scroll.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        controls = self._controls_scroll.content
        controls.grid_columnconfigure(0, weight=1)
        self._build_controls(controls)
        self._register_scroll_target(self._controls_scroll, self._controls_scroll._canvas)
        self._register_scroll_target(self._controls_scroll._canvas)
        self._register_scroll_target(self._controls_scroll.content, self._controls_scroll._canvas)

        stage = tk.Frame(body, bg=C["bg"])
        stage.grid(row=0, column=1, sticky="nsew")
        reg(stage, lambda w: w.configure(bg=C["bg"]))
        stage.grid_columnconfigure(0, weight=1)
        stage.grid_rowconfigure(0, weight=1)
        stage.grid_rowconfigure(1, weight=0)
        self._build_preview(stage)
        self._build_log(stage)

        self._build_banner()
        self._build_footer()
        body.pack(fill="both", expand=True, padx=16, pady=16)
        self._bind_preview_updates()
        self._show_empty_state()

    def _setup_scroll_routing(self):
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.bind_all(sequence, self._route_mousewheel, add="+")

    def _register_scroll_target(self, widget, target=None):
        setattr(widget, SCROLL_TARGET_ATTR, target or widget)

    def _route_mousewheel(self, event):
        units = normalize_mousewheel_units(event)
        if units == 0:
            return
        target = resolve_scroll_target(event.widget, units)
        if target is None:
            return
        try:
            widget_class = event.widget.winfo_class()
        except Exception:
            widget_class = ""
        if target is event.widget and widget_class in {"Text", "Listbox"} and can_scroll_target(target, units):
            return
        try:
            target.yview_scroll(units, "units")
            return "break"
        except Exception:
            return

    def _build_controls(self, parent):
        left = tk.Frame(parent, bg=C["bg"])
        left.grid(row=0, column=0, sticky="ew")
        left.grid_columnconfigure(0, weight=1)
        reg(left, lambda w: w.configure(bg=C["bg"]))

        project_card = Card(left)
        project_card.grid(row=0, column=0, sticky="ew")
        project_inner = project_card.inner()
        self._section(project_inner, "Project", "Folder Contexta will read. Nothing in it is modified.").pack(anchor="w")
        row = tk.Frame(project_inner, bg=C["card"])
        row.pack(fill="x", pady=(14, 0))
        reg(row, lambda w: w.configure(bg=C["card"]))
        path_shell = self._input_shell(row)
        path_shell.pack(side="left", fill="x", expand=True)
        entry = tk.Entry(
            path_shell,
            textvariable=self._path_var,
            font=FM,
            bg=C["input"],
            fg=C["text"],
            insertbackground=C["accent"],
            relief="flat",
            bd=0,
            selectbackground=C["accent"],
            selectforeground=readable_fg(C["accent"]),
        )
        entry.pack(fill="x", padx=10, ipady=8)
        reg(entry, lambda w: w.configure(bg=C["input"], fg=C["text"], insertbackground=C["accent"], selectbackground=C["accent"], selectforeground=readable_fg(C["accent"])))
        self._bind_input_focus(entry, path_shell)
        self._btn_pick = FlatBtn(row, "Browse", "accent", self._pick_folder, font=FBS, padx=14, pady=7, surface_key="card", variant="soft")
        self._btn_pick.pack(side="left", padx=(10, 0))

        strategy_card = Card(left)
        strategy_card.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        strategy_inner = strategy_card.inner()
        self._section(strategy_inner, "Context strategy", "A pack is the preset. Mode and focus shape which files rise to the top.").pack(anchor="w")
        self._combo_field(strategy_inner, "Context pack", self._pack_var, PACK_OPTIONS).pack(fill="x", pady=(14, 0))
        self._combo_field(strategy_inner, "Context mode", self._mode_var, CONTEXT_MODE_OPTIONS).pack(fill="x", pady=(12, 0))
        self._entry_field(strategy_inner, "Focus", self._focus_var, "Optional. Try login, billing, or a file name.").pack(fill="x", pady=(12, 0))

        output_card = Card(left)
        output_card.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        output_inner = output_card.inner()
        self._section(output_inner, "Output", "Who will read the pack, what they should do, and how much code to keep.").pack(anchor="w")
        self._combo_field(output_inner, "AI target", self._ai_var, AI_PROFILE_OPTIONS).pack(fill="x", pady=(14, 0))
        self._combo_field(output_inner, "Task", self._task_var, TASK_PROFILE_OPTIONS).pack(fill="x", pady=(12, 0))
        self._combo_field(output_inner, "Compression", self._compression_var, COMPRESSION_OPTIONS).pack(fill="x", pady=(12, 0))

        goal_label = tk.Label(output_inner, text="Custom goal", font=FT, bg=C["card"], fg=C["text3"])
        goal_label.pack(anchor="w", pady=(14, 6))
        reg(goal_label, lambda w: w.configure(bg=C["card"], fg=C["text3"]))
        goal_shell = self._input_shell(output_inner)
        goal_shell.pack(fill="x")
        self._prompt = tk.Text(
            goal_shell,
            height=3,
            font=FS,
            bg=C["input"],
            fg=C["text"],
            insertbackground=C["accent"],
            relief="flat",
            bd=0,
            padx=10,
            pady=8,
            wrap="word",
            selectbackground=C["accent"],
            selectforeground=readable_fg(C["accent"]),
        )
        self._prompt.pack(fill="x")
        reg(self._prompt, lambda w: w.configure(bg=C["input"], fg=C["text"], insertbackground=C["accent"], selectbackground=C["accent"], selectforeground=readable_fg(C["accent"])))
        self._bind_input_focus(self._prompt, goal_shell)
        self._register_scroll_target(self._prompt)

        options_card = Card(left)
        options_card.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        options_inner = options_card.inner()
        self._section(options_inner, "Scan options", "Widen the scan or lean on git. Details live in the guide.").pack(anchor="w")
        toggles = tk.Frame(options_inner, bg=C["card"])
        toggles.pack(fill="x", pady=(12, 0))
        toggles.grid_columnconfigure(0, weight=1)
        toggles.grid_columnconfigure(1, weight=1)
        reg(toggles, lambda w: w.configure(bg=C["card"]))
        toggle_specs = (
            ("_toggle_hidden", "Hidden files", self._hidden_var),
            ("_toggle_unknown", "Unknown extensions", self._unknown_var),
            ("_toggle_diff", "Prefer git changes", self._diff_var),
            ("_toggle_staged", "Staged changes only", self._staged_var),
            ("_toggle_copy", "Copy pack after export", self._copy_var),
        )
        for index, (attr, label, variable) in enumerate(toggle_specs):
            toggle = Toggle(toggles, label, variable)
            setattr(self, attr, toggle)
            toggle.grid(row=index // 2, column=index % 2, sticky="w", pady=5, padx=(0, 8))

        # Room for options added elsewhere (budgets, redaction, presets).
        self.extension_slot = tk.Frame(left, bg=C["bg"])
        self.extension_slot.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        reg(self.extension_slot, lambda w: w.configure(bg=C["bg"]))

        mcp_card = Card(left)
        mcp_card.grid(row=5, column=0, sticky="ew", pady=(12, 0))
        mcp_inner = mcp_card.inner()
        self._section(mcp_inner, "MCP Server Setup", "Auto-configure Contexta as a tool server for your AI editor.").pack(anchor="w")
        mcp_btns = tk.Frame(mcp_inner, bg=C["card"])
        mcp_btns.pack(fill="x", pady=(12, 0))
        reg(mcp_btns, lambda w: w.configure(bg=C["card"]))
        FlatBtn(mcp_btns, "Claude Code", "accent_dk", self._setup_claude_code, font=FBS, surface_key="card").pack(side="left", padx=(0, 8))
        FlatBtn(mcp_btns, "Cursor", "violet", self._setup_cursor, font=FBS, surface_key="card").pack(side="left", padx=(0, 8))
        FlatBtn(mcp_btns, "Windsurf", "green", self._setup_windsurf, font=FBS, surface_key="card").pack(side="left")
        mcp_hint = tk.Label(mcp_inner, text="Writes the MCP config so the editor can call Contexta as a tool server. Restart the editor after setup.", font=FT, bg=C["card"], fg=C["text3"], wraplength=360, justify="left")
        mcp_hint.pack(anchor="w", pady=(10, 0))
        reg(mcp_hint, lambda w: w.configure(bg=C["card"], fg=C["text3"]))

    def _build_preview(self, parent):
        self._reader = Card(parent, pad=14)
        self._reader.grid(row=0, column=0, sticky="nsew")
        inner = self._reader.inner()
        inner.grid_columnconfigure(0, weight=1)
        inner.grid_rowconfigure(2, weight=1)

        header = tk.Frame(inner, bg=C["card"])
        header.grid(row=0, column=0, sticky="ew")
        reg(header, lambda w: w.configure(bg=C["card"]))
        self._section(header, "Pack", "What this export will emphasize, then the Markdown itself.").pack(side="left", anchor="w")
        self._view_switch = Segmented(header, [("preview", "Preview"), ("result", "Result")], self._set_view)
        self._view_switch.pack(side="right", anchor="e")

        self._metrics = tk.Frame(inner, bg=C["card"])
        self._metrics.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        reg(self._metrics, lambda w: w.configure(bg=C["card"]))
        self._metrics.grid_columnconfigure(0, weight=1)
        self._metrics.grid_columnconfigure(1, weight=1)
        self._metrics.grid_columnconfigure(2, weight=1)
        self._chip_scanned = StatChip(self._metrics, "Files scanned")
        self._chip_selected = StatChip(self._metrics, "Selected")
        self._chip_tokens = StatChip(self._metrics, "Rough tokens")
        self._chip_scanned.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self._chip_selected.grid(row=0, column=1, sticky="ew", padx=4)
        self._chip_tokens.grid(row=0, column=2, sticky="ew", padx=(8, 0))

        self._preview_stack = tk.Frame(inner, bg=C["card"])
        self._preview_stack.grid(row=2, column=0, sticky="nsew", pady=(12, 0))
        self._preview_stack.grid_columnconfigure(0, weight=1)
        self._preview_stack.grid_rowconfigure(0, weight=1)
        reg(self._preview_stack, lambda w: w.configure(bg=C["card"]))

        self._empty_state = tk.Frame(self._preview_stack, bg=C["bg2"], highlightthickness=1, highlightbackground=C["border"])
        self._empty_state.grid(row=0, column=0, sticky="nsew")
        reg(self._empty_state, lambda w: w.configure(bg=C["bg2"], highlightbackground=C["border"]))
        empty_inner = tk.Frame(self._empty_state, bg=C["bg2"])
        empty_inner.place(relx=0.5, rely=0.5, anchor="center")
        reg(empty_inner, lambda w: w.configure(bg=C["bg2"]))
        empty_mark = tk.Label(empty_inner, text="GET STARTED", font=FT, bg=C["bg2"], fg=C["accent"])
        empty_mark.pack(anchor="center")
        reg(empty_mark, lambda w: w.configure(bg=C["bg2"], fg=C["accent"]))
        empty_title = tk.Label(empty_inner, text="Choose a project to begin", font=FL, bg=C["bg2"], fg=C["text"])
        empty_title.pack(anchor="center", pady=(8, 4))
        reg(empty_title, lambda w: w.configure(bg=C["bg2"], fg=C["text"]))
        empty_copy = tk.Label(
            empty_inner,
            text="Pick a folder, keep the onboarding pack or switch it,\nthen create the Markdown from the bar below.",
            font=FS,
            bg=C["bg2"],
            fg=C["text2"],
            justify="center",
        )
        empty_copy.pack(anchor="center")
        reg(empty_copy, lambda w: w.configure(bg=C["bg2"], fg=C["text2"]))
        steps = tk.Label(
            empty_inner,
            text="1  Folder      2  Pack      3  Create",
            font=FT,
            bg=C["bg2"],
            fg=C["text3"],
        )
        steps.pack(anchor="center", pady=(12, 14))
        reg(steps, lambda w: w.configure(bg=C["bg2"], fg=C["text3"]))
        FlatBtn(empty_inner, "Choose folder", "accent", self._pick_folder, font=FBS, padx=14, pady=7, surface_key="bg2", variant="solid").pack(anchor="center")

        self._preview_shell = tk.Frame(self._preview_stack, bg=C["bg2"], highlightthickness=1, highlightbackground=C["border"])
        self._preview_shell.grid(row=0, column=0, sticky="nsew")
        self._preview_shell.grid_columnconfigure(0, weight=1)
        self._preview_shell.grid_rowconfigure(0, weight=1)
        reg(self._preview_shell, lambda w: w.configure(bg=C["bg2"], highlightbackground=C["border"]))
        self._preview = tk.Text(
            self._preview_shell,
            font=FS,
            bg=C["bg2"],
            fg=C["text"],
            insertbackground=C["accent"],
            relief="flat",
            bd=0,
            padx=14,
            pady=12,
            wrap="word",
            state="disabled",
            cursor="arrow",
            spacing1=1,
            spacing3=2,
        )
        self._preview.grid(row=0, column=0, sticky="nsew")
        reg(self._preview, lambda w: w.configure(bg=C["bg2"], fg=C["text"], insertbackground=C["accent"]))
        preview_scroll = ttk.Scrollbar(self._preview_shell, orient="vertical", command=self._preview.yview)
        preview_scroll.grid(row=0, column=1, sticky="ns")
        self._preview.configure(yscrollcommand=preview_scroll.set)
        self._register_scroll_target(self._preview_shell, self._preview)
        self._register_scroll_target(self._preview)
        self._configure_preview_tags()

        self._result_shell = tk.Frame(self._preview_stack, bg=C["bg2"], highlightthickness=1, highlightbackground=C["border"])
        self._result_shell.grid(row=0, column=0, sticky="nsew")
        self._result_shell.grid_columnconfigure(0, weight=1)
        self._result_shell.grid_rowconfigure(1, weight=1)
        reg(self._result_shell, lambda w: w.configure(bg=C["bg2"], highlightbackground=C["border"]))
        self._result_meta = tk.Label(self._result_shell, text="", font=FT, bg=C["bg2"], fg=C["text3"], anchor="w", justify="left", wraplength=560, padx=14, pady=8)
        self._result_meta.grid(row=0, column=0, columnspan=2, sticky="ew")
        reg(self._result_meta, lambda w: w.configure(bg=C["bg2"], fg=C["text3"]))
        self._result = tk.Text(
            self._result_shell,
            font=FS,
            bg=C["bg2"],
            fg=C["text"],
            relief="flat",
            bd=0,
            padx=14,
            pady=8,
            wrap="word",
            state="disabled",
            cursor="arrow",
        )
        self._result.grid(row=1, column=0, sticky="nsew")
        reg(self._result, lambda w: w.configure(bg=C["bg2"], fg=C["text"]))
        result_scroll = ttk.Scrollbar(self._result_shell, orient="vertical", command=self._result.yview)
        result_scroll.grid(row=1, column=1, sticky="ns")
        self._result.configure(yscrollcommand=result_scroll.set)
        self._register_scroll_target(self._result_shell, self._result)
        self._register_scroll_target(self._result)
        self._configure_result_tags()
        self._result_shell.grid_remove()
        self._preview_shell.grid_remove()

    def _build_log(self, parent):
        log_card = Card(parent, pad=12)
        log_card.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        log_inner = log_card.inner()
        log_inner.grid_columnconfigure(0, weight=1)
        self._section(log_inner, "Activity", "Scan notes appear here while a pack is created.").grid(row=0, column=0, sticky="w")
        log_shell = tk.Frame(log_inner, bg=C["bg2"], highlightthickness=1, highlightbackground=C["border"])
        log_shell.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        log_shell.grid_columnconfigure(0, weight=1)
        log_shell.grid_rowconfigure(0, weight=1)
        reg(log_shell, lambda w: w.configure(bg=C["bg2"], highlightbackground=C["border"]))
        self._log = tk.Text(log_shell, height=6, font=FM, bg=C["bg2"], fg=C["text2"], insertbackground=C["accent"], relief="flat", bd=0, padx=12, pady=8, wrap="word", state="disabled", cursor="arrow")
        self._log.grid(row=0, column=0, sticky="nsew")
        reg(self._log, lambda w: w.configure(bg=C["bg2"], fg=C["text2"], insertbackground=C["accent"]))
        scrollbar = ttk.Scrollbar(log_shell, orient="vertical", command=self._log.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self._log.configure(yscrollcommand=scrollbar.set)
        self._register_scroll_target(log_shell, self._log)
        self._register_scroll_target(self._log)
        self._configure_log_tags()
        self._log_write("Waiting for a project.", "muted")

    def _build_banner(self):
        self._banner = tk.Frame(self, bg=C["danger_soft"])
        reg(self._banner, lambda w: self._paint_banner())
        self._banner_text = ""
        self._banner_label = tk.Label(self._banner, text="", font=FS, bg=C["danger_soft"], fg=C["red"], anchor="w", justify="left", wraplength=860)
        self._banner_label.pack(side="left", fill="x", expand=True, padx=16, pady=10)
        self._banner_dismiss = tk.Label(self._banner, text="Dismiss", font=FBS, bg=C["danger_soft"], fg=C["red"], cursor="hand2", padx=8)
        self._banner_dismiss.pack(side="right", padx=16)
        self._banner_dismiss.bind("<Button-1>", lambda _event: self._hide_banner())
        self._banner_dismiss.bind("<Return>", lambda _event: self._hide_banner())

    def _build_footer(self):
        self._footer = tk.Frame(self, bg=C["card"])
        self._footer.pack(fill="x", side="bottom")
        reg(self._footer, lambda w: w.configure(bg=C["card"]))
        rule = tk.Frame(self._footer, bg=C["border"], height=1)
        rule.pack(fill="x")
        reg(rule, lambda w: w.configure(bg=C["border"]))

        inner = tk.Frame(self._footer, bg=C["card"])
        inner.pack(fill="x", padx=16, pady=12)
        reg(inner, lambda w: w.configure(bg=C["card"]))
        inner.grid_columnconfigure(2, weight=1)

        self._btn_generate = FlatBtn(inner, "Create context pack", "accent", self._start, surface_key="card")
        self._btn_generate.configure(state="disabled")
        self._btn_generate.grid(row=0, column=0, sticky="w")
        self._btn_copy = FlatBtn(inner, "Copy latest", "violet", self._copy_to_clipboard, font=FBS, surface_key="card", variant="ghost")
        self._btn_copy.configure(state="disabled")
        self._btn_copy.grid(row=0, column=1, sticky="w", padx=(8, 0))

        self._status_text = "Choose a folder"
        self._status = tk.Label(inner, text=self._status_text, font=FT, bg=C["tag_bg"], fg=C["tag_fg"], padx=10, pady=5)
        self._status.grid(row=0, column=3, sticky="e")
        reg(self._status, lambda w: self._paint_status())

        hint = tk.Label(inner, text="Writes a Markdown file to your desktop.", font=FT, bg=C["card"], fg=C["text3"])
        hint.grid(row=1, column=0, columnspan=3, sticky="w", pady=(8, 0))
        reg(hint, lambda w: w.configure(bg=C["card"], fg=C["text3"]))

        self._progress = ttk.Progressbar(inner, style="TProgressbar", mode="indeterminate")
        self._progress.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        self._progress.grid_remove()

    def _section(self, parent, title: str, subtitle: str):
        row = tk.Frame(parent, bg=C["card"])
        reg(row, lambda w: w.configure(bg=C["card"]))
        title_label = tk.Label(row, text=title, font=FL, bg=C["card"], fg=C["text"])
        title_label.pack(anchor="w")
        reg(title_label, lambda w: w.configure(bg=C["card"], fg=C["text"]))
        subtitle_label = tk.Label(row, text=subtitle, font=FT, bg=C["card"], fg=C["text3"], justify="left", wraplength=260)
        subtitle_label.pack(anchor="w", pady=(3, 0))
        # Wrap to the card width. A fixed width clipped the text on narrow cards.
        parent.bind("<Configure>", lambda e, lab=subtitle_label: lab.configure(wraplength=max(e.width - 8, 160)), add="+")
        reg(subtitle_label, lambda w: w.configure(bg=C["card"], fg=C["text3"]))
        return row

    def _input_shell(self, parent):
        shell = tk.Frame(parent, bg=C["input"], highlightthickness=1, highlightbackground=C["border"], highlightcolor=C["accent"], bd=0)
        reg(shell, lambda w: w.configure(bg=C["input"], highlightbackground=C["border"], highlightcolor=C["accent"]))
        return shell

    def _bind_input_focus(self, widget, shell):
        def on_in(_event):
            shell.configure(highlightbackground=C["accent"])

        def on_out(_event):
            shell.configure(highlightbackground=C["border"])

        widget.bind("<FocusIn>", on_in, add="+")
        widget.bind("<FocusOut>", on_out, add="+")

    def _combo_field(self, parent, label: str, var: tk.StringVar, options: dict[str, str], helper_text: str = ""):
        frame = tk.Frame(parent, bg=C["card"])
        reg(frame, lambda w: w.configure(bg=C["card"]))
        label_widget = tk.Label(frame, text=label, font=FT, bg=C["card"], fg=C["text3"])
        label_widget.pack(anchor="w", pady=(0, 6))
        reg(label_widget, lambda w: w.configure(bg=C["card"], fg=C["text3"]))
        values = [f"{key}  ·  {value}" for key, value in options.items()]
        combo = ttk.Combobox(frame, values=values, state="readonly", font=FS)
        combo.pack(fill="x")
        current_label = f"{var.get()}  ·  {options[var.get()]}"
        combo.set(current_label)
        combo.bind("<<ComboboxSelected>>", lambda _e, v=var, c=combo: v.set(c.get().split("  ·  ", 1)[0]))
        self._combo_widgets[str(var)] = (var, combo, options)
        if helper_text:
            helper = tk.Label(frame, text=helper_text, font=FT, bg=C["card"], fg=C["text3"], wraplength=420, justify="left")
            helper.pack(anchor="w", pady=(6, 0))
            reg(helper, lambda w: w.configure(bg=C["card"], fg=C["text3"]))
        return frame

    def _entry_field(self, parent, label: str, var: tk.StringVar, hint: str, helper_text: str = ""):
        frame = tk.Frame(parent, bg=C["card"])
        reg(frame, lambda w: w.configure(bg=C["card"]))
        label_widget = tk.Label(frame, text=label, font=FT, bg=C["card"], fg=C["text3"])
        label_widget.pack(anchor="w", pady=(0, 6))
        reg(label_widget, lambda w: w.configure(bg=C["card"], fg=C["text3"]))
        shell = self._input_shell(frame)
        shell.pack(fill="x")
        entry = tk.Entry(
            shell,
            textvariable=var,
            font=FS,
            bg=C["input"],
            fg=C["text"],
            insertbackground=C["accent"],
            relief="flat",
            bd=0,
            selectbackground=C["accent"],
            selectforeground=readable_fg(C["accent"]),
        )
        entry.pack(fill="x", padx=10, ipady=7)
        reg(entry, lambda w: w.configure(bg=C["input"], fg=C["text"], insertbackground=C["accent"], selectbackground=C["accent"], selectforeground=readable_fg(C["accent"])))
        self._bind_input_focus(entry, shell)
        helper = tk.Label(frame, text=hint, font=FT, bg=C["card"], fg=C["text3"], wraplength=420, justify="left")
        helper.pack(anchor="w", pady=(6, 0))
        reg(helper, lambda w: w.configure(bg=C["card"], fg=C["text3"]))
        if helper_text:
            explainer = tk.Label(frame, text=helper_text, font=FT, bg=C["card"], fg=C["text3"], wraplength=420, justify="left")
            explainer.pack(anchor="w", pady=(4, 0))
            reg(explainer, lambda w: w.configure(bg=C["card"], fg=C["text3"]))
        return frame

    def _bind_preview_updates(self):
        self._pack_var.trace_add("write", lambda *_: self._apply_pack_profile())
        for var in (self._mode_var, self._ai_var, self._task_var, self._compression_var, self._focus_var):
            var.trace_add("write", lambda *_: self._refresh_preview())
        for var in (self._diff_var, self._staged_var, self._hidden_var, self._unknown_var):
            var.trace_add("write", lambda *_: self._invalidate_preview_snapshot())
        self._diff_var.trace_add("write", lambda *_: self._sync_option_states())
        self._prompt.bind("<KeyRelease>", lambda _e: self._refresh_preview())

    def _invalidate_preview_snapshot(self):
        self._preview_snapshot = None
        self._refresh_preview()

    def _load_preview_snapshot(self) -> dict[str, int] | None:
        if not self._project_path:
            return None
        if self._preview_snapshot is not None:
            return self._preview_snapshot
        try:
            gitignore_patterns = load_gitignore_patterns(self._project_path)
            counter = [0]
            tree = build_tree(
                self._project_path,
                self._hidden_var.get(),
                self._unknown_var.get(),
                lambda *_args, **_kwargs: None,
                counter,
                gitignore_patterns,
                self._project_path,
            )
            total_files = count_files(tree)
            changed_files = get_git_changed_files(self._project_path, staged_only=self._staged_var.get()) or []
            self._preview_snapshot = {
                "total_files": total_files,
                "changed_files": len(changed_files),
            }
        except Exception:
            self._preview_snapshot = {
                "total_files": 0,
                "changed_files": 0,
            }
        return self._preview_snapshot

    def _apply_pack_profile(self):
        preset = PACK_DEFAULTS.get(self._pack_var.get())
        if preset:
            if "context_mode" in preset:
                self._mode_var.set(preset["context_mode"])
            if "ai_profile" in preset:
                self._ai_var.set(preset["ai_profile"])
            if "task_profile" in preset:
                self._task_var.set(preset["task_profile"])
            if "compression" in preset:
                self._compression_var.set(preset["compression"])
        preset_focus = preset.get("focus_query", "") if preset else ""
        next_focus, self._last_auto_focus = resolve_pack_focus(
            self._focus_var.get(),
            self._last_auto_focus,
            preset_focus,
        )
        if next_focus != self._focus_var.get():
            self._focus_var.set(next_focus)

        for _name, (variable, combo, options) in self._combo_widgets.items():
            key = variable.get()
            if key in options:
                combo.set(f"{key}  ·  {options[key]}")
        self._refresh_preview()

    def _sync_option_states(self):
        if not self._diff_var.get():
            self._staged_var.set(False)
        self._toggle_staged.configure(state="normal" if self._diff_var.get() else "disabled")

    def _refresh_preview(self):
        pack_key = self._pack_var.get()
        mode_key = self._mode_var.get()
        ai_key = self._ai_var.get()
        task_key = self._task_var.get()
        compression_key = self._compression_var.get()
        focus_text = self._focus_var.get().strip()
        snapshot = self._load_preview_snapshot()
        total_files = snapshot["total_files"] if snapshot else 0
        changed_files = snapshot["changed_files"] if snapshot else 0
        estimated_files = estimate_selected_files(total_files, changed_files, mode_key, bool(focus_text))
        estimated_tokens = estimate_tokens_for_preview(estimated_files, compression_key)
        full_tokens = estimate_tokens_for_preview(estimate_selected_files(total_files, changed_files, mode_key, bool(focus_text)), "full")
        balanced_tokens = estimate_tokens_for_preview(estimated_files, "balanced")
        focused_tokens = estimate_tokens_for_preview(estimated_files, "focused")
        signatures_tokens = estimate_tokens_for_preview(estimated_files, "signatures")
        reduction_vs_full = 0
        if full_tokens:
            reduction_vs_full = max(0, round((1 - (estimated_tokens / full_tokens)) * 100))
        custom_goal = self._prompt.get("1.0", "end").strip()
        section_titles = section_titles_for_preview(mode_key, task_key, bool(custom_goal))
        guidance_lines = format_model_guidance(ai_key).splitlines()

        if snapshot:
            self._chip_scanned.set(f"{total_files}")
            self._chip_selected.set(f"~{estimated_files}")
            self._chip_tokens.set(format_token_k(estimated_tokens))
        else:
            self._chip_scanned.set("—")
            self._chip_selected.set("—")
            self._chip_tokens.set("—")

        focus_line = focus_text if focus_text else "Not set. Selection stays broad."
        git_line = "Changed files and nearby context move up." if self._diff_var.get() else "Git changes stay a background signal."
        blocks = [
            ("kicker", "PACK\n"),
            ("title", f"{PACK_OPTIONS.get(pack_key, 'Custom pack')}\n"),
            ("body", f"{PACK_HELP.get(pack_key, 'Custom workflow.')}\n"),
            ("kicker", "SELECTION\n"),
            ("strong", f"{CONTEXT_MODE_OPTIONS.get(mode_key, mode_key)}\n"),
            ("body", f"{MODE_HELP.get(mode_key, '')}\n"),
            ("bullet", f"Focus     {focus_line}\n"),
            ("bullet", f"Git       {git_line}\n"),
            ("bullet", f"Changed   {changed_files if snapshot else '—'}\n"),
            ("kicker", "OUTPUT\n"),
            ("strong", f"{AI_PROFILE_OPTIONS.get(ai_key, ai_key)}\n"),
            ("body", f"{AI_HELP.get(ai_key, '')}\n"),
            ("strong", f"{TASK_PROFILE_OPTIONS.get(task_key, task_key)}\n"),
            ("body", f"{TASK_HELP.get(task_key, '')}\n"),
            ("strong", f"{COMPRESSION_OPTIONS.get(compression_key, compression_key)}\n"),
            ("body", f"{COMPRESSION_HELP.get(compression_key, '')}\n"),
            ("kicker", "TOKEN SHAPE\n"),
            ("bullet", f"Full {format_token_k(full_tokens)}     Balanced {format_token_k(balanced_tokens)}     Focused {format_token_k(focused_tokens)}     Signatures {format_token_k(signatures_tokens)}\n"),
            ("body", f"About {reduction_vs_full}% smaller than Full. These counts are rough.\n"),
            ("kicker", "SECTIONS IN THE PACK\n"),
        ]
        for title in section_titles[:8]:
            blocks.append(("bullet", f"{title}\n"))
        if len(section_titles) > 8:
            blocks.append(("body", f"{len(section_titles) - 8} more sections follow in the export.\n"))
        notes = [line.strip() for line in guidance_lines if line.strip()]
        if notes:
            blocks.append(("kicker", "MODEL NOTES\n"))
            for line in notes[:6]:
                blocks.append(("bullet", f"{line.lstrip('-').strip()}\n"))
        if custom_goal:
            blocks.extend([("kicker", "CUSTOM GOAL\n"), ("body", custom_goal + "\n")])
        self._write_tagged(self._preview, blocks)
        if self._project_path or self._last_md or self._view_switch._current == "result":
            self._show_reader()
        else:
            self._show_empty_state()

    def _configure_preview_tags(self):
        sans = FS[0]
        self._preview.tag_configure("kicker", font=(sans, 9, "bold"), foreground=C["accent"], spacing1=12, spacing3=2)
        self._preview.tag_configure("title", font=(sans, 14, "bold"), foreground=C["text"], spacing3=3)
        self._preview.tag_configure("strong", font=(sans, 10, "bold"), foreground=C["text"], spacing1=6, spacing3=1)
        self._preview.tag_configure("body", font=FS, foreground=C["text2"], spacing3=2)
        self._preview.tag_configure("bullet", font=FS, foreground=C["text"], spacing1=1, lmargin1=4, lmargin2=16)

    def _configure_result_tags(self):
        sans = FS[0]
        self._result.tag_configure("h1", font=(sans, 16, "bold"), foreground=C["text"], spacing1=6, spacing3=8)
        self._result.tag_configure("h2", font=(sans, 13, "bold"), foreground=C["text"], spacing1=12, spacing3=4)
        self._result.tag_configure("h3", font=(sans, 11, "bold"), foreground=C["text2"], spacing1=8, spacing3=2)
        self._result.tag_configure("body", font=FS, foreground=C["text2"], spacing3=1)
        self._result.tag_configure("quote", font=FS, foreground=C["text3"], lmargin1=8)
        self._result.tag_configure("code", font=FM, foreground=C["text2"], lmargin1=12, lmargin2=12)
        self._result.tag_configure("empty_title", font=(sans, 13, "bold"), foreground=C["text"], spacing3=4)
        self._result.tag_configure("empty_body", font=FS, foreground=C["text2"])

    def _configure_log_tags(self):
        for tag, color_key in (("ok", "green"), ("warn", "amber"), ("err", "red"), ("info", "accent"), ("muted", "text3")):
            self._log.tag_configure(tag, foreground=C[color_key])

    def _write_tagged(self, widget, blocks: list[tuple[str, str]]):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        for tag, text in blocks:
            widget.insert("end", text, tag)
        widget.configure(state="disabled")

    def _show_empty_state(self):
        self._empty_state.grid()
        self._preview_shell.grid_remove()
        self._result_shell.grid_remove()

    def _show_reader(self):
        self._empty_state.grid_remove()
        if self._view_switch._current == "result":
            self._preview_shell.grid_remove()
            self._result_shell.grid()
        else:
            self._result_shell.grid_remove()
            self._preview_shell.grid()

    def _set_view(self, key: str):
        if not self._project_path and not self._last_md and key == "preview":
            self._show_empty_state()
            return
        if key == "result" and not self._last_md:
            self._render_result_placeholder()
        self._show_reader()

    def _render_result_placeholder(self):
        self._result_meta.configure(text="Nothing exported yet")
        self._write_tagged(
            self._result,
            [
                ("empty_title", "No pack yet\n"),
                ("empty_body", "Create a context pack and the Markdown will open here, ready to read or copy.\n"),
            ],
        )

    def _show_result(self, markdown: str, out_file: Path):
        self._last_output = out_file
        lines = markdown.splitlines()
        shown = lines[:180]
        size_kb = max(len(markdown.encode("utf-8")), 1) / 1024
        meta = f"{out_file}      {len(lines)} lines      {size_kb:.1f} KB"
        if len(lines) > len(shown):
            meta += "      first 180 lines"
        self._result_meta.configure(text=meta)
        self._result.configure(state="normal")
        self._result.delete("1.0", "end")
        in_code = False
        for line in shown:
            if line.startswith("```"):
                in_code = not in_code
                self._result.insert("end", line + "\n", "code")
                continue
            if in_code:
                tag = "code"
            elif line.startswith("# "):
                tag = "h1"
                line = line[2:]
            elif line.startswith("## "):
                tag = "h2"
                line = line[3:]
            elif line.startswith("### "):
                tag = "h3"
                line = line[4:]
            elif line.startswith(">"):
                tag = "quote"
            else:
                tag = "body"
            self._result.insert("end", line + "\n", tag)
        self._result.configure(state="disabled")
        self._result.see("1.0")
        self._view_switch.set("result")
        self._show_reader()

    def _paint_status(self):
        bg_key, fg_key = self._status_pair
        background = C[bg_key]
        foreground = C[fg_key]
        if contrast_ratio(foreground, background) < 4.5:
            foreground = readable_fg(background)
        self._status.configure(text=self._status_text, bg=background, fg=foreground)

    def _banner_colors(self):
        tone = self._banner_tone or "err"
        return {
            "err": ("danger_soft", "red"),
            "warn": ("warn_soft", "amber"),
            "ok": ("ok_soft", "green"),
        }[tone]

    def _paint_banner(self):
        bg_key, fg_key = self._banner_colors()
        self._banner.configure(bg=C[bg_key])
        self._banner_label.configure(text=self._banner_text, bg=C[bg_key], fg=C[fg_key])
        self._banner_dismiss.configure(bg=C[bg_key], fg=C[fg_key])

    def _show_banner(self, text: str, tone: str = "err"):
        self._banner_text = text
        self._banner_tone = tone
        self._paint_banner()
        if not self._banner.winfo_ismapped():
            self._banner.pack(fill="x", before=self._footer)

    def _hide_banner(self):
        self._banner_tone = None
        self._banner_text = ""
        if self._banner.winfo_ismapped():
            self._banner.pack_forget()

    def _show_error(self, message: str):
        self._set_status("Error", "danger_soft", "red")
        self._show_banner(message, "err")

    def _toggle_theme(self):
        toggle_theme()
        self._refresh_ttk()
        ThemeRegistry.repaint()
        self.configure(bg=C["bg"])
        self._configure_preview_tags()
        self._configure_result_tags()
        self._configure_log_tags()
        self._paint_status()
        if self._banner_tone:
            self._paint_banner()
        self._refresh_preview()
        if self._help_window and self._help_window.winfo_exists():
            self._render_help()

    def _pick_folder(self):
        path = filedialog.askdirectory(title="Select project folder")
        if not path:
            return
        self._project_path = Path(path)
        self._preview_snapshot = None
        self._path_var.set(str(self._project_path))
        self._btn_generate.configure(state="normal")
        self._hide_banner()
        self._log_clear()
        self._log_write(f"Project folder selected: {self._project_path.name}", "info")
        self._set_status(self._project_path.name, "tag_bg", "tag_fg")
        self._view_switch.set("preview")
        self._refresh_preview()

    def _start(self):
        if self._running or not self._project_path:
            return
        self._running = True
        self._hide_banner()
        self._btn_generate.configure(state="disabled", text="Creating…")
        self._btn_pick.configure(state="disabled")
        self._btn_copy.configure(state="disabled")
        self._progress.grid()
        self._progress.start(12)
        self._log_clear()
        self._log_write("Reading the project…", "info")
        self._set_status("Working", "accent", "ink")
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        try:
            custom_goal = self._prompt.get("1.0", "end").strip()
            markdown = generate_markdown(
                self._project_path,
                include_hidden=self._hidden_var.get(),
                include_unknown=self._unknown_var.get(),
                diff_mode=self._diff_var.get(),
                staged_only=self._staged_var.get(),
                system_prompt=custom_goal,
                context_mode=self._mode_var.get(),
                ai_profile=self._ai_var.get(),
                task_profile=self._task_var.get(),
                compression=self._compression_var.get(),
                pack_profile=self._pack_var.get(),
                focus_query=self._focus_var.get().strip(),
                log_cb=self._log_write,
            )
            desktop = get_desktop()
            safe_name = safe_project_name(self._project_path.name)
            out_file = desktop / f"contexta - {safe_name}.md"
            out_file.write_text(markdown, encoding="utf-8")
            self.after(0, lambda: self._finish_success(markdown, out_file, self._copy_var.get()))
        except Exception as exc:
            message = str(exc)
            self._log_write(f"Error: {message}", "err")
            self.after(0, lambda m=message: self._show_error(m))
        finally:
            self._running = False
            self.after(0, self._hide_progress)
            self.after(0, lambda: self._btn_generate.configure(state="normal", text="Create context pack"))
            self.after(0, lambda: self._btn_pick.configure(state="normal"))

    def _hide_progress(self):
        self._progress.stop()
        self._progress.grid_remove()

    def _finish_success(self, markdown: str, out_file: Path, copy_requested: bool):
        self._last_md = markdown
        if copy_requested:
            self._do_copy(markdown)
            self._log_write("Copied the pack to the clipboard.", "ok")
        self._log_write(f"Saved: {out_file}", "ok")
        self._btn_copy.configure(state="normal")
        self._set_status("Ready", "ok_soft", "green")
        self._show_result(markdown, out_file)

    def _copy_to_clipboard(self):
        if not self._last_md:
            self._show_banner("Create a context pack first.", "warn")
            return
        self._do_copy(self._last_md)
        self._hide_banner()
        self._set_status("Copied", "ok_soft", "green")
        self._log_write("Copied the latest pack.", "ok")

    def _do_copy(self, text: str):
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()

    def _set_status(self, text: str, bg_key: str, fg_key: str):
        self._status_text = text if len(text) <= 32 else text[:31] + "…"
        self._status_pair = (bg_key, fg_key)
        self._paint_status()

    def _log_clear(self):
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")

    def _log_write(self, msg: str, tag: str = ""):
        def _write():
            marks = {"ok": "✓  ", "warn": "!  ", "err": "×  ", "info": "·  ", "muted": "·  "}
            self._log.configure(state="normal")
            self._log.insert("end", marks.get(tag, "") + msg + "\n", tag or "muted")
            self._log.see("end")
            self._log.configure(state="disabled")

        self.after(0, _write)

    def _center(self):
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        self.geometry(f"{width}x{height}+{(screen_width - width) // 2}+{(screen_height - height) // 2}")

    def _open_help(self):
        if self._help_window and self._help_window.winfo_exists():
            self._help_window.lift()
            self._help_window.focus_force()
            return

        self._help_window = tk.Toplevel(self)
        self._help_window.title("Contexta Guide")
        self._help_window.geometry("760x620")
        self._help_window.minsize(620, 460)
        self._help_window.configure(bg=C["bg"])
        _apply_window_icon(self._help_window, self._icon_photo)
        self._render_help()

    def _render_help(self):
        if not self._help_window or not self._help_window.winfo_exists():
            return

        for child in self._help_window.winfo_children():
            child.destroy()

        shell = tk.Frame(self._help_window, bg=C["bg"])
        shell.pack(fill="both", expand=True, padx=18, pady=18)
        reg(shell, lambda w: w.configure(bg=C["bg"]))

        title = tk.Label(shell, text="How to use Contexta", font=FH, bg=C["bg"], fg=C["text"])
        title.pack(anchor="w")
        reg(title, lambda w: w.configure(bg=C["bg"], fg=C["text"]))
        subtitle = tk.Label(shell, text="A quick explanation of the controls so you can build the right context pack faster.", font=FS, bg=C["bg"], fg=C["text2"])
        subtitle.pack(anchor="w", pady=(4, 14))
        reg(subtitle, lambda w: w.configure(bg=C["bg"], fg=C["text2"]))

        text_shell = tk.Frame(shell, bg=C["card"], highlightthickness=1, highlightbackground=C["border"])
        text_shell.pack(fill="both", expand=True)
        text_shell.grid_columnconfigure(0, weight=1)
        text_shell.grid_rowconfigure(0, weight=1)
        reg(text_shell, lambda w: w.configure(bg=C["card"], highlightbackground=C["border"]))

        guide = tk.Text(text_shell, font=FS, bg=C["card"], fg=C["text2"], relief="flat", bd=0, wrap="word", padx=18, pady=16, spacing3=2)
        guide.grid(row=0, column=0, sticky="nsew")
        guide.configure(insertbackground=C["accent"])
        guide.tag_configure("h", font=FL, foreground=C["text"], spacing1=12, spacing3=4)
        guide.tag_configure("b", font=FS, foreground=C["text2"])
        reg(guide, lambda w: w.configure(bg=C["card"], fg=C["text2"], insertbackground=C["accent"]))
        scroll = ttk.Scrollbar(text_shell, orient="vertical", command=guide.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        guide.configure(yscrollcommand=scroll.set)
        self._register_scroll_target(text_shell, guide)
        self._register_scroll_target(guide)

        sections = [
            ("Quick start", "Choose a folder, pick a Context Pack, optionally add Focus, then click Create Context Pack in the fixed footer."),
            ("Context Pack", "\n".join(f"- {label}: {PACK_HELP.get(key, '')}" for key, label in PACK_OPTIONS.items())),
            ("Context Mode", "\n".join(f"- {label}: {MODE_HELP.get(key, '')}" for key, label in CONTEXT_MODE_OPTIONS.items())),
            ("AI Target", "\n".join(f"- {label}: {AI_HELP.get(key, '')}" for key, label in AI_PROFILE_OPTIONS.items())),
            ("AI Target guidance", "\n\n".join(format_model_guidance(key) for key in AI_PROFILE_OPTIONS)),
            ("Task Mode", "\n".join(f"- {label}: {TASK_HELP.get(key, '')}" for key, label in TASK_PROFILE_OPTIONS.items())),
            ("Compression", "\n".join(f"- {label}: {COMPRESSION_HELP.get(key, '')}" for key, label in COMPRESSION_OPTIONS.items())),
            ("Focus", "Use a bug name, feature, route, service, file name, or keyword when you want Contexta to bias scoring, ordering, excerpts, and related files around a specific area."),
            ("Options", OPTION_GUIDE),
        ]

        for heading, body in sections:
            guide.insert("end", heading + "\n", "h")
            guide.insert("end", body + "\n\n", "b")

        guide.configure(state="disabled")

        close_row = tk.Frame(shell, bg=C["bg"])
        close_row.pack(fill="x", pady=(12, 0))
        reg(close_row, lambda w: w.configure(bg=C["bg"]))
        close_btn = FlatBtn(close_row, "Close", "accent", self._help_window.destroy, font=FBS, surface_key="bg", variant="ghost")
        close_btn.pack(anchor="e")

    def _get_mcp_entry(self) -> dict:
        mcp_script = Path(__file__).resolve().parent.parent / "contexta_mcp.py"
        python_cmd = sys.executable
        return {
            "command": python_cmd.replace("\\", "/"),
            "args": [str(mcp_script).replace("\\", "/")],
        }

    def _write_mcp_config(self, config_path: Path, editor_name: str):
        import json

        config_path.parent.mkdir(parents=True, exist_ok=True)
        existing = {}
        if config_path.exists():
            try:
                existing = json.loads(config_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        if "mcpServers" not in existing:
            existing["mcpServers"] = {}
        existing["mcpServers"]["contexta"] = self._get_mcp_entry()
        config_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        self._log_write(f"MCP configured for {editor_name}: {config_path}", "ok")
        messagebox.showinfo("Contexta", f"MCP server configured for {editor_name}.\n\nConfig: {config_path}\n\nRestart {editor_name} to activate.")

    def _setup_claude_code(self):
        config_path = Path.home() / ".claude" / ".mcp.json"
        self._write_mcp_config(config_path, "Claude Code")

    def _setup_cursor(self):
        config_path = Path.home() / ".cursor" / "mcp.json"
        self._write_mcp_config(config_path, "Cursor")

    def _setup_windsurf(self):
        config_path = Path.home() / ".codeium" / "windsurf" / "mcp_config.json"
        self._write_mcp_config(config_path, "Windsurf")
