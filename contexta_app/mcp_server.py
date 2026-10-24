"""
mcp_server.py - MCP server for Contexta.

Exposes project understanding as tools callable by Claude Code, Cursor,
Windsurf, and any MCP-compatible client.

Start via:
    contexta serve
    python contexta_mcp.py
"""

from __future__ import annotations

import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from contexta_app import __version__
from contexta_app.cache import get_analysis, get_cache_stats, invalidate
from contexta_app.context_engine import (
    PACK_DEFAULTS,
    PACK_OPTIONS,
    ExportConfig,
)
from contexta_app.graph import ProjectGraph
from contexta_app.redaction import redact_secrets
from contexta_app.safety import is_sensitive_path
from contexta_app.renderer import generate_markdown
from contexta_app.scanner import GitError, get_language, read_file_safe

_ROOTS: list[Path] | None = None


def configure_roots(roots: list[str | Path] | None) -> list[Path]:
    """Set the folders the tools may read. ``None`` goes back to the default."""
    global _ROOTS
    _ROOTS = None if roots is None else [Path(r).expanduser().resolve() for r in roots]
    return allowed_roots()


def allowed_roots() -> list[Path]:
    """Configured roots, else CONTEXTA_ROOT (path-separated), else the working directory."""
    if _ROOTS is not None:
        return list(_ROOTS)
    raw = os.environ.get("CONTEXTA_ROOT", "").strip()
    if raw:
        return [Path(part).expanduser().resolve() for part in raw.split(os.pathsep) if part.strip()]
    return [Path.cwd().resolve()]


def parse_serve_args(args: list[str]) -> list[str]:
    """Pull ``--root DIR`` (repeatable, or ``--root=DIR``) out of ``contexta serve`` arguments."""
    roots: list[str] = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in ("-h", "--help"):
            print("Usage: contexta serve [--root DIR]\n\nStart the MCP server over stdio. Tools only read inside --root\n(repeatable), CONTEXTA_ROOT, or the current directory.")
            raise SystemExit(0)
        if arg == "--root":
            if i + 1 >= len(args):
                raise SystemExit("contexta serve: --root needs a folder")
            roots.append(args[i + 1])
            i += 2
            continue
        if arg.startswith("--root="):
            roots.append(arg.split("=", 1)[1])
        else:
            raise SystemExit(f"contexta serve: unknown option {arg!r}. Usage: contexta serve [--root DIR]")
        i += 1
    return roots


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def resolve_project(project_path: str) -> tuple[Path | None, str]:
    """Resolve ``project_path`` and require it to sit inside an allowed root.

    Returns ``(path, "")`` or ``(None, error_message)``.
    """
    try:
        path = Path(project_path).expanduser().resolve()
    except (OSError, RuntimeError):
        return None, f"Error: '{project_path}' is not a valid directory."
    if not path.is_dir():
        return None, f"Error: '{project_path}' is not a valid directory."
    if not any(_is_within(path, root) for root in allowed_roots()):
        names = ", ".join(str(root) for root in allowed_roots())
        return None, (
            f"Error: '{project_path}' is outside the folders this server may read ({names}). "
            "Start the server with --root <folder> to allow it."
        )
    return path, ""


def resolve_file(project: Path, rel: str) -> tuple[Path | None, str]:
    """Resolve ``rel`` inside ``project``. Rejects escapes, symlinks out, and credential files."""
    if not rel or "\x00" in rel:
        return None, "Not a valid file path."
    try:
        full = (project / rel).resolve()
    except (OSError, RuntimeError):
        return None, "Not a valid file path."
    if not _is_within(full, project):
        return None, "Path is outside the project folder."
    if is_sensitive_path(full.relative_to(project)):
        return None, "Credential file. Contexta does not serve these."
    return full, ""


mcp = FastMCP(
    "Contexta",
    instructions=(
        "Contexta is a codebase context engine. Use it to understand projects: "
        "scan_project for a quick fingerprint, generate_context for a full "
        "AI-optimized context pack, read_files to get specific file contents, "
        "find_files to locate files by name/pattern, and get_architecture for "
        "a high-level project overview. Start with scan_project to understand "
        "what you're working with. For code questions: repo_map shows the important "
        "files and symbols in a small budget, search_symbols and find_files locate "
        "things, impacted_tests says which tests to run for a change, graph_query "
        "answers who-uses-what, and context_for returns the context for a task "
        "inside a token budget. Results are cached and the project graph updates "
        "itself as files change."
    ),
)
mcp._mcp_server.version = __version__  # the server reports Contexta's version, not the MCP library's


@mcp.tool()
def generate_context(
    project_path: str,
    pack: str = "custom",
    mode: str = "full",
    ai_profile: str = "generic",
    task: str = "general",
    compression: str = "balanced",
    focus: str = "",
    diff_mode: bool = False,
    include_hidden: bool = False,
    base: str = "",
    redact: bool = True,
    budget: int = 0,
) -> str:
    """Generate an AI-optimized context pack for a project directory.

    Returns a curated Markdown document with project structure, key files,
    architecture notes, and AI-specific guidance.

    Args:
        project_path: Absolute path to the project folder.
        pack: Preset — custom, chatgpt, onboarding, pr_review, risk_review,
              debug, bugfix, backend, frontend, changes_related, refactor, raw_files.
        mode: Context mode — full, debug, feature, diff, onboarding, refactor.
        ai_profile: Target AI — generic, chatgpt, claude, gemini, copilot.
        task: Task profile — general, ai_handoff, bug_report, code_review,
              explain_project, risk_analysis, refactor_request, pr_summary,
              write_tests, find_dead_code.
        compression: full, balanced, focused, signatures, lean.
        focus: Topic to prioritize (e.g. "authentication flow").
        diff_mode: Scope context to git-changed files.
        include_hidden: Include hidden/dot files.
        base: Git ref to compare against, such as main or origin/main.
        redact: Replace likely secrets before returning the pack. On by default.
        budget: Token budget. Files are ranked and cut until the pack fits. 0 means no limit.
    """
    path, error = resolve_project(project_path)
    if path is None:
        return error
    if budget < 0:
        return "Error: budget must be zero or a positive number of tokens."

    try:
        return generate_markdown(
            project_path=path,
            include_hidden=include_hidden,
            diff_mode=diff_mode,
            context_mode=mode,
            ai_profile=ai_profile,
            task_profile=task,
            compression=compression,
            pack_profile=pack,
            focus_query=focus,
            redact_secrets=redact,
            base_ref=base or None,
            token_budget=budget or None,
            use_graph=True,
        )
    except GitError as exc:
        return f"Error: {exc}"
    except Exception as exc:
        return f"Error generating context: {exc}"


@mcp.tool()
def scan_project(project_path: str) -> str:
    """Quick project fingerprint — type, language, frameworks, file count,
    entry points, and key dependencies. Fast and cached. Use this first
    to understand what you're working with.

    Args:
        project_path: Absolute path to the project folder.
    """
    path, error = resolve_project(project_path)
    if path is None:
        return error

    try:
        analysis, _, file_count, cached = get_analysis(path)
        fp = analysis.fingerprint

        lines = [
            f"# Project: {path.name}" + (" (cached)" if cached else ""),
            "",
            f"- Type: {fp.project_type or 'unknown'}",
            f"- Language: {fp.primary_language or 'unknown'}",
            f"- Purpose: {fp.probable_purpose or 'unknown'}",
            f"- Files: {file_count}",
            f"- Confidence: {fp.confidence:.0%}",
        ]

        if fp.frameworks:
            lines.append(f"- Frameworks: {', '.join(fp.frameworks)}")
        if fp.runtime:
            lines.append(f"- Runtime: {', '.join(fp.runtime)}")
        if fp.package_managers:
            lines.append(f"- Package managers: {', '.join(fp.package_managers)}")
        if fp.build_tools:
            lines.append(f"- Build tools: {', '.join(fp.build_tools)}")
        if fp.main_dependencies:
            lines.append(f"- Key deps: {', '.join(fp.main_dependencies[:20])}")
        if analysis.technologies:
            lines.append(f"- Technologies: {', '.join(analysis.technologies[:15])}")
        if analysis.entrypoints:
            entries = [e.relpath.as_posix() for e in analysis.entrypoints[:8]]
            lines.append(f"- Entry points: {', '.join(entries)}")

        if analysis.summary_lines:
            lines.append("")
            lines.append("## Summary")
            lines.extend(analysis.summary_lines[:10])

        return "\n".join(lines)
    except Exception as exc:
        return f"Error scanning project: {exc}"


@mcp.tool()
def get_architecture(project_path: str) -> str:
    """High-level architecture overview — module relationships, folder
    structure, entry points, risks, and key patterns. More detail than
    scan_project, faster than a full context pack. Cached.

    Args:
        project_path: Absolute path to the project folder.
    """
    path, error = resolve_project(project_path)
    if path is None:
        return error

    try:
        analysis, _, _, cached = get_analysis(path)

        lines = [f"# Architecture: {path.name}" + (" (cached)" if cached else ""), ""]

        if analysis.summary_lines:
            lines.append("## Summary")
            lines.extend(analysis.summary_lines)
            lines.append("")

        if analysis.architecture_lines:
            lines.append("## Architecture")
            lines.extend(analysis.architecture_lines)
            lines.append("")

        if analysis.folder_summaries:
            lines.append("## Folder Structure")
            lines.extend(analysis.folder_summaries[:20])
            lines.append("")

        if analysis.relationships:
            lines.append("## Module Relationships")
            lines.extend(analysis.relationships[:20])
            lines.append("")

        if analysis.entrypoints:
            lines.append("## Entry Points")
            for ep in analysis.entrypoints[:10]:
                lines.append(f"- `{ep.relpath.as_posix()}` — {ep.summary}")
            lines.append("")

        if analysis.important_files:
            lines.append("## Key Files")
            for f in analysis.important_files[:15]:
                lines.append(f"- `{f.relpath.as_posix()}` — {f.summary}")
            lines.append("")

        if analysis.risks:
            lines.append("## Risks")
            lines.extend(analysis.risks[:10])

        return "\n".join(lines)
    except Exception as exc:
        return f"Error: {exc}"


MAX_CONTENT_FILE_BYTES = 1_000_000


def _graph_for(path: Path) -> ProjectGraph:
    """The project's graph, brought up to date. Only changed files are parsed again."""
    graph = ProjectGraph(path)
    try:
        graph.update()
    except Exception:
        graph.close()
        raise
    return graph


def _content_matches(path: Path, graph: ProjectGraph, needle: str, limit: int) -> list[str]:
    """``path:line: text`` for files whose content has ``needle``. Lines are redacted. Credential files are never opened."""
    needle_l = needle.lower()
    hits: list[str] = []
    for row in graph.con.execute("SELECT path, size FROM files WHERE kind IN ('source','test','config','doc') ORDER BY rank DESC, path"):
        if row["size"] > MAX_CONTENT_FILE_BYTES:
            continue
        full, _problem = resolve_file(path, row["path"])
        if full is None or not full.is_file():
            continue
        try:
            text = full.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if needle_l not in text.lower():
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            if needle_l in line.lower():
                snippet, _ = redact_secrets(line.strip()[:200])
                hits.append(f"- `{row['path']}:{number}` {snippet}")
                break
        if len(hits) >= limit:
            break
    return hits


@mcp.tool()
def find_files(project_path: str, query: str, search: str = "all") -> str:
    """Find files by name, by symbol, or by what is inside them.

    Args:
        project_path: Absolute path to the project folder.
        query: Search term. Examples: "auth", "controller", ".tsx", "SessionInterface", "retry_count".
        search: "name" (file paths), "symbols" (class and function names), "content"
                (text inside files, first matching line each), or "all" (default).
    """
    path, error = resolve_project(project_path)
    if path is None:
        return error
    if search not in {"all", "name", "symbols", "content"}:
        return "Error: search must be one of all, name, symbols, content."
    if not query.strip():
        return "Error: query is empty."

    try:
        sections: list[str] = []
        if search in {"all", "name"}:
            analysis, _, _, _ = get_analysis(path)
            query_lower = query.lower()
            matches = sorted(
                f"- `{f.relpath.as_posix()}` ({f.lang or 'unknown'}, {f.line_count} lines)"
                for f in analysis.all_files
                if query_lower in f.relpath.as_posix().lower()
            )
            if matches:
                sections.append(f"## By name ({len(matches)})\n" + "\n".join(matches[:50]))
        if search in {"all", "symbols", "content"}:
            graph = _graph_for(path)
            try:
                if search in {"all", "symbols"}:
                    symbols = graph.search_symbols(query, limit=25)
                    if symbols:
                        lines = [f"- `{s['path']}:{s['line']}` {s['kind']} `{s['signature'] or s['symbol']}`" for s in symbols]
                        sections.append(f"## By symbol ({len(lines)})\n" + "\n".join(lines))
                if search in {"all", "content"}:
                    hits = _content_matches(path, graph, query, limit=25)
                    if hits:
                        sections.append(f"## By content ({len(hits)})\n" + "\n".join(hits))
            finally:
                graph.close()
        if not sections:
            return f"No files matching '{query}' in {path.name}."
        return f"# Matches for '{query}' in {path.name}\n\n" + "\n\n".join(sections)
    except Exception as exc:
        return f"Error: {exc}"


@mcp.tool()
def repo_map(project_path: str, budget: int = 1500, focus: str = "") -> str:
    """A compact map of the repository: the most important files, each with its
    most used classes and functions, inside a small token budget. Call this first
    to see where things are before reading files.

    Args:
        project_path: Absolute path to the project folder.
        budget: Token budget for the map (default 1500).
        focus: Optional topic. Files and symbols matching these words rise to the top.
    """
    path, error = resolve_project(project_path)
    if path is None:
        return error
    if budget < 100:
        return "Error: budget must be at least 100 tokens."
    try:
        graph = _graph_for(path)
        try:
            result = graph.repo_map(budget, focus or None)
        finally:
            graph.close()
        return f"```\n{result['text']}```\n~{result['tokens']} tokens, {result['files']} files, {result['symbols']} symbols"
    except Exception as exc:
        return f"Error: {exc}"


@mcp.tool()
def search_symbols(project_path: str, query: str, kind: str = "", limit: int = 20) -> str:
    """Find classes, functions and methods by name. Returns file, line and signature.

    Args:
        project_path: Absolute path to the project folder.
        query: Part of a symbol name, for example "Session" or "parse_".
        kind: Optional filter: class, function, method, const, type, interface, enum.
        limit: Maximum results (default 20, max 100).
    """
    path, error = resolve_project(project_path)
    if path is None:
        return error
    try:
        graph = _graph_for(path)
        try:
            rows = graph.search_symbols(query, limit=max(1, min(limit, 100)), kind=kind or None)
        finally:
            graph.close()
        if not rows:
            return f"No symbols matching '{query}' in {path.name}."
        return "\n".join(f"- `{r['path']}:{r['line']}` {r['kind']} `{r['signature'] or r['symbol']}`" for r in rows)
    except Exception as exc:
        return f"Error: {exc}"


def _format_impact(result: dict, tests_only: bool = False) -> str:
    lines: list[str] = []
    if not tests_only:
        lines.append("Changed: " + (", ".join(f"`{p}`" for p in result["changed"]) or "(nothing found in the graph)"))
        lines.append(f"\n## Impacted files ({result['impacted_total']})")
        lines += [f"- `{r['path']}` (distance {r['distance']}, via {r['via']})" for r in result["impacted"]] or ["- none"]
    lines.append(f"\n## Tests to run ({result['tests_total']})")
    lines += [f"- `{t['path']}` {t['reason']}" for t in result["tests"]] or ["- none found"]
    if result["cochanged"] and not tests_only:
        lines.append("\n## Usually change together")
        lines += [f"- `{c['path']}` ({c['times_together']} commits)" for c in result["cochanged"]]
    return "\n".join(lines)


@mcp.tool()
def impacted_tests(project_path: str, files: list[str] | None = None, since: str = "", depth: int = 3) -> str:
    """Which tests to run for a change, and what else the change reaches.

    Args:
        project_path: Absolute path to the project folder.
        files: Files or path::Symbol targets that changed. Empty means the files changed
               in git (uncommitted work, plus everything since `since` when given).
        since: Optional commit, tag, branch or YYYY-MM-DD date to compare against.
        depth: How many hops of dependents to follow (default 3).
    """
    path, error = resolve_project(project_path)
    if path is None:
        return error
    try:
        graph = _graph_for(path)
        try:
            targets = [t for t in (files or [])]
            for target in targets:
                if resolve_file(path, target.split("::", 1)[0])[0] is None:
                    return f"Error: '{target}' is outside the project or is a credential file."
            if not targets:
                targets = [f["path"] for f in graph.changed_since(since or None)["files"]]
            if not targets:
                return "No changed files found. Pass `files`, or `since` with a commit, tag, branch or date."
            return _format_impact(graph.impact(targets, depth=max(1, min(depth, 6))))
        finally:
            graph.close()
    except (ValueError, GitError) as exc:
        return f"Error: {exc}"
    except Exception as exc:
        return f"Error: {exc}"


GRAPH_OPS = ("status", "dependents", "dependencies", "impact", "changed", "hot", "symbols")


@mcp.tool()
def graph_query(project_path: str, op: str, target: str = "", depth: int = 1, limit: int = 20, since: str = "") -> str:
    """Ask the project graph (imports, calls, tests, git history) a question.

    Args:
        project_path: Absolute path to the project folder.
        op: One of
            status       what the graph holds
            dependents   who uses `target` (a path, path::Symbol, or symbol name)
            dependencies what `target` uses
            impact       what a change to `target` reaches, with ranked tests
            changed      files changed since `since` (commit, tag, branch, YYYY-MM-DD) or uncommitted
            hot          most changed source files (git history)
            symbols      symbols whose name matches `target`
        target: File, symbol or search text, depending on op.
        depth: Hops to follow for dependents/dependencies/impact.
        limit: Maximum rows.
        since: For changed: the commit, tag, branch or date.
    """
    path, error = resolve_project(project_path)
    if path is None:
        return error
    if op not in GRAPH_OPS:
        return f"Error: op must be one of {', '.join(GRAPH_OPS)}."
    if op in {"dependents", "dependencies", "impact", "symbols"} and not target:
        return f"Error: {op} needs a target."
    if target and op != "symbols":
        problem = resolve_file(path, target.split("::", 1)[0])[1] if "/" in target or "." in target else ""
        if problem and ("outside" in problem or "Credential" in problem):
            return f"Error: {problem}"
    limit = max(1, min(limit, 100))
    try:
        graph = _graph_for(path)
        try:
            if op == "status":
                info = graph.stats()
                return "\n".join([f"- files: {info['files']}", f"- symbols: {info['symbols']}", f"- tests: {info['tests']}",
                                   "- edges: " + ", ".join(f"{k} {v}" for k, v in sorted(info["edges"].items())),
                                   f"- commits read: {info['commits']}", f"- updated: {info['updated_at']}"])
            if op in {"dependents", "dependencies"}:
                fn = graph.dependents if op == "dependents" else graph.dependencies
                rows = fn(target, depth=max(1, min(depth, 6)))[:limit]
                if not rows:
                    return f"No {op} found for `{target}`."
                return "\n".join(f"- `{r['path']}{'::' + r['symbol'] if r.get('symbol') else ''}` (distance {r['distance']}, {r['via']})" for r in rows)
            if op == "impact":
                return _format_impact(graph.impact([target], depth=max(1, min(depth, 6)), limit=limit))
            if op == "changed":
                result = graph.changed_since(since or None)
                lines = [f"{len(result['files'])} file(s) changed {result['since']}"]
                lines += [f"- `{r['path']}` ({r['kind']}, {r['dependents']} dependents)" for r in result["files"][:limit]]
                return "\n".join(lines)
            if op == "hot":
                rows = graph.hot_files(limit)
                if not rows:
                    return "No git history found."
                return "\n".join(f"- `{r['path']}` {r['commits']} commits, last {r['last_changed']}" for r in rows)
            rows = graph.search_symbols(target, limit=limit)
            return "\n".join(f"- `{r['path']}:{r['line']}` {r['kind']} `{r['signature']}`" for r in rows) or f"No symbols match `{target}`."
        finally:
            graph.close()
    except (ValueError, GitError) as exc:
        return f"Error: {exc}"
    except Exception as exc:
        return f"Error: {exc}"


@mcp.tool()
def context_for(project_path: str, task: str, budget: int = 8000, focus: str = "", redact: bool = True) -> str:
    """The context an agent needs for a task, inside a token budget: a small repo map,
    the tests that cover the best-matching files, and a pack of the files ranked for
    the task. Secrets are redacted.

    Args:
        project_path: Absolute path to the project folder.
        task: What you are about to do, in plain words ("fix the session cookie signing bug").
        budget: Total token budget for everything returned (default 8000, minimum 1000).
        focus: Optional keywords to rank by. Defaults to the task text.
        redact: Replace likely secrets. On by default.
    """
    path, error = resolve_project(project_path)
    if path is None:
        return error
    if not task.strip():
        return "Error: describe the task."
    if budget < 1000:
        return "Error: budget must be at least 1000 tokens."
    try:
        from contexta_app.renderer import estimate_tokens

        query = focus.strip() or task.strip()
        graph = _graph_for(path)
        try:
            top = graph.rank_files(focus=query, limit=6)
            tests = graph.tests_for([r["path"] for r in top[:4]], limit=8)
            map_budget = max(300, min(900, budget // 8))
            repo = graph.repo_map(map_budget, query)
        finally:
            graph.close()
        head = ["## Repo map", "```", repo["text"].rstrip(), "```", ""]
        if tests:
            head += ["## Tests near these files"] + [f"- `{t['path']}` {t['reason']}" for t in tests] + [""]
        prefix = "\n".join(head) + "\n"
        pack = generate_markdown(
            project_path=path,
            context_mode="full",
            task_profile="general",
            compression="balanced",
            pack_profile="custom",
            focus_query=query,
            redact_secrets=redact,
            token_budget=max(500, budget - estimate_tokens(prefix)),
            use_graph=True,
        )
        return prefix + pack
    except GitError as exc:
        return f"Error: {exc}"
    except Exception as exc:
        return f"Error generating context: {exc}"


@mcp.tool()
def read_files(project_path: str, files: list[str]) -> str:
    """Read the contents of specific files from a project. Returns each file's
    path and full content in fenced code blocks.

    Args:
        project_path: Absolute path to the project folder.
        files: Relative file paths to read (e.g. ["src/main.py", "config.json"]).
               Max 20 files per call.
    """
    path, error = resolve_project(project_path)
    if path is None:
        return error

    results = []
    for rel in files[:20]:
        full, problem = resolve_file(path, rel)
        if full is None:
            results.append(f"## `{rel}`\n\n{problem}\n")
            continue
        if not full.is_file():
            results.append(f"## `{rel}`\n\nFile not found.\n")
            continue

        content, truncated, _ = read_file_safe(full)
        if content is None:
            results.append(f"## `{rel}`\n\nBinary or unreadable file.\n")
            continue

        content, redacted = redact_secrets(content)
        lang = get_language(full) or ""
        notes = []
        if truncated:
            notes.append("truncated to 1000 lines")
        if redacted:
            notes.append("secrets redacted")
        trunc_note = f" ({', '.join(notes)})" if notes else ""
        results.append(f"## `{rel}`{trunc_note}\n\n```{lang}\n{content}\n```\n")

    if not results:
        return "No files specified."
    return "\n".join(results)


@mcp.tool()
def list_packs() -> str:
    """List all available context pack presets with their configurations.
    Each pack bundles a mode, AI profile, task, and compression level."""
    lines = ["# Available Packs\n"]
    for key, label in PACK_OPTIONS.items():
        defaults = PACK_DEFAULTS.get(key, {})
        if defaults:
            details = ", ".join(f"{k}={v}" for k, v in defaults.items())
            lines.append(f"- **{key}** ({label}): {details}")
        else:
            lines.append(f"- **{key}** ({label}): fully customizable")
    return "\n".join(lines)


@mcp.tool()
def cache_status() -> str:
    """Show cache statistics — how many projects are cached, hit/miss counts.
    Useful for debugging performance."""
    stats = get_cache_stats()
    lines = [
        "# Cache Status",
        "",
        f"- Cached projects: {stats['entries']}",
        f"- Cache hits: {stats['hits']}",
        f"- Cache misses: {stats['misses']}",
        f"- Invalidations: {stats['invalidations']}",
    ]
    if stats["projects"]:
        lines.append("")
        lines.append("## Cached Projects")
        for p in stats["projects"]:
            lines.append(f"- {p}")
    return "\n".join(lines)


@mcp.tool()
def refresh_cache(project_path: str = "") -> str:
    """Force-refresh the cache for a project, or clear all caches.

    Args:
        project_path: Path to refresh. Empty string clears all caches.
    """
    if not project_path:
        count = invalidate()
        return f"Cleared all caches ({count} entries)."

    path, error = resolve_project(project_path)
    if path is None:
        return error

    invalidate(path)
    analysis, _, file_count, _ = get_analysis(path, force_refresh=True)
    return f"Refreshed cache for {path.name} ({file_count} files)."
