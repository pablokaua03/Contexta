"""Skip the GUI test modules on machines without Tk (headless CI, slim Linux)."""

from __future__ import annotations

import importlib.util
import os

collect_ignore: list[str] = []

if importlib.util.find_spec("tkinter") is None:
    collect_ignore += ["test_ui.py", "test_theme.py"]


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_contexta_home(tmp_path_factory, monkeypatch):
    """Keep tests away from the real ~/.contexta (user config and the app's saved choices)."""
    if "CONTEXTA_HOME" not in os.environ:
        monkeypatch.setenv("CONTEXTA_HOME", str(tmp_path_factory.mktemp("contexta-home")))
