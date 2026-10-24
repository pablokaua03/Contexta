import json
import subprocess
import sys
from pathlib import Path

import pytest

from contexta_app.install import BEGIN, END, run_install

ROOT = Path(__file__).resolve().parent.parent


def run(project: Path, *args: str) -> int:
    return run_install([*args, "-C", str(project)])


def test_creates_every_target_and_is_idempotent(tmp_path, capsys):
    assert run(tmp_path, "all") == 0
    first = {p.relative_to(tmp_path).as_posix(): p.read_text() for p in tmp_path.rglob("*") if p.is_file()}
    assert set(first) == {".cursor/rules/contexta.mdc", "CLAUDE.md", ".github/copilot-instructions.md", ".mcp.json"}
    assert first[".cursor/rules/contexta.mdc"].startswith("---\n") and "alwaysApply: true" in first[".cursor/rules/contexta.mdc"]
    capsys.readouterr()
    assert run(tmp_path, "all") == 0
    out = capsys.readouterr().out
    assert out.count("ok ") == 4 and "created" not in out
    second = {p.relative_to(tmp_path).as_posix(): p.read_text() for p in tmp_path.rglob("*") if p.is_file()}
    assert first == second


def test_rules_mention_the_tools_that_exist():
    text = (ROOT / "contexta_app" / "install.py").read_text()
    from contexta_app import mcp_server

    for tool in ("repo_map", "search_symbols", "impacted_tests", "graph_query", "context_for", "find_files"):
        assert tool in text
        assert hasattr(mcp_server, tool), tool


def test_claude_md_keeps_existing_content(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# My rules\n\nAlways use tabs.\n")
    run(tmp_path, "claude")
    text = (tmp_path / "CLAUDE.md").read_text()
    assert text.startswith("# My rules\n\nAlways use tabs.\n") and BEGIN in text and END in text
    run(tmp_path, "claude")
    assert (tmp_path / "CLAUDE.md").read_text() == text


def test_edited_block_needs_force_and_only_the_block_changes(tmp_path, capsys):
    (tmp_path / "CLAUDE.md").write_text("before\n")
    run(tmp_path, "claude")
    path = tmp_path / "CLAUDE.md"
    edited = path.read_text().replace("Never ask for", "Please do not ask for") + "\nafter my block\n"
    path.write_text(edited)
    capsys.readouterr()
    run(tmp_path, "claude")
    assert path.read_text() == edited and "skipped" in capsys.readouterr().out
    run(tmp_path, "claude", "--force")
    forced = path.read_text()
    assert forced.startswith("before\n") and forced.rstrip().endswith("after my block")
    assert "Please do not ask for" not in forced and forced.count(BEGIN) == 1


def test_cursor_rule_is_not_overwritten_without_force(tmp_path, capsys):
    run(tmp_path, "cursor")
    path = tmp_path / ".cursor/rules/contexta.mdc"
    path.write_text("my own rule\n")
    run(tmp_path, "cursor")
    assert path.read_text() == "my own rule\n"
    run(tmp_path, "cursor", "--force")
    assert path.read_text().startswith("---")


def test_mcp_merges_with_other_servers(tmp_path, capsys):
    (tmp_path / ".mcp.json").write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}, "keep": 1}))
    run(tmp_path, "mcp")
    data = json.loads((tmp_path / ".mcp.json").read_text())
    assert data["mcpServers"]["other"] == {"command": "x"} and data["keep"] == 1
    assert data["mcpServers"]["contexta"] == {"command": "contexta", "args": ["serve"]}


def test_mcp_conflict_needs_force(tmp_path, capsys):
    (tmp_path / ".mcp.json").write_text(json.dumps({"mcpServers": {"contexta": {"command": "custom"}}}))
    run(tmp_path, "mcp")
    assert json.loads((tmp_path / ".mcp.json").read_text())["mcpServers"]["contexta"] == {"command": "custom"}
    run(tmp_path, "mcp", "--force")
    assert json.loads((tmp_path / ".mcp.json").read_text())["mcpServers"]["contexta"]["command"] == "contexta"


def test_mcp_refuses_broken_json_even_with_force(tmp_path):
    (tmp_path / ".mcp.json").write_text("{ nope")
    assert run(tmp_path, "mcp", "--force") == 1
    assert (tmp_path / ".mcp.json").read_text() == "{ nope"


def test_mcp_clients_and_roots(tmp_path):
    run(tmp_path, "mcp", "--client", "vscode", "--root", "src")
    data = json.loads((tmp_path / ".vscode/mcp.json").read_text())
    assert data["servers"]["contexta"] == {"type": "stdio", "command": "contexta", "args": ["serve", "--root", "src"]}
    run(tmp_path, "mcp", "--client", "cursor")
    assert (tmp_path / ".cursor/mcp.json").exists()


def test_dry_run_writes_nothing(tmp_path, capsys):
    run(tmp_path, "all", "--dry-run")
    assert list(tmp_path.iterdir()) == []
    assert "Dry run" in capsys.readouterr().out


def test_generated_files_hold_no_personal_paths(tmp_path):
    run(tmp_path, "all")
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert str(tmp_path) not in path.read_text()


def test_entry_point_dispatches_install(tmp_path):
    result = subprocess.run([sys.executable, str(ROOT / "contexta.py"), "install", "cursor", "-C", str(tmp_path)], capture_output=True, text=True)
    assert result.returncode == 0 and (tmp_path / ".cursor/rules/contexta.mdc").exists()
