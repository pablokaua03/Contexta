"""
mcp_server.py - MCP server for Contexta.

Exposes project understanding as tools callable by Claude Code, Cursor,
Windsurf, and any MCP-compatible client.

Start via:
    contexta serve
    python contexta_mcp.py
"""

from __future__ import annotations

from pathlib import Path

from mcp.server.fastmcp import FastMCP

from contexta_app.cache import get_analysis, get_cache_stats, invalidate
from contexta_app.context_engine import (
    PACK_DEFAULTS,
    PACK_OPTIONS,
    ExportConfig,
)
from contexta_app.redaction import redact_secrets
from contexta_app.renderer import generate_markdown
from contexta_app.scanner import GitError, get_language, read_file_safe

mcp = FastMCP(
    "Contexta",
    instructions=(
        "Contexta is a codebase context engine. Use it to understand projects: "
        "scan_project for a quick fingerprint, generate_context for a full "
        "AI-optimized context pack, read_files to get specific file contents, "
        "find_files to locate files by name/pattern, and get_architecture for "
        "a high-level project overview. Start with scan_project to understand "
        "what you're working with. Results are cached — repeat calls are instant "
        "until files change on disk."
    ),
)


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
    path = Path(project_path).resolve()
    if not path.is_dir():
        return f"Error: '{project_path}' is not a valid directory."
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
    path = Path(project_path).resolve()
    if not path.is_dir():
        return f"Error: '{project_path}' is not a valid directory."

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
    path = Path(project_path).resolve()
    if not path.is_dir():
        return f"Error: '{project_path}' is not a valid directory."

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


@mcp.tool()
def find_files(project_path: str, query: str) -> str:
    """Find files in a project by name, extension, or keyword. Returns matching
    file paths with language and line count. Cached.

    Args:
        project_path: Absolute path to the project folder.
        query: Search term — matches file names and paths.
               Examples: "auth", "controller", ".tsx", "test_user".
    """
    path = Path(project_path).resolve()
    if not path.is_dir():
        return f"Error: '{project_path}' is not a valid directory."

    try:
        analysis, _, _, _ = get_analysis(path)
        query_lower = query.lower()
        matches = []

        for f in analysis.all_files:
            rel = f.relpath.as_posix().lower()
            if query_lower in rel:
                lang = f.lang or "unknown"
                matches.append(f"- `{f.relpath.as_posix()}` ({lang}, {f.line_count} lines)")

        if not matches:
            return f"No files matching '{query}' in {path.name}."

        matches.sort()
        header = f"# Files matching '{query}' in {path.name}\n\nFound {len(matches)} file(s):\n"
        return header + "\n".join(matches[:50])
    except Exception as exc:
        return f"Error: {exc}"


@mcp.tool()
def read_files(project_path: str, files: list[str]) -> str:
    """Read the contents of specific files from a project. Returns each file's
    path and full content in fenced code blocks.

    Args:
        project_path: Absolute path to the project folder.
        files: Relative file paths to read (e.g. ["src/main.py", "config.json"]).
               Max 20 files per call.
    """
    path = Path(project_path).resolve()
    if not path.is_dir():
        return f"Error: '{project_path}' is not a valid directory."

    results = []
    for rel in files[:20]:
        full = path / rel
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

    path = Path(project_path).resolve()
    if not path.is_dir():
        return f"Error: '{project_path}' is not a valid directory."

    invalidate(path)
    analysis, _, file_count, _ = get_analysis(path, force_refresh=True)
    return f"Refreshed cache for {path.name} ({file_count} files)."
