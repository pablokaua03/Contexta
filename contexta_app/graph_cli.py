"""
graph_cli.py - ``contexta graph ...``: ask the project graph questions from the terminal.

    contexta graph update            index or refresh (also happens before every query)
    contexta graph status
    contexta graph dependents FILE[::SYMBOL]
    contexta graph dependencies FILE[::SYMBOL]
    contexta graph impact FILE...    dependents, ranked tests, files that usually change together
    contexta graph changed [--since REF|YYYY-MM-DD]
    contexta graph hot
    contexta graph symbols QUERY
    contexta graph map [--budget N] [--focus TEXT]
    contexta graph export [--format json|jsonl|md] [-o FILE]
    contexta graph clear
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from contexta_app.graph import ProjectGraph
from contexta_app.renderer import __version__
from contexta_app.scanner import GitError

EXAMPLES = """examples:
  contexta graph update
  contexta graph impact src/app/auth.py            what breaks, and which tests to run
  contexta graph dependents src/app/auth.py::login who uses this function
  contexta graph changed --since main              changed files with their reach
  contexta graph hot --days 90                     most changed source files
  contexta graph map --budget 1500 --focus login   a small map of the repo
  contexta graph export --format json -o graph.json
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="contexta graph",
        description="Ask the project graph (.contexta/graph.db) about files, symbols, impact and history.",
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-C", "--project", default=".", metavar="DIR", help="Project folder (default: current directory)")
    common.add_argument("--json", action="store_true", help="Print JSON instead of text")
    common.add_argument("--no-update", action="store_true", help="Do not refresh the graph before answering")
    common.add_argument("--no-git", action="store_true", help="Skip git history (no hot files or co-change)")
    sub = parser.add_subparsers(dest="op", required=True, metavar="COMMAND")

    sub.add_parser("update", parents=[common], help="Index or refresh the graph")
    sub.add_parser("status", parents=[common], help="Show what the graph holds")
    sub.add_parser("clear", parents=[common], help="Delete the graph database")

    for name, help_text in (("dependents", "Who uses a file or symbol"), ("dependencies", "What a file or symbol uses")):
        p = sub.add_parser(name, parents=[common], help=help_text)
        p.add_argument("target", help="path, path::Symbol, or a symbol name")
        p.add_argument("--depth", type=int, default=1, help="How many hops to follow (default 1)")

    p = sub.add_parser("impact", parents=[common], help="What a change reaches, and which tests to run")
    p.add_argument("targets", nargs="*", help="Files or symbols. Default: files changed in git")
    p.add_argument("--depth", type=int, default=3)
    p.add_argument("--limit", type=int, default=40)
    p.add_argument("--tests-only", action="store_true", help="Print only the test paths, one per line")

    p = sub.add_parser("changed", parents=[common], help="Files changed since a commit, tag, branch or date")
    p.add_argument("--since", default=None, metavar="REF", help="commit, tag, branch or YYYY-MM-DD (default: uncommitted work)")

    p = sub.add_parser("hot", parents=[common], help="Most changed files")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--days", type=int, default=None, help="Only count the last N days")
    p.add_argument("--all-kinds", action="store_true", help="Include tests, docs and config")

    p = sub.add_parser("symbols", parents=[common], help="Search symbols by name")
    p.add_argument("query")
    p.add_argument("--kind", default=None, help="class, function, method, ...")
    p.add_argument("--limit", type=int, default=20)

    p = sub.add_parser("map", parents=[common], help="A compact repo map inside a token budget")
    p.add_argument("--budget", type=int, default=1500, metavar="N")
    p.add_argument("--focus", default=None)

    p = sub.add_parser("export", parents=[common], help="Export the graph for other tools")
    p.add_argument("--format", choices=("json", "jsonl", "md"), default="json")
    p.add_argument("-o", "--output", default=None, help="Write to a file instead of stdout")
    return parser


def _emit(args, payload, text: str) -> None:
    sys.stdout.write((json.dumps(payload, indent=2, ensure_ascii=False) + "\n") if args.json else text)


def _rows(rows: list[dict], fields: list[str]) -> str:
    return "".join("  " + "  ".join(str(row.get(f, "")) for f in fields).rstrip() + "\n" for row in rows)


def format_status(info: dict, name: str) -> str:
    lines = [f"Graph for {name} (Contexta {__version__})"]
    lines.append(f"  {info['files']} files, {info['symbols']} symbols, {info['tests']} tests, {info['commits']} commits read")
    lines.append("  edges: " + (", ".join(f"{k} {v}" for k, v in sorted(info["edges"].items())) or "none"))
    lines.append("  parsers: " + ", ".join(f"{k} {v}" for k, v in sorted(info["parsers"].items())))
    lines.append(f"  updated {info['updated_at']}   db {info['db']}")
    return "\n".join(lines) + "\n"


def format_impact(result: dict) -> str:
    text = f"Changed: {', '.join(result['changed']) or '(none found in graph)'}\n"
    text += f"\nImpacted files ({result['impacted_total']}):\n" + _rows(result["impacted"], ["path", "distance", "via"])
    text += f"\nTests to run ({result['tests_total']}):\n" + _rows(result["tests"], ["path", "reason"])
    if result["cochanged"]:
        text += "\nUsually change together:\n" + _rows(result["cochanged"], ["path", "times_together"])
    return text


def format_hot(rows: list[dict]) -> str:
    return ("Most changed files\n" + _rows(rows, ["commits", "last_changed", "path"])) if rows else "No git history found.\n"


def format_symbols(rows: list[dict]) -> str:
    for row in rows:
        row["where"] = f"{row['path']}:{row['line']}"
    return _rows(rows, ["where", "kind", "signature"]) if rows else "No symbols match.\n"


def run_graph(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = Path(args.project).expanduser()
    if not root.is_dir():
        print(f"Not a folder: {args.project}", file=sys.stderr)
        return 1
    graph = ProjectGraph(root)
    err = lambda msg: print(msg, file=sys.stderr)  # noqa: E731

    if args.op == "clear":
        base = graph.db_path.parent
        graph.close()
        if base.name == ".contexta" and base.is_dir():
            shutil.rmtree(base)
            print(f"Removed {base.name}/")
        elif graph.db_path.exists():
            graph.db_path.unlink()
            print("Removed the graph database")
        else:
            print("No graph to remove")
        return 0

    try:
        if args.op == "update" or not args.no_update or graph.is_empty():
            stats = graph.update(use_git=not args.no_git)
            if args.op == "update":
                _emit(args, stats.to_dict(), stats.summary() + "\n")
                return 0
            if stats.added or stats.changed or stats.removed:
                err(stats.summary())

        if args.op == "status":
            info = graph.stats()
            _emit(args, info, format_status(info, root.resolve().name))
        elif args.op in {"dependents", "dependencies"}:
            fn = graph.dependents if args.op == "dependents" else graph.dependencies
            rows = fn(args.target, depth=args.depth)
            for row in rows:
                if row.get("symbol"):
                    row["path"] = f"{row['path']}::{row['symbol']}"
            _emit(args, rows, (f"{len(rows)} {args.op} of {args.target}\n" + _rows(rows, ["path", "distance", "via", "kind"])) if rows else f"No {args.op} found for {args.target}\n")
        elif args.op == "impact":
            targets = list(args.targets)
            if not targets:
                targets = [f["path"] for f in graph.changed_since(None)["files"]]
                if not targets:
                    err("No targets given and no uncommitted changes.")
                    return 1
            result = graph.impact(targets, depth=args.depth, limit=args.limit)
            if args.tests_only and not args.json:
                sys.stdout.write("".join(t["path"] + "\n" for t in result["tests"]))
            else:
                _emit(args, result, format_impact(result))
        elif args.op == "changed":
            result = graph.changed_since(args.since)
            text = f"Changed {result['since']}: {len(result['files'])} file(s)\n" + _rows(result["files"], ["path", "kind", "dependents"])
            _emit(args, result, text)
        elif args.op == "hot":
            rows = graph.hot_files(args.limit, since_days=args.days, kind=None if args.all_kinds else "source")
            _emit(args, rows, format_hot(rows))
        elif args.op == "symbols":
            rows = graph.search_symbols(args.query, args.limit, args.kind)
            text = format_symbols(rows)  # also adds "where" to each row, which --json prints
            _emit(args, rows, text)
        elif args.op == "map":
            result = graph.repo_map(args.budget, args.focus)
            _emit(args, result, result["text"] + f"\n~{result['tokens']} tokens, {result['files']} files, {result['symbols']} symbols\n")
        elif args.op == "export":
            data = graph.export(args.format)
            if args.output:
                Path(args.output).write_text(data, encoding="utf-8")
                err(f"Wrote {args.output}")
            else:
                sys.stdout.write(data)
    except (ValueError, GitError) as exc:
        err(str(exc))
        return 1
    finally:
        graph.close()
    return 0


def main(argv: list[str] | None = None) -> None:
    raise SystemExit(run_graph(sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    main()
