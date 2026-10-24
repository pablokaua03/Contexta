"""The GitHub Action: its manifest, the PR report, and the comment that updates itself."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from contexta_app import ci_report
from tests.test_graph import GIT_ENV, write

ROOT = Path(__file__).resolve().parent.parent
FAKE_KEY = "ghp_" + "abcdefghijklmnopqrstuvwxyz0123456789"


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "commit.gpgsign=false", *args], cwd=root, check=True, capture_output=True, env={**os.environ, **GIT_ENV})


@pytest.fixture()
def pr_repo(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    write(tmp_path, "pkg/util.py", "def slugify(t):\n    return t.lower()\n")
    write(tmp_path, "pkg/other.py", "def other():\n    return 1\n")
    write(tmp_path, "tests/test_util.py", "from pkg.util import slugify\n\n\ndef test_s():\n    assert slugify('A') == 'a'\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "init")
    git(tmp_path, "checkout", "-qb", "feature")
    write(tmp_path, "pkg/util.py", f"def slugify(t):\n    return t.lower().strip()\n\nTOKEN = '{FAKE_KEY}'\n")
    git(tmp_path, "commit", "-qam", "change")
    return tmp_path


def test_action_manifest_is_a_composite_action():
    yaml = pytest.importorskip("yaml")
    data = yaml.safe_load((ROOT / "action.yml").read_text(encoding="utf-8"))
    assert data["runs"]["using"] == "composite"
    assert {"base-ref", "budget", "comment"} <= set(data["inputs"])
    assert {"pack-path", "tokens", "changed-files", "tests"} <= set(data["outputs"])
    for step in data["runs"]["steps"]:
        assert "uses" in step or step.get("shell") == "bash"
    assert any("upload-artifact" in step.get("uses", "") for step in data["runs"]["steps"])
    run = next(step["run"] for step in data["runs"]["steps"] if step.get("id") == "report")
    assert "contexta_app.ci_report" in run and "${{" not in run  # inputs go through env, never into the shell text


def test_report_lists_changed_files_and_tests_and_redacts(pr_repo, tmp_path_factory):
    out = tmp_path_factory.mktemp("out") / "pack.md"
    summary = out.with_name("summary.md")
    code = ci_report.main(["--project", str(pr_repo), "--base", "main", "--budget", "6000", "--output", str(out), "--summary-file", str(summary)])
    assert code == 0
    pack = out.read_text(encoding="utf-8")
    assert "`pkg/util.py`" in pack and "`tests/test_util.py`" in pack
    assert FAKE_KEY not in pack
    text = summary.read_text(encoding="utf-8")
    assert text.startswith(ci_report.MARKER) and "tests/test_util.py" in text and "def " not in text
    from contexta_app.renderer import estimate_tokens

    assert estimate_tokens(pack) <= 6000


def test_report_respects_a_small_budget(pr_repo, tmp_path_factory):
    for i in range(25):
        write(pr_repo, f"pkg/big{i}.py", "\n".join(f"def f{i}_{j}():\n    return {j}" for j in range(40)) + "\n")
    git(pr_repo, "add", "-A")
    git(pr_repo, "commit", "-qm", "many")
    out = tmp_path_factory.mktemp("out") / "pack.md"
    assert ci_report.main(["--project", str(pr_repo), "--base", "main", "--budget", "3000", "--output", str(out)]) == 0
    from contexta_app.renderer import estimate_tokens

    assert estimate_tokens(out.read_text(encoding="utf-8")) <= 3300


def test_missing_base_explains_fetch_depth(pr_repo, capsys):
    assert ci_report.main(["--project", str(pr_repo), "--base", "origin/nope", "--output", str(pr_repo / "x.md")]) == 2
    assert "fetch-depth: 0" in capsys.readouterr().err


def test_post_comment_creates_then_updates():
    calls: list[tuple] = []
    existing: list[dict] = []

    def fake(method, url, token, payload=None):
        calls.append((method, url))
        if method == "GET":
            return list(existing)
        if method == "POST":
            existing.append({"id": 7, "body": payload["body"]})
        return {}

    body = ci_report.MARKER + "\nhello"
    assert ci_report.post_comment(body, "o/r", 5, "t", request=fake) == "created"
    assert ci_report.post_comment(body + "2", "o/r", 5, "t", request=fake) == "updated"
    assert [m for m, _ in calls].count("POST") == 1
    assert calls[-1] == ("PATCH", "https://api.github.com/repos/o/r/issues/comments/7")


def test_post_comment_finds_the_marker_on_a_later_page():
    def fake(method, url, token, payload=None):
        if method == "GET":
            if url.endswith("&page=1"):
                return [{"id": i, "body": "x"} for i in range(100)]
            return [{"id": 999, "body": ci_report.MARKER}]
        return {}

    assert ci_report.post_comment(ci_report.MARKER, "o/r", 1, "t", request=fake) == "updated"


def test_find_pr_number(tmp_path):
    event = tmp_path / "e.json"
    event.write_text(json.dumps({"pull_request": {"number": 42}}), encoding="utf-8")
    assert ci_report.find_pr_number(str(event)) == 42
    assert ci_report.find_pr_number(str(tmp_path / "missing.json")) is None


def test_comment_failure_does_not_fail_the_run(pr_repo, tmp_path_factory, monkeypatch):
    import urllib.error

    event = tmp_path_factory.mktemp("ev") / "e.json"
    event.write_text(json.dumps({"pull_request": {"number": 3}}), encoding="utf-8")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")

    def boom(*a, **k):
        raise urllib.error.URLError("403 from a fork")

    monkeypatch.setattr(ci_report, "post_comment", boom)
    out = tmp_path_factory.mktemp("out") / "pack.md"
    assert ci_report.main(["--project", str(pr_repo), "--base", "main", "--output", str(out), "--comment"]) == 0
    assert out.exists()


def test_module_runs_as_a_script():
    result = subprocess.run([sys.executable, "-m", "contexta_app.ci_report", "--help"], cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0 and "--base" in result.stdout


def test_docs_name_every_input():
    yaml = pytest.importorskip("yaml")
    data = yaml.safe_load((ROOT / "action.yml").read_text(encoding="utf-8"))
    docs = (ROOT / "docs" / "github-action.md").read_text(encoding="utf-8")
    for name in data["inputs"]:
        assert f"`{name}`" in docs, name
