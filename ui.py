"""
ui.py — Tkinter GUI: widgets, layout, and App class.
"""

import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path

from renderer import __version__, generate_markdown
from theme import C, FL, FM, FS, FB, FBS, FH, FT, ThemeRegistry, darken, reg, toggle_theme
from utils import get_desktop, safe_project_name


# ─────────────────────────────────────────────────────────────────────────────
# ICON HELPER
# ─────────────────────────────────────────────────────────────────────────────

def _icon_path() -> Path | None:
    if getattr(sys, "frozen", False):
        return None
    p = Path(__file__).parent / "icon.ico"
    return p if p.is_file() else None


# ─────────────────────────────────────────────────────────────────────────────
# FLAT BUTTON
# ─────────────────────────────────────────────────────────────────────────────

class FlatBtn(tk.Frame):
    def __init__(self, parent, text: str, color_key: str, command,
                 font=None, padx: int = 22, pady: int = 10, **kw):
        super().__init__(parent, bg=C["bg"], cursor="hand2")
        self._ck      = color_key
        self._enabled = True

        self._btn = tk.Button(
            self, text=text, font=font or FB,
            bg=C[color_key], fg=C["white"],
            activebackground=darken(C[color_key]),
            activeforeground=C["white"],
            relief="flat", bd=0,
            padx=padx, pady=pady,
            cursor="hand2", command=command,
        )
        self._btn.pack(fill="both", expand=True)
        self._btn.bind("<Enter>", self._hover_on)
        self._btn.bind("<Leave>", self._hover_off)
        reg(self, lambda w: w._repaint())

    def _repaint(self):
        self.configure(bg=C["bg"])
        if self._enabled:
            self._btn.configure(bg=C[self._ck], fg=C["white"],
                                activebackground=darken(C[self._ck]))
        else:
            self._btn.configure(bg=C["border"], fg=C["text3"])

    def _hover_on(self, _=None):
        if self._enabled:
            self._btn.configure(bg=darken(C[self._ck]))

    def _hover_off(self, _=None):
        if self._enabled:
            self._btn.configure(bg=C[self._ck])

    def configure(self, **kw):
        if "state" in kw:
            self._enabled = kw.pop("state") != "disabled"
            if self._enabled:
                self._btn.configure(state="normal", bg=C[self._ck], fg=C["white"])
            else:
                self._btn.configure(state="disabled", bg=C["border"], fg=C["text3"])
        if "text" in kw:
            self._btn.configure(text=kw.pop("text"))
        if kw:
            super().configure(**kw)


# ─────────────────────────────────────────────────────────────────────────────
# INPUT FIELD
# ─────────────────────────────────────────────────────────────────────────────

class InputField(tk.Frame):
    def __init__(self, parent, var=None, font=None, placeholder: str = "", **kw):
        super().__init__(parent, bg=C["input"],
                         highlightthickness=1,
                         highlightbackground=C["border"],
                         highlightcolor=C["accent"])
        self._var         = var or tk.StringVar()
        self._placeholder = placeholder

        self._entry = tk.Entry(
            self, textvariable=self._var,
            font=font or FM,
            bg=C["input"], fg=C["text"],
            insertbackground=C["accent"],
            disabledbackground=C["input"],
            disabledforeground=C["text2"],
            relief="flat", bd=0,
        )
        self._entry.pack(fill="x", padx=12, pady=9)

        if placeholder:
            self._set_ph()
            self._entry.bind("<FocusIn>",  self._fi)
            self._entry.bind("<FocusOut>", self._fo)

        reg(self, lambda w: w._repaint())

    def _repaint(self):
        col = C["input"]
        self.configure(bg=col,
                       highlightbackground=C["border"],
                       highlightcolor=C["accent"])
        self._entry.configure(
            bg=col,
            fg=C["text3"] if self._is_placeholder() else C["text"],
            insertbackground=C["accent"],
            disabledbackground=col,
            disabledforeground=C["text2"],
        )

    def _is_placeholder(self) -> bool:
        return bool(self._placeholder and self._var.get() == self._placeholder)

    def _set_ph(self):
        self._var.set(self._placeholder)
        self._entry.configure(fg=C["text3"])

    def _fi(self, _):
        if self._is_placeholder():
            self._var.set("")
            self._entry.configure(fg=C["text"])

    def _fo(self, _):
        if not self._var.get().strip():
            self._set_ph()

    def get_value(self) -> str:
        v = self._var.get()
        return "" if self._placeholder and v == self._placeholder else v

    def set_value(self, v: str):
        self._var.set(v)
        self._entry.configure(fg=C["text"])


# ─────────────────────────────────────────────────────────────────────────────
# TOGGLE SWITCH
# ─────────────────────────────────────────────────────────────────────────────

class Toggle(tk.Frame):
    W, H = 38, 22

    def __init__(self, parent, text: str, variable: tk.BooleanVar,
                 bg_key: str = "card", **kw):
        super().__init__(parent, bg=C[bg_key], cursor="hand2")
        self._var    = variable
        self._bg_key = bg_key
        self._enabled = True

        self._cv = tk.Canvas(self, width=self.W, height=self.H,
                              bg=C[bg_key], highlightthickness=0, cursor="hand2")
        self._cv.pack(side="left", padx=(10, 8), pady=8)

        self._lbl = tk.Label(self, text=text, font=FS,
                              bg=C[bg_key], fg=C["text2"], cursor="hand2")
        self._lbl.pack(side="left", pady=8, padx=(0, 12))

        self._draw()
        for w in (self, self._cv, self._lbl):
            w.bind("<Button-1>", self._toggle)

        reg(self, lambda w: w._repaint())

    def _draw(self):
        self._cv.delete("all")
        on    = self._var.get()
        if not self._enabled:
            track = C["border"]
        else:
            track = C["accent"] if on else C["border2"]
        r     = self.H // 2
        self._cv.create_oval(0, 0, self.H, self.H, fill=track, outline=track)
        self._cv.create_oval(self.W - self.H, 0, self.W, self.H, fill=track, outline=track)
        self._cv.create_rectangle(r, 0, self.W - r, self.H, fill=track, outline=track)
        p  = 3
        kx = self.W - r if on else r
        self._cv.create_oval(kx - r + p + 1, p, kx + r - p - 1, self.H - p,
                               fill=C["white"], outline="")

    def _repaint(self):
        bg = C[self._bg_key]
        self.configure(bg=bg)
        self._cv.configure(bg=bg)
        self._lbl.configure(bg=bg, fg=C["text2"] if self._enabled else C["text3"])
        self._draw()

    def _toggle(self, _=None):
        if not self._enabled:
            return
        self._var.set(not self._var.get())
        self._draw()

    def configure(self, **kw):
        if "state" in kw:
            self._enabled = kw.pop("state") != "disabled"
            cursor = "hand2" if self._enabled else "arrow"
            super().configure(cursor=cursor)
            self._cv.configure(cursor=cursor)
            self._lbl.configure(cursor=cursor)
            self._draw()
        if kw:
            super().configure(**kw)


# ─────────────────────────────────────────────────────────────────────────────
# THEME TOGGLE BUTTON
# ─────────────────────────────────────────────────────────────────────────────

class ThemeToggleBtn(tk.Canvas):
    SIZE = 32

    def __init__(self, parent, on_toggle, **kw):
        super().__init__(parent, width=self.SIZE, height=self.SIZE,
                          highlightthickness=0, cursor="hand2", bd=0)
        self._on_toggle = on_toggle
        self._draw()
        self.bind("<Button-1>", lambda _: on_toggle())
        self.bind("<Enter>",    lambda _: self._draw(hover=True))
        self.bind("<Leave>",    lambda _: self._draw(hover=False))
        reg(self, lambda w: w._draw())

    def _draw(self, hover: bool = False):
        self.delete("all")
        self.configure(bg=C["card"])
        icon = "☀" if C["mode"] == "dark" else "🌙"
        col  = C["accent"] if hover else C["text2"]
        self.create_text(self.SIZE // 2, self.SIZE // 2,
                          text=icon, font=("Segoe UI", 14), fill=col)


# ─────────────────────────────────────────────────────────────────────────────
# STATUS PILL
# ─────────────────────────────────────────────────────────────────────────────

class StatusPill(tk.Frame):
    def __init__(self, parent, **kw):
        super().__init__(parent, bg=C["bg"])
        reg(self, lambda w: w.configure(bg=C["bg"]))
        self._lbl = tk.Label(self, text="", font=FT,
                              bg=C["tag_bg"], fg=C["tag_fg"],
                              padx=8, pady=2)
        reg(self._lbl, lambda w: w.configure(bg=C["tag_bg"], fg=C["tag_fg"]))

    def set(self, text: str, kind: str = "info"):
        mapping = {
            "info": ("tag_bg", "tag_fg"),
            "ok":   ("green",  "white"),
            "err":  ("red",    "white"),
            "warn": ("amber",  "white"),
        }
        bg_k, fg_k = mapping.get(kind, ("tag_bg", "tag_fg"))
        self._lbl.configure(
            text=f"  {text}  ",
            bg=C[bg_k],
            fg=C[fg_k] if fg_k != "white" else C["white"],
        )
        self._lbl.pack(side="left")

    def clear(self):
        self._lbl.configure(text="")
        self._lbl.pack_forget()


# ─────────────────────────────────────────────────────────────────────────────
# CARD
# ─────────────────────────────────────────────────────────────────────────────

class Card(tk.Frame):
    def __init__(self, parent, bg_key: str = "card", **kw):
        super().__init__(parent, bg=C[bg_key],
                         highlightthickness=1,
                         highlightbackground=C["border"], **kw)
        self._bk = bg_key
        reg(self, lambda w: w.configure(bg=C[w._bk],
                                         highlightbackground=C["border"]))


# ─────────────────────────────────────────────────────────────────────────────
# SECTION HEADER + HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def section(parent, title: str, subtitle: str = "") -> tk.Frame:
    row = tk.Frame(parent, bg=C["bg"])
    reg(row, lambda w: w.configure(bg=C["bg"]))

    pip = tk.Frame(row, bg=C["accent"], width=3, height=14)
    pip.pack(side="left", padx=(0, 8))
    reg(pip, lambda w: w.configure(bg=C["accent"]))

    lbl = tk.Label(row, text=title, font=FL, bg=C["bg"], fg=C["text"])
    lbl.pack(side="left")
    reg(lbl, lambda w: w.configure(bg=C["bg"], fg=C["text"]))

    if subtitle:
        sub = tk.Label(row, text=subtitle, font=FS, bg=C["bg"], fg=C["text3"])
        sub.pack(side="left", padx=(8, 0))
        reg(sub, lambda w: w.configure(bg=C["bg"], fg=C["text3"]))

    return row


def sp(parent, h: int):
    """Spacing frame."""
    f = tk.Frame(parent, bg=C["bg"], height=h)
    f.pack()
    reg(f, lambda w: w.configure(bg=C["bg"]))


def div(parent):
    """Horizontal divider."""
    f = tk.Frame(parent, bg=C["border"], height=1)
    f.pack(fill="x")
    reg(f, lambda w: w.configure(bg=C["border"]))


def badge(parent, text: str, bg_key: str = "tag_bg", fg_key: str = "tag_fg") -> tk.Frame:
    frame = tk.Frame(parent, bg=C[bg_key], highlightthickness=1, highlightbackground=C["border"])
    reg(frame, lambda w: w.configure(bg=C[bg_key], highlightbackground=C["border"]))

    label = tk.Label(frame, text=text, font=FT, bg=C[bg_key], fg=C[fg_key], padx=10, pady=4)
    label.pack()
    reg(label, lambda w: w.configure(bg=C[bg_key], fg=C[fg_key]))

    return frame


# ─────────────────────────────────────────────────────────────────────────────
# DESKTOP HELPER
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# APP
# ─────────────────────────────────────────────────────────────────────────────

class App(tk.Tk):
    W = 860

    def __init__(self):
        super().__init__()
        self.title(f"mdcodebrief  v{__version__}")
        self.configure(bg=C["bg"])
        self.resizable(False, False)

        self._project_path: Path | None = None
        self._running  = False
        self._last_md  = ""

        ico = _icon_path()
        if ico:
            try:
                self.iconbitmap(str(ico))
            except Exception:
                pass

        self._setup_ttk()
        self._build_ui()
        self._center()

    # ── TTK ───────────────────────────────────────────────────────────────────

    def _setup_ttk(self):
        s = ttk.Style()
        s.theme_use("clam")
        s.configure("TProgressbar",
                    troughcolor=C["card2"], background=C["accent"],
                    bordercolor=C["bg"], lightcolor=C["accent"],
                    darkcolor=C["accent"], thickness=4)
        s.configure("TScrollbar",
                    troughcolor=C["card"], background=C["border"],
                    arrowcolor=C["text3"], bordercolor=C["card"],
                    relief="flat")

    def _refresh_ttk(self):
        s = ttk.Style()
        s.configure("TProgressbar",
                    troughcolor=C["card2"], background=C["accent"],
                    bordercolor=C["bg"], lightcolor=C["accent"],
                    darkcolor=C["accent"])
        s.configure("TScrollbar",
                    troughcolor=C["card"], background=C["border"],
                    arrowcolor=C["text3"], bordercolor=C["card"])

    # ── BUILD UI ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        ThemeRegistry.reset()

        # ── Header ────────────────────────────────────────────────────────────
        hdr = tk.Frame(self, bg=C["card"])
        hdr.pack(fill="x")
        reg(hdr, lambda w: w.configure(bg=C["card"]))

        hdr_inner = tk.Frame(hdr, bg=C["card"])
        hdr_inner.pack(fill="x", padx=24, pady=18)
        reg(hdr_inner, lambda w: w.configure(bg=C["card"]))

        logo_f = tk.Frame(hdr_inner, bg=C["card"])
        logo_f.pack(side="left")
        reg(logo_f, lambda w: w.configure(bg=C["card"]))

        title_row = tk.Frame(logo_f, bg=C["card"])
        title_row.pack(anchor="w")
        reg(title_row, lambda w: w.configure(bg=C["card"]))

        bolt = tk.Label(title_row, text="⚡", font=("Segoe UI", 16),
                         bg=C["card"], fg=C["accent"])
        bolt.pack(side="left", padx=(0, 6))
        reg(bolt, lambda w: w.configure(bg=C["card"], fg=C["accent"]))

        name_lbl = tk.Label(title_row, text="mdcodebrief",
                             font=FH, bg=C["card"], fg=C["text"])
        name_lbl.pack(side="left")
        reg(name_lbl, lambda w: w.configure(bg=C["card"], fg=C["text"]))

        sub_lbl = tk.Label(
            logo_f,
            text="Turn any project into a clean AI-ready Markdown brief with safer defaults.",
            font=FS,
            bg=C["card"],
            fg=C["text2"],
        )
        sub_lbl.pack(anchor="w", pady=(4, 0))
        reg(sub_lbl, lambda w: w.configure(bg=C["card"], fg=C["text2"]))

        meta_row = tk.Frame(logo_f, bg=C["card"])
        meta_row.pack(anchor="w", pady=(12, 0))
        reg(meta_row, lambda w: w.configure(bg=C["card"]))

        badge(meta_row, "Read-only").pack(side="left", padx=(0, 8))
        badge(meta_row, "Zero dependency").pack(side="left", padx=(0, 8))
        badge(meta_row, "AI-ready export").pack(side="left")

        right_f = tk.Frame(hdr_inner, bg=C["card"])
        right_f.pack(side="right", anchor="n")
        reg(right_f, lambda w: w.configure(bg=C["card"]))

        ThemeToggleBtn(right_f, self._toggle_theme).pack(side="right", padx=(10, 0))
        badge(right_f, f"v{__version__}").pack(side="right")

        div(self)

        # ── Body ──────────────────────────────────────────────────────────────
        body = tk.Frame(self, bg=C["bg"])
        body.pack(fill="both", padx=22, pady=18)
        reg(body, lambda w: w.configure(bg=C["bg"]))

        intro = Card(body, bg_key="card2")
        intro.pack(fill="x")
        intro_inner = tk.Frame(intro, bg=C["card2"])
        intro_inner.pack(fill="x", padx=18, pady=16)
        reg(intro_inner, lambda w: w.configure(bg=C["card2"]))

        intro_title = tk.Label(
            intro_inner,
            text="Build a focused project brief in one pass",
            font=FL,
            bg=C["card2"],
            fg=C["text"],
        )
        intro_title.pack(anchor="w")
        reg(intro_title, lambda w: w.configure(bg=C["card2"], fg=C["text"]))

        intro_copy = tk.Label(
            intro_inner,
            text="Pick a folder, choose your scan scope, and generate a Markdown context file that is easier to paste into AI tools.",
            font=FS,
            bg=C["card2"],
            fg=C["text2"],
        )
        intro_copy.pack(anchor="w", pady=(5, 0))
        reg(intro_copy, lambda w: w.configure(bg=C["card2"], fg=C["text2"]))

        sp(body, 16)

        # Project Folder
        section(body, "Project Folder").pack(anchor="w")
        sp(body, 6)
        row1 = tk.Frame(body, bg=C["bg"])
        row1.pack(fill="x")
        reg(row1, lambda w: w.configure(bg=C["bg"]))

        self._path_entry = InputField(row1, placeholder="Select a project folder…")
        self._path_entry.pack(side="left", fill="x", expand=True)

        self._btn_pick = FlatBtn(row1, "  Browse  ", "violet",
                                  self._pick_folder, font=FBS, padx=18, pady=9)
        self._btn_pick.pack(side="left", padx=(8, 0))

        folder_note = tk.Label(
            body,
            text="Hidden files stay out by default, and the generated brief is saved to your Desktop.",
            font=FT,
            bg=C["bg"],
            fg=C["text3"],
        )
        folder_note.pack(anchor="w", pady=(8, 0))
        reg(folder_note, lambda w: w.configure(bg=C["bg"], fg=C["text3"]))

        sp(body, 20)

        # Two columns
        row2 = tk.Frame(body, bg=C["bg"])
        row2.pack(fill="x")
        reg(row2, lambda w: w.configure(bg=C["bg"]))

        left_col = tk.Frame(row2, bg=C["bg"])
        left_col.pack(side="left", fill="both", expand=True, padx=(0, 10))
        reg(left_col, lambda w: w.configure(bg=C["bg"]))

        section(left_col, "AI Instruction", "— optional").pack(anchor="w")
        sp(left_col, 6)
        hint = tk.Label(left_col,
                         text='"Find the memory leak" · "Refactor to TypeScript"',
                         font=FT, bg=C["bg"], fg=C["text3"])
        hint.pack(anchor="w", pady=(0, 6))
        reg(hint, lambda w: w.configure(bg=C["bg"], fg=C["text3"]))

        self._prompt_var   = tk.StringVar()
        self._prompt_field = InputField(
            left_col, var=self._prompt_var,
            font=("Segoe UI", 10),
            placeholder="Type an instruction for the AI…",
        )
        self._prompt_field.pack(fill="x")

        right_col = tk.Frame(row2, bg=C["bg"])
        right_col.pack(side="left", fill="both", expand=True)
        reg(right_col, lambda w: w.configure(bg=C["bg"]))

        section(right_col, "Options").pack(anchor="w")
        sp(right_col, 6)

        opts_card = Card(right_col)
        opts_card.pack(fill="x")

        self._var_hidden  = tk.BooleanVar()
        self._var_unknown = tk.BooleanVar()
        self._var_diff    = tk.BooleanVar()
        self._var_staged  = tk.BooleanVar()
        self._var_copy    = tk.BooleanVar()

        col_a = tk.Frame(opts_card, bg=C["card"])
        col_a.pack(side="left", fill="x", expand=True)
        col_b = tk.Frame(opts_card, bg=C["card"])
        col_b.pack(side="left", fill="x", expand=True)
        reg(col_a, lambda w: w.configure(bg=C["card"]))
        reg(col_b, lambda w: w.configure(bg=C["card"]))

        self._toggle_hidden = Toggle(col_a, "Hidden files", self._var_hidden, "card")
        self._toggle_hidden.pack(anchor="w")
        self._toggle_unknown = Toggle(col_a, "Unknown extensions", self._var_unknown, "card")
        self._toggle_unknown.pack(anchor="w")
        self._toggle_diff = Toggle(col_b, "Git diff mode", self._var_diff, "card")
        self._toggle_diff.pack(anchor="w")
        self._toggle_staged = Toggle(col_b, "Staged only", self._var_staged, "card")
        self._toggle_staged.pack(anchor="w")
        self._toggle_copy = Toggle(col_b, "Copy to clipboard", self._var_copy, "card")
        self._toggle_copy.pack(anchor="w")
        self._var_diff.trace_add("write", lambda *_: self._sync_option_states())

        sp(body, 20)

        # Log
        section(body, "Log").pack(anchor="w")
        sp(body, 6)
        log_card = Card(body)
        log_card.pack(fill="x")

        self._log = tk.Text(
            log_card, height=7, font=FM,
            bg=C["bg2"], fg=C["text"],
            insertbackground=C["accent"],
            relief="flat", bd=10,
            state="disabled", wrap="word", cursor="arrow",
        )
        reg(self._log, lambda w: w.configure(bg=C["bg2"], fg=C["text"]))

        sb = ttk.Scrollbar(log_card, orient="vertical", command=self._log.yview)
        self._log.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._log.pack(fill="x")

        for tag, col_key in [("ok", "green"), ("warn", "amber"),
                              ("err", "red"),  ("info", "accent"),
                              ("muted", "text3")]:
            self._log.tag_config(tag, foreground=C[col_key])

        # Progress
        self._progress = ttk.Progressbar(body, style="TProgressbar", mode="indeterminate")
        self._progress.pack(fill="x", pady=(10, 0))

        sp(body, 16)
        div(body)
        sp(body, 14)

        # Action bar
        bar = tk.Frame(body, bg=C["bg"])
        bar.pack(fill="x")
        reg(bar, lambda w: w.configure(bg=C["bg"]))

        self._btn_gen = FlatBtn(bar, "  Generate .md  ", "green",
                                 self._start, padx=24, pady=11)
        self._btn_gen.configure(state="disabled")
        self._btn_gen.pack(side="left")

        self._btn_clip = FlatBtn(bar, "  Copy Latest  ", "accent_dk",
                                  self._copy_to_clipboard, font=FBS, padx=18, pady=11)
        self._btn_clip.configure(state="disabled")
        self._btn_clip.pack(side="left", padx=(10, 0))

        self._pill = StatusPill(bar)
        self._pill.pack(side="right")

        sp(body, 10)
        footer = tk.Frame(body, bg=C["bg"])
        footer.pack(fill="x")
        reg(footer, lambda w: w.configure(bg=C["bg"]))
        badge(footer, "Local only").pack(side="left", padx=(0, 8))
        badge(footer, "No telemetry").pack(side="left", padx=(0, 8))
        badge(footer, "Safer hidden-file defaults").pack(side="left")

        sp(body, 4)
        self._sync_option_states()
        self.update_idletasks()
        self.geometry(f"{self.W}x{self.winfo_reqheight()}")

    # ── Theme ─────────────────────────────────────────────────────────────────

    def _toggle_theme(self):
        toggle_theme()
        self._refresh_ttk()
        ThemeRegistry.repaint()
        self.configure(bg=C["bg"])
        for tag, col_key in [("ok", "green"), ("warn", "amber"),
                              ("err", "red"),  ("info", "accent"),
                              ("muted", "text3")]:
            self._log.tag_config(tag, foreground=C[col_key])

    def _sync_option_states(self):
        diff_enabled = self._var_diff.get()
        if not diff_enabled:
            self._var_staged.set(False)
        self._toggle_staged.configure(state="normal" if diff_enabled else "disabled")

    def _finish_success(self, md: str, out_file: Path, copy_requested: bool):
        self._last_md = md
        if copy_requested:
            self._do_copy(md)
            self._log_write("📋  Copied to clipboard!", "ok")

        self._log_write(f"\n✅  Saved: {out_file}", "ok")
        self._pill.set("Done ✓", "ok")
        self._btn_clip.configure(state="normal")
        messagebox.showinfo(
            "Done 🎉",
            f"Saved to your Desktop:\n\n{out_file.name}\n\n{out_file}"
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _center(self):
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

    # ── Events ────────────────────────────────────────────────────────────────

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
        self._btn_gen.configure(state="disabled", text="  Working...  ")
        self._btn_pick.configure(state="disabled")
        self._btn_clip.configure(state="disabled")
        self._log_clear()
        self._progress.start(10)
        self._pill.set("Scanning…", "info")
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
            desktop  = get_desktop()
            safe     = safe_project_name(self._project_path.name)
            out_file = desktop / f"resume - {safe}.md"
            out_file.write_text(md, encoding="utf-8")

            self.after(0, lambda: self._finish_success(md, out_file, self._var_copy.get()))

        except Exception as exc:
            self._log_write(f"\n❌  {exc}", "err")
            self.after(0, lambda: self._pill.set("Error", "err"))
            self.after(0, lambda: messagebox.showerror("Error", str(exc)))

        finally:
            self._running = False
            self.after(0, self._progress.stop)
            self.after(0, lambda: self._btn_gen.configure(
                state="normal", text="  Generate .md  "))
            self.after(0, lambda: self._btn_pick.configure(state="normal"))

    def _copy_to_clipboard(self):
        if not self._last_md:
            messagebox.showwarning("Nothing to copy", "Generate a file first.")
            return
        self._do_copy(self._last_md)
        self._pill.set("Copied ✓", "ok")

    def _do_copy(self, text: str):
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()

    def _log_clear(self):
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")

    def _log_write(self, msg: str, tag: str = ""):
        def _do():
            self._log.configure(state="normal")
            self._log.insert("end", msg + "\n", tag)
            self._log.see("end")
            self._log.configure(state="disabled")
        self.after(0, _do)
