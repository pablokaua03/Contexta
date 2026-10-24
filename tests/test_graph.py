"""The project graph: incremental indexing, queries, export, and what it refuses to store."""

from __future__ import annotations

import json
import os
import random
import string
import subprocess
import time
from pathlib import Path

import pytest

from contexta_app import syntax
from contexta_app.graph import GRAPH_DIRNAME, ProjectGraph, classify_kind
from contexta_app.renderer import estimate_tokens
from contexta_app.symbols import extract_facts

GIT_ENV = {
    "GIT_AUTHOR_NAME": "tester", "GIT_AUTHOR_EMAIL": "tester@example.com",
    "GIT_COMMITTER_NAME": "tester", "GIT_COMMITTER_EMAIL": "tester@example.com",
}


def write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def make_project(root: Path) -> None:
    write(root, "pkg/__init__.py", "from .core import Engine\nfrom .util import slugify\n")
    write(root, "pkg/core.py", (
        "from .util import slugify\n\n\nclass Engine:\n    def run(self, name):\n        return slugify(name)\n\n"
        "def build():\n    return Engine()\n"
    ))
    write(root, "pkg/util.py", "def slugify(text):\n    return text.lower()\n\n\ndef unused_helper():\n    return 1\n")
    write(root, "pkg/api.py", "from pkg import Engine\n\n\ndef handler():\n    return Engine().run('x')\n")
    write(root, "tests/test_core.py", "from pkg.core import build\n\n\ndef test_build():\n    assert build()\n")
    write(root, "tests/test_api.py", "from pkg import Engine\n\n\ndef test_engine():\n    Engine()\n")
    write(root, "README.md", "# demo\n")


@pytest.fixture()
def project(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    make_project(root)
    return root


@pytest.fixture()
def graph(project):
    g = ProjectGraph(project)
    g.update(use_git=False)
    yield g
    g.close()


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, env={**os.environ, **GIT_ENV}, check=True).stdout


class TestIndexing:
    def test_files_symbols_and_kinds(self, graph):
        assert graph.stats()["files"] == 7
        rows = {r["path"]: r["kind"] for r in graph.con.execute("SELECT path, kind FROM files")}
        assert rows["tests/test_core.py"] == "test" and rows["pkg/core.py"] == "source" and rows["README.md"] == "doc"
        syms = {r["qualname"]: r for r in graph.con.execute("SELECT * FROM symbols WHERE path='pkg/core.py'")}
        assert syms["Engine"]["kind"] == "class" and syms["Engine"]["line"] == 4
        assert syms["Engine.run"]["kind"] == "method" and syms["Engine.run"]["signature"] == "def run(self, name)"

    def test_second_update_parses_nothing(self, project, graph):
        stats = graph.update(use_git=False)
        assert (stats.added, stats.changed, stats.removed) == (0, 0, 0) and stats.unchanged == 7

    def test_edit_reparses_only_that_file(self, project, graph):
        time.sleep(0.01)
        write(project, "pkg/util.py", "def slugify(text):\n    return text.lower()\n\n\ndef another():\n    return 2\n")
        stats = graph.update(use_git=False)
        assert (stats.added, stats.changed, stats.removed) == (0, 1, 0)
        assert graph.search_symbols("another")[0]["path"] == "pkg/util.py"
        assert graph.search_symbols("unused_helper") == []

    def test_touch_without_content_change_is_not_a_change(self, project, graph):
        path = project / "pkg" / "util.py"
        os.utime(path, (time.time() + 5, time.time() + 5))
        stats = graph.update(use_git=False)
        assert stats.changed == 0 and stats.unchanged == 7

    def test_new_and_deleted_files(self, project, graph):
        write(project, "pkg/extra.py", "def extra():\n    pass\n")
        (project / "pkg" / "api.py").unlink()
        stats = graph.update(use_git=False)
        assert (stats.added, stats.removed) == (1, 1)
        assert not graph.has_file("pkg/api.py") and graph.has_file("pkg/extra.py")
        assert graph.dependents("pkg/core.py", depth=1)[0]["path"] != "pkg/api.py"

    def test_schema_change_starts_clean(self, project, graph):
        graph.con.execute("UPDATE meta SET value='0' WHERE key='schema'")
        graph.con.commit()
        graph.close()
        fresh = ProjectGraph(project)
        assert fresh.is_empty()
        fresh.close()


class TestEdges:
    def test_relative_and_absolute_imports(self, graph):
        deps = {d["path"] for d in graph.dependencies("pkg/core.py")}
        assert "pkg/util.py" in deps
        assert {d["path"] for d in graph.dependents("pkg/util.py")} >= {"pkg/core.py", "pkg/__init__.py"}

    def test_reexport_is_followed_to_the_real_module(self, graph):
        # api imports Engine from the package; it really lives in pkg/core.py
        assert "pkg/core.py" in {d["path"] for d in graph.dependencies("pkg/api.py")}

    def test_calls_are_symbol_level(self, graph):
        rows = graph.con.execute("SELECT * FROM edges WHERE kind='calls' AND src_file='pkg/core.py' AND src_sym='Engine.run'").fetchall()
        assert [(r["dst_file"], r["dst_sym"]) for r in rows] == [("pkg/util.py", "slugify")]

    def test_symbol_dependents(self, graph):
        users = {d["path"] for d in graph.dependents("pkg/util.py::slugify")}
        assert "pkg/core.py" in users
        assert "unused_helper" not in json.dumps(graph.dependents("pkg/util.py::unused_helper"))
        assert graph.dependents("pkg/util.py::unused_helper") == []

    def test_bare_symbol_name_resolves(self, graph):
        assert {d["path"] for d in graph.dependents("slugify")} >= {"pkg/core.py"}

    def test_tests_link_to_sources(self, graph):
        covers = {t["path"] for t in graph.tests_for(["pkg/core.py"])}
        assert "tests/test_core.py" in covers and "tests/test_api.py" in covers  # api test imports Engine

    def test_impact_of_a_change(self, graph):
        result = graph.impact(["pkg/util.py"])
        assert result["changed"] == ["pkg/util.py"]
        assert {r["path"] for r in result["impacted"]} >= {"pkg/core.py", "pkg/api.py"}
        assert {t["path"] for t in result["tests"]} >= {"tests/test_core.py", "tests/test_api.py"}
        first = result["tests"][0]
        assert first["weight"] >= result["tests"][-1]["weight"]

    def test_impact_does_not_walk_through_package_init(self, project):
        write(project, "other/consumer.py", "import pkg\n\n\ndef go():\n    return pkg\n")
        g = ProjectGraph(project)
        g.update(use_git=False)
        result = g.impact(["pkg/util.py"])
        assert "other/consumer.py" not in {r["path"] for r in result["impacted"]}
        g.close()

    def test_distance_and_depth(self, graph):
        deps = graph.dependents("pkg/util.py", depth=3)
        distances = {d["path"]: d["distance"] for d in deps}
        assert distances["pkg/core.py"] == 1


class TestGitSignals:
    @pytest.fixture()
    def repo(self, project):
        git(project, "init", "-q")
        git(project, "add", "-A")
        git(project, "commit", "-q", "-m", "one")
        first = git(project, "rev-parse", "HEAD").strip()
        for i in range(3):
            (project / "pkg" / "core.py").write_text((project / "pkg" / "core.py").read_text() + f"\n# {i}\n")
            (project / "pkg" / "util.py").write_text((project / "pkg" / "util.py").read_text() + f"\n# {i}\n")
            git(project, "add", "-A")
            git(project, "commit", "-q", "-m", f"change {i}")
        return project, first

    def test_hot_files_and_cochange(self, repo):
        project, _ = repo
        g = ProjectGraph(project)
        g.update()
        hot = g.hot_files(3)
        assert {h["path"] for h in hot[:2]} == {"pkg/core.py", "pkg/util.py"}
        assert hot[0]["commits"] == 4
        assert g.cochanged(["pkg/core.py"])[0] == {"path": "pkg/util.py", "times_together": 4}
        assert "pkg/util.py" in {c["path"] for c in g.impact(["pkg/core.py"])["cochanged"]}
        g.close()

    def test_changed_since_commit_and_date(self, repo):
        project, first = repo
        g = ProjectGraph(project)
        g.update()
        paths = {f["path"] for f in g.changed_since(first)["files"]}
        assert paths == {"pkg/core.py", "pkg/util.py"}
        assert {f["path"] for f in g.changed_since("2000-01-01")["files"]} >= {"pkg/core.py", "README.md"}
        with pytest.raises(ValueError):
            g.changed_since("not-a-ref")
        (project / "pkg" / "api.py").write_text("x = 1\n")
        assert "pkg/api.py" in {f["path"] for f in g.changed_since()["files"]}
        g.close()

    def test_no_authors_or_emails_are_stored(self, repo):
        project, _ = repo
        g = ProjectGraph(project)
        g.update()
        dump = g.export("json") + g.export("md") + "".join(str(tuple(r)) for r in g.con.execute("SELECT * FROM history"))
        assert "tester" not in dump and "example.com" not in dump
        g.close()


class TestSafety:
    def test_signatures_are_redacted(self, tmp_path):
        token = "ghp_" + "".join(random.Random(3).choice(string.ascii_letters + string.digits) for _ in range(36))
        root = tmp_path / "p"
        write(root, "a.py", f'def connect(host, token="{token}"):\n    return host\n')
        g = ProjectGraph(root)
        g.update(use_git=False)
        assert token not in g.export("json") and token not in g.export("md")
        sig = g.search_symbols("connect")[0]["signature"]
        assert "[REDACTED]" in sig
        raw = g.db_path.read_bytes()
        assert token.encode() not in raw
        g.close()

    def test_credential_files_are_not_indexed(self, tmp_path):
        root = tmp_path / "p"
        write(root, "app.py", "x = 1\n")
        write(root, ".env", "SECRET_KEY=abc\n")
        write(root, "id_rsa", "-----BEGIN-----\n")
        write(root, "config/credentials.json", "{}\n")
        g = ProjectGraph(root)
        g.update(files=[root / n for n in ("app.py", ".env", "id_rsa", "config/credentials.json")], use_git=False)
        assert {r[0] for r in g.con.execute("SELECT path FROM files")} == {"app.py"}
        g.close()

    def test_no_file_content_in_the_database(self, project):
        write(project, "pkg/secret_logic.py", "def f():\n    marker = 'UNIQUE-BODY-TEXT-12345'\n    return marker\n")
        g = ProjectGraph(project)
        g.update(use_git=False)
        g.con.execute("PRAGMA wal_checkpoint(FULL)")
        assert b"UNIQUE-BODY-TEXT-12345" not in g.db_path.read_bytes()
        assert "UNIQUE-BODY-TEXT-12345" not in g.export("json")
        g.close()

    def test_database_is_gitignored_by_default_and_not_scanned(self, project):
        g = ProjectGraph(project)
        g.update(use_git=False)
        guard = project / GRAPH_DIRNAME / ".gitignore"
        assert guard.read_text().strip().splitlines()[-1] == "*"
        git(project, "init", "-q")
        assert git(project, "status", "--porcelain", "--untracked-files=all").count(".contexta") == 0
        assert not any(p.startswith(".contexta") for (p,) in g.con.execute("SELECT path FROM files"))
        g.close()

    def test_exports_have_no_absolute_paths(self, project, graph):
        for fmt in ("json", "jsonl", "md"):
            assert str(project.parent) not in graph.export(fmt)


class TestExport:
    def test_json_shape(self, graph):
        data = json.loads(graph.export("json"))
        assert data["format"] == "contexta.graph.v1" and data["project"] == "proj"
        ids = {n["id"] for n in data["nodes"]}
        assert "pkg/core.py" in ids and "pkg/core.py::Engine.run" in ids
        assert all(e["source"] in ids and e["target"] in ids for e in data["edges"])
        kinds = {e["kind"] for e in data["edges"]}
        assert {"imports", "calls", "tests"} <= kinds

    def test_jsonl_has_one_record_per_line(self, graph):
        lines = [json.loads(line) for line in graph.export("jsonl").splitlines()]
        assert lines[0]["record"] == "meta" and {l["record"] for l in lines} == {"meta", "node", "edge"}

    def test_markdown_is_readable(self, graph):
        md = graph.export("md")
        assert "# proj: project graph" in md and "### `pkg/core.py`" in md and "used by:" in md

    def test_unknown_format(self, graph):
        with pytest.raises(ValueError):
            graph.export("xml")


class TestRepoMap:
    def test_respects_budget(self, graph):
        for budget in (40, 120, 400):
            out = graph.repo_map(budget)
            assert estimate_tokens(out["text"]) <= budget + 10, out

    def test_focus_pulls_matching_files_first(self, graph):
        out = graph.repo_map(300, focus="slugify util")
        assert out["text"].index("pkg/util.py") < out["text"].index("pkg/api.py")

    def test_most_used_symbols_come_first(self, graph):
        text = graph.repo_map(40)["text"]
        assert "slugify" in text and "unused_helper" not in text


class TestParsers:
    PY = "import os\nfrom a.b import c\n\n@deco\ndef f(x: int = 1) -> int:\n    return g(x)\n\nclass A(Base):\n    def m(self):\n        h()\n"

    def test_python_facts(self):
        facts = extract_facts(self.PY, "python")
        assert facts.backend == "ast"
        assert [(s.qualname, s.kind) for s in facts.symbols] == [("f", "function"), ("A", "class"), ("A.m", "method")]
        assert {(i.module, i.names) for i in facts.imports} == {("os", ()), ("a.b", ("c",))}
        assert ("f", "g") in facts.calls and ("A", "Base") in facts.calls and ("A.m", "h") in facts.calls and ("f", "deco") in facts.calls

    def test_broken_python_does_not_raise(self):
        assert extract_facts("def (:\n", "python").symbols == []

    JS = "import x from './x';\nexport function load(a) { return fetch(a); }\nexport const run = async () => { load(1); };\nclass Svc { go() {} }\n"
    GO = 'package m\nimport "example.com/app/util"\nfunc Run() {}\ntype T struct{}\nfunc (t T) Go() {}\n'
    RS = "use crate::util;\npub fn run() {}\npub struct S;\nimpl S { fn go(&self) {} }\n"

    @pytest.mark.parametrize("backend", ["regex", "tree-sitter"])
    def test_other_languages(self, backend, monkeypatch):
        if backend == "regex":
            monkeypatch.setattr(syntax, "get_parser", None)
        elif not syntax.available():
            pytest.skip("tree-sitter not installed")
        js = extract_facts(self.JS, "javascript")
        assert js.backend == backend
        assert {"load", "run", "Svc"} <= {s.name for s in js.symbols}
        assert "./x" in {i.module for i in js.imports}
        go = extract_facts(self.GO, "go")
        assert {"Run", "T", "Go"} <= {s.name for s in go.symbols}
        assert "example.com/app/util" in {i.module for i in go.imports}
        rs = extract_facts(self.RS, "rust")
        assert {"run", "S"} <= {s.name for s in rs.symbols}

    def test_classify_kind(self):
        assert classify_kind("src/a_test.go", "go") == "test"
        assert classify_kind("web/a.spec.ts", "typescript") == "test"
        assert classify_kind("tests/data.json", "json") == "config"
        assert classify_kind("x/y.py", "python") == "source"
