"""Token budget control and scan-option layout in the desktop app."""

from __future__ import annotations

import importlib.util
import threading

import pytest

HAS_TK = importlib.util.find_spec("tkinter") is not None
needs_tk = pytest.mark.skipif(not HAS_TK, reason="needs Tk")


@needs_tk
@pytest.mark.parametrize(
    "text,expected",
    [("", None), ("   ", None), ("8000", 8000), ("8,000", 8000), ("32k", 32000), ("1.5K", 1500), ("128000", 128000)],
)
def test_parse_budget_accepts_plain_and_short_forms(text, expected):
    from contexta_app.ui import parse_token_budget

    assert parse_token_budget(text) == (expected, "")


@needs_tk
@pytest.mark.parametrize("text", ["abc", "-5", "12 apples", "100"])
def test_parse_budget_rejects_nonsense(text):
    from contexta_app.ui import parse_token_budget

    value, problem = parse_token_budget(text)
    assert value is None and problem


@pytest.fixture()
def app(tmp_path, monkeypatch):
    if not HAS_TK:
        pytest.skip("needs Tk")
    import tkinter

    from contexta_app import ui

    monkeypatch.setenv("CONTEXTA_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(ui, "get_desktop", lambda: tmp_path / "desktop")
    (tmp_path / "desktop").mkdir()
    try:
        window = ui.App()
    except tkinter.TclError:
        pytest.skip("no display")
    window.update()
    yield window
    try:
        window.destroy()
    except tkinter.TclError:
        pass


def _run_start(app, monkeypatch, project, budget_text):
    from contexta_app import ui

    seen = {}
    monkeypatch.setattr(ui, "generate_markdown", lambda path, **kw: seen.update(kw) or "# pack\n")

    class Inline(threading.Thread):  # run the worker on the calling thread so the test is deterministic
        def start(self):
            self.run()

    monkeypatch.setattr(ui.threading, "Thread", Inline)
    app._project_path = project
    app._budget_var.set(budget_text)
    app._start()
    app.update()
    return seen


@needs_tk
def test_budget_reaches_the_engine(app, tmp_path, monkeypatch):
    seen = _run_start(app, monkeypatch, tmp_path, "32k")
    assert seen["token_budget"] == 32000


@needs_tk
def test_empty_budget_means_no_limit(app, tmp_path, monkeypatch):
    seen = _run_start(app, monkeypatch, tmp_path, "")
    assert seen["token_budget"] is None


@needs_tk
def test_bad_budget_shows_a_message_and_does_not_start(app, tmp_path, monkeypatch):
    seen = _run_start(app, monkeypatch, tmp_path, "lots")
    assert seen == {}
    assert "Token budget" in app._banner_text and app._running is False


@needs_tk
def test_scan_option_labels_are_not_clipped(app):
    app.geometry("1100x760")
    app.update()
    for attr in ("_toggle_hidden", "_toggle_unknown", "_toggle_diff", "_toggle_staged", "_toggle_copy"):
        label = getattr(app, attr)._label
        assert label.winfo_width() >= label.winfo_reqwidth(), f"{attr}: label needs {label.winfo_reqwidth()}px but got {label.winfo_width()}px"
