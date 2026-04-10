"""
mdcodebrief — MD Code Brief
Scans an entire project and generates a structured .md file
with full code context, ideal for AI models.

Author: https://github.com/pablokaua03
Repository: https://github.com/pablokaua03/mdcodebrief
License: MIT
"""

import os
import sys
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
from datetime import datetime

# ─────────────────────────────────────────────────────────────────────────────
# VERSION
# ─────────────────────────────────────────────────────────────────────────────

__version__ = "1.2.0"
__author__  = "pablokaua03"

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

CODE_EXTENSIONS: dict[str, str] = {
    ".html": "html", ".htm": "html", ".css": "css", ".scss": "scss",
    ".sass": "sass", ".less": "less", ".js": "javascript", ".jsx": "jsx",
    ".ts": "typescript", ".tsx": "tsx", ".vue": "vue", ".svelte": "svelte",
    ".py": "python", ".rb": "ruby", ".php": "php", ".java": "java",
    ".cs": "csharp", ".go": "go", ".rs": "rust", ".cpp": "cpp",
    ".c": "c", ".h": "c", ".hpp": "cpp", ".swift": "swift",
    ".kt": "kotlin", ".kts": "kotlin", ".scala": "scala",
    ".sh": "bash", ".bash": "bash", ".zsh": "bash", ".fish": "fish",
    ".ps1": "powershell", ".bat": "bat", ".cmd": "bat",
    ".json": "json", ".yaml": "yaml", ".yml": "yaml", ".toml": "toml",
    ".ini": "ini", ".cfg": "ini", ".env": "dotenv",
    ".xml": "xml", ".graphql": "graphql", ".proto": "protobuf",
    ".md": "markdown", ".mdx": "mdx", ".rst": "rst", ".txt": "text",
    ".sql": "sql", ".tf": "hcl", ".hcl": "hcl",
    "dockerfile": "dockerfile", ".dockerfile": "dockerfile",
    ".r": "r", ".lua": "lua", ".ex": "elixir", ".exs": "elixir",
    ".dart": "dart", ".nim": "nim", ".zig": "zig",
}

IGNORE_DIRS: set[str] = {
    ".git", ".svn", ".hg", ".bzr",
    "node_modules", ".npm", ".yarn", ".pnp",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "venv", ".venv", "env", ".env",
    ".tox", ".nox",
    "dist", "build", ".build", "out",
    ".next", ".nuxt", ".svelte-kit", ".astro",
    "coverage", ".coverage", "htmlcov",
    ".idea", ".vscode", ".vs",
    "*.egg-info", ".eggs",
    "target", "vendor", ".terraform",
    "tmp", "temp", ".tmp", ".temp",
    "logs", ".logs", "cache", ".cache",
}

IGNORE_FILES: set[str] = {
    ".DS_Store", "Thumbs.db", "desktop.ini",
    ".gitignore", ".gitattributes", ".gitmodules",
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "Pipfile.lock", "poetry.lock", "composer.lock", "Cargo.lock",
}

IGNORE_SUFFIXES: tuple[str, ...] = (
    ".pyc", ".pyo", ".pyd", ".class",
    ".o", ".obj", ".a", ".lib", ".so", ".dll", ".dylib",
    ".exe", ".bin", ".wasm", ".log", ".map",
    ".min.js", ".min.css",
)

MAX_FILE_LINES  = 1_000
MAX_TOTAL_FILES = 2_000


# ─────────────────────────────────────────────────────────────────────────────
# GITIGNORE PARSER
# ─────────────────────────────────────────────────────────────────────────────

def _load_gitignore_patterns(root: Path) -> list[str]:
    gitignore = root / ".gitignore"
    if not gitignore.is_file():
        return []
    patterns: list[str] = []
    try:
        for line in gitignore.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                patterns.append(line)
    except Exception:
        pass
    return patterns


def _matches_gitignore(path: Path, root: Path, patterns: list[str]) -> bool:
    import fnmatch
    try:
        rel = path.relative_to(root).as_posix()
    except ValueError:
        return False
    name = path.name
    for pattern in patterns:
        if pattern.startswith("!"):
            continue
        p = pattern.rstrip("/")
        if fnmatch.fnmatch(name, p):
            return True
        if fnmatch.fnmatch(rel, p):
            return True
        if fnmatch.fnmatch(rel, f"**/{p}"):
            return True
        if fnmatch.fnmatch(rel, p + "/*"):
            return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# GIT DIFF
# ─────────────────────────────────────────────────────────────────────────────

def _get_git_changed_files(root: Path, staged_only: bool = False) -> list[Path] | None:
    try:
        cmd = ["git", "diff", "--name-only"]
        if staged_only:
            cmd.append("--cached")
        result = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return None
        files = []
        for line in result.stdout.strip().splitlines():
            p = root / line.strip()
            if p.is_file():
                files.append(p)
        return files or None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


# ─────────────────────────────────────────────────────────────────────────────
# TOKEN ESTIMATION
# ─────────────────────────────────────────────────────────────────────────────

def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _token_label(n: int) -> str:
    if n < 8_000:
        hint = "fits most models"
    elif n < 32_000:
        hint = "GPT-4o · Claude Sonnet · Gemini Flash"
    elif n < 128_000:
        hint = "Claude 200k · Gemini 1.5 Pro"
    elif n < 200_000:
        hint = "Claude 200k · Gemini 1.5 Pro 1M"
    else:
        hint = "Gemini 1.5 Pro 1M — consider splitting"
    return f"~{n/1000:.1f}k tokens  ({hint})"


# ─────────────────────────────────────────────────────────────────────────────
# FILTERING
# ─────────────────────────────────────────────────────────────────────────────

def _should_ignore_dir(name: str, include_hidden: bool) -> bool:
    if name in IGNORE_DIRS:
        return True
    if not include_hidden and name.startswith("."):
        return True
    return False


def _should_ignore_file(path: Path, include_unknown: bool,
                         root: Path | None = None,
                         gitignore_patterns: list[str] | None = None) -> bool:
    name = path.name
    if name in IGNORE_FILES:
        return True
    for suffix in IGNORE_SUFFIXES:
        if name.endswith(suffix):
            return True
    if gitignore_patterns and root:
        if _matches_gitignore(path, root, gitignore_patterns):
            return True
    if _get_language(path) is None and not include_unknown:
        return True
    return False


def _get_language(filepath: Path) -> str | None:
    name_lower = filepath.name.lower()
    if name_lower in CODE_EXTENSIONS:
        return CODE_EXTENSIONS[name_lower]
    return CODE_EXTENSIONS.get(filepath.suffix.lower())


# ─────────────────────────────────────────────────────────────────────────────
# FILE READING
# ─────────────────────────────────────────────────────────────────────────────

def _read_file_safe(filepath: Path) -> tuple[str, bool]:
    for enc in ("utf-8", "utf-8-sig", "latin-1", "cp1252", "utf-16"):
        try:
            raw = filepath.read_text(encoding=enc, errors="strict")
            lines = raw.splitlines()
            if len(lines) > MAX_FILE_LINES:
                return "\n".join(lines[:MAX_FILE_LINES]), True
            return raw, False
        except (UnicodeDecodeError, PermissionError):
            continue
    return "_[Binary or unreadable file — content omitted]_", False


# ─────────────────────────────────────────────────────────────────────────────
# TREE BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def _build_tree(root, include_hidden, include_unknown,
                log_cb, counter, gitignore_patterns, project_root) -> dict:
    node = {"name": root.name, "path": root, "dirs": [], "files": []}
    try:
        entries = sorted(root.iterdir(), key=lambda e: (e.is_file(), e.name.lower()))
    except PermissionError:
        log_cb(f"⚠  Permission denied: {root}", "warn")
        return node

    for entry in entries:
        if counter[0] >= MAX_TOTAL_FILES:
            log_cb(f"⚠  Reached {MAX_TOTAL_FILES}-file limit.", "warn")
            return node
        if entry.is_dir():
            if _should_ignore_dir(entry.name, include_hidden):
                continue
            if gitignore_patterns and _matches_gitignore(entry, project_root, gitignore_patterns):
                continue
            log_cb(f"📁  {entry.relative_to(root.parent)}", "muted")
            node["dirs"].append(_build_tree(entry, include_hidden, include_unknown,
                                             log_cb, counter, gitignore_patterns, project_root))
        elif entry.is_file():
            if _should_ignore_file(entry, include_unknown, project_root, gitignore_patterns):
                continue
            counter[0] += 1
            node["files"].append({"name": entry.name, "path": entry, "lang": _get_language(entry)})
    return node


def _build_diff_tree(changed_files: list[Path], root: Path) -> dict:
    node = {"name": root.name, "path": root, "dirs": [], "files": []}
    for fpath in changed_files:
        try:
            parts = fpath.relative_to(root).parts
        except ValueError:
            continue
        current = node
        for part in parts[:-1]:
            existing = next((d for d in current["dirs"] if d["name"] == part), None)
            if not existing:
                existing = {"name": part,
                            "path": root / Path(*parts[:parts.index(part)+1]),
                            "dirs": [], "files": []}
                current["dirs"].append(existing)
            current = existing
        current["files"].append({"name": fpath.name, "path": fpath, "lang": _get_language(fpath)})
    return node


# ─────────────────────────────────────────────────────────────────────────────
# MARKDOWN RENDERERS
# ─────────────────────────────────────────────────────────────────────────────

def _render_tree_ascii(node: dict, prefix: str = "", is_root: bool = True) -> str:
    lines = []
    if is_root:
        lines.append(f"📦 {node['name']}/")
        child_prefix = ""
    else:
        lines.append(f"{prefix}📁 {node['name']}/")
        child_prefix = prefix.replace("├── ", "│   ").replace("└── ", "    ")

    for i, item in enumerate(node["dirs"]):
        connector = "├── " if i < len(node["dirs"]) - 1 or node["files"] else "└── "
        lines.append(_render_tree_ascii(item, child_prefix + connector, False))
    for i, f in enumerate(node["files"]):
        connector = "└── " if i == len(node["files"]) - 1 else "├── "
        lines.append(f"{child_prefix}{connector}📄 {f['name']}")
    return "\n".join(lines)


def _render_files_md(node: dict, depth: int, root_path: Path) -> str:
    parts = []
    h  = "#" * min(depth + 1, 6)
    fh = "#" * min(depth + 2, 6)
    rel = node["path"].relative_to(root_path.parent)

    if depth == 1:
        parts.append(f"# 📦 `{node['name']}`\n")
    else:
        parts.append(f"\n{h} 📁 `{rel}`\n")

    for f in node["files"]:
        fpath = f["path"]
        lang  = f["lang"] or ""
        rel_f = fpath.relative_to(root_path.parent)
        size_kb = fpath.stat().st_size / 1024
        parts.append(f"\n{fh} 📄 `{f['name']}`\n")
        parts.append(f"> **Path:** `{rel_f}`  ")
        parts.append(f"> **Size:** {size_kb:.1f} KB\n")
        content, truncated = _read_file_safe(fpath)
        if truncated:
            parts.append(f"> ⚠️ **Truncated** — first {MAX_FILE_LINES} lines only.\n")
        parts.append(f"\n```{lang}\n{content}\n```\n")

    for sub in node["dirs"]:
        parts.append(_render_files_md(sub, depth + 1, root_path))
    return "\n".join(parts)


def _count_files(node: dict) -> int:
    return len(node["files"]) + sum(_count_files(d) for d in node["dirs"])


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

def generate_markdown(project_path: Path, include_hidden=False, include_unknown=False,
                      diff_mode=False, staged_only=False, system_prompt="", log_cb=None) -> str:
    if log_cb is None:
        log_cb = lambda msg, tag="": None

    gitignore_patterns = _load_gitignore_patterns(project_path)
    if gitignore_patterns:
        log_cb(f"📋  Loaded {len(gitignore_patterns)} rules from .gitignore", "info")

    now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    if diff_mode:
        log_cb("🔀  Git diff mode — scanning changed files only…", "info")
        changed = _get_git_changed_files(project_path, staged_only)
        if changed is None:
            log_cb("⚠  No git changes found. Falling back to full scan.", "warn")
            diff_mode = False
        else:
            log_cb(f"✅  {len(changed)} changed file(s) found.", "ok")
            tree = _build_diff_tree(changed, project_path)

    if not diff_mode:
        log_cb("🔍  Scanning project…", "info")
        counter = [0]
        tree = _build_tree(project_path, include_hidden, include_unknown,
                           log_cb, counter, gitignore_patterns, project_path)

    n_files = _count_files(tree)
    log_cb(f"✅  {n_files} files found.", "ok")
    log_cb("📝  Building Markdown…", "info")

    md = []
    if system_prompt.strip():
        md.append(f"> 🤖 **AI Instruction:** {system_prompt.strip()}\n\n---\n")

    md.append(f"# 🗂️ Project Context: `{project_path.name}`\n")
    md.append("> **Generated by [mdcodebrief](https://github.com/pablokaua03/mdcodebrief)**  ")
    md.append(f"> Date: **{now}**  ")
    md.append(f"> Files: **{n_files}**\n")
    if diff_mode:
        md.append(f"> Mode: **Git diff{'  (staged)' if staged_only else ''}**\n")
    md.append("\n---\n")

    md.append("## 🌳 Directory Tree\n```\n")
    md.append(_render_tree_ascii(tree))
    md.append("\n```\n\n---\n")

    md.append("## 📂 File Contents\n")
    md.append(_render_files_md(tree, depth=1, root_path=project_path))

    full_md = "\n".join(md)
    tokens = _estimate_tokens(full_md)
    token_str = _token_label(tokens)
    log_cb(f"🧮  {token_str}", "info")

    full_md += f"\n\n---\n_Generated by **mdcodebrief {__version__}** · {now} · {token_str}_\n"
    return full_md



# ─────────────────────────────────────────────────────────────────────────────
# THEMES
# ─────────────────────────────────────────────────────────────────────────────

DARK = {
    "bg":         "#0d1117",
    "bg2":        "#10141c",
    "card":       "#161b27",
    "card2":      "#1c2133",
    "input":      "#1a1f2e",
    "border":     "#252d40",
    "border2":    "#2e3850",
    "accent":     "#3b82f6",   # blue
    "accent_dk":  "#2563eb",
    "accent_glow":"#3b82f620",
    "green":      "#22c55e",
    "green_dk":   "#16a34a",
    "violet":     "#8b5cf6",
    "violet_dk":  "#7c3aed",
    "amber":      "#f59e0b",
    "red":        "#ef4444",
    "text":       "#f1f5f9",
    "text2":      "#94a3b8",
    "text3":      "#4a5568",
    "tag_bg":     "#1e2d40",
    "tag_fg":     "#60a5fa",
    "white":      "#ffffff",
    "mode":       "dark",
}

LIGHT = {
    "bg":         "#f8fafc",
    "bg2":        "#f1f5f9",
    "card":       "#ffffff",
    "card2":      "#f8fafc",
    "input":      "#ffffff",
    "border":     "#e2e8f0",
    "border2":    "#cbd5e1",
    "accent":     "#3b82f6",
    "accent_dk":  "#2563eb",
    "accent_glow":"#3b82f615",
    "green":      "#16a34a",
    "green_dk":   "#15803d",
    "violet":     "#7c3aed",
    "violet_dk":  "#6d28d9",
    "amber":      "#d97706",
    "red":        "#dc2626",
    "text":       "#0f172a",
    "text2":      "#475569",
    "text3":      "#94a3b8",
    "tag_bg":     "#dbeafe",
    "tag_fg":     "#2563eb",
    "white":      "#ffffff",
    "mode":       "light",
}

# Active theme — mutable reference
C: dict = dict(DARK)


def _apply_theme(theme: dict):
    C.clear()
    C.update(theme)


def _darken(hex_color: str, amount: int = 25) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"#{max(0,r-amount):02x}{max(0,g-amount):02x}{max(0,b-amount):02x}"


def _icon_path() -> Path | None:
    # Only load icon when running as .py — avoids SmartScreen issues in .exe
    if getattr(sys, "frozen", False):
        return None
    p = Path(__file__).parent / "icon.ico"
    return p if p.is_file() else None


# ─────────────────────────────────────────────────────────────────────────────
# FONT DEFINITIONS
# ─────────────────────────────────────────────────────────────────────────────

FH  = ("Segoe UI", 16, "bold")   # hero title
FL  = ("Segoe UI", 10, "bold")   # label
FS  = ("Segoe UI",  9)           # small / caption
FM  = ("Consolas",  9)           # mono
FB  = ("Segoe UI", 10, "bold")   # button primary
FBS = ("Segoe UI",  9, "bold")   # button secondary
FT  = ("Segoe UI",  8)           # tag / badge


# ─────────────────────────────────────────────────────────────────────────────
# WIDGET REGISTRY — for live theme switching
# ─────────────────────────────────────────────────────────────────────────────

class ThemeRegistry:
    """Keeps weak refs to all themed widgets so we can repaint on toggle."""
    _entries: list[tuple] = []   # (widget_ref, cfg_fn)

    @classmethod
    def register(cls, widget, cfg_fn):
        cls._entries.append((widget, cfg_fn))

    @classmethod
    def repaint(cls):
        dead = []
        for i, (w, fn) in enumerate(cls._entries):
            try:
                fn(w)
            except tk.TclError:
                dead.append(i)
        for i in reversed(dead):
            cls._entries.pop(i)

    @classmethod
    def reset(cls):
        cls._entries.clear()


def reg(widget, cfg_fn):
    ThemeRegistry.register(widget, cfg_fn)
    return widget


# ─────────────────────────────────────────────────────────────────────────────
# FLAT BUTTON
# ─────────────────────────────────────────────────────────────────────────────

class FlatBtn(tk.Frame):
    def __init__(self, parent, text, color_key: str, command,
                 font=None, padx=22, pady=10, **kw):
        super().__init__(parent, bg=C["bg"], cursor="hand2")
        self._ck  = color_key
        self._cmd = command
        self._font = font or FB
        self._padx = padx
        self._pady = pady
        self._text = text
        self._enabled = True

        self._btn = tk.Button(
            self, text=text, font=self._font,
            bg=C[color_key], fg=C["white"],
            activebackground=_darken(C[color_key]),
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
                                activebackground=_darken(C[self._ck]))
        else:
            self._btn.configure(bg=C["border"], fg=C["text3"])

    def _hover_on(self, _=None):
        if self._enabled:
            self._btn.configure(bg=_darken(C[self._ck]))

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
    def __init__(self, parent, var=None, font=None, placeholder="", **kw):
        super().__init__(parent, bg=C["input"],
                         highlightthickness=1,
                         highlightbackground=C["border"],
                         highlightcolor=C["accent"])
        self._var         = var or tk.StringVar()
        self._placeholder = placeholder
        self._has_focus   = False

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
        self._entry.configure(bg=col,
                              fg=C["text3"] if self._is_placeholder() else C["text"],
                              insertbackground=C["accent"],
                              disabledbackground=col,
                              disabledforeground=C["text2"])

    def _is_placeholder(self):
        return self._placeholder and self._var.get() == self._placeholder

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

    def get_value(self):
        v = self._var.get()
        return "" if self._placeholder and v == self._placeholder else v

    def set_value(self, v: str):
        self._var.set(v)
        self._entry.configure(fg=C["text"])

    def disable(self): self._entry.configure(state="disabled")
    def enable(self):  self._entry.configure(state="normal")


# ─────────────────────────────────────────────────────────────────────────────
# TOGGLE SWITCH (pill-style)
# ─────────────────────────────────────────────────────────────────────────────

class Toggle(tk.Frame):
    W, H = 38, 22

    def __init__(self, parent, text, variable, bg_key="card", **kw):
        super().__init__(parent, bg=C[bg_key], cursor="hand2")
        self._var    = variable
        self._bg_key = bg_key

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
        on = self._var.get()
        bg = C["bg_key"] if hasattr(C, "bg_key") else C[self._bg_key]
        track = C["accent"] if on else C["border2"]
        r = self.H // 2
        # track
        self._cv.create_oval(0, 0, self.H, self.H, fill=track, outline=track)
        self._cv.create_oval(self.W - self.H, 0, self.W, self.H, fill=track, outline=track)
        self._cv.create_rectangle(r, 0, self.W - r, self.H, fill=track, outline=track)
        # knob
        p = 3
        kx = self.W - r if on else r
        self._cv.create_oval(kx - r + p + 1, p, kx + r - p - 1, self.H - p,
                               fill=C["white"], outline="")

    def _repaint(self):
        bg = C[self._bg_key]
        self.configure(bg=bg)
        self._cv.configure(bg=bg)
        self._lbl.configure(bg=bg, fg=C["text2"])
        self._draw()

    def _toggle(self, _=None):
        self._var.set(not self._var.get())
        self._draw()


# ─────────────────────────────────────────────────────────────────────────────
# THEME TOGGLE BUTTON (sun / moon)
# ─────────────────────────────────────────────────────────────────────────────

class ThemeToggleBtn(tk.Canvas):
    SIZE = 32

    def __init__(self, parent, on_toggle, **kw):
        super().__init__(parent, width=self.SIZE, height=self.SIZE,
                          highlightthickness=0, cursor="hand2", bd=0)
        self._on_toggle = on_toggle
        self._draw()
        self.bind("<Button-1>", lambda _: on_toggle())
        self.bind("<Enter>", lambda _: self._hover(True))
        self.bind("<Leave>", lambda _: self._hover(False))
        reg(self, lambda w: w._draw())

    def _draw(self, hover=False):
        self.delete("all")
        bg = C["card"]
        self.configure(bg=bg)
        icon = "☀" if C["mode"] == "dark" else "🌙"
        col  = C["text2"] if not hover else C["accent"]
        self.create_text(self.SIZE // 2, self.SIZE // 2, text=icon,
                          font=("Segoe UI", 14), fill=col)

    def _hover(self, on: bool):
        self._draw(hover=on)


# ─────────────────────────────────────────────────────────────────────────────
# DIVIDER
# ─────────────────────────────────────────────────────────────────────────────

class Div(tk.Frame):
    def __init__(self, parent, **kw):
        super().__init__(parent, height=1, **kw)
        self.configure(bg=C["border"])
        reg(self, lambda w: w.configure(bg=C["border"]))


# ─────────────────────────────────────────────────────────────────────────────
# CARD FRAME
# ─────────────────────────────────────────────────────────────────────────────

class Card(tk.Frame):
    def __init__(self, parent, bg_key="card", **kw):
        super().__init__(parent, bg=C[bg_key],
                         highlightthickness=1,
                         highlightbackground=C["border"], **kw)
        self._bk = bg_key
        reg(self, lambda w: w.configure(bg=C[w._bk],
                                         highlightbackground=C["border"]))


# ─────────────────────────────────────────────────────────────────────────────
# SECTION HEADER
# ─────────────────────────────────────────────────────────────────────────────

def section(parent, title: str, subtitle: str = "") -> tk.Frame:
    row = tk.Frame(parent, bg=C["bg"])
    reg(row, lambda w: w.configure(bg=C["bg"]))

    # colored left pip
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
        colors = {
            "info":    ("tag_bg",   "tag_fg"),
            "ok":      ("green",    "white"),
            "err":     ("red",      "white"),
            "warn":    ("amber",    "white"),
        }
        bg_k, fg_k = colors.get(kind, ("tag_bg", "tag_fg"))
        self._lbl.configure(text=f"  {text}  ",
                             bg=C[bg_k],
                             fg=C[fg_k] if fg_k != "white" else C["white"])
        self._lbl.pack(side="left")

    def clear(self):
        self._lbl.configure(text="")
        self._lbl.pack_forget()


# ─────────────────────────────────────────────────────────────────────────────
# MAIN APP
# ─────────────────────────────────────────────────────────────────────────────

class App(tk.Tk):
    W = 720

    def __init__(self):
        super().__init__()
        self.title(f"mdcodebrief  v{__version__}")
        self.configure(bg=C["bg"])
        self.resizable(False, False)

        self._project_path: Path | None = None
        self._running   = False
        self._last_md   = ""

        ico = _icon_path()
        if ico:
            try: self.iconbitmap(str(ico))
            except Exception: pass

        self._setup_styles()
        self._build_ui()
        self._center()

    # ── TTK ───────────────────────────────────────────────────────────────────

    def _setup_styles(self):
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

    def _refresh_styles(self):
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
        W = self.W

        # ── HEADER ────────────────────────────────────────────────────────────
        hdr = tk.Frame(self, bg=C["card"], width=W)
        hdr.pack(fill="x")
        reg(hdr, lambda w: w.configure(bg=C["card"]))

        hdr_inner = tk.Frame(hdr, bg=C["card"])
        hdr_inner.pack(fill="x", padx=24, pady=18)
        reg(hdr_inner, lambda w: w.configure(bg=C["card"]))

        # Left: logo
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

        sub_lbl = tk.Label(logo_f,
                            text="Export any project as a single AI-ready .md context file",
                            font=FS, bg=C["card"], fg=C["text3"])
        sub_lbl.pack(anchor="w", pady=(4, 0))
        reg(sub_lbl, lambda w: w.configure(bg=C["card"], fg=C["text3"]))

        # Right: theme toggle + version
        right_f = tk.Frame(hdr_inner, bg=C["card"])
        right_f.pack(side="right", anchor="n")
        reg(right_f, lambda w: w.configure(bg=C["card"]))

        self._theme_btn = ThemeToggleBtn(right_f, self._toggle_theme)
        self._theme_btn.pack(side="right", padx=(8, 0))

        ver_badge = tk.Frame(right_f, bg=C["tag_bg"],
                              highlightthickness=1,
                              highlightbackground=C["border"])
        ver_badge.pack(side="right")
        reg(ver_badge, lambda w: w.configure(bg=C["tag_bg"],
                                              highlightbackground=C["border"]))
        ver_lbl = tk.Label(ver_badge, text=f"v{__version__}",
                            font=FT, bg=C["tag_bg"], fg=C["tag_fg"])
        ver_lbl.pack(padx=10, pady=5)
        reg(ver_lbl, lambda w: w.configure(bg=C["tag_bg"], fg=C["tag_fg"]))

        Div(self).pack(fill="x")

        # ── BODY ──────────────────────────────────────────────────────────────
        body = tk.Frame(self, bg=C["bg"])
        body.pack(fill="both", padx=22, pady=18)
        reg(body, lambda w: w.configure(bg=C["bg"]))

        # ── Row 1: Project Folder ──────────────────────────────────────────────
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

        sp(body, 20)

        # ── Row 2: two columns ────────────────────────────────────────────────
        row2 = tk.Frame(body, bg=C["bg"])
        row2.pack(fill="x")
        reg(row2, lambda w: w.configure(bg=C["bg"]))

        # Left col: AI Instruction
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

        self._prompt_var = tk.StringVar()
        self._prompt_field = InputField(left_col, var=self._prompt_var,
                                         font=("Segoe UI", 10),
                                         placeholder="Type an instruction for the AI…")
        self._prompt_field.pack(fill="x")

        # Right col: Options
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

        Toggle(col_a, "Hidden files",       self._var_hidden,  "card").pack(anchor="w")
        Toggle(col_a, "Unknown extensions", self._var_unknown, "card").pack(anchor="w")
        Toggle(col_b, "Git diff mode",      self._var_diff,    "card").pack(anchor="w")
        Toggle(col_b, "Staged only",        self._var_staged,  "card").pack(anchor="w")
        Toggle(col_b, "Copy to clipboard",  self._var_copy,    "card").pack(anchor="w")

        sp(body, 20)

        # ── Log ────────────────────────────────────────────────────────────────
        section(body, "Log").pack(anchor="w")
        sp(body, 6)

        log_card = Card(body)
        log_card.pack(fill="x")

        self._log = tk.Text(
            log_card, height=7, font=FM,
            bg=C["card"], fg=C["text"],
            insertbackground=C["accent"],
            relief="flat", bd=10,
            state="disabled", wrap="word", cursor="arrow",
        )
        reg(self._log, lambda w: w.configure(bg=C["card"], fg=C["text"]))

        sb = ttk.Scrollbar(log_card, orient="vertical", command=self._log.yview)
        self._log.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._log.pack(fill="x")

        self._log.tag_config("ok",    foreground=C["green"])
        self._log.tag_config("warn",  foreground=C["amber"])
        self._log.tag_config("err",   foreground=C["red"])
        self._log.tag_config("info",  foreground=C["accent"])
        self._log.tag_config("muted", foreground=C["text3"])

        # ── Progress ───────────────────────────────────────────────────────────
        self._progress = ttk.Progressbar(body, style="TProgressbar", mode="indeterminate")
        self._progress.pack(fill="x", pady=(10, 0))

        sp(body, 16)
        Div(body).pack(fill="x")
        sp(body, 14)

        # ── Action bar ─────────────────────────────────────────────────────────
        bar = tk.Frame(body, bg=C["bg"])
        bar.pack(fill="x")
        reg(bar, lambda w: w.configure(bg=C["bg"]))

        self._btn_gen = FlatBtn(bar, "  ✨  Generate .md  ", "green",
                                 self._start, padx=24, pady=11)
        self._btn_gen.configure(state="disabled")
        self._btn_gen.pack(side="left")

        self._btn_clip = FlatBtn(bar, "  📋  Copy  ", "accent_dk",
                                  self._copy_to_clipboard, font=FBS, padx=18, pady=11)
        self._btn_clip.configure(state="disabled")
        self._btn_clip.pack(side="left", padx=(10, 0))

        self._pill = StatusPill(bar)
        self._pill.pack(side="right")

        sp(body, 4)
        self.update_idletasks()
        self.geometry(f"{W}x{self.winfo_reqheight()}")

    # ── Theme toggle ──────────────────────────────────────────────────────────

    def _toggle_theme(self):
        _apply_theme(LIGHT if C["mode"] == "dark" else DARK)
        self._refresh_styles()
        ThemeRegistry.repaint()
        # Refresh log tag colors
        self._log.tag_config("ok",    foreground=C["green"])
        self._log.tag_config("warn",  foreground=C["amber"])
        self._log.tag_config("err",   foreground=C["red"])
        self._log.tag_config("info",  foreground=C["accent"])
        self._log.tag_config("muted", foreground=C["text3"])
        self.configure(bg=C["bg"])

    # ── Section spacing helper ────────────────────────────────────────────────

    # ── Events ────────────────────────────────────────────────────────────────

    def _center(self):
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

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
        self._btn_gen.configure(state="disabled", text="  ⏳  Working…  ")
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
            self._last_md = md

            desktop  = _get_desktop()
            safe     = "".join(c for c in self._project_path.name
                               if c.isalnum() or c in " _-").strip() or "project"
            out_file = desktop / f"resume - {safe}.md"
            out_file.write_text(md, encoding="utf-8")

            if self._var_copy.get():
                self._do_copy(md)
                self._log_write("📋  Copied to clipboard!", "ok")

            self._log_write(f"\n✅  Saved: {out_file}", "ok")
            self.after(0, lambda: self._pill.set("Done ✓", "ok"))
            self.after(0, lambda: self._btn_clip.configure(state="normal"))
            self.after(0, lambda: messagebox.showinfo(
                "Done 🎉",
                f"Saved to your Desktop:\n\n{out_file.name}\n\n{out_file}"
            ))
        except Exception as exc:
            self._log_write(f"\n❌  {exc}", "err")
            self.after(0, lambda: self._pill.set("Error", "err"))
            self.after(0, lambda: messagebox.showerror("Error", str(exc)))
        finally:
            self._running = False
            self.after(0, self._progress.stop)
            self.after(0, lambda: self._btn_gen.configure(
                state="normal", text="  ✨  Generate .md  "))
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


# ─────────────────────────────────────────────────────────────────────────────
# SPACING HELPER
# ─────────────────────────────────────────────────────────────────────────────

def sp(parent, h: int):
    f = tk.Frame(parent, bg=C["bg"], height=h)
    f.pack()
    reg(f, lambda w: w.configure(bg=C["bg"]))


# ─────────────────────────────────────────────────────────────────────────────
# UTILITIES
# ─────────────────────────────────────────────────────────────────────────────

def _get_desktop() -> Path:
    if sys.platform == "win32":
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders",
            )
            desktop, _ = winreg.QueryValueEx(key, "Desktop")
            return Path(desktop)
        except Exception:
            pass
    xdg = os.environ.get("XDG_DESKTOP_DIR")
    if xdg:
        return Path(xdg)
    return Path.home() / "Desktop"


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _cli():
    import argparse
    parser = argparse.ArgumentParser(prog="mdcodebrief",
        description="Generate a structured Markdown context file from a project folder.")
    parser.add_argument("project")
    parser.add_argument("-o", "--output")
    parser.add_argument("--hidden",  action="store_true")
    parser.add_argument("--unknown", action="store_true")
    parser.add_argument("--diff",    action="store_true")
    parser.add_argument("--staged",  action="store_true")
    parser.add_argument("-p", "--prompt", default="")
    parser.add_argument("-c", "--copy",   action="store_true")
    parser.add_argument("--version", action="version", version=f"mdcodebrief {__version__}")
    args = parser.parse_args()

    project_path = Path(args.project).resolve()
    if not project_path.is_dir():
        print(f"❌  '{project_path}' is not a valid directory.", file=sys.stderr)
        sys.exit(1)

    md = generate_markdown(project_path,
                           include_hidden=args.hidden,
                           include_unknown=args.unknown,
                           diff_mode=args.diff or args.staged,
                           staged_only=args.staged,
                           system_prompt=args.prompt,
                           log_cb=lambda msg, tag="": print(msg))

    safe = "".join(c for c in project_path.name if c.isalnum() or c in " _-").strip()
    out  = Path(args.output) if args.output else (_get_desktop() / f"resume - {safe}.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print(f"\n✅  Saved: {out}")

    if args.copy:
        try:
            if sys.platform == "win32":
                proc = subprocess.Popen(["clip"], stdin=subprocess.PIPE)
                proc.communicate(input=md.encode("utf-16"))
            elif sys.platform == "darwin":
                subprocess.run(["pbcopy"], input=md.encode("utf-8"), check=True)
            else:
                subprocess.run(["xclip", "-selection", "clipboard"],
                               input=md.encode("utf-8"), check=True)
            print("📋  Copied to clipboard!")
        except Exception as e:
            print(f"⚠  Could not copy: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) > 1:
        _cli()
    else:
        app = App()
        app.mainloop()
