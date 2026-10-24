"""
cli_style.py — Terminal presentation for Contexta.

Color is applied only when the destination stream is a TTY and NO_COLOR is
unset. Piped and captured output keeps the original plain lines so scripts
that read Contexta do not see ANSI codes or extra prefixes.
"""

from __future__ import annotations

import os
import sys
from typing import TextIO

_RESET = "\033[0m"
_STYLES = {
    "info": "\033[36m",
    "ok": "\033[32m",
    "warn": "\033[33m",
    "err": "\033[31m",
    "muted": "\033[2m",
    "accent": "\033[38;2;61;204;142m",
    "title": "\033[1;38;2;61;204;142m",
    "bold": "\033[1m",
}

_MARKS = {
    "ok": "✓",
    "warn": "!",
    "err": "×",
    "info": "·",
    "muted": "·",
}


def color_enabled(stream: TextIO | None = None) -> bool:
    forced = os.environ.get("CONTEXTA_COLOR", "").strip().lower()
    if forced in {"0", "false", "no", "never"}:
        return False
    if os.environ.get("NO_COLOR", "") != "" and forced not in {"1", "true", "yes", "always"}:
        return False
    if forced in {"1", "true", "yes", "always"}:
        return True
    target = sys.stdout if stream is None else stream
    try:
        return bool(target.isatty())
    except Exception:
        return False


def paint(text: str, role: str = "info", stream: TextIO | None = None) -> str:
    if not color_enabled(stream):
        return text
    code = _STYLES.get(role)
    if not code:
        return text
    return f"{code}{text}{_RESET}"


def format_log_line(msg: str, tag: str = "", stream: TextIO | None = None) -> str:
    """Style a progress line. Plain mode returns *msg* unchanged."""
    if not color_enabled(stream):
        return msg
    role = tag if tag in _STYLES else "info"
    mark = _MARKS.get(role, "·")
    return paint(f"{mark}  {msg}", role, stream)


def format_banner(version: str, project: str, pack: str, stream: TextIO | None = None) -> str:
    """A one-line identity header for interactive runs. Empty when not a TTY."""
    if not color_enabled(stream):
        return ""
    title = paint("contexta", "title", stream)
    version_text = paint(f"v{version}", "muted", stream)
    detail = paint(f"{project}   {pack}", "muted", stream)
    return f"{title}  {version_text}\n{detail}\n"


def format_saved(path: str, stream: TextIO | None = None) -> str:
    if not color_enabled(stream):
        return f"\nSaved: {path}"
    return f"\n{paint('saved', 'ok', stream)}  {path}"


def format_rule(stream: TextIO | None = None) -> str:
    rule = "─" * 56
    return paint(rule, "muted", stream)


def format_ai_header(label: str, stream: TextIO | None = None) -> str:
    if not color_enabled(stream):
        rule = "=" * 60
        return f"\n{rule}\nAI Response ({label}):\n{rule}"
    return f"\n{format_rule(stream)}\n{paint(f'AI response   {label}', 'title', stream)}\n{format_rule(stream)}"
