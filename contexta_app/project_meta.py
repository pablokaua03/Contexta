"""
project_meta.py - What a project says about itself.

Reads the one-line description a project publishes in its own metadata
(pyproject.toml, package.json, Cargo.toml, composer.json, pubspec.yaml,
setup.cfg) and falls back to the first prose paragraph of its README. Contexta
never writes this text itself, so it cannot describe a project wrongly.
"""

from __future__ import annotations

import configparser
import json
import re
import tomllib
from pathlib import Path

MAX_DESCRIPTION_CHARS = 220
_MAX_META_BYTES = 256_000
_README_NAMES = ("README.md", "README.rst", "README.txt", "README", "readme.md", "Readme.md")


def _read(path: Path) -> str:
    try:
        if not path.is_file() or path.stat().st_size > _MAX_META_BYTES:
            return ""
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _clean(text: object) -> str:
    if not isinstance(text, str):
        return ""
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > MAX_DESCRIPTION_CHARS:
        cut = text[:MAX_DESCRIPTION_CHARS].rsplit(" ", 1)[0].rstrip(",;:- ")
        text = cut + "..."
    return text


def _toml(path: Path) -> dict:
    try:
        return tomllib.loads(_read(path))
    except tomllib.TOMLDecodeError:
        return {}


def _from_pyproject(root: Path) -> str:
    data = _toml(root / "pyproject.toml")
    project = data.get("project") or {}
    poetry = (data.get("tool") or {}).get("poetry") or {}
    flit = (data.get("tool") or {}).get("flit", {}).get("metadata", {}) if isinstance(data.get("tool"), dict) else {}
    return _clean(project.get("description") or poetry.get("description") or flit.get("description"))


def _from_setup_cfg(root: Path) -> str:
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read_string(_read(root / "setup.cfg"))
    except configparser.Error:
        return ""
    return _clean(parser.get("metadata", "description", fallback=""))


def _from_json(root: Path, name: str) -> str:
    try:
        data = json.loads(_read(root / name) or "{}")
    except json.JSONDecodeError:
        return ""
    return _clean(data.get("description")) if isinstance(data, dict) else ""


def _from_cargo(root: Path) -> str:
    data = _toml(root / "Cargo.toml")
    return _clean((data.get("package") or {}).get("description"))


def _from_pubspec(root: Path) -> str:
    match = re.search(r"^description:\s*(.+)$", _read(root / "pubspec.yaml"), re.MULTILINE)
    return _clean(match.group(1).strip("'\"")) if match else ""


def _readme_paragraph(root: Path) -> str:
    text = ""
    for name in _README_NAMES:
        text = _read(root / name)
        if text:
            break
    if not text:
        return ""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    in_fence = False
    paragraph: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith(("```", "~~~")):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        skip = (
            not line
            or line.startswith(("#", "[![", "![", "|", ">", "=", "-", "*", ".. ", "+", ":"))
            or re.fullmatch(r"[=\-~`^\"#*+<>_ ]+", line) is not None
            or "shields.io" in line
        )
        if skip:
            if paragraph:
                break
            continue
        line = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", line)
        line = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", line)
        line = re.sub(r"[*_`]{1,3}", "", line).strip()
        if not line:
            continue
        paragraph.append(line)
        if line.endswith((".", "!", "?")) and len(" ".join(paragraph)) >= 40:
            break
    text = " ".join(paragraph)
    match = re.match(r"(.+?[.!?])(\s|$)", text)
    if match and len(match.group(1)) >= 30:
        text = match.group(1)
    return _clean(text) if len(text) >= 20 else ""


def read_project_description(root: Path) -> str:
    """Return the project's own one-line description, or an empty string."""
    for reader in (
        _from_pyproject,
        _from_setup_cfg,
        lambda r: _from_json(r, "package.json"),
        _from_cargo,
        lambda r: _from_json(r, "composer.json"),
        _from_pubspec,
        _readme_paragraph,
    ):
        value = reader(root)
        if value:
            return value
    return ""
