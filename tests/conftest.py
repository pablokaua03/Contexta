"""Skip the GUI test modules on machines without Tk (headless CI, slim Linux)."""

from __future__ import annotations

import importlib.util

collect_ignore: list[str] = []

if importlib.util.find_spec("tkinter") is None:
    collect_ignore += ["test_ui.py", "test_theme.py"]
