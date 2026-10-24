"""
memory.py - The project memory as the desktop app and the CLI use it, without any GUI code.

A *memory* is the graph database described in graph.py: names, signatures and relations,
never file content, credentials or authors. This module decides which memory a run uses
(the project's own, a chosen folder's, or none), reports its status, and answers the
questions the app's "Project memory" card asks. Every answer comes from ProjectGraph
and the formatters in graph_cli.py.
"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from contexta_app.config import user_config_dir
from contexta_app.graph import GRAPH_DIRNAME, GRAPH_FILENAME, MemoryOwnerError, ProjectGraph
from contexta_app.graph_cli import format_hot, format_impact, format_status, format_symbols
from contexta_app.scanner import GitError

MODES = ("project", "folder", "none")
MODE_LABELS = {
    "project": "This project's memory",
    "folder": "Another folder's memory",
    "none": "No memory",
}


class MemoryProblem(Exception):
    """A plain-language reason the memory cannot be used right now."""


class MemoryMissing(MemoryProblem):
    """No memory has been built yet. The app offers to build it."""


@dataclass(frozen=True)
class MemoryChoice:
    """What the user picked for one analysis."""

    save: bool = True
    mode: str = "project"
    folder: str = ""

    def normalized(self) -> "MemoryChoice":
        mode = self.mode if self.mode in MODES else "project"
        return MemoryChoice(bool(self.save), mode, (self.folder or "").strip())


@dataclass(frozen=True)
class MemoryPlan:
    """How one run treats the memory."""

    use: bool = False
    read_only: bool = False
    db_path: Path | None = None  # None = the project's default location
    problem: str = ""
    label: str = ""


def resolve_db(folder: str) -> Path:
    """The graph.db a chosen folder (or a graph.db file) stands for. Nothing is created.

    A folder that already has ``.contexta/graph.db`` (another project) means that file. A
    ``.contexta`` folder or one holding ``graph.db`` means that file. Any other folder gets a
    plain ``graph.db`` of its own, so it never collides with that folder's project memory.
    """
    raw = Path(folder).expanduser()
    if raw.is_file():
        return raw
    if not raw.is_dir():
        raise MemoryProblem(f"Memory folder not found: {raw.name or folder}")
    inside = raw / GRAPH_DIRNAME / GRAPH_FILENAME
    if inside.is_file():
        return inside
    return raw / GRAPH_FILENAME


def _is_default_location(project: Path, db: Path) -> bool:
    try:
        return db.resolve() == (project.resolve() / GRAPH_DIRNAME / GRAPH_FILENAME)
    except OSError:
        return False


def plan_for(project: Path, choice: MemoryChoice) -> MemoryPlan:
    """Turn the toggle and the selector into what a run does.

    - mode "none": the memory is neither read nor written.
    - save off: an existing memory may still inform the ranking, but is only read.
    - save on: the memory is updated as the project is read.
    """
    choice = choice.normalized()
    if choice.mode == "none":
        return MemoryPlan(label="Memory off")
    db: Path | None = None
    label = "This project's memory"
    if choice.mode == "folder":
        if not choice.folder:
            return MemoryPlan(problem="Choose a memory folder, or switch the memory to this project or to none.", label="Memory off")
        try:
            if Path(choice.folder).expanduser().resolve() == project.resolve():
                return MemoryPlan(use=True, read_only=not choice.save, label=label)
            db = resolve_db(choice.folder)
        except MemoryProblem as exc:
            return MemoryPlan(problem=str(exc), label="Memory off")
        label = f"Memory in {db.parent.parent.name if db.parent.name == GRAPH_DIRNAME else db.parent.name}"
        if _is_default_location(project, db):
            db = None
            label = "This project's memory"
    return MemoryPlan(use=True, read_only=not choice.save, db_path=db, label=label)


def open_graph(project: Path, plan: MemoryPlan, *, readonly: bool | None = None) -> ProjectGraph:
    return ProjectGraph(project, plan.db_path, readonly=plan.read_only if readonly is None else readonly)


# ---------------------------------------------------------------- status


def _owner_root(project: Path, plan: MemoryPlan) -> Path:
    """The folder a memory describes. Another project's own memory describes that project;
    every other memory describes the open project."""
    if plan.db_path is not None and plan.db_path.parent.name == GRAPH_DIRNAME:
        return plan.db_path.parent.parent
    return project


def memory_status(project: Path | None, choice: MemoryChoice | None = None) -> dict:
    """Never creates or changes anything. ``state`` is one of
    no_project, disabled, needs_folder, absent, empty, ready, error."""
    choice = (choice or MemoryChoice()).normalized()
    if choice.mode == "none":
        return {"state": "disabled", "message": "Memory is off for this analysis. Nothing is read or written."}
    if project is None:
        return {"state": "no_project", "message": "Choose a project folder to see its memory."}
    project = Path(project)
    if not project.is_dir():
        return {"state": "no_project", "message": "That project folder is not available."}
    plan = plan_for(project, choice)
    if plan.problem:
        if choice.mode == "folder" and not choice.folder:
            return {"state": "needs_folder", "message": "Browse to a folder, or switch to This project or None."}
        return {"state": "error", "message": plan.problem}
    root = _owner_root(project, plan)
    graph = ProjectGraph(root, plan.db_path, readonly=True)
    try:
        info = graph.stats()
    except FileNotFoundError:
        return {"state": "absent", "message": "Update it to index this project."}
    except (ValueError, sqlite3.DatabaseError) as exc:
        return {"state": "error", "message": _plain(exc)}
    finally:
        graph.close()
    out = {
        "files": info["files"],
        "symbols": info["symbols"],
        "edges": sum(info["edges"].values()),
        "tests": info["tests"],
        "commits": info["commits"],
        "updated_at": info["updated_at"],
        "db": info["db"],
    }
    if not info["files"]:
        return {**out, "state": "empty", "message": "The memory exists but holds no files. Update it after adding source files."}
    return {**out, "state": "ready", "message": ""}


def _plain(exc: BaseException) -> str:
    if isinstance(exc, sqlite3.DatabaseError):
        return "The memory file could not be read. Update it to rebuild it, or clear the .contexta folder."
    return str(exc) or exc.__class__.__name__


# ---------------------------------------------------------------- actions


def update_memory(project: Path | None, choice: MemoryChoice, *, use_git: bool = True) -> str:
    """Index or refresh the chosen memory. Runs in whatever thread calls it."""
    plan = _require_plan(project, choice)
    root = _owner_root(Path(project), plan)
    graph = ProjectGraph(root, plan.db_path)
    try:
        stats = graph.update(use_git=use_git)
    except MemoryOwnerError as exc:
        raise MemoryProblem(str(exc)) from exc
    except (GitError, ValueError, OSError, sqlite3.DatabaseError) as exc:
        raise MemoryProblem(_plain(exc)) from exc
    finally:
        graph.close()
    if stats.total == 0:
        raise MemoryProblem("Nothing to remember: this folder has no readable source files (ignored, hidden and credential files are skipped).")
    return stats.summary() + "\n"


def _require_plan(project: Path | None, choice: MemoryChoice) -> MemoryPlan:
    if project is None or not Path(project).is_dir():
        raise MemoryProblem("Choose a project folder first.")
    plan = plan_for(Path(project), choice)
    if plan.problem:
        raise MemoryProblem(plan.problem)
    if not plan.use:
        raise MemoryProblem("Memory is off for this analysis. Pick a memory first.")
    return plan


def _query(project: Path | None, choice: MemoryChoice, fn):
    plan = _require_plan(project, choice)
    root = _owner_root(Path(project), plan)
    graph = ProjectGraph(root, plan.db_path, readonly=True)
    try:
        try:
            graph.stats()
        except FileNotFoundError as exc:
            raise MemoryMissing("No memory yet. Update it first.") from exc
        return fn(graph)
    except MemoryProblem:
        raise
    except (ValueError, GitError, OSError, sqlite3.DatabaseError) as exc:
        raise MemoryProblem(_plain(exc)) from exc
    finally:
        graph.close()


def memory_summary(project: Path | None, choice: MemoryChoice) -> str:
    return _query(project, choice, lambda g: format_status(g.stats(), g.root.name))


def hot_files(project: Path | None, choice: MemoryChoice, limit: int = 15) -> str:
    return _query(project, choice, lambda g: format_hot(g.hot_files(limit)))


def find_symbols(project: Path | None, choice: MemoryChoice, query: str, limit: int = 30) -> str:
    query = query.strip()
    if not query:
        raise MemoryProblem("Type part of a name to search for, for example login.")
    return _query(project, choice, lambda g: format_symbols(g.search_symbols(query, limit)))


def project_relative(project: Path, text: str) -> str:
    """A path as the memory stores it: relative to the project, with forward slashes."""
    value = text.strip().strip('"')
    path = Path(value).expanduser()
    if path.is_absolute():
        try:
            return path.resolve().relative_to(Path(project).resolve()).as_posix()
        except (ValueError, OSError):
            return value
    return value.replace("\\", "/")


def impact_of(project: Path | None, choice: MemoryChoice, target: str) -> str:
    if not target.strip():
        raise MemoryProblem("Type a file path from the project, for example src/app.py.")
    rel = project_relative(Path(project), target) if project else target

    def run(graph: ProjectGraph) -> str:
        found, _ = graph.normalize(rel)
        if not found or not graph.has_file(found):
            raise MemoryProblem(f"{rel} is not in the memory. Use a path relative to the project, and Update memory if the file is new.")
        return format_impact(graph.impact([rel]))

    return _query(project, choice, run)


def map_text(project: Path | None, choice: MemoryChoice, budget: int = 1500) -> str:
    def run(graph: ProjectGraph) -> str:
        result = graph.repo_map(budget)
        if not result["files"]:
            raise MemoryProblem("The memory holds no files yet. Update it first.")
        return result["text"] + f"\n~{result['tokens']} tokens, {result['files']} files, {result['symbols']} symbols\n"

    return _query(project, choice, run)


def export_map(project: Path | None, choice: MemoryChoice, out_file: Path) -> Path:
    """Write the memory as a readable Markdown map (names and relations only)."""
    def run(graph: ProjectGraph) -> str:
        if graph.is_empty():
            raise MemoryProblem("The memory holds no files yet. Update it first.")
        return graph.export("md")

    text = _query(project, choice, run)
    out_file.write_text(text, encoding="utf-8")
    return out_file


# ---------------------------------------------------------------- saved choices


def prefs_path() -> Path:
    return user_config_dir() / "gui.json"


def load_choice() -> MemoryChoice:
    """The last memory choice made in the app. Missing or unreadable means the defaults."""
    try:
        data = json.loads(prefs_path().read_text(encoding="utf-8"))
        block = data.get("memory", {})
        return MemoryChoice(bool(block.get("save", True)), str(block.get("mode", "project")), str(block.get("folder", ""))).normalized()
    except (OSError, ValueError, AttributeError):
        return MemoryChoice()


def save_choice(choice: MemoryChoice) -> bool:
    """Remember the choice for the next launch. Returns False when the file cannot be written."""
    path = prefs_path()
    try:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                data = {}
        except (OSError, ValueError):
            data = {}
        choice = choice.normalized()
        data["memory"] = {"save": choice.save, "mode": choice.mode, "folder": choice.folder}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return True
    except OSError:
        return False
