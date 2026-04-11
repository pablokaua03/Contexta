"""
renderer.py — Markdown rendering and token estimation.
"""

from datetime import datetime
from pathlib import Path

from scanner import (
    MAX_FILE_LINES,
    build_diff_tree, build_tree, count_files,
    get_git_changed_files, load_gitignore_patterns,
    read_file_safe,
)

__version__ = "1.3.0"


# ─────────────────────────────────────────────────────────────────────────────
# TOKEN ESTIMATION
# ─────────────────────────────────────────────────────────────────────────────

def estimate_tokens(text: str) -> int:
    """Estimate token count using the 1 token ≈ 4 chars heuristic."""
    return max(1, len(text) // 4)


def token_label(n: int) -> str:
    """Return a human-friendly token count with model hints."""
    if n < 8_000:
        hint = "fits most models"
    elif n < 32_000:
        hint = "GPT-4o · Claude Sonnet · Gemini Flash"
    elif n < 128_000:
        hint = "Claude 200k · Gemini 1.5 Pro"
    elif n < 200_000:
        hint = "Claude 200k · Gemini 1.5 Pro 1M"
    else:
        hint = "Gemini 1.5 Pro 1M — consider splitting"
    return f"~{n/1000:.1f}k tokens  ({hint})"


# ─────────────────────────────────────────────────────────────────────────────
# ASCII TREE
# ─────────────────────────────────────────────────────────────────────────────

def render_tree_ascii(node: dict, prefix: str = "", is_root: bool = True) -> str:
    lines: list[str] = []

    if is_root:
        lines.append(f"📦 {node['name']}/")
        child_prefix = ""
    else:
        lines.append(f"{prefix}📁 {node['name']}/")
        child_prefix = prefix.replace("├── ", "│   ").replace("└── ", "    ")

    for i, item in enumerate(node["dirs"]):
        connector = "├── " if i < len(node["dirs"]) - 1 or node["files"] else "└── "
        lines.append(render_tree_ascii(item, child_prefix + connector, False))

    for i, f in enumerate(node["files"]):
        connector = "└── " if i == len(node["files"]) - 1 else "├── "
        lines.append(f"{child_prefix}{connector}📄 {f['name']}")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# FILE CONTENTS
# ─────────────────────────────────────────────────────────────────────────────

def render_files_md(node: dict, depth: int, root_path: Path) -> str:
    parts: list[str] = []
    h  = "#" * min(depth + 1, 6)
    fh = "#" * min(depth + 2, 6)
    rel = node["path"].relative_to(root_path.parent)

    if depth == 1:
        parts.append(f"# 📦 `{node['name']}`\n")
    else:
        parts.append(f"\n{h} 📁 `{rel}`\n")

    for f in node["files"]:
        fpath: Path = f["path"]
        lang: str   = f["lang"] or ""
        rel_f       = fpath.relative_to(root_path.parent)
        size_kb     = fpath.stat().st_size / 1024

        parts.append(f"\n{fh} 📄 `{f['name']}`\n")
        parts.append(f"> **Path:** `{rel_f}`  ")
        parts.append(f"> **Size:** {size_kb:.1f} KB\n")

        content, truncated = read_file_safe(fpath)
        if truncated:
            parts.append(f"> ⚠️ **Truncated** — first {MAX_FILE_LINES} lines only.\n")
        parts.append(f"\n```{lang}\n{content}\n```\n")

    for sub in node["dirs"]:
        parts.append(render_files_md(sub, depth + 1, root_path))

    return "\n".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

def generate_markdown(
    project_path: Path,
    include_hidden: bool = False,
    include_unknown: bool = False,
    diff_mode: bool = False,
    staged_only: bool = False,
    system_prompt: str = "",
    log_cb=None,
) -> str:
    """
    Scan *project_path* and return a complete Markdown string.
    """
    if log_cb is None:
        log_cb = lambda msg, tag="": None

    gitignore_patterns = load_gitignore_patterns(project_path)
    if gitignore_patterns:
        log_cb(f"📋  Loaded {len(gitignore_patterns)} rules from .gitignore", "info")

    now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    if diff_mode:
        log_cb("🔀  Git diff mode — scanning changed files only…", "info")
        changed = get_git_changed_files(project_path, staged_only)
        if changed is None:
            log_cb("⚠  Git diff unavailable here. Falling back to full scan.", "warn")
            diff_mode = False
        else:
            log_cb(f"✅  {len(changed)} changed file(s) found.", "ok")
            tree = build_diff_tree(
                changed,
                project_path,
                include_hidden,
                include_unknown,
                gitignore_patterns,
            )

    if not diff_mode:
        log_cb("🔍  Scanning project…", "info")
        counter = [0]
        tree = build_tree(
            project_path, include_hidden, include_unknown,
            log_cb, counter, gitignore_patterns, project_path,
        )

    n_files = count_files(tree)
    log_cb(f"✅  {n_files} files found.", "ok")
    log_cb("📝  Building Markdown…", "info")

    md: list[str] = []

    if system_prompt.strip():
        md.append(f"> 🤖 **AI Instruction:** {system_prompt.strip()}\n\n---\n")

    md.append(f"# 🗂️ Project Context: `{project_path.name}`\n")
    md.append("> **Generated by [mdcodebrief](https://github.com/pablokaua03/mdcodebrief)**  ")
    md.append(f"> Date: **{now}**  ")
    md.append(f"> Files: **{n_files}**\n")

    if diff_mode:
        md.append(f"> Mode: **Git diff{'  (staged)' if staged_only else ''}**\n")
        if n_files == 0:
            md.append("> Result: **No changed files matched the current filters**\n")

    md.append("\n---\n")
    md.append("## 🌳 Directory Tree\n```\n")
    md.append(render_tree_ascii(tree))
    md.append("\n```\n\n---\n")
    md.append("## 📂 File Contents\n")
    md.append(render_files_md(tree, depth=1, root_path=project_path))

    full_md = "\n".join(md)
    tokens = estimate_tokens(full_md)
    t_str  = token_label(tokens)
    log_cb(f"🧮  {t_str}", "info")

    full_md += f"\n\n---\n_Generated by **mdcodebrief {__version__}** · {now} · {t_str}_\n"
    return full_md
