"""contexta_app.engine.blobs: split out of context_engine.py. Bodies are unchanged."""

from __future__ import annotations

import re

from contexta_app.engine.models import (
    FileInsight,
)

def _strip_wrapping_quotes(text: str) -> str:
    stripped = text.strip().strip(",")
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {"'", '"'}:
        return stripped[1:-1]
    if len(stripped) >= 3 and stripped[0] == "b" and stripped[1] in {"'", '"'} and stripped[1] == stripped[-1]:
        return stripped[2:-1]
    return stripped

def is_blob_like_line(line: str) -> bool:
    candidate = line.strip().strip(",")
    if "=" in candidate:
        _prefix, _sep, suffix = candidate.partition("=")
        candidate = suffix.strip()
    candidate = _strip_wrapping_quotes(candidate)
    if len(candidate) < 96:
        return False
    if re.search(r"\s", candidate):
        return False
    cleaned = candidate
    allowed = re.sub(r"[^A-Za-z0-9+/=_-]", "", cleaned)
    if len(allowed) < 96:
        return False
    density = len(allowed) / max(len(cleaned), 1)
    if density < 0.97:
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9+/=_-]+", allowed))

def has_embedded_asset_payload(item: FileInsight) -> bool:
    if item.lang in {"markdown", "mdx", "rst"}:
        return False
    rel = item.relpath.as_posix().lower()
    blob_lines = sum(1 for line in item.content.splitlines() if is_blob_like_line(line))
    asset_signal = any(token in rel for token in ("asset", "icon", "logo", "brand"))
    base64_signal = bool(re.search(r"\b[A-Z][A-Z0-9_]*B64\b|\bbase64\b", item.content))
    assignment_signal = bool(re.search(r"^\s*[A-Z][A-Z0-9_]{2,}\s*=\s*\(?\s*$", item.content, re.MULTILINE))
    return blob_lines >= 8 and (asset_signal or base64_signal or assignment_signal)

def should_sanitize_blob_excerpt(item: FileInsight) -> bool:
    if "embedded_asset" in item.tags:
        return True
    rel = item.relpath.as_posix().lower()
    if any(token in rel for token in ("asset", "icon", "logo", "brand")):
        return True
    if re.search(r"\b[A-Z][A-Z0-9_]*B64\b|\bbase64\b", item.content):
        return True
    return False

def build_embedded_asset_excerpt(item: FileInsight) -> str:
    lines: list[str] = []
    docstring = re.search(r'^\s*"""([^"\n]+)"""', item.content, re.MULTILINE)
    if docstring:
        lines.append(f'"""{docstring.group(1)}"""')
    names = re.findall(r"^\s*([A-Z][A-Z0-9_]{2,})\s*=", item.content, re.MULTILINE)
    for name in names[:4]:
        lines.append(f"{name} = <embedded asset data omitted>")
    if not lines:
        lines.append("<embedded asset data omitted>")
    return "\n".join(lines)

def sanitize_excerpt_lines(item: FileInsight, lines: list[str]) -> tuple[list[str], bool]:
    sanitized: list[str] = []
    omitted_blob = False
    placeholder_open = False
    allow_blob_sanitization = should_sanitize_blob_excerpt(item)

    for line in lines:
        if allow_blob_sanitization and is_blob_like_line(line):
            omitted_blob = True
            if not placeholder_open:
                sanitized.append("<embedded blob omitted>")
                placeholder_open = True
            continue
        placeholder_open = False
        sanitized.append(line)

    return sanitized, omitted_blob
