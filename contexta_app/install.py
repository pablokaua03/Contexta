"""
install.py - ``contexta install``: write agent rules and MCP config into a project.

    contexta install cursor            .cursor/rules/contexta.mdc
    contexta install claude            CLAUDE.md (a managed block)
    contexta install copilot           .github/copilot-instructions.md (a managed block)
    contexta install mcp               .mcp.json   (--client cursor|vscode for the other editors)

Safe to run twice: identical content is left alone. Existing files are never
overwritten without ``--force``. Files with a managed block get the block
appended (their other content is untouched); a changed block needs ``--force``
and only that block is replaced.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

BEGIN = "<!-- contexta:begin -->"
END = "<!-- contexta:end -->"

RULES = """## Contexta: get the right context first

This project has Contexta (MCP server `contexta`, or the `contexta` command). Use it before
reading files at random.

- **Start with the map.** Call `repo_map` (or `contexta graph map --budget 1500`) to see the
  important files and symbols in a few hundred tokens.
- **Find things by meaning, not by name.** `search_symbols` finds a class or function;
  `find_files` also searches file contents.
- **Pull context for a task.** `context_for` with the task and a token budget returns the files
  that matter, trimmed to fit. Do not paste the whole repo.
- **Before you change a file**, call `impacted_tests` with it. Run those tests after the change.
  `graph_query` answers "who uses this function" (`dependents`) and "what does it use".
- **Never ask for `.env`, keys or credentials.** Contexta refuses them and redacts secrets.

Without MCP, the same questions work in a terminal:
`contexta graph impact <file>`, `contexta graph dependents <file>::<symbol>`,
`contexta . --for bugfix --budget 20000 --focus "<what you are fixing>"`.
"""

CURSOR_FRONTMATTER = """---
description: Use Contexta to find the right files, symbols and tests before editing
alwaysApply: true
---

"""


def managed_block() -> str:
    return f"{BEGIN}\n{RULES.rstrip()}\n{END}\n"


@dataclass
class Result:
    path: str
    status: str  # created | appended | updated | unchanged | skipped | refused
    note: str = ""

    def line(self) -> str:
        labels = {
            "created": "created ", "appended": "appended", "updated": "updated ",
            "unchanged": "ok      ", "skipped": "skipped ", "refused": "refused ",
        }
        return f"  {labels[self.status]} {self.path}" + (f"  ({self.note})" if self.note else "")


def _write(path: Path, text: str, dry_run: bool) -> None:
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def install_file(root: Path, rel: str, content: str, force: bool, dry_run: bool) -> Result:
    """A file Contexta owns outright (a Cursor rule)."""
    path = root / rel
    if not path.exists():
        _write(path, content, dry_run)
        return Result(rel, "created")
    if path.read_text(encoding="utf-8") == content:
        return Result(rel, "unchanged")
    if not force:
        return Result(rel, "skipped", "exists and differs; use --force to replace it")
    _write(path, content, dry_run)
    return Result(rel, "updated")


def install_block(root: Path, rel: str, force: bool, dry_run: bool) -> Result:
    """A shared file (CLAUDE.md): only the managed block is ours."""
    path = root / rel
    block = managed_block()
    if not path.exists():
        _write(path, block, dry_run)
        return Result(rel, "created")
    text = path.read_text(encoding="utf-8")
    start, end = text.find(BEGIN), text.find(END)
    if start == -1 or end == -1 or end < start:
        joined = text.rstrip("\n") + ("\n\n" if text.strip() else "") + block
        _write(path, joined, dry_run)
        return Result(rel, "appended", "your existing content is untouched")
    end += len(END)
    current = text[start:end] + ("\n" if text[end:end + 1] == "\n" else "")
    if current.rstrip("\n") == block.rstrip("\n"):
        return Result(rel, "unchanged")
    if not force:
        return Result(rel, "skipped", "the Contexta block was edited; use --force to replace it")
    tail = text[end:].lstrip("\n")
    updated = text[:start] + block.rstrip("\n") + ("\n\n" + tail if tail else "\n")
    _write(path, updated, dry_run)
    return Result(rel, "updated", "only the Contexta block was replaced")


MCP_FILES = {
    "claude": (".mcp.json", "mcpServers"),
    "cursor": (".cursor/mcp.json", "mcpServers"),
    "vscode": (".vscode/mcp.json", "servers"),
}


def mcp_entry(roots: list[str]) -> dict:
    args = ["serve"]
    for root in roots:
        args += ["--root", root]
    return {"command": "contexta", "args": args}


def install_mcp(root: Path, client: str, roots: list[str], force: bool, dry_run: bool) -> Result:
    rel, key = MCP_FILES[client]
    path = root / rel
    entry = mcp_entry(roots)
    if client == "vscode":
        entry = {"type": "stdio", **entry}
    data: dict = {}
    file_existed = path.exists()
    if file_existed:
        try:
            data = json.loads(path.read_text(encoding="utf-8") or "{}")
            if not isinstance(data, dict):
                raise ValueError("top level is not an object")
        except ValueError as exc:
            return Result(rel, "refused", f"not valid JSON ({exc}); fix or remove it first")
    servers = data.setdefault(key, {})
    if not isinstance(servers, dict):
        return Result(rel, "refused", f"'{key}' is not an object")
    if servers.get("contexta") == entry:
        return Result(rel, "unchanged")
    existed = "contexta" in servers
    if existed and not force:
        return Result(rel, "skipped", "a different 'contexta' server is configured; use --force to replace it")
    servers["contexta"] = entry
    _write(path, json.dumps(data, indent=2) + "\n", dry_run)
    return Result(rel, "updated" if existed else ("appended" if file_existed else "created"))


TARGETS = ("cursor", "claude", "copilot", "mcp")

EXAMPLES = """examples:
  contexta install cursor                 write .cursor/rules/contexta.mdc
  contexta install claude mcp             CLAUDE.md block and .mcp.json
  contexta install mcp --client cursor    .cursor/mcp.json
  contexta install copilot --dry-run      show what would change
  contexta install mcp --root ~/code      limit the server to a folder (default: the folder it starts in)
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="contexta install",
        description="Write agent rules and MCP config for this project. Safe to run twice; never overwrites without --force.",
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("targets", nargs="+", choices=TARGETS + ("all",), metavar="TARGET", help="cursor, claude, copilot, mcp, or all")
    parser.add_argument("-C", "--project", default=".", metavar="DIR", help="Project folder (default: current directory)")
    parser.add_argument("--client", choices=sorted(MCP_FILES), default="claude", help="Which editor's MCP file to write (default: claude, .mcp.json)")
    parser.add_argument("--root", action="append", default=[], metavar="DIR", help="Folder the MCP server may read. Repeatable. Default: its working directory")
    parser.add_argument("--force", action="store_true", help="Replace files or blocks that already exist and differ")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change and write nothing")
    return parser


def run_install(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.project).expanduser().resolve()
    if not root.is_dir():
        print(f"Not a folder: {args.project}", file=sys.stderr)
        return 1
    targets = list(TARGETS) if "all" in args.targets else list(dict.fromkeys(args.targets))
    results: list[Result] = []
    for target in targets:
        if target == "cursor":
            results.append(install_file(root, ".cursor/rules/contexta.mdc", CURSOR_FRONTMATTER + RULES, args.force, args.dry_run))
        elif target == "claude":
            results.append(install_block(root, "CLAUDE.md", args.force, args.dry_run))
        elif target == "copilot":
            results.append(install_block(root, ".github/copilot-instructions.md", args.force, args.dry_run))
        elif target == "mcp":
            results.append(install_mcp(root, args.client, args.root, args.force, args.dry_run))
    print(("Dry run. Nothing was written.\n" if args.dry_run else "") + "\n".join(r.line() for r in results))
    if any(r.status == "refused" for r in results):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(run_install(sys.argv[1:]))
