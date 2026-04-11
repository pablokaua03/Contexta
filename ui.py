"""
ui.py - Tkinter GUI for mdcodebrief.
"""

from __future__ import annotations

import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from renderer import __version__, generate_markdown
from theme import C, FB, FBS, FH, FL, FM, FS, FT, ThemeRegistry, darken, reg, toggle_theme
from utils import get_desktop, safe_project_name

LOGO_GIF = (
    "R0lGODlhIAAgAPcAAAAAAAAAMwAAZgAAmQAAzAAA/wArAAArMwArZgArmQArzAAr/wBVAABVMwBV"
    "ZgBVmQBVzABV/wCAAACAMwCAZgCAmQCAzACA/wCqAACqMwCqZgCqmQCqzACq/wDVAADVMwDVZgDV"
    "mQDVzADV/wD/AAD/MwD/ZgD/mQD/zAD//zMAADMAMzMAZjMAmTMAzDMA/zMrADMrMzMrZjMrmTMr"
    "zDMr/zNVADNVMzNVZjNVmTNVzDNV/zOAADOAMzOAZjOAmTOAzDOA/zOqADOqMzOqZjOqmTOqzDOq"
    "/zPVADPVMzPVZjPVmTPVzDPV/zP/ADP/MzP/ZjP/mTP/zDP//2YAAGYAM2YAZmYAmWYAzGYA/2Yr"
    "AGYrM2YrZmYrmWYrzGYr/2ZVAGZVM2ZVZmZVmWZVzGZV/2aAAGaAM2aAZmaAmWaAzGaA/2aqAGaq"
    "M2aqZmaqmWaqzGaq/2bVAGbVM2bVZmbVmWbVzGbV/2b/AGb/M2b/Zmb/mWb/zGb//5kAAJkAM5kA"
    "ZpkAmZkAzJkA/5krAJkrM5krZpkrmZkrzJkr/5lVAJlVM5lVZplVmZlVzJlV/5mAAJmAM5mAZpmA"
    "mZmAzJmA/5mqAJmqM5mqZpmqmZmqzJmq/5nVAJnVM5nVZpnVmZnVzJnV/5n/AJn/M5n/Zpn/mZn/"
    "zJn//8wAAMwAM8wAZswAmcwAzMwA/8wrAMwrM8wrZswrmcwrzMwr/8xVAMxVM8xVZsxVmcxVzMxV"
    "/8yAAMyAM8yAZsyAmcyAzMyA/8yqAMyqM8yqZsyqmcyqzMyq/8zVAMzVM8zVZszVmczVzMzV/8z/"
    "AMz/M8z/Zsz/mcz/zMz///8AAP8AM/8AZv8Amf8AzP8A//8rAP8rM/8rZv8rmf8rzP8r//9VAP9V"
    "M/9VZv9Vmf9VzP9V//+AAP+AM/+AZv+Amf+AzP+A//+qAP+qM/+qZv+qmf+qzP+q///VAP/VM//V"
    "Zv/Vmf/VzP/V////AP//M///Zv//mf//zP///wAAAAAAAAAAAAAAACH5BAEAAPwALAAAAAAgACAA"
    "AAj/AAEIBCAmTRoxOMSgGbMQzcGHCsf4EFMwzcCBCXHguJFRo8ePHxFuzIhR5A0uHDMipKgy4w0ZN"
    "8TARAgg4Y0YOHDi2DIyjEeRHsPI2AhzpkacMFEO5ShSTMo0b4DyjPGyak2qMHEI3bmxKY43y3xoLV"
    "oV5z4xONPiyOpRJ4400TSNWeuxqgydMdQO9chFI8IfoPa9+fgyJ1W8ht9mgpNp8MdM0ZT9yPFGU+U0"
    "RNMezqrJYBo4mjymWRb3x2LPoWHm1XgXpxg4Hy3jyAGKtJo3sD1qynGzdd6qOHLr1PRDUzRQoODAy"
    "fHR8eGjeYfCTonjBxxomkIlx7wRJ2zfeQ9Q/z0QPCddHKBCwVEGx0gOsXuni0dwM2+MoYPZZscdbV"
    "l6ZcxR9Z194f2WAxxqpaGeQcrBcQooP5gHm3jixVCheDgUYR566in3g3WhpGEEUSPWV6GF9+EARE4"
    "yAAbKHempYQQoajgAhwwyNDChfRSGlyEO9OXA3AMKGqFJbiPitCKKPaKookdGOCCdcqEwh0CEa2l"
    "4wAp5BbDClhbKAEQRQBjxww0I4BCKEaFEeIAMnqXxw13iGWAhDBfGIKWUbyp4x443pAFTGsTktOW"
    "hKxjwJZOLBtcHKIaRhxB+adiHpwoUqmAhlxSquUwOCKA4hiaLZTJJGuIFcICmq6IIQAx2ipGXQzD"
    "9QhVGpNchiKmr656aAwB5IWAJqDIkKqFaXQGx6lj3LkqGjAEa+erih5wQ2ihHgDDokDh4AOKAaARA"
    "LWLVmuhocA661dGibZrAABfRruttr9uOW26iwZg7kD6xittvjH06i+e6cI67gEXAaBCsK82HDCsiT"
    "4cgLwIJ6pCwgMZcDAA0WrcsL4gq/AuxgEBADs="
)


def _icon_path() -> Path | None:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    icon = root / "icon.ico"
    return icon if icon.is_file() else None


class FlatBtn(tk.Frame):
    def __init__(self, parent, text: str, color_key: str, command, font=None, padx: int = 18, pady: int = 8):
        super().__init__(parent, bg=C["bg"])
        self._color_key = color_key
        self._enabled = True
        self._btn = tk.Button(
            self,
            text=text,
            font=font or FB,
            bg=C[color_key],
            fg=C["white"],
            activebackground=darken(C[color_key]),
            activeforeground=C["white"],
            relief="flat",
            bd=0,
            padx=padx,
            pady=pady,
            cursor="hand2",
            command=command,
        )
        self._btn.pack(fill="both", expand=True)
        self._btn.bind("<Enter>", self._hover_on)
        self._btn.bind("<Leave>", self._hover_off)
        reg(self, lambda w: w._repaint())

    def _repaint(self):
        self.configure(bg=C["bg"])
        if self._enabled:
            self._btn.configure(bg=C[self._color_key], fg=C["white"], activebackground=darken(C[self._color_key]), cursor="hand2")
        else:
            self._btn.configure(bg=C["border"], fg=C["text3"], cursor="arrow")

    def _hover_on(self, _=None):
        if self._enabled:
            self._btn.configure(bg=darken(C[self._color_key]))

    def _hover_off(self, _=None):
        if self._enabled:
            self._btn.configure(bg=C[self._color_key])

    def configure(self, **kw):
        if "state" in kw:
            self._enabled = kw.pop("state") != "disabled"
            self._btn.configure(state="normal" if self._enabled else "disabled")
            self._repaint()
        if "text" in kw:
            self._btn.configure(text=kw.pop("text"))
        if kw:
            super().configure(**kw)


class InputField(tk.Frame):
    def __init__(self, parent, var=None, placeholder: str = "", font=None):
        super().__init__(parent, bg=C["input"], highlightthickness=1, highlightbackground=C["border"], highlightcolor=C["accent"])
        self._var = var or tk.StringVar()
        self._placeholder = placeholder
        self._entry = tk.Entry(
            self,
            textvariable=self._var,
            font=font or FM,
            bg=C["input"],
            fg=C["text"],
            insertbackground=C["accent"],
            relief="flat",
            bd=0,
        )
        self._entry.pack(fill="x", padx=12, pady=10)
        if placeholder:
            self._set_placeholder()
            self._entry.bind("<FocusIn>", self._on_focus_in)
            self._entry.bind("<FocusOut>", self._on_focus_out)
        reg(self, lambda w: w._repaint())

    def _repaint(self):
        self.configure(bg=C["input"], highlightbackground=C["border"], highlightcolor=C["accent"])
        self._entry.configure(
            bg=C["input"],
            fg=C["text3"] if self._is_placeholder() else C["text"],
            insertbackground=C["accent"],
            disabledbackground=C["input"],
            disabledforeground=C["text3"],
        )

    def _is_placeholder(self) -> bool:
        return bool(self._placeholder and self._var.get() == self._placeholder)

    def _set_placeholder(self):
        self._var.set(self._placeholder)
        self._entry.configure(fg=C["text3"])

    def _on_focus_in(self, _):
        if self._is_placeholder():
            self._var.set("")
            self._entry.configure(fg=C["text"])

    def _on_focus_out(self, _):
        if not self._var.get().strip():
            self._set_placeholder()

    def set_value(self, value: str):
        self._var.set(value)
        self._entry.configure(fg=C["text"])

    def get_value(self) -> str:
        return "" if self._is_placeholder() else self._var.get()


class Toggle(tk.Frame):
    WIDTH = 36
    HEIGHT = 20

    def __init__(self, parent, text: str, variable: tk.BooleanVar):
        super().__init__(parent, bg=C["card"])
        self._var = variable
        self._enabled = True
        self._canvas = tk.Canvas(self, width=self.WIDTH, height=self.HEIGHT, highlightthickness=0, bg=C["card"], cursor="hand2")
        self._canvas.pack(side="left")
        self._label = tk.Label(self, text=text, font=FS, bg=C["card"], fg=C["text2"], cursor="hand2")
        self._label.pack(side="left", padx=(10, 0))
        for widget in (self, self._canvas, self._label):
            widget.bind("<Button-1>", self._toggle)
        reg(self, lambda w: w._repaint())
        self._draw()

    def _repaint(self):
        self.configure(bg=C["card"])
        self._canvas.configure(bg=C["card"], cursor="hand2" if self._enabled else "arrow")
        self._label.configure(bg=C["card"], fg=C["text2"] if self._enabled else C["text3"], cursor="hand2" if self._enabled else "arrow")
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
    SIZE = 30

    def __init__(self, parent, command):
        super().__init__(parent, width=self.SIZE, height=self.SIZE, highlightthickness=0, bd=0, bg=C["card"], cursor="hand2")
        self._command = command
        self.bind("<Button-1>", lambda _: self._command())
        self.bind("<Enter>", lambda _: self._draw(True))
        self.bind("<Leave>", lambda _: self._draw(False))
        reg(self, lambda w: w._draw(False))
        self._draw(False)

    def _draw(self, hover: bool):
        self.delete("all")
        self.configure(bg=C["card"])
        color = C["accent"] if hover else C["text2"]
        center = self.SIZE // 2

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
            self.create_oval(center - 2, center - 7, center + 7, center + 5, fill=C["card"], outline=C["card"])


class StatusPill(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=C["bg"])
        self._label = tk.Label(self, font=FT, padx=10, pady=4, bg=C["tag_bg"], fg=C["tag_fg"])
        reg(self, lambda w: w.configure(bg=C["bg"]))
        reg(self._label, lambda w: w.configure(bg=C["tag_bg"], fg=C["tag_fg"]))

    def set(self, text: str, kind: str = "info"):
        colors = {"info": ("tag_bg", "tag_fg"), "ok": ("green", "white"), "warn": ("amber", "white"), "err": ("red", "white")}
        bg_key, fg_key = colors.get(kind, ("tag_bg", "tag_fg"))
        self._label.configure(text=text, bg=C[bg_key], fg=C[fg_key])
        self._label.pack(side="right")

    def clear(self):
        self._label.pack_forget()


class Card(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=C["card"], highlightthickness=1, highlightbackground=C["border"])
        reg(self, lambda w: w.configure(bg=C["card"], highlightbackground=C["border"]))


def section(parent, title: str, subtitle: str = "", bg_key: str = "bg"):
    row = tk.Frame(parent, bg=C[bg_key])
    reg(row, lambda w: w.configure(bg=C[bg_key]))
    label = tk.Label(row, text=title, font=FL, bg=C[bg_key], fg=C["text"])
    label.pack(side="left")
    reg(label, lambda w: w.configure(bg=C[bg_key], fg=C["text"]))
    if subtitle:
        sub = tk.Label(row, text=subtitle, font=FT, bg=C[bg_key], fg=C["text3"])
        sub.pack(side="left", padx=(8, 0))
        reg(sub, lambda w: w.configure(bg=C[bg_key], fg=C["text3"]))
    return row


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"mdcodebrief v{__version__}")
        self.configure(bg=C["bg"])
        self.geometry("820x580")
        self.minsize(700, 500)
        self.resizable(True, True)

        self._project_path: Path | None = None
        self._running = False
        self._last_md = ""
        self._logo_img = tk.PhotoImage(data=LOGO_GIF)
        self.iconphoto(True, self._logo_img)

        icon = _icon_path()
        if icon:
            try:
                self.iconbitmap(default=str(icon))
            except Exception:
                pass

        self._setup_ttk()
        self._build_ui()
        self._center()

    def _setup_ttk(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TProgressbar", troughcolor=C["bg2"], background=C["accent"], bordercolor=C["bg"], lightcolor=C["accent"], darkcolor=C["accent"], thickness=6)
        style.configure("TScrollbar", troughcolor=C["card"], background=C["border"], arrowcolor=C["text3"], bordercolor=C["card"], relief="flat")

    def _refresh_ttk(self):
        style = ttk.Style()
        style.configure("TProgressbar", troughcolor=C["bg2"], background=C["accent"], bordercolor=C["bg"], lightcolor=C["accent"], darkcolor=C["accent"])
        style.configure("TScrollbar", troughcolor=C["card"], background=C["border"], arrowcolor=C["text3"], bordercolor=C["card"])

    def _build_ui(self):
        ThemeRegistry.reset()

        header = tk.Frame(self, bg=C["card"], height=72)
        header.pack(fill="x")
        header.pack_propagate(False)
        reg(header, lambda w: w.configure(bg=C["card"]))

        header_inner = tk.Frame(header, bg=C["card"])
        header_inner.pack(fill="both", expand=True, padx=18, pady=12)
        reg(header_inner, lambda w: w.configure(bg=C["card"]))

        left = tk.Frame(header_inner, bg=C["card"])
        left.pack(side="left", fill="x", expand=True)
        reg(left, lambda w: w.configure(bg=C["card"]))

        logo = tk.Label(left, image=self._logo_img, bg=C["card"])
        logo.pack(side="left", padx=(0, 12))
        reg(logo, lambda w: w.configure(bg=C["card"]))

        title_group = tk.Frame(left, bg=C["card"])
        title_group.pack(side="left", fill="x", expand=True)
        reg(title_group, lambda w: w.configure(bg=C["card"]))

        title = tk.Label(title_group, text="mdcodebrief", font=FH, bg=C["card"], fg=C["text"])
        title.pack(anchor="w")
        reg(title, lambda w: w.configure(bg=C["card"], fg=C["text"]))

        subtitle = tk.Label(title_group, text="Compact project briefs for AI review, refactors, and debugging.", font=FT, bg=C["card"], fg=C["text2"])
        subtitle.pack(anchor="w", pady=(2, 0))
        reg(subtitle, lambda w: w.configure(bg=C["card"], fg=C["text2"]))

        right = tk.Frame(header_inner, bg=C["card"])
        right.pack(side="right")
        reg(right, lambda w: w.configure(bg=C["card"]))

        version = tk.Label(right, text=f"v{__version__}", font=FT, bg=C["tag_bg"], fg=C["tag_fg"], padx=10, pady=4)
        version.pack(side="right", padx=(8, 0))
        reg(version, lambda w: w.configure(bg=C["tag_bg"], fg=C["tag_fg"]))

        ThemeToggleBtn(right, self._toggle_theme).pack(side="right")

        body = tk.Frame(self, bg=C["bg"])
        body.pack(fill="both", expand=True, padx=16, pady=16)
        reg(body, lambda w: w.configure(bg=C["bg"]))
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(2, weight=1)

        self._var_hidden = tk.BooleanVar()
        self._var_unknown = tk.BooleanVar()
        self._var_diff = tk.BooleanVar()
        self._var_staged = tk.BooleanVar()
        self._var_copy = tk.BooleanVar()

        folder_card = Card(body)
        folder_card.grid(row=0, column=0, columnspan=2, sticky="ew")
        folder_inner = tk.Frame(folder_card, bg=C["card"])
        folder_inner.pack(fill="both", expand=True, padx=14, pady=14)
        reg(folder_inner, lambda w: w.configure(bg=C["card"]))
        section(folder_inner, "Project folder", "required", "card").pack(anchor="w")

        folder_row = tk.Frame(folder_inner, bg=C["card"])
        folder_row.pack(fill="x", pady=(10, 0))
        reg(folder_row, lambda w: w.configure(bg=C["card"]))

        self._path_entry = InputField(folder_row, placeholder="Select a project folder...")
        self._path_entry.pack(side="left", fill="x", expand=True)

        self._btn_pick = FlatBtn(folder_row, "Browse", "accent_dk", self._pick_folder, font=FBS)
        self._btn_pick.pack(side="left", padx=(10, 0))

        folder_hint = tk.Label(folder_inner, text="Hidden files stay out by default. Output is saved to your Desktop.", font=FT, bg=C["card"], fg=C["text3"])
        folder_hint.pack(anchor="w", pady=(8, 0))
        reg(folder_hint, lambda w: w.configure(bg=C["card"], fg=C["text3"]))

        prompt_card = Card(body)
        prompt_card.grid(row=1, column=0, sticky="nsew", pady=(14, 0), padx=(0, 8))
        prompt_inner = tk.Frame(prompt_card, bg=C["card"])
        prompt_inner.pack(fill="both", expand=True, padx=14, pady=14)
        reg(prompt_inner, lambda w: w.configure(bg=C["card"]))
        section(prompt_inner, "AI instruction", "optional", "card").pack(anchor="w")

        hint = tk.Label(prompt_inner, text='"Review this PR"  |  "Find the bug"  |  "Summarize the architecture"', font=FT, bg=C["card"], fg=C["text3"])
        hint.pack(anchor="w", pady=(8, 8))
        reg(hint, lambda w: w.configure(bg=C["card"], fg=C["text3"]))

        self._prompt_var = tk.StringVar()
        self._prompt_field = InputField(prompt_inner, var=self._prompt_var, placeholder="Tell the AI what you want from this export...", font=FS)
        self._prompt_field.pack(fill="x")

        options_card = Card(body)
        options_card.grid(row=1, column=1, sticky="nsew", pady=(14, 0), padx=(8, 0))
        options_inner = tk.Frame(options_card, bg=C["card"])
        options_inner.pack(fill="both", expand=True, padx=14, pady=14)
        reg(options_inner, lambda w: w.configure(bg=C["card"]))
        section(options_inner, "Options", bg_key="card").pack(anchor="w")

        toggles = tk.Frame(options_inner, bg=C["card"])
        toggles.pack(fill="both", expand=True, pady=(10, 0))
        reg(toggles, lambda w: w.configure(bg=C["card"]))

        self._toggle_hidden = Toggle(toggles, "Include hidden files", self._var_hidden)
        self._toggle_hidden.pack(anchor="w", pady=(0, 8))
        self._toggle_unknown = Toggle(toggles, "Include unknown extensions", self._var_unknown)
        self._toggle_unknown.pack(anchor="w", pady=(0, 8))
        self._toggle_diff = Toggle(toggles, "Git diff mode", self._var_diff)
        self._toggle_diff.pack(anchor="w", pady=(0, 8))
        self._toggle_staged = Toggle(toggles, "Staged only", self._var_staged)
        self._toggle_staged.pack(anchor="w", pady=(0, 8))
        self._toggle_copy = Toggle(toggles, "Copy to clipboard", self._var_copy)
        self._toggle_copy.pack(anchor="w")
        self._var_diff.trace_add("write", lambda *_: self._sync_option_states())

        log_card = Card(body)
        log_card.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(14, 0))
        log_inner = tk.Frame(log_card, bg=C["card"])
        log_inner.pack(fill="both", expand=True, padx=14, pady=14)
        reg(log_inner, lambda w: w.configure(bg=C["card"]))
        log_inner.grid_rowconfigure(1, weight=1)
        log_inner.grid_columnconfigure(0, weight=1)
        section(log_inner, "Log", bg_key="card").grid(row=0, column=0, sticky="w")

        log_shell = tk.Frame(log_inner, bg=C["bg2"], highlightthickness=1, highlightbackground=C["border"])
        log_shell.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        log_shell.grid_rowconfigure(0, weight=1)
        log_shell.grid_columnconfigure(0, weight=1)
        reg(log_shell, lambda w: w.configure(bg=C["bg2"], highlightbackground=C["border"]))

        self._log = tk.Text(log_shell, font=FM, bg=C["bg2"], fg=C["text"], insertbackground=C["accent"], relief="flat", bd=0, padx=12, pady=12, state="disabled", wrap="word", cursor="arrow")
        self._log.grid(row=0, column=0, sticky="nsew")
        reg(self._log, lambda w: w.configure(bg=C["bg2"], fg=C["text"]))

        scrollbar = ttk.Scrollbar(log_shell, orient="vertical", command=self._log.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self._log.configure(yscrollcommand=scrollbar.set)

        for tag, color_key in (("ok", "green"), ("warn", "amber"), ("err", "red"), ("info", "accent"), ("muted", "text3")):
            self._log.tag_config(tag, foreground=C[color_key])

        self._progress = ttk.Progressbar(body, style="TProgressbar", mode="indeterminate")
        self._progress.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(12, 0))

        action_bar = tk.Frame(body, bg=C["bg"])
        action_bar.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        action_bar.grid_columnconfigure(2, weight=1)
        reg(action_bar, lambda w: w.configure(bg=C["bg"]))

        self._btn_gen = FlatBtn(action_bar, "Generate .md", "green", self._start)
        self._btn_gen.configure(state="disabled")
        self._btn_gen.grid(row=0, column=0, sticky="w")

        self._btn_clip = FlatBtn(action_bar, "Copy latest", "violet", self._copy_to_clipboard, font=FBS)
        self._btn_clip.configure(state="disabled")
        self._btn_clip.grid(row=0, column=1, sticky="w", padx=(10, 0))

        self._pill = StatusPill(action_bar)
        self._pill.grid(row=0, column=3, sticky="e")

        self._sync_option_states()

    def _toggle_theme(self):
        toggle_theme()
        self._refresh_ttk()
        ThemeRegistry.repaint()
        self.configure(bg=C["bg"])
        for tag, color_key in (("ok", "green"), ("warn", "amber"), ("err", "red"), ("info", "accent"), ("muted", "text3")):
            self._log.tag_config(tag, foreground=C[color_key])

    def _sync_option_states(self):
        if not self._var_diff.get():
            self._var_staged.set(False)
        self._toggle_staged.configure(state="normal" if self._var_diff.get() else "disabled")

    def _finish_success(self, md: str, out_file: Path, copy_requested: bool):
        self._last_md = md
        if copy_requested:
            self._do_copy(md)
            self._log_write("Copied to clipboard.", "ok")
        self._log_write(f"Saved: {out_file}", "ok")
        self._pill.set("Done", "ok")
        self._btn_clip.configure(state="normal")
        messagebox.showinfo("Done", f"Saved to:\n\n{out_file}")

    def _center(self):
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        self.geometry(f"{width}x{height}+{(screen_width - width) // 2}+{(screen_height - height) // 2}")

    def _pick_folder(self):
        path = filedialog.askdirectory(title="Select project folder")
        if not path:
            return
        self._project_path = Path(path)
        self._path_entry.set_value(str(self._project_path))
        self._btn_gen.configure(state="normal")
        self._log_clear()
        self._log_write(f"Folder: {self._project_path}", "info")
        self._pill.set(self._project_path.name, "info")

    def _start(self):
        if self._running or not self._project_path:
            return
        self._running = True
        self._btn_gen.configure(state="disabled", text="Working...")
        self._btn_pick.configure(state="disabled")
        self._btn_clip.configure(state="disabled")
        self._log_clear()
        self._pill.set("Scanning", "info")
        self._progress.start(10)
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        try:
            md = generate_markdown(
                self._project_path,
                include_hidden=self._var_hidden.get(),
                include_unknown=self._var_unknown.get(),
                diff_mode=self._var_diff.get(),
                staged_only=self._var_staged.get(),
                system_prompt=self._prompt_field.get_value(),
                log_cb=self._log_write,
            )
            desktop = get_desktop()
            safe_name = safe_project_name(self._project_path.name)
            out_file = desktop / f"resume - {safe_name}.md"
            out_file.write_text(md, encoding="utf-8")
            self.after(0, lambda: self._finish_success(md, out_file, self._var_copy.get()))
        except Exception as exc:
            self._log_write(f"Error: {exc}", "err")
            self.after(0, lambda: self._pill.set("Error", "err"))
            self.after(0, lambda: messagebox.showerror("Error", str(exc)))
        finally:
            self._running = False
            self.after(0, self._progress.stop)
            self.after(0, lambda: self._btn_gen.configure(state="normal", text="Generate .md"))
            self.after(0, lambda: self._btn_pick.configure(state="normal"))

    def _copy_to_clipboard(self):
        if not self._last_md:
            messagebox.showwarning("Nothing to copy", "Generate a file first.")
            return
        self._do_copy(self._last_md)
        self._pill.set("Copied", "ok")

    def _do_copy(self, text: str):
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()

    def _log_clear(self):
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")

    def _log_write(self, msg: str, tag: str = ""):
        def _write():
            self._log.configure(state="normal")
            self._log.insert("end", msg + "\n", tag)
            self._log.see("end")
            self._log.configure(state="disabled")

        self.after(0, _write)
