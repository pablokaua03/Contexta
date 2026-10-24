"""Packaging guard: the wheel must carry everything the `contexta` command imports."""

from __future__ import annotations

import importlib
import importlib.util
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def test_console_script_points_inside_the_package() -> None:
    meta = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    target = meta["project"]["scripts"]["contexta"]
    module, func = target.split(":")
    assert module.startswith("contexta_app."), "the console script must live in the package, not a top-level module"
    assert callable(getattr(importlib.import_module(module), func))


def test_legacy_launchers_still_work() -> None:
    import contexta
    import contexta_app.entry as entry

    assert contexta.main is entry.main


def test_serve_help_exits_zero() -> None:
    r = subprocess.run([sys.executable, "-m", "contexta_app", "serve", "--help"], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0
    assert "contexta serve" in r.stdout


@pytest.mark.skipif(importlib.util.find_spec("hatchling") is None, reason="hatchling not installed")
def test_wheel_contains_entry_modules(tmp_path: Path) -> None:
    r = subprocess.run([sys.executable, "-m", "hatchling", "build", "-t", "wheel", "-d", str(tmp_path)], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stdout + r.stderr
    wheel = next(tmp_path.glob("*.whl"))
    with zipfile.ZipFile(wheel) as z:
        names = set(z.namelist())
        entry = next(n for n in names if n.endswith("entry_points.txt"))
        assert "contexta_app.entry:main" in z.read(entry).decode()
    for required in ("contexta_app/entry.py", "contexta_app/__main__.py", "contexta_app/mcp_server.py", "contexta_app/cli.py"):
        assert required in names, f"{required} missing from the wheel"
