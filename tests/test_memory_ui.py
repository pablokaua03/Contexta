"""The Project memory card and the Memory panel in the desktop app. Logic that needs no window comes first."""

from __future__ import annotations

import importlib.util
import time
from pathlib import Path

import pytest

from contexta_app import memory as mem
from contexta_app.graph import GRAPH_DIRNAME
from tests.test_graph import make_project, write

HAS_TK = importlib.util.find_spec("tkinter") is not None
needs_tk = pytest.mark.skipif(not HAS_TK, reason="needs Tk")


# ---- no window -------------------------------------------------------------------------------------


@needs_tk
def test_status_wording_for_every_state():
    from contexta_app.ui import describe_memory_status

    tone, title, detail = describe_memory_status({"state": "ready", "files": 1200, "symbols": 3400, "edges": 99, "updated_at": "2026-01-02T03:04:05Z"})
    assert (tone, title) == ("ok", "Memory ready")
    assert "1,200 files" in detail and "3,400 symbols" in detail and "99 edges" in detail and "Updated" in detail
    assert describe_memory_status({"state": "absent", "message": "No memory yet."})[:2] == ("warn", "No memory yet")
    assert describe_memory_status({"state": "empty", "message": "x"})[0] == "warn"
    assert describe_memory_status({"state": "needs_folder", "message": "x"})[1] == "Choose a memory folder"
    assert describe_memory_status({"state": "disabled", "message": "off"})[1] == "Memory off"
    assert describe_memory_status({"state": "error", "message": "bad"}) == ("err", "Memory problem", "bad")
    assert describe_memory_status({"state": "no_project", "message": "pick"})[1] == "No project"


@needs_tk
def test_hint_follows_the_toggle_and_selector():
    from contexta_app.ui import memory_hint

    assert "updates this memory" in memory_hint(mem.MemoryChoice(True, "project"))
    assert "will not write" in memory_hint(mem.MemoryChoice(False, "project"))
    assert "will not read or write" in memory_hint(mem.MemoryChoice(True, "none"))


@needs_tk
def test_friendly_time_is_local_and_forgiving():
    from contexta_app.ui import friendly_time

    assert friendly_time(None) == "never"
    assert friendly_time("garbage") == "garbage"
    assert "," in friendly_time("2026-10-24T20:55:12Z")


# ---- with a window ---------------------------------------------------------------------------------


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


@pytest.fixture()
def project(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    make_project(root)
    return root


def choose(app, project: Path):
    app._project_path = project
    app._path_var.set(str(project))
    app._btn_generate.configure(state="normal")
    app._refresh_memory_status()
    app.update()


def pump(app, done, timeout=20.0):
    end = time.time() + timeout
    while time.time() < end:
        app.update()
        if done():
            return
        time.sleep(0.02)
    raise AssertionError("timed out waiting for the app")


def panel(app) -> str:
    return app._memory_text.get("1.0", "end")


def run_memory(app, action):
    action()
    assert app._mem_busy, "memory work must run in the background"
    pump(app, lambda: not app._mem_busy)


def test_card_defaults(app):
    assert app._mem_save_var.get() is True
    assert app._mem_selector._current == "project"
    assert app._mem_title_text == "No project"
    for text in ("Update memory", "Hot files", "Symbols", "Impact", "Open map"):
        assert any(b._btn.cget("text") == text for b in app._mem_buttons)
    assert not app._mem_folder_row.winfo_ismapped()


def test_every_button_asks_for_a_project_first(app):
    for action in (app._memory_update, app._memory_hot, app._memory_symbols, app._memory_impact, app._memory_open_map):
        action()
        assert "Choose a project folder first" in panel(app)
        assert app._mem_busy is False


def test_update_runs_in_the_background_and_shows_the_result(app, project):
    choose(app, project)
    assert app._mem_title_text == "No memory yet"
    run_memory(app, app._memory_update)
    assert app._mem_title_text == "Memory ready"
    assert "file(s)" in panel(app) and app._view_switch._current == "memory"
    assert all(b._enabled for b in app._mem_buttons)
    assert (project / GRAPH_DIRNAME / "graph.db").is_file()


def test_buttons_are_disabled_while_the_work_runs(app, project, monkeypatch):
    choose(app, project)
    import threading

    gate = threading.Event()
    real = mem.update_memory
    monkeypatch.setattr(mem, "update_memory", lambda p, c: (gate.wait(10), real(p, c))[1])
    app._memory_update()
    app.update()
    assert app._mem_busy and not any(b._enabled for b in app._mem_buttons)
    assert str(app._btn_generate._btn.cget("state")) == "disabled"
    assert "Reading the project" in panel(app)
    gate.set()
    pump(app, lambda: not app._mem_busy)
    assert all(b._enabled for b in app._mem_buttons)


def test_queries_without_memory_offer_an_update(app, project):
    choose(app, project)
    run_memory(app, app._memory_hot)
    assert "No memory yet" in panel(app)
    assert app._memory_offer.winfo_ismapped()
    app._memory_offer._btn.invoke()
    pump(app, lambda: not app._mem_busy)
    assert app._mem_title_text == "Memory ready" and not app._memory_offer.winfo_ismapped()


def test_hot_symbols_impact_show_answers(app, project, monkeypatch):
    choose(app, project)
    run_memory(app, app._memory_update)
    run_memory(app, app._memory_hot)
    assert "No git history" in panel(app)
    monkeypatch.setattr(app, "_ask_text", lambda *a: "slugify")
    run_memory(app, app._memory_symbols)
    assert "def slugify" in panel(app) and "pkg/util.py" in panel(app)
    monkeypatch.setattr(app, "_ask_text", lambda *a: "pkg/util.py")
    run_memory(app, app._memory_impact)
    assert "pkg/core.py" in panel(app) and "Tests to run" in panel(app)


def test_cancelled_prompt_does_nothing(app, project, monkeypatch):
    choose(app, project)
    monkeypatch.setattr(app, "_ask_text", lambda *a: None)
    app._memory_symbols()
    app._memory_impact()
    assert app._mem_busy is False


def test_errors_are_plain(app, project, monkeypatch):
    choose(app, project)
    run_memory(app, app._memory_update)
    monkeypatch.setattr(app, "_ask_text", lambda *a: "no/such/file.py")
    run_memory(app, app._memory_impact)
    assert "not in the memory" in panel(app) and "Traceback" not in panel(app)
    monkeypatch.setattr(mem, "hot_files", lambda p, c: 1 / 0)
    run_memory(app, app._memory_hot)
    assert "Memory could not finish" in panel(app)
    assert app._mem_busy is False


def test_empty_project_is_explained(app, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    choose(app, empty)
    run_memory(app, app._memory_update)
    assert "Nothing to remember" in panel(app)


def test_open_map_saves_shows_and_opens(app, project, tmp_path, monkeypatch):
    from contexta_app import ui

    opened: list[Path] = []
    monkeypatch.setattr(ui, "open_with_system", lambda p: opened.append(p))
    choose(app, project)
    run_memory(app, app._memory_update)
    run_memory(app, app._memory_open_map)
    target = tmp_path / "desktop" / "contexta map - proj.md"
    assert target.is_file() and "project graph" in target.read_text(encoding="utf-8")
    assert opened == [target]
    assert "pkg/core.py" in panel(app)


def test_open_map_survives_no_default_app(app, project, monkeypatch):
    from contexta_app import ui

    def boom(path):
        raise OSError("No app is set up to open this file.")

    monkeypatch.setattr(ui, "open_with_system", boom)
    choose(app, project)
    run_memory(app, app._memory_update)
    run_memory(app, app._memory_open_map)
    assert "pkg/core.py" in panel(app)
    assert "could not be opened" in app._log.get("1.0", "end")


# ---- per-analysis control --------------------------------------------------------------------------


def run_pack(app, monkeypatch, tmp_path):
    from contexta_app import ui

    app._copy_var.set(False)
    seen: dict = {}
    real = ui.generate_markdown

    def spy(*args, **kwargs):
        seen.update(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(ui, "generate_markdown", spy)
    app._start()
    pump(app, lambda: not app._running)
    pump(app, lambda: str(app._btn_generate._btn.cget("state")) == "normal")
    return seen


def test_analysis_saves_to_memory_by_default(app, project, monkeypatch, tmp_path):
    choose(app, project)
    seen = run_pack(app, monkeypatch, tmp_path)
    assert (seen["use_graph"], seen["graph_readonly"], seen["graph_db"]) == (True, False, None)
    assert (project / GRAPH_DIRNAME / "graph.db").is_file()
    assert app._mem_title_text == "Memory ready"


def test_toggle_off_never_writes_the_database(app, project, monkeypatch, tmp_path):
    import hashlib

    choose(app, project)
    run_memory(app, app._memory_update)
    db = project / GRAPH_DIRNAME / "graph.db"
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    write(project, "pkg/fresh.py", "def fresh():\n    return 1\n")
    app._mem_save_var.set(False)
    seen = run_pack(app, monkeypatch, tmp_path)
    assert (seen["use_graph"], seen["graph_readonly"]) == (True, True)
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before


def test_toggle_off_with_no_memory_creates_nothing(app, project, monkeypatch, tmp_path):
    choose(app, project)
    app._mem_save_var.set(False)
    run_pack(app, monkeypatch, tmp_path)
    assert not (project / GRAPH_DIRNAME).exists()


def test_selector_none_skips_memory_entirely(app, project, monkeypatch, tmp_path):
    choose(app, project)
    app._mem_selector.set("none", notify=True)
    app.update()
    assert app._mem_title_text == "Memory off"
    assert str(app._toggle_mem_save._enabled) == "False"
    seen = run_pack(app, monkeypatch, tmp_path)
    assert seen["use_graph"] is False
    assert not (project / GRAPH_DIRNAME).exists()
    run_memory(app, app._memory_update)
    assert "Memory is off" in panel(app)


def test_selector_folder_uses_that_memory(app, project, tmp_path, monkeypatch):
    store = tmp_path / "store"
    store.mkdir()
    choose(app, project)
    app._mem_selector.set("folder", notify=True)
    app.update()
    assert app._mem_folder_row.winfo_ismapped()
    assert "Choose a memory folder" in app._mem_title_text + app._mem_detail_text
    app._mem_folder_var.set(str(store))
    app.update()
    assert app._mem_title_text == "No memory yet"
    seen = run_pack(app, monkeypatch, tmp_path)
    assert seen["graph_db"] == store / "graph.db"
    assert (store / "graph.db").is_file() and not (project / GRAPH_DIRNAME).exists()
    assert app._mem_title_text == "Memory ready"


def test_choices_persist_between_launches(app, project, tmp_path):
    from contexta_app import ui

    app._mem_save_var.set(False)
    app._mem_selector.set("folder", notify=True)
    app._mem_folder_var.set(str(tmp_path))
    app.update()
    app.destroy()  # one Tk root at a time
    again = ui.App()
    try:
        again.update()
        assert again._mem_save_var.get() is False
        assert again._mem_selector._current == "folder"
        assert again._mem_folder_var.get() == str(tmp_path)
    finally:
        again.destroy()


def test_both_themes_repaint_the_card_and_the_panel(app, project):
    from contexta_app import theme

    choose(app, project)
    run_memory(app, app._memory_update)
    seen = {}
    for _ in range(2):
        app._toggle_theme()
        app.update()
        seen[theme.C["mode"]] = (str(app._mem_title.cget("fg")), str(app._memory_text.tag_cget("title", "foreground")), str(app._memory_text.cget("bg")))
        assert seen[theme.C["mode"]][0] == theme.C["text"] and seen[theme.C["mode"]][1] == theme.C["text"]
    assert len(seen) == 2 and seen["dark"] != seen["light"]


def test_window_fits_at_1200x820(app, project):
    app.geometry("1200x820+0+0")
    choose(app, project)
    app.update()
    assert app.winfo_height() >= 700
    # the left column scrolls, so a card taller than the window is reachable
    canvas = app._controls_scroll._canvas
    assert canvas.bbox("all")[3] > canvas.winfo_height()
    assert app._controls_scroll._scrollbar.winfo_ismapped()
