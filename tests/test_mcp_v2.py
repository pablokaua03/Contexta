"""MCP v2 tools: repo_map, search_symbols, impacted_tests, graph_query, context_for, find_files."""

import random
import string
from pathlib import Path

import pytest

from contexta_app import mcp_server as m
from tests.test_graph import make_project, write


@pytest.fixture()
def proj(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    make_project(root)
    write(root, "pkg/settings.py", "RETRY_COUNT = 3\n\ndef load():\n    return RETRY_COUNT\n")
    m.configure_roots([tmp_path])
    yield root
    m.configure_roots(None)


def test_new_tools_are_registered():
    names = {t.name for t in m.mcp._tool_manager.list_tools()}
    assert {"repo_map", "search_symbols", "impacted_tests", "graph_query", "context_for", "find_files"} <= names


def test_repo_map(proj):
    out = m.repo_map(str(proj), budget=300)
    assert "pkg/core.py" in out and "class Engine" in out and "tokens" in out
    assert "Error" in m.repo_map(str(proj), budget=10)


def test_search_symbols(proj):
    out = m.search_symbols(str(proj), "slug")
    assert "pkg/util.py:1" in out and "def slugify(text)" in out
    assert "No symbols" in m.search_symbols(str(proj), "zzzzzz")
    assert "class" in m.search_symbols(str(proj), "Engine", kind="class")


def test_impacted_tests_for_files(proj):
    out = m.impacted_tests(str(proj), files=["pkg/util.py"])
    assert "tests/test_core.py" in out and "pkg/core.py" in out and "Tests to run" in out


def test_impacted_tests_defaults_to_git_changes(proj):
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=proj, check=True)
    (proj / "pkg" / "util.py").write_text("def slugify(text):\n    return text\n")
    out = m.impacted_tests(str(proj))
    assert "pkg/util.py" in out and "tests/test_core.py" in out


def test_graph_query_ops(proj):
    assert "pkg/core.py" in m.graph_query(str(proj), "dependents", "pkg/util.py")
    assert "pkg/util.py" in m.graph_query(str(proj), "dependencies", "pkg/core.py")
    assert "pkg/core.py" in m.graph_query(str(proj), "dependents", "pkg/util.py::slugify")
    assert "Tests to run" in m.graph_query(str(proj), "impact", "pkg/util.py")
    assert "files:" in m.graph_query(str(proj), "status")
    assert "needs a target" in m.graph_query(str(proj), "dependents")
    assert "op must be" in m.graph_query(str(proj), "drop_tables")


def test_find_files_by_name_symbol_and_content(proj):
    assert "By name" in m.find_files(str(proj), "core", "name")
    assert "By symbol" in m.find_files(str(proj), "slugify", "symbols")
    out = m.find_files(str(proj), "RETRY_COUNT", "content")
    assert "pkg/settings.py:1" in out and "By content" in out
    assert "No files matching" in m.find_files(str(proj), "nothing_like_this_xyz")
    assert "Error" in m.find_files(str(proj), "x", "bogus")


def test_content_search_redacts_and_skips_credentials(proj):
    token = "ghp_" + "".join(random.Random(9).choice(string.ascii_letters + string.digits) for _ in range(36))
    write(proj, "pkg/leaky.py", f'MARKER_NEEDLE = "{token}"\n')
    write(proj, ".env", "MARKER_NEEDLE=hunter2hunter2\n")
    out = m.find_files(str(proj), "MARKER_NEEDLE", "content")
    assert "pkg/leaky.py" in out and token not in out and "[REDACTED]" in out
    assert ".env" not in out and "hunter2" not in out


def test_context_for_stays_inside_budget(proj):
    from contexta_app.renderer import estimate_tokens

    out = m.context_for(str(proj), "fix slugify handling of text", budget=3000)
    assert "## Repo map" in out and "pkg/util.py" in out
    assert estimate_tokens(out) <= 3300
    assert "Error" in m.context_for(str(proj), "", budget=3000)
    assert "Error" in m.context_for(str(proj), "x", budget=10)


def test_everything_is_confined_to_the_root(proj, tmp_path):
    outside = tmp_path.parent / "elsewhere"
    outside.mkdir(exist_ok=True)
    (outside / "a.py").write_text("def secret_fn():\n    pass\n")
    m.configure_roots([proj])
    target = str(outside)
    calls = [
        m.repo_map(target), m.search_symbols(target, "secret"), m.impacted_tests(target, files=["a.py"]),
        m.graph_query(target, "status"), m.context_for(target, "anything", 2000), m.find_files(target, "secret", "content"),
    ]
    assert all("outside" in c for c in calls), calls
    assert not (outside / ".contexta").exists()


def test_files_argument_cannot_escape_or_name_credentials(proj, tmp_path):
    write(proj, ".env", "TOKEN=abcdefgh12345\n")
    assert "outside" in m.impacted_tests(str(proj), files=["../../etc/passwd"])
    assert "credential" in m.impacted_tests(str(proj), files=[".env"]).lower()
    assert "Credential" in m.graph_query(str(proj), "dependents", ".env")


def test_graph_database_stays_in_the_project(proj):
    m.repo_map(str(proj))
    assert (proj / ".contexta" / "graph.db").exists()
    assert not list(proj.parent.glob("*.db"))
