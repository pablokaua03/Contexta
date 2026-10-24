"""Packs and the graph: --for, --no-graph, graph ranking under a budget, the large-repo prefilter, scan order."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from contexta_app import renderer
from contexta_app.cli import FOR_PACKS, ConfigError, build_parser, build_plan
from contexta_app.scanner import build_tree
from tests.test_graph import GIT_ENV, git, make_project, write

ROOT = Path(__file__).resolve().parent.parent


def plan_for(project: Path, *argv: str):
    args = build_parser().parse_args(list(argv))
    return build_plan(args, project, stdout_isatty=True)


def run_pack(project: Path, *args: str):
    return subprocess.run([sys.executable, str(ROOT / "contexta.py"), str(project), "--stdout", *args], capture_output=True, text=True, timeout=120)


@pytest.mark.parametrize("task,pack", sorted(FOR_PACKS.items()))
def test_for_maps_to_pack(tmp_path, task, pack):
    make_project(tmp_path)
    assert plan_for(tmp_path, "--for", task).pack_profile == pack


def test_for_conflicts_with_a_different_pack(tmp_path):
    make_project(tmp_path)
    with pytest.raises(ConfigError):
        plan_for(tmp_path, "--for", "bugfix", "--pack", "onboarding")
    assert plan_for(tmp_path, "--for", "bugfix", "--pack", "bugfix").pack_profile == "bugfix"


def test_review_defaults_its_base_to_main(tmp_path):
    make_project(tmp_path)
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "add", "-A")
    subprocess.run(["git", "-c", "commit.gpgsign=false", "commit", "-qm", "init"], cwd=tmp_path, check=True, env={**os.environ, **GIT_ENV})
    assert plan_for(tmp_path, "--for", "review").base_ref == "main"
    assert plan_for(tmp_path, "--for", "review", "--base", "HEAD").base_ref == "HEAD"


def test_no_graph_flag_and_default(tmp_path):
    make_project(tmp_path)
    assert plan_for(tmp_path).use_graph is True
    assert plan_for(tmp_path, "--no-graph").use_graph is False
    (tmp_path / "contexta.toml").write_text("graph = false\n", encoding="utf-8")
    assert plan_for(tmp_path).use_graph is False


def test_pack_writes_graph_only_when_enabled(tmp_path):
    make_project(tmp_path)
    assert run_pack(tmp_path, "--no-graph").returncode == 0
    assert not (tmp_path / ".contexta").exists()
    assert run_pack(tmp_path).returncode == 0
    assert (tmp_path / ".contexta" / "graph.db").exists()
    assert (tmp_path / ".contexta" / ".gitignore").read_text().splitlines()[-1] == "*"
    assert "graph.db" not in run_pack(tmp_path).stdout


def test_focus_pack_keeps_the_related_tests(tmp_path):
    make_project(tmp_path)
    out = run_pack(tmp_path, "--focus", "slugify", "--budget", "3000").stdout
    assert "pkg/util.py" in out and "tests/test_core.py" in out


def test_graph_rank_lifts_hub_files_under_a_budget():
    class Item:
        def __init__(self, rank, hot=0.0):
            self.score, self.graph_rank, self.graph_hot = 1.0, rank, hot
            self.relpath, self.path, self.tags = Path("pkg/a.py"), Path("a.py"), ()

    assert renderer.budget_priority(Item(0.9)) > renderer.budget_priority(Item(0.0))
    assert renderer.budget_priority(Item(0.0, 1.0)) > renderer.budget_priority(Item(0.0))


def test_prefilter_keeps_ranked_files_and_survives_failure(tmp_path, monkeypatch):
    make_project(tmp_path)
    for i in range(30):
        write(tmp_path, f"gen/mod{i}.py", f"def f{i}():\n    return {i}\n")
    monkeypatch.setattr(renderer, "PREFILTER_MIN_FILES", 10)
    monkeypatch.setattr(renderer, "PREFILTER_KEEP", 8)
    stats: dict = {}
    out = renderer.export_pack(tmp_path, stats=stats, token_budget=4000, focus_query="slugify", use_graph=True)
    assert stats["prefilter"]["kept"] < stats["prefilter"]["total"]
    assert "pkg/util.py" in out

    def boom(*a, **k):
        raise RuntimeError("db broken")

    monkeypatch.setattr(renderer, "ProjectGraph", boom)
    fallback = renderer.export_pack(tmp_path, stats={}, token_budget=4000, focus_query="slugify", use_graph=True)
    assert "pkg/util.py" in fallback


def test_scan_cap_reaches_source_before_docs(tmp_path):
    for i in range(40):
        write(tmp_path, f"docs_src/ex{i}.py", f"x = {i}\n")
    write(tmp_path, "zlib/core.py", "def real():\n    return 1\n")
    tree = build_tree(tmp_path, False, False, lambda *a, **k: None, [0], [], tmp_path, max_files=10)
    names = [d["name"] for d in tree["dirs"]]
    assert "zlib" in names
    assert names == sorted(names, key=str.lower)
