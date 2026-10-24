"""Project memory in the app and the CLI: which memory a run uses, status, answers, and the no-write guarantees."""

from __future__ import annotations

import hashlib
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from contexta_app import memory as mem
from contexta_app import renderer
from contexta_app.cli import ConfigError
from contexta_app.graph import GRAPH_DIRNAME, MemoryOwnerError, ProjectGraph
from tests.test_graph import make_project, write
from tests.test_pack_graph import plan_for as cli_plan
from tests.test_pack_graph import run_pack

ROOT = Path(__file__).resolve().parent.parent
ON = mem.MemoryChoice(True, "project")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture()
def project(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    make_project(root)
    return root


# ---- choices and plans ---------------------------------------------------------------------------


def test_defaults_save_into_the_projects_own_memory(project):
    plan = mem.plan_for(project, mem.MemoryChoice())
    assert (plan.use, plan.read_only, plan.db_path, plan.problem) == (True, False, None, "")


def test_save_off_reads_without_writing(project):
    plan = mem.plan_for(project, mem.MemoryChoice(False, "project"))
    assert (plan.use, plan.read_only) == (True, True)


def test_none_uses_nothing_whatever_the_toggle_says(project):
    for save in (True, False):
        plan = mem.plan_for(project, mem.MemoryChoice(save, "none"))
        assert plan.use is False and plan.problem == ""


def test_folder_without_a_path_or_with_a_missing_path_is_explained(project, tmp_path):
    assert "Choose a memory folder" in mem.plan_for(project, mem.MemoryChoice(True, "folder", "")).problem
    missing = mem.plan_for(project, mem.MemoryChoice(True, "folder", str(tmp_path / "nope")))
    assert missing.use is False and "not found" in missing.problem


def test_folder_resolution(tmp_path, project):
    plain = tmp_path / "shared"
    plain.mkdir()
    assert mem.resolve_db(str(plain)) == plain / "graph.db"
    other = tmp_path / "other"
    (other / GRAPH_DIRNAME).mkdir(parents=True)
    (other / GRAPH_DIRNAME / "graph.db").write_bytes(b"")
    assert mem.resolve_db(str(other)) == other / GRAPH_DIRNAME / "graph.db"
    assert mem.resolve_db(str(other / GRAPH_DIRNAME)) == other / GRAPH_DIRNAME / "graph.db"
    assert mem.plan_for(project, mem.MemoryChoice(True, "folder", str(project))).db_path is None


def test_unknown_mode_falls_back_to_project():
    assert mem.MemoryChoice(True, "weird").normalized().mode == "project"


def test_choice_round_trips_through_the_user_config_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTEXTA_HOME", str(tmp_path / "home"))
    assert mem.load_choice() == mem.MemoryChoice()
    chosen = mem.MemoryChoice(False, "folder", "/somewhere")
    assert mem.save_choice(chosen) is True
    assert mem.load_choice() == chosen
    (tmp_path / "home" / "gui.json").write_text("{not json", encoding="utf-8")
    assert mem.load_choice() == mem.MemoryChoice()


def test_saving_the_choice_keeps_other_settings_in_the_file(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTEXTA_HOME", str(tmp_path))
    (tmp_path / "gui.json").write_text('{"other": 1}', encoding="utf-8")
    mem.save_choice(mem.MemoryChoice(False, "none"))
    assert '"other": 1' in (tmp_path / "gui.json").read_text(encoding="utf-8")


# ---- status --------------------------------------------------------------------------------------


def test_status_without_a_project():
    assert mem.memory_status(None)["state"] == "no_project"


def test_status_for_a_missing_folder(tmp_path):
    assert mem.memory_status(tmp_path / "gone")["state"] == "no_project"


def test_status_absent_never_creates_anything(project):
    assert mem.memory_status(project)["state"] == "absent"
    assert not (project / GRAPH_DIRNAME).exists()


def test_status_none_is_disabled(project):
    assert mem.memory_status(project, mem.MemoryChoice(True, "none"))["state"] == "disabled"


def test_status_folder_mode_without_a_folder_asks_for_one(project):
    assert mem.memory_status(project, mem.MemoryChoice(True, "folder", ""))["state"] == "needs_folder"
    assert mem.memory_status(project, mem.MemoryChoice(True, "folder", str(project / "nope")))["state"] == "error"


def test_status_ready_after_update(project):
    mem.update_memory(project, ON)
    info = mem.memory_status(project)
    assert info["state"] == "ready"
    assert info["files"] >= 4 and info["symbols"] > 0 and info["edges"] > 0
    assert info["updated_at"].endswith("Z")


def test_status_does_not_touch_the_database(project):
    mem.update_memory(project, ON)
    db = project / GRAPH_DIRNAME / "graph.db"
    before = digest(db)
    for _ in range(3):
        mem.memory_status(project)
    assert digest(db) == before


def test_status_empty_graph(project):
    ProjectGraph(project).con.close()  # creates an empty database
    assert mem.memory_status(project)["state"] == "empty"


def test_status_for_a_damaged_file_is_plain(project):
    (project / GRAPH_DIRNAME).mkdir()
    (project / GRAPH_DIRNAME / "graph.db").write_bytes(b"this is not sqlite" * 50)
    info = mem.memory_status(project)
    assert info["state"] == "error" and "could not be read" in info["message"]


def test_status_for_an_old_schema_says_to_update(project):
    (project / GRAPH_DIRNAME).mkdir()
    con = sqlite3.connect(project / GRAPH_DIRNAME / "graph.db")
    con.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    con.execute("INSERT INTO meta VALUES ('schema', '1')")
    con.commit()
    con.close()
    info = mem.memory_status(project)
    assert info["state"] == "error" and "another Contexta version" in info["message"]
    mem.update_memory(project, ON)  # rebuilds in place
    assert mem.memory_status(project)["state"] == "ready"


# ---- actions -------------------------------------------------------------------------------------


def test_update_in_an_empty_folder_says_so(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(mem.MemoryProblem, match="Nothing to remember"):
        mem.update_memory(empty, ON)


def test_actions_without_a_project():
    for call in (lambda: mem.update_memory(None, ON), lambda: mem.hot_files(None, ON), lambda: mem.impact_of(None, ON, "a.py")):
        with pytest.raises(mem.MemoryProblem, match="Choose a project folder"):
            call()


def test_queries_before_any_memory_offer_an_update_and_create_nothing(project):
    for call in (lambda: mem.hot_files(project, ON), lambda: mem.find_symbols(project, ON, "slug"), lambda: mem.impact_of(project, ON, "pkg/util.py"),
                 lambda: mem.map_text(project, ON), lambda: mem.export_map(project, ON, project.parent / "map.md")):
        with pytest.raises(mem.MemoryMissing):
            call()
    assert not (project / GRAPH_DIRNAME).exists()


def test_answers_come_from_the_graph(project):
    assert "file(s)" in mem.update_memory(project, ON)
    assert "slugify" in mem.find_symbols(project, ON, "slugify")
    impact = mem.impact_of(project, ON, "pkg/util.py")
    assert "pkg/core.py" in impact and "Tests to run" in impact
    assert "pkg/util.py" in mem.map_text(project, ON)
    assert "No git history" in mem.hot_files(project, ON)


def test_impact_accepts_an_absolute_path_and_rejects_unknown_files(project):
    mem.update_memory(project, ON)
    assert "pkg/core.py" in mem.impact_of(project, ON, str(project / "pkg" / "util.py"))
    with pytest.raises(mem.MemoryProblem, match="not in the memory"):
        mem.impact_of(project, ON, "nothing/here.py")
    with pytest.raises(mem.MemoryProblem, match="file path"):
        mem.impact_of(project, ON, "  ")
    with pytest.raises(mem.MemoryProblem, match="part of a name"):
        mem.find_symbols(project, ON, " ")


def test_export_map_is_names_and_relations_only(project, tmp_path):
    write(project, "pkg/secret_logic.py", "def f():\n    marker = 'UNIQUE-BODY-TEXT-12345'\n    return marker\n")
    mem.update_memory(project, ON)
    out = mem.export_map(project, ON, tmp_path / "map.md")
    text = out.read_text(encoding="utf-8")
    assert "project graph" in text and "UNIQUE-BODY-TEXT-12345" not in text and str(tmp_path) not in text


def test_the_database_holds_no_content_credentials_or_authors(project):
    write(project, ".env", "API_KEY=sk-live-ABCDEFGHIJKLMNOP0123456789\n")
    write(project, "pkg/secret_logic.py", "def f():\n    marker = 'UNIQUE-BODY-TEXT-12345'\n    return marker\n")
    mem.update_memory(project, ON)
    raw = (project / GRAPH_DIRNAME / "graph.db").read_bytes()
    assert b"UNIQUE-BODY-TEXT-12345" not in raw and b"sk-live-ABCDEF" not in raw and b".env" not in raw


def test_update_in_a_chosen_folder_leaves_the_project_untouched(project, tmp_path):
    store = tmp_path / "store"
    store.mkdir()
    choice = mem.MemoryChoice(True, "folder", str(store))
    mem.update_memory(project, choice)
    assert (store / "graph.db").is_file() and not (project / GRAPH_DIRNAME).exists()
    assert mem.memory_status(project, choice)["state"] == "ready"
    assert "slugify" in mem.find_symbols(project, choice, "slugify")


def test_another_projects_memory_is_never_overwritten_by_a_run(project, tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    write(other, "main.py", "def only_here():\n    return 1\n")
    mem.update_memory(other, ON)
    db = other / GRAPH_DIRNAME / "graph.db"
    before = digest(db)
    with pytest.raises(MemoryOwnerError, match="already holds another project"):
        ProjectGraph(project, db).update(use_git=False)
    assert digest(db) == before
    # the card, pointed at that folder, refreshes that folder's own memory
    mem.update_memory(project, mem.MemoryChoice(True, "folder", str(other)))
    assert mem.memory_status(project, mem.MemoryChoice(True, "folder", str(other)))["files"] == 1


def test_a_shared_memory_is_stamped_and_refuses_a_second_project(project, tmp_path):
    store = tmp_path / "store"
    store.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    write(other, "main.py", "def x():\n    return 1\n")
    mem.update_memory(project, mem.MemoryChoice(True, "folder", str(store)))
    with pytest.raises(mem.MemoryProblem, match="different project"):
        mem.update_memory(other, mem.MemoryChoice(True, "folder", str(store)))
    mem.update_memory(project, mem.MemoryChoice(True, "folder", str(store)))  # the owner may keep going
    with pytest.raises(MemoryOwnerError):
        ProjectGraph(other, store / "graph.db").update(use_git=False)


# ---- read-only graph -----------------------------------------------------------------------------


def test_readonly_graph_cannot_write_or_create(project, tmp_path):
    with pytest.raises(FileNotFoundError):
        ProjectGraph(project, readonly=True).stats()
    assert not (project / GRAPH_DIRNAME).exists()
    mem.update_memory(project, ON)
    g = ProjectGraph(project, readonly=True)
    assert g.stats()["files"] > 0
    with pytest.raises(RuntimeError):
        g.update()
    g.close()


# ---- what a run does with the memory -------------------------------------------------------------


def pack(project: Path, **kwargs) -> str:
    return renderer.generate_markdown(project, token_budget=None, **kwargs)


def test_pack_with_memory_on_writes_the_graph(project):
    pack(project, use_graph=True)
    assert (project / GRAPH_DIRNAME / "graph.db").is_file()


def test_pack_with_memory_off_writes_nothing(project):
    pack(project, use_graph=False)
    assert not (project / GRAPH_DIRNAME).exists()


def test_pack_with_save_off_never_creates_or_changes_the_database(project):
    pack(project, use_graph=True, graph_readonly=True)
    assert not (project / GRAPH_DIRNAME).exists()
    mem.update_memory(project, ON)
    db = project / GRAPH_DIRNAME / "graph.db"
    before = digest(db)
    write(project, "pkg/new_module.py", "def brand_new():\n    return 1\n")
    logs: list[str] = []
    pack(project, use_graph=True, graph_readonly=True, log_cb=lambda m, t="": logs.append(m))
    assert digest(db) == before
    assert mem.find_symbols(project, ON, "brand_new").startswith("No symbols")


def test_pack_with_a_chosen_folder_uses_it_not_the_project(project, tmp_path):
    store = tmp_path / "store"
    store.mkdir()
    pack(project, use_graph=True, graph_db=store / "graph.db")
    assert (store / "graph.db").is_file() and not (project / GRAPH_DIRNAME).exists()


def test_pack_falls_back_to_read_only_for_a_foreign_memory(project, tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    write(other, "main.py", "def only_here():\n    return 1\n")
    mem.update_memory(other, ON)
    db = other / GRAPH_DIRNAME / "graph.db"
    before = digest(db)
    logs: list[str] = []
    out = pack(project, use_graph=True, graph_db=db, log_cb=lambda m, t="": logs.append(m))
    assert "pkg/core.py" in out
    assert digest(db) == before
    assert any("read-only" in line for line in logs)


# ---- command line --------------------------------------------------------------------------------


def test_cli_flags_map_to_a_plan(project, tmp_path):
    base = cli_plan(project)
    assert (base.use_graph, base.graph_db, base.graph_readonly) == (True, None, False)
    assert cli_plan(project, "--no-memory").use_graph is False
    assert cli_plan(project, "--memory-read-only").graph_readonly is True
    store = tmp_path / "store"
    store.mkdir()
    chosen = cli_plan(project, "--memory", str(store))
    assert chosen.graph_db == store.resolve() / "graph.db" and chosen.graph_readonly is False
    assert cli_plan(project, "--memory", str(store), "--no-memory").graph_db is None


def test_cli_rejects_a_missing_memory_folder(project, tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        cli_plan(project, "--memory", str(tmp_path / "nope"))


def test_config_file_keys(project, tmp_path):
    store = tmp_path / "store"
    store.mkdir()
    (project / "contexta.toml").write_text(f'memory_save = false\nmemory_path = "{store.as_posix()}"\n', encoding="utf-8")
    plan = cli_plan(project)
    assert plan.graph_readonly is True and plan.graph_db == store.resolve() / "graph.db"
    assert cli_plan(project, "--memory-read-only").graph_readonly is True


def test_cli_run_no_memory_writes_nothing(project):
    assert run_pack(project, "--no-memory").returncode == 0
    assert not (project / GRAPH_DIRNAME).exists()


def test_cli_run_read_only_without_memory_creates_nothing(project):
    assert run_pack(project, "--memory-read-only").returncode == 0
    assert not (project / GRAPH_DIRNAME).exists()


def test_cli_run_with_memory_path_keeps_the_project_clean(project, tmp_path):
    store = tmp_path / "store"
    store.mkdir()
    done = run_pack(project, "--memory", str(store))
    assert done.returncode == 0, done.stderr
    assert (store / "graph.db").is_file() and not (project / GRAPH_DIRNAME).exists()


def test_cli_help_lists_the_memory_flags():
    out = subprocess.run([sys.executable, str(ROOT / "contexta.py"), "--help"], capture_output=True, text=True, timeout=60).stdout
    for flag in ("--no-memory", "--memory PATH", "--memory-read-only"):
        assert flag in out
