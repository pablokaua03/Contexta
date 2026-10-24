import json
import subprocess
import sys
from pathlib import Path

from tests.test_graph import make_project

ROOT = Path(__file__).resolve().parent.parent


def cli(project: Path, *args: str):
    return subprocess.run([sys.executable, str(ROOT / "contexta.py"), "graph", *args, "-C", str(project)], capture_output=True, text=True, timeout=60)


def test_update_status_and_incremental(tmp_path):
    make_project(tmp_path)
    first = cli(tmp_path, "update", "--no-git")
    assert first.returncode == 0 and "7 new" in first.stdout
    assert "0 new, 0 changed" in cli(tmp_path, "update", "--no-git").stdout
    status = cli(tmp_path, "status", "--no-git")
    assert "7 files" in status.stdout and "calls" in status.stdout


def test_impact_text_json_and_tests_only(tmp_path):
    make_project(tmp_path)
    text = cli(tmp_path, "impact", "pkg/util.py", "--no-git").stdout
    assert "Tests to run" in text and "tests/test_core.py" in text
    data = json.loads(cli(tmp_path, "impact", "pkg/util.py", "--json", "--no-git").stdout)
    assert "pkg/core.py" in {r["path"] for r in data["impacted"]}
    only = cli(tmp_path, "impact", "pkg/util.py", "--tests-only", "--no-git").stdout.split()
    assert "tests/test_core.py" in only and all(p.startswith("tests/") for p in only)


def test_dependents_symbols_map_and_export(tmp_path):
    make_project(tmp_path)
    assert "pkg/core.py" in cli(tmp_path, "dependents", "pkg/util.py::slugify", "--no-git").stdout
    assert "def slugify" in cli(tmp_path, "symbols", "slug", "--no-git").stdout
    assert "pkg/core.py" in cli(tmp_path, "map", "--budget", "200", "--no-git").stdout
    out = tmp_path / "g.json"
    cli(tmp_path, "export", "-o", str(out), "--no-git")
    assert json.loads(out.read_text())["format"] == "contexta.graph.v1"
    assert cli(tmp_path, "export", "--format", "md", "--no-git").stdout.startswith("# ")


def test_changed_rejects_unknown_ref(tmp_path):
    make_project(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path)
    result = cli(tmp_path, "changed", "--since", "nope-not-a-ref")
    assert result.returncode == 1 and "Could not read git history" in result.stderr


def test_clear_removes_the_database(tmp_path):
    make_project(tmp_path)
    cli(tmp_path, "update", "--no-git")
    assert (tmp_path / ".contexta").is_dir()
    cli(tmp_path, "clear")
    assert not (tmp_path / ".contexta").exists()


def test_help_has_examples():
    out = subprocess.run([sys.executable, str(ROOT / "contexta.py"), "graph", "--help"], capture_output=True, text=True).stdout
    assert "examples:" in out and "impact" in out
