"""contexta_app.engine.scoring: split out of context_engine.py. Bodies are unchanged."""

from __future__ import annotations

import re
from pathlib import Path

from contexta_app.engine.constants import (
    DOC_FILENAMES,
)
from contexta_app.engine.models import (
    FileInsight,
    ProjectFingerprint,
)
from contexta_app.engine.blobs import (
    has_embedded_asset_payload,
)
from contexta_app.engine.manifests import (
    identity_weight_for,
)
from contexta_app.engine.roles import (
    infer_file_role,
    summarize_doc_file,
    summarize_support_file,
)

def classify_file(item: FileInsight) -> set[str]:
    rel = item.relpath.as_posix().lower()
    stem = item.path.stem.lower()
    imports_tk = bool(re.search(r"^\s*(?:from\s+tkinter|import\s+tkinter)", item.content, re.MULTILINE))
    imports_argparse = bool(re.search(r"^\s*(?:from\s+argparse|import\s+argparse)", item.content, re.MULTILINE))
    imports_threading = bool(re.search(r"^\s*(?:from\s+threading|import\s+threading)", item.content, re.MULTILINE))
    imports_subprocess = bool(re.search(r"^\s*(?:from\s+subprocess|import\s+subprocess)", item.content, re.MULTILINE))
    tags: set[str] = set()

    if "test" in rel:
        tags.add("test")
    if stem == "__init__":
        tags.add("init")

    if "test" not in tags:
        if stem in {"ui", "window", "view"} or (imports_tk and stem not in {"theme"}):
            tags.add("ui")
        if stem == "cli" or imports_argparse:
            tags.add("cli")
        if imports_threading:
            tags.add("async")
        if stem in {"scanner", "renderer", "cli"} or imports_subprocess:
            tags.add("integration")
        if stem == "context_engine" or "def build_analysis(" in item.content or "class ProjectAnalysis" in item.content:
            tags.add("analysis")
        if stem == "renderer" or (stem not in {"context_engine"} and "def generate_markdown(" in item.content):
            tags.add("renderer")
        if stem == "scanner" or "def build_tree(" in item.content or "gitignore" in item.content.lower():
            tags.add("scanner")
        if stem == "theme" or ("toggle_theme" in item.content and "apply_theme" in item.content):
            tags.add("theme")
        if "config" in rel or item.path.suffix.lower() in {".json", ".yaml", ".yml", ".toml", ".ini"}:
            tags.add("config")

    if item.lang in {"markdown", "mdx", "rst"} or item.path.name.lower() in DOC_FILENAMES:
        tags.add("docs")
    if any(token in rel for token in ("assets/", "_assets", "brand_assets")):
        tags.add("assets")
    if has_embedded_asset_payload(item):
        tags.update({"assets", "embedded_asset"})
    if "test" not in tags and ("util" in rel or "helper" in rel):
        tags.add("utility")
    if "test" not in tags and ("__name__ == \"__main__\"" in item.content or stem in {"main", "app", "index", "server", "contexta"}):
        tags.add("entrypoint")

    return tags

def detect_entrypoints(insights: list[FileInsight]) -> list[FileInsight]:
    scored: list[tuple[int, FileInsight]] = []
    for item in insights:
        if "test" in item.tags:
            continue
        score = 0
        rel = item.relpath.as_posix().lower()
        if "entrypoint" in item.tags:
            score += 5
        if item.path.name.lower() in {"main.py", "app.py", "index.js", "manage.py", "server.py", "contexta.py"}:
            score += 4
        if rel.count("/") == 0:
            score += 1
        if score >= 4:
            scored.append((score, item))
    scored.sort(key=lambda pair: (-pair[0], pair[1].relpath.as_posix()))
    return [item for _, item in scored[:4]]

def score_file(
    item: FileInsight,
    entry_relpaths: set[str],
    changed_paths: set[Path],
    fingerprint: ProjectFingerprint,
) -> tuple[float, list[str]]:
    score = 1.0
    breakdown = ["+1 base"]
    rel = item.relpath.as_posix()
    depth = len(item.relpath.parts)
    depth_bonus = max(0.0, 2.0 - (depth * 0.25))
    if depth_bonus:
        score += depth_bonus
        breakdown.append(f"+{depth_bonus:.1f} shallow path")
    dependent_bonus = min(item.dependents * 1.4, 8.0)
    if dependent_bonus:
        score += dependent_bonus
        breakdown.append(f"+{dependent_bonus:.1f} dependents")
    import_bonus = min(len(item.local_imports) * 0.5, 4.0)
    if import_bonus:
        score += import_bonus
        breakdown.append(f"+{import_bonus:.1f} imports")
    size_bonus = min(item.line_count / 180.0, 4.0)
    if size_bonus:
        score += size_bonus
        breakdown.append(f"+{size_bonus:.1f} size")
    if rel in entry_relpaths:
        score += 6.0
        breakdown.append("+6.0 entrypoint")
    if item.resolved in changed_paths:
        score += 4.0
        breakdown.append("+4.0 changed file")
    if item.focus_score:
        score += item.focus_score
        breakdown.append(f"+{item.focus_score:.1f} focus match")
    identity_bonus, identity_label = identity_weight_for(item)
    if identity_bonus:
        score += identity_bonus
        breakdown.append(f"+{identity_bonus:.1f} {identity_label}")
    if "test" in item.tags:
        score += 1.0
        breakdown.append("+1.0 test coverage")
    if {"ui", "cli", "renderer", "scanner", "config"} & item.tags:
        score += 2.0
        breakdown.append("+2.0 key role")
    if "analysis" in item.tags or "theme" in item.tags:
        score += 1.0
        breakdown.append("+1.0 core logic")
    if "docs" in item.tags:
        score -= 1.5
        breakdown.append("-1.5 docs")
    if "embedded_asset" in item.tags:
        score -= 2.5
        breakdown.append("-2.5 embedded asset")
    if "init" in item.tags:
        score -= 1.5
        breakdown.append("-1.5 init")
    if fingerprint.project_type and rel.lower() in {"package.json", "composer.json", "requirements.txt", "pyproject.toml"}:
        score += 1.0
        breakdown.append("+1.0 stack-defining manifest")
    return round(score, 2), breakdown[:8]

def summarize_file(item: FileInsight, reverse_index: dict[str, set[str]], project_type: str | None = None) -> str:
    rel = item.relpath.as_posix()
    dependents = len(reverse_index.get(rel, set()))
    if "docs" in item.tags:
        return summarize_doc_file(item)
    inferred_role = infer_file_role(item, project_type)
    if inferred_role and inferred_role != "Contains application logic related to the selected context.":
        return inferred_role
    support_summary = summarize_support_file(item)
    if support_summary:
        return support_summary
    if "embedded_asset" in item.tags:
        return "Stores embedded binary-like asset payloads."
    if "test" in item.tags and "init" in item.tags:
        return "Marks the tests package for discovery and shared imports."
    if "init" in item.tags:
        return "Initializes the package namespace and shared module exports."
    if "entrypoint" in item.tags:
        return "Acts as a likely application entry point and routes the main execution flow."
    if "test" in item.tags:
        if item.path.stem.startswith("test_"):
            target = item.path.stem.removeprefix("test_").replace("_", " ")
            return f"Contains automated tests for {target} behavior."
        return "Contains supporting test helpers, fixtures, or test-only package setup."
    if "ui" in item.tags:
        return "Contains user-interface code."
    if "cli" in item.tags:
        return "Handles command-line arguments and execution flow."
    if "config" in item.tags:
        return "Holds configuration, metadata, or runtime settings used by other modules."
    if "utility" in item.tags:
        return "Provides shared helper utilities used across the codebase."

    summary_bits = []
    if item.functions:
        summary_bits.append(f"Defines {len(item.functions)} function(s)")
    if item.classes:
        summary_bits.append(f"{len(item.classes)} class(es)")
    if dependents:
        summary_bits.append(f"referenced by {dependents} other file(s)")
    if not summary_bits:
        summary_bits.append(inferred_role or "Contains supporting project logic")
    return ", ".join(summary_bits) + "."
