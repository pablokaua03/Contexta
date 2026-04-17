"""
context_engine.py - Project analysis and smart context selection for Contexta.
"""

from __future__ import annotations

import json
import re
import tomllib
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from pathlib import Path

from scanner import get_language, read_file_safe

APP_NAME = "Contexta"

CONTEXT_MODE_OPTIONS: dict[str, str] = {
    "full": "Full Context",
    "debug": "Debug Context",
    "feature": "Feature Context",
    "diff": "Diff Context",
    "onboarding": "Onboarding Context",
    "refactor": "Refactor Context",
}

AI_PROFILE_OPTIONS: dict[str, str] = {
    "generic": "Generic LLM",
    "chatgpt": "ChatGPT Mode",
    "claude": "Claude Mode",
    "gemini": "Gemini Mode",
    "copilot": "Copilot Mode",
}

TASK_PROFILE_OPTIONS: dict[str, str] = {
    "general": "General Context",
    "ai_handoff": "AI Handoff",
    "bug_report": "Bug Report Mode",
    "code_review": "Code Review Mode",
    "explain_project": "Explain This Project",
    "risk_analysis": "Risk Analysis",
    "refactor_request": "Refactor Request",
    "pr_summary": "PR Summary",
    "write_tests": "Write Tests",
    "find_dead_code": "Find Dead Code",
}

COMPRESSION_OPTIONS: dict[str, str] = {
    "full": "Full Content",
    "balanced": "Balanced Compression",
    "focused": "Focused Compression",
    "signatures": "Signatures Only",
}

PACK_OPTIONS: dict[str, str] = {
    "custom": "Custom Pack",
    "chatgpt": "ChatGPT Pack",
    "onboarding": "Onboarding Pack",
    "pr_review": "PR Review Pack",
    "risk_review": "Risk Review Pack",
    "debug": "Debug Pack",
    "backend": "Backend Pack",
    "frontend": "Frontend Pack",
    "changes_related": "Changes + Related",
}

PACK_DEFAULTS: dict[str, dict[str, str]] = {
    "chatgpt": {
        "ai_profile": "chatgpt",
        "context_mode": "full",
        "task_profile": "general",
        "compression": "balanced",
    },
    "onboarding": {
        "ai_profile": "generic",
        "context_mode": "onboarding",
        "task_profile": "explain_project",
        "compression": "balanced",
    },
    "pr_review": {
        "ai_profile": "claude",
        "context_mode": "diff",
        "task_profile": "code_review",
        "compression": "focused",
    },
    "risk_review": {
        "ai_profile": "generic",
        "context_mode": "debug",
        "task_profile": "risk_analysis",
        "compression": "focused",
    },
    "debug": {
        "ai_profile": "chatgpt",
        "context_mode": "debug",
        "task_profile": "bug_report",
        "compression": "focused",
    },
    "backend": {
        "ai_profile": "generic",
        "context_mode": "feature",
        "task_profile": "explain_project",
        "compression": "focused",
        "focus_query": "backend api server db service model repository",
    },
    "frontend": {
        "ai_profile": "generic",
        "context_mode": "feature",
        "task_profile": "explain_project",
        "compression": "focused",
        "focus_query": "frontend ui component page view screen style layout",
    },
    "changes_related": {
        "ai_profile": "claude",
        "context_mode": "debug",
        "task_profile": "code_review",
        "compression": "focused",
    },
}

MODEL_PROMPT_GUIDANCE: dict[str, dict[str, list[str] | str]] = {
    "generic": {
        "label": "Generic LLM",
        "summary": "Balanced default when the task and expected output are stated clearly.",
        "works_well": [
            "State the task and expected output format clearly.",
            "Keep instructions concise but precise.",
        ],
        "avoid": [
            "Vague goals with no definition of done.",
            "Overloading the prompt with unrelated asks.",
        ],
        "usage": [
            "Good default when you want balanced structure.",
            "Token and latency behavior vary a lot by provider and task.",
        ],
    },
    "chatgpt": {
        "label": "ChatGPT",
        "summary": "Works well with concise instructions, explicit deliverables, and optional short examples.",
        "works_well": [
            "Give a clear task, constraints, and final deliverable.",
            "Ask for a step-by-step explanation or reasoning summary when useful.",
        ],
        "avoid": [
            "Asking for hidden chain-of-thought.",
            "Mixing architecture questions and implementation requests without priority.",
        ],
        "usage": [
            "Likes explicit structure and concise instructions.",
            "Larger prompts can work, but visible output size and reasoning effort affect latency.",
        ],
    },
    "claude": {
        "label": "Claude",
        "summary": "Works well with structured requests, architecture context, and clearly scoped review goals.",
        "works_well": [
            "Give architecture context and a clearly scoped review or writing goal.",
            "Ask for organized sections with concrete recommendations.",
        ],
        "avoid": [
            "Broad prompts with no priority order.",
            "Asking for exhaustive output when a ranked answer would do.",
        ],
        "usage": [
            "Comfortable with richer context and structured analysis.",
            "Long prompts still benefit from a short task summary at the top.",
        ],
    },
    "gemini": {
        "label": "Gemini",
        "summary": "Works well with broader context plus explicit priorities so long inputs stay on task.",
        "works_well": [
            "Provide the project context plus explicit priorities.",
            "Tell it what to focus on before asking for conclusions.",
        ],
        "avoid": [
            "Assuming the largest context window means no prompt structure is needed.",
            "Mixing many unrelated tasks in one pass.",
        ],
        "usage": [
            "Comfortable with broader context packs.",
            "Latency and output quality still depend heavily on task shape.",
        ],
    },
    "copilot": {
        "label": "Copilot / Coding Agent",
        "summary": "Works well when files, constraints, and the expected end state are concrete and implementation-oriented.",
        "works_well": [
            "Specify the files, constraints, and expected final state.",
            "Ask for concrete code changes, tests, or a patch plan.",
        ],
        "avoid": [
            "High-level goals with no file or behavior target.",
            "Asking for hidden reasoning instead of a brief rationale.",
        ],
        "usage": [
            "Strong for implementation-first workflows.",
            "Benefits from smaller, well-scoped tasks and explicit acceptance criteria.",
        ],
    },
}

TASK_GUIDANCE: dict[str, str] = {
    "general": "Understand the project quickly and answer follow-up questions with accurate file references.",
    "ai_handoff": "Prepare a handoff-ready context pack that another AI can consume immediately with minimal extra prompting.",
    "bug_report": "Identify likely failure paths, root causes, and the smallest useful fix area.",
    "code_review": "Prioritize correctness risks, regressions, missing tests, and maintainability issues.",
    "explain_project": "Explain the architecture, main flows, and how the core modules fit together.",
    "risk_analysis": "Identify likely regression hotspots, broad-impact modules, missing coverage, and maintenance weak spots without treating them as confirmed defects.",
    "refactor_request": "Find central abstractions, coupling hotspots, and safe refactor seams.",
    "pr_summary": "Summarize the meaningful changes, impacted files, and any review concerns.",
    "write_tests": "Spot untested paths, likely edge cases, and the best modules to cover next.",
    "find_dead_code": "Look for low-signal modules, disconnected utilities, and code that appears unused.",
}

STOPWORDS = {
    "the", "and", "for", "with", "this", "that", "from", "into", "your", "what",
    "when", "where", "just", "more", "only", "have", "uses", "using", "mode",
    "pack", "project", "context", "code", "file", "files", "task", "request",
    "review", "write", "tests", "find", "debug", "feature", "refactor", "bug",
}

DOC_FILENAMES = {
    "readme",
    "readme.md",
    "readme.pt-br.md",
    "changelog.md",
    "contributing.md",
    "security.md",
    "license",
    "license.md",
}

TECH_LABELS = {
    "python": "Python",
    "javascript": "JavaScript",
    "jsx": "React JSX",
    "typescript": "TypeScript",
    "tsx": "React TSX",
    "php": "PHP",
    "html": "HTML",
    "css": "CSS",
    "scss": "SCSS",
    "vue": "Vue",
    "svelte": "Svelte",
    "json": "JSON config",
    "yaml": "YAML",
    "toml": "TOML",
    "powershell": "PowerShell",
    "bash": "Shell scripts",
    "markdown": "Markdown docs",
    "dockerfile": "Docker",
}

CODE_LANGUAGE_WEIGHTS = {
    "python": 1.4,
    "typescript": 1.3,
    "tsx": 1.3,
    "javascript": 1.2,
    "jsx": 1.2,
    "php": 1.2,
    "rust": 1.2,
    "go": 1.2,
    "csharp": 1.2,
    "java": 1.2,
    "css": 0.2,
    "scss": 0.2,
    "json": 0.15,
    "yaml": 0.15,
    "toml": 0.15,
    "xml": 0.15,
    "markdown": 0.0,
    "mdx": 0.0,
    "text": 0.0,
}

IDENTITY_FILE_WEIGHTS = {
    "package.json": (8.0, "package manifest"),
    "composer.json": (8.0, "package manifest"),
    "requirements.txt": (8.0, "dependency manifest"),
    "pyproject.toml": (8.0, "project manifest"),
    "cargo.toml": (8.0, "package manifest"),
    "go.mod": (8.0, "module manifest"),
    "pom.xml": (8.0, "build manifest"),
    "tsconfig.json": (6.0, "compiler config"),
    "dockerfile": (5.0, "container build"),
    ".env.example": (4.0, "environment template"),
    "readme.md": (3.0, "project overview"),
    "readme.pt-br.md": (3.0, "project overview"),
}

IDENTITY_SUFFIX_WEIGHTS = {
    ".csproj": (8.0, "project manifest"),
}

IDENTITY_PREFIX_WEIGHTS = {
    "next.config.": (6.5, "framework config"),
    "vite.config.": (6.0, "bundler config"),
    "tailwind.config.": (5.0, "styling config"),
}

PROJECT_TYPE_RULES = {
    "frontend_web_app": [
        ("has_next", 5),
        ("has_react", 4),
        ("has_tsx_pages", 4),
        ("has_components_dir", 3),
        ("has_tailwind", 2),
    ],
    "backend_api": [
        ("has_fastapi", 5),
        ("has_express", 4),
        ("has_routes_dir", 3),
        ("has_controllers", 2),
        ("has_db_models", 2),
    ],
    "php_crud_app": [
        ("has_php", 3),
        ("has_composer", 3),
        ("has_form_pages", 3),
        ("has_service_layer", 2),
        ("has_dao_layer", 3),
    ],
    "desktop_python_app": [
        ("has_python", 3),
        ("has_tkinter", 5),
        ("has_cli_entrypoint", 2),
        ("has_gui_module", 3),
    ],
}

PROJECT_TYPE_LABELS = {
    "frontend_web_app": "Frontend web application",
    "backend_api": "Backend API service",
    "php_crud_app": "PHP CRUD web application",
    "desktop_python_app": "Desktop GUI + CLI developer tool",
}

DOMAIN_HINTS = {
    "education": ["aluno", "alunos", "escola", "matricula", "matrícula", "professor", "turma", "student", "students", "school", "course"],
    "ecommerce": ["cart", "checkout", "product", "products", "catalog", "catalogo", "catálogo", "price", "pricing", "order"],
    "marketing_site": ["hero", "navbar", "footer", "cta", "landing", "testimonial", "marketing", "campaign", "banner"],
    "admin_panel": ["dashboard", "users", "settings", "reports", "admin", "management", "analytics"],
}

FRONTEND_PAGE_LANGS = {"tsx", "jsx", "vue", "svelte", "html", "php"}
ROUTE_STOPWORDS = {
    "app",
    "src",
    "pages",
    "page",
    "views",
    "view",
    "route",
    "routes",
    "index",
    "tsx",
    "jsx",
    "js",
    "ts",
    "php",
    "html",
}
ROUTE_ROLE_PATTERNS: list[tuple[set[str], str]] = [
    ({"contact", "contacto", "contato", "contacts"}, "Implements the contact page and user-facing contact form flow."),
    ({"product", "products", "producto", "productos", "catalog", "catalogo", "shop", "store"}, "Implements the product catalog or browsing page."),
    ({"course", "courses", "curso", "cursos", "academy"}, "Implements the courses listing and discovery page."),
    ({"faq", "help", "support", "ajuda", "soporte"}, "Implements the FAQ or help content page."),
    ({"register", "signup", "cadastro", "inscricao", "inscripcion"}, "Implements the user registration flow."),
    ({"login", "signin", "auth", "acceso", "entrar"}, "Implements the user sign-in and authentication flow."),
    ({"dashboard", "panel", "admin"}, "Implements the authenticated dashboard view."),
    ({"about", "company", "sobre"}, "Implements the about or company overview page."),
    ({"pricing", "plans", "planos", "precos", "precios"}, "Implements the pricing and plan comparison page."),
    ({"blog", "news", "articles", "posts"}, "Implements the blog or news listing page."),
    ({"profile", "account", "settings"}, "Implements the account or settings management view."),
    ({"checkout", "cart", "basket"}, "Implements the cart or checkout flow."),
]


@dataclass
class ExportConfig:
    include_hidden: bool = False
    include_unknown: bool = False
    diff_mode: bool = False
    staged_only: bool = False
    system_prompt: str = ""
    context_mode: str = "full"
    ai_profile: str = "generic"
    task_profile: str = "general"
    compression: str = "balanced"
    pack_profile: str = "custom"
    focus_query: str = ""


@dataclass
class FileInsight:
    path: Path
    relpath: Path
    lang: str | None
    content: str
    truncated: bool
    line_count: int
    rendered_line_count: int
    functions: list[str] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    local_imports: list[str] = field(default_factory=list)
    external_imports: list[str] = field(default_factory=list)
    tags: set[str] = field(default_factory=set)
    summary: str = ""
    score: float = 0.0
    score_breakdown: list[str] = field(default_factory=list)
    risk_score: float = 0.0
    risk_reasons: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    dependents: int = 0
    matched_focus: bool = False
    focus_score: float = 0.0
    selection_reasons: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.path.name


@dataclass
class ProjectFingerprint:
    primary_language: str | None
    frameworks: list[str]
    runtime: list[str]
    package_managers: list[str]
    build_tools: list[str]
    main_dependencies: list[str]
    scripts: list[str]
    project_type: str | None
    probable_purpose: str | None
    confidence: float
    evidence: list[str]
    evidence_sources: list[str] = field(default_factory=list)
    summary_evidence: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class RiskInsight:
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)


@dataclass
class FileSignals:
    has_react_context: bool = False
    has_translation_dict: bool = False
    has_tkinter: bool = False
    has_cli_args: bool = False
    has_require_once: bool = False
    has_service_class: bool = False
    has_dao_usage: bool = False
    has_next_page_export: bool = False
    has_form_handling: bool = False
    imports_firebase_auth: bool = False
    imports_next_navigation: bool = False
    raw_matches: list[str] = field(default_factory=list)


@dataclass
class ProjectAnalysis:
    config: ExportConfig
    all_files: list[FileInsight]
    selected_files: list[FileInsight]
    selected_paths: list[Path]
    changed_paths: set[Path]
    technologies: list[str]
    fingerprint: ProjectFingerprint
    entrypoints: list[FileInsight]
    important_files: list[FileInsight]
    architecture_lines: list[str]
    risks: list[str]
    relationships: list[str]
    folder_summaries: list[str]
    task_prompt: str
    likely_purpose: str
    summary_lines: list[str]
    diff_fallback_notice: str = ""


def resolve_config(config: ExportConfig) -> ExportConfig:
    resolved = replace(config)
    if resolved.pack_profile in PACK_DEFAULTS:
        for key, value in PACK_DEFAULTS[resolved.pack_profile].items():
            setattr(resolved, key, value)
    if resolved.diff_mode and resolved.context_mode == "full":
        resolved.context_mode = "diff"
    return resolved


def flatten_tree(node: dict) -> list[Path]:
    files = [item["path"] for item in node["files"]]
    for sub in node["dirs"]:
        files.extend(flatten_tree(sub))
    return files


def build_analysis(
    project_path: Path,
    full_tree: dict,
    changed_files: list[Path] | None,
    config: ExportConfig,
    log_cb=None,
) -> ProjectAnalysis:
    if log_cb is None:
        log_cb = lambda msg, tag="": None

    config = resolve_config(config)
    file_paths = flatten_tree(full_tree)
    insights = [make_file_insight(project_path, path) for path in file_paths]
    module_map = build_module_map(insights)
    rel_index, reverse_index = resolve_local_relationships(insights, module_map)
    changed_set = {path.resolve() for path in changed_files or []}

    for insight in insights:
        insight.local_imports = sorted(rel_index[insight.relpath.as_posix()])
        insight.dependents = len(reverse_index[insight.relpath.as_posix()])
        insight.focus_score = compute_focus_score(insight, config.focus_query or config.system_prompt)
        insight.matched_focus = insight.focus_score > 0
        insight.tags.update(classify_file(insight))

    entrypoints = detect_entrypoints(insights)
    entry_relpaths = {item.relpath.as_posix() for item in entrypoints}
    fingerprint = detect_project_fingerprint(project_path, insights, entrypoints)

    for insight in insights:
        insight.score, insight.score_breakdown = score_file(insight, entry_relpaths, changed_set, fingerprint)
        insight.summary = summarize_file(insight, reverse_index, fingerprint.project_type)
        risk = compute_risk_score(insight, insights, changed_set, reverse_index, fingerprint)
        insight.risk_score = risk.score
        insight.risk_reasons = risk.reasons
        insight.risk_flags = risk.risk_flags

    important_candidates = [item for item in insights if "test" not in item.tags and "docs" not in item.tags]
    important_files = sorted(important_candidates or insights, key=lambda item: (-item.score, item.relpath.as_posix()))[:8]
    selected_files = select_files(insights, config, changed_set, reverse_index)
    diff_fallback_notice = ""
    if config.context_mode == "diff" and not selected_files:
        selected_files = select_diff_fallback_files(insights, {item.relpath.as_posix(): item for item in insights}, reverse_index, [item for item in insights if "test" in item.tags])
        if changed_set:
            diff_fallback_notice = "No changed files matched the current filters, so Contexta fell back to central files and nearby tests."
        else:
            diff_fallback_notice = "No valid changed files were detected, so Contexta fell back to central files and nearby tests."
    selected_paths = [item.path for item in selected_files]
    technologies = detect_supporting_technologies(insights, fingerprint)
    quality_signals = detect_quality_signals(insights)
    likely_purpose = fingerprint.probable_purpose or "Organize project structure and expose the most relevant code paths for developer workflows."
    architecture = build_architecture_overview(project_path, insights, entrypoints, technologies, fingerprint, quality_signals)
    risk_source = insights if config.context_mode == "full" else selected_files
    risks = build_risks(risk_source, reverse_index, insights, fingerprint)
    relationships = build_relationship_map(selected_files, reverse_index)
    folder_summaries = build_folder_summaries(selected_files)
    task_prompt = build_task_prompt(project_path, config)
    summary_lines = build_summary_lines(
        project_path,
        selected_files,
        entrypoints,
        important_files,
        technologies,
        fingerprint,
        quality_signals,
    )

    for item in selected_files:
        item.selection_reasons = infer_selection_reasons(
            item,
            selected_files,
            config,
            changed_set,
            reverse_index,
            diff_fallback=bool(diff_fallback_notice),
        )

    log_cb(f"Insight layer ready: {len(selected_files)} curated file(s) selected.", "ok")

    return ProjectAnalysis(
        config=config,
        all_files=insights,
        selected_files=selected_files,
        selected_paths=selected_paths,
        changed_paths=changed_set,
        technologies=technologies,
        fingerprint=fingerprint,
        entrypoints=entrypoints,
        important_files=important_files,
        architecture_lines=architecture,
        risks=risks,
        relationships=relationships,
        folder_summaries=folder_summaries,
        task_prompt=task_prompt,
        likely_purpose=likely_purpose,
        summary_lines=summary_lines,
        diff_fallback_notice=diff_fallback_notice,
    )


def make_file_insight(project_path: Path, path: Path) -> FileInsight:
    content, truncated, total_line_count = read_file_safe(path)
    lang = get_language(path)
    functions, classes, imports = extract_symbols(content, lang)
    external_imports = [item for item in imports if not item.startswith(".")]
    return FileInsight(
        path=path,
        relpath=path.relative_to(project_path),
        lang=lang,
        content=content,
        truncated=truncated,
        line_count=total_line_count,
        rendered_line_count=len(content.splitlines()),
        functions=functions,
        classes=classes,
        imports=imports,
        external_imports=external_imports,
    )


def extract_symbols(content: str, lang: str | None) -> tuple[list[str], list[str], list[str]]:
    if lang == "python":
        functions = re.findall(r"^\s*(?:async\s+def|def)\s+([A-Za-z_]\w*)", content, re.MULTILINE)
        classes = re.findall(r"^\s*class\s+([A-Za-z_]\w*)", content, re.MULTILINE)
        imports = []
        imports.extend(re.findall(r"^\s*import\s+([A-Za-z0-9_\.]+)", content, re.MULTILINE))
        imports.extend(re.findall(r"^\s*from\s+([A-Za-z0-9_\.]+|\.+[A-Za-z0-9_\.]*)\s+import", content, re.MULTILINE))
        return functions[:12], classes[:8], imports[:24]

    if lang in {"javascript", "jsx", "typescript", "tsx"}:
        functions = re.findall(r"(?:function|const|let|var)\s+([A-Za-z_]\w*)", content)
        classes = re.findall(r"class\s+([A-Za-z_]\w*)", content)
        imports = re.findall(r"""from\s+['"]([^'"]+)['"]|require\(\s*['"]([^'"]+)['"]\s*\)""", content)
        flat_imports = [left or right for left, right in imports]
        return functions[:12], classes[:8], flat_imports[:24]

    if lang == "php":
        functions = re.findall(r"function\s+([A-Za-z_]\w*)", content, re.IGNORECASE)
        classes = re.findall(r"class\s+([A-Za-z_]\w*)", content, re.IGNORECASE)
        imports = []
        imports.extend(
            re.findall(r"""(?:require|require_once|include|include_once)\s*(?:\(|)\s*['"]([^'"]+)['"]""", content, re.IGNORECASE)
        )
        imports.extend(re.findall(r"^\s*use\s+([A-Za-z0-9_\\\\]+)", content, re.MULTILINE))
        return functions[:12], classes[:8], imports[:24]

    return [], [], []


def build_module_map(insights: list[FileInsight]) -> dict[str, str]:
    module_map: dict[str, str] = {}
    for item in insights:
        parts = list(item.relpath.with_suffix("").parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        if not parts:
            continue
        dotted = ".".join(parts)
        module_map[dotted] = item.relpath.as_posix()
        path_like = "/".join(parts)
        module_map[path_like.lower()] = item.relpath.as_posix()
        if len(parts) == 1:
            module_map.setdefault(parts[0], item.relpath.as_posix())
        stem = item.path.stem.lower()
        module_map.setdefault(stem, item.relpath.as_posix())
        module_map.setdefault(item.path.name.lower(), item.relpath.as_posix())
    return module_map


def resolve_local_relationships(
    insights: list[FileInsight],
    module_map: dict[str, str],
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    rel_index: dict[str, set[str]] = defaultdict(set)
    reverse_index: dict[str, set[str]] = defaultdict(set)

    for item in insights:
        for imported in item.imports:
            target = resolve_local_import(item, imported, module_map)
            if not target or target == item.relpath.as_posix():
                continue
            rel_index[item.relpath.as_posix()].add(target)
            reverse_index[target].add(item.relpath.as_posix())

        related_tests = resolve_related_tests(item, insights)
        for test_rel in related_tests:
            reverse_index[item.relpath.as_posix()].add(test_rel)

    return rel_index, reverse_index


def resolve_local_import(item: FileInsight, imported: str, module_map: dict[str, str]) -> str | None:
    if item.lang == "python":
        if imported.startswith("."):
            base_parts = list(item.relpath.parent.parts)
            dots = len(imported) - len(imported.lstrip("."))
            tail = imported.lstrip(".")
            if dots <= len(base_parts):
                base_parts = base_parts[: len(base_parts) - dots + 1]
            else:
                base_parts = []
            if tail:
                base_parts.extend(tail.split("."))
            dotted = ".".join(part for part in base_parts if part)
            return module_map.get(dotted)
        return module_map.get(imported) or module_map.get(imported.split(".")[-1])
    if item.lang in {"javascript", "jsx", "typescript", "tsx"}:
        normalized = imported.strip().replace("\\", "/").lower()
        if not normalized:
            return None
        normalized = normalized.removeprefix("@/")
        normalized = normalized.removeprefix("./")
        if normalized.startswith("../"):
            base_parts = list(item.relpath.parent.parts)
            while normalized.startswith("../"):
                normalized = normalized[3:]
                if base_parts:
                    base_parts.pop()
            joined = "/".join(part.lower() for part in base_parts if part)
            normalized = f"{joined}/{normalized}" if joined else normalized
        candidates = [normalized.rstrip("/")]
        stem_candidate = candidates[0].rsplit("/", 1)[-1]
        candidates.extend(
            [
                f"{candidates[0]}/page",
                f"{candidates[0]}/index",
                stem_candidate,
                f"{stem_candidate}.tsx",
                f"{stem_candidate}.ts",
                f"{stem_candidate}.jsx",
                f"{stem_candidate}.js",
            ]
        )
        for candidate in candidates:
            target = module_map.get(candidate)
            if target:
                return target
        for key, target in module_map.items():
            if key.endswith(candidates[0]) or key.endswith(stem_candidate):
                return target
        return None
    if item.lang == "php":
        normalized = imported.strip().replace("\\", "/").lower()
        if not normalized:
            return None
        normalized = normalized.removeprefix("./")
        base_parts = list(item.relpath.parent.parts)
        while normalized.startswith("../"):
            normalized = normalized[3:]
            if base_parts:
                base_parts.pop()
        joined = "/".join(part.lower() for part in base_parts if part)
        if joined and "/" not in normalized and not normalized.endswith(".php"):
            candidates = [normalized, f"{normalized}.php"]
        else:
            combined = f"{joined}/{normalized}" if joined and "/" not in normalized else normalized
            candidates = [combined]
            if not combined.endswith(".php"):
                candidates.append(f"{combined}.php")
        candidates.extend([Path(candidate).stem.lower() for candidate in candidates])
        for candidate in candidates:
            target = module_map.get(candidate)
            if target:
                return target
        for key, target in module_map.items():
            if any(key.endswith(candidate) for candidate in candidates):
                return target
        return None
    return None


def resolve_related_tests(item: FileInsight, insights: list[FileInsight]) -> set[str]:
    related: set[str] = set()
    for candidate in insights:
        if is_related_test_for(item, candidate):
            related.add(candidate.relpath.as_posix())
    return related


def matches_focus(item: FileInsight, query: str) -> bool:
    return compute_focus_score(item, query) > 0


def compute_focus_score(item: FileInsight, query: str) -> float:
    keywords = extract_keywords(query)
    if not keywords:
        return 0.0

    score = 0.0
    rel = item.relpath.as_posix().lower()
    stem = item.path.stem.lower()
    imports_blob = " ".join(imported.lower() for imported in item.imports)
    functions_blob = " ".join(func.lower() for func in item.functions)
    classes_blob = " ".join(cls.lower() for cls in item.classes)
    content_lower = item.content.lower()

    for keyword in keywords:
        if keyword == stem or keyword in rel:
            score += 2.0
        if keyword in functions_blob or keyword in classes_blob:
            score += 1.8
        if keyword in imports_blob:
            score += 1.4
        if re.search(rf"\b{re.escape(keyword)}\b", content_lower):
            score += 0.8
        elif keyword in content_lower:
            score += 0.4

    return round(min(score, 6.0), 2)


def extract_keywords(text: str) -> list[str]:
    parts = re.findall(r"[A-Za-z0-9_/-]+", text.lower())
    keywords = [part for part in parts if len(part) > 2 and part not in STOPWORDS]
    return list(dict.fromkeys(keywords[:10]))


def _strip_wrapping_quotes(text: str) -> str:
    stripped = text.strip().strip(",")
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {"'", '"'}:
        return stripped[1:-1]
    if len(stripped) >= 3 and stripped[0] == "b" and stripped[1] in {"'", '"'} and stripped[1] == stripped[-1]:
        return stripped[2:-1]
    return stripped


def is_blob_like_line(line: str) -> bool:
    candidate = line.strip().strip(",")
    if "=" in candidate:
        _prefix, _sep, suffix = candidate.partition("=")
        candidate = suffix.strip()
    candidate = _strip_wrapping_quotes(candidate)
    if len(candidate) < 96:
        return False
    if re.search(r"\s", candidate):
        return False
    cleaned = candidate
    allowed = re.sub(r"[^A-Za-z0-9+/=_-]", "", cleaned)
    if len(allowed) < 96:
        return False
    density = len(allowed) / max(len(cleaned), 1)
    if density < 0.97:
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9+/=_-]+", allowed))


def has_embedded_asset_payload(item: FileInsight) -> bool:
    if item.lang in {"markdown", "mdx", "rst"}:
        return False
    rel = item.relpath.as_posix().lower()
    blob_lines = sum(1 for line in item.content.splitlines() if is_blob_like_line(line))
    asset_signal = any(token in rel for token in ("asset", "icon", "logo", "brand"))
    base64_signal = bool(re.search(r"\b[A-Z][A-Z0-9_]*B64\b|\bbase64\b", item.content))
    assignment_signal = bool(re.search(r"^\s*[A-Z][A-Z0-9_]{2,}\s*=\s*\(?\s*$", item.content, re.MULTILINE))
    return blob_lines >= 8 and (asset_signal or base64_signal or assignment_signal)


def should_sanitize_blob_excerpt(item: FileInsight) -> bool:
    if "embedded_asset" in item.tags:
        return True
    rel = item.relpath.as_posix().lower()
    if any(token in rel for token in ("asset", "icon", "logo", "brand")):
        return True
    if re.search(r"\b[A-Z][A-Z0-9_]*B64\b|\bbase64\b", item.content):
        return True
    return False


def is_named_test_for(item: FileInsight, candidate: FileInsight) -> bool:
    rel = candidate.relpath.as_posix().lower()
    if "test" not in rel:
        return False

    target = item.path.stem.lower()
    cand = candidate.path.stem.lower()
    if cand == f"test_{target}" or cand == f"{target}_test":
        return True
    if cand.startswith("test_") and cand.endswith(f"_{target}"):
        return True
    return False


def test_relation_score(item: FileInsight, candidate: FileInsight) -> int:
    rel = candidate.relpath.as_posix().lower()
    if "test" not in rel:
        return 0

    score = 0
    if is_named_test_for(item, candidate):
        score += 4

    item_stem = item.path.stem.lower()
    item_module = ".".join(item.relpath.with_suffix("").parts).lower()
    imports_lower = [imported.lower() for imported in candidate.imports]
    if any(
        imported == item_stem
        or imported == item_module
        or imported.endswith(f".{item_stem}")
        or item_module.endswith(imported)
        for imported in imports_lower
    ):
        score += 2

    symbol_names = [name for name in item.functions[:6] + item.classes[:4] if len(name) >= 4]
    mention_hits = sum(
        1
        for name in symbol_names
        if re.search(rf"\b{re.escape(name.lower())}\b", candidate.content.lower())
    )
    if mention_hits >= 2:
        score += 2
    elif mention_hits == 1:
        score += 1

    parent_name = item.relpath.parent.name.lower()
    if parent_name and parent_name != "." and parent_name in rel:
        score += 1

    return score


def is_related_test_for(item: FileInsight, candidate: FileInsight) -> bool:
    return test_relation_score(item, candidate) >= 4


def is_explicit_test_cover(item: FileInsight, candidate: FileInsight) -> bool:
    if not is_named_test_for(item, candidate):
        cand = candidate.path.stem.lower()
        target = item.path.stem.lower()
        if not (cand.startswith("test_") and target in cand):
            return False
    return test_relation_score(item, candidate) >= 4


def summarize_doc_file(item: FileInsight) -> str:
    name = item.path.name.lower()
    if name.startswith("readme"):
        return "Introduces the project, installation steps, and everyday usage."
    if name == "changelog.md":
        return "Tracks notable releases and user-visible changes across versions."
    if name == "contributing.md":
        return "Explains how contributors can work on the project safely and consistently."
    if name == "security.md":
        return "Describes security expectations, reporting, and support policy."
    if name.startswith("license"):
        return "Records the repository license terms and redistribution rules."
    return "Provides project documentation, release notes, or policy guidance."


def summarize_support_file(item: FileInsight) -> str | None:
    name = item.path.name.lower()
    rel = item.relpath.as_posix().lower()

    if name == "requirements.txt":
        return "Documents Python runtime, packaging, and test-time dependency expectations."
    if name == "version_info.txt":
        return "Defines Windows version metadata used in packaged executable builds."
    if name == "build.bat":
        return "Automates Windows executable packaging through PyInstaller build steps."
    if name == "build.sh":
        return "Automates Unix-like executable packaging through PyInstaller build steps."
    if name.endswith(".spec") and "pyinstaller" in item.content.lower():
        return "Defines the PyInstaller build spec used to package the desktop application."
    if name == "contexta.py":
        return "Acts as the main entrypoint that routes execution into the GUI or CLI flow."
    if name == "mdcodebrief.py":
        return "Legacy compatibility shim that forwards execution to contexta.main()."
    if name == "cli.py":
        return "Parses CLI flags, invokes pack generation, and handles file output or clipboard copy."
    if name == "ui.py":
        return "Implements the desktop interface, preview controls, and export workflow orchestration."
    if name == "theme.py":
        return "Defines theme palettes and repaint helpers for dark/light interface rendering."
    if name == "utils.py":
        return "Provides small desktop-path and filename helpers used by the app entry points."
    if rel.startswith("tests/") and name.startswith("test_"):
        target = item.path.stem.removeprefix("test_").replace("_", " ")
        return f"Exercises {target} behavior with focused automated checks."
    return None


def extract_route_tokens(rel: str) -> list[str]:
    tokens = re.findall(r"[A-Za-zÀ-ÿ0-9]+", rel.lower())
    filtered: list[str] = []
    for token in tokens:
        if token in ROUTE_STOPWORDS or token.isdigit():
            continue
        filtered.append(token)
    return filtered


def humanize_route_tokens(tokens: list[str]) -> str:
    if not tokens:
        return ""
    cleaned: list[str] = []
    for token in tokens:
        token = token.strip("-_")
        if not token or token in cleaned:
            continue
        cleaned.append(token.replace("-", " ").replace("_", " "))
    return " ".join(cleaned[:3])


def infer_page_role(item: FileInsight) -> str | None:
    rel = item.relpath.as_posix().lower()
    content_lower = item.content.lower()
    is_page_entry = (
        "/app/page." in rel
        or rel.endswith(("/page.tsx", "/page.jsx", "/page.vue", "/page.svelte"))
        or "/pages/" in rel
        or "/views/" in rel
        or item.path.name.lower() == "index.php"
    )
    if not is_page_entry:
        return None

    route_tokens = extract_route_tokens(rel)
    token_set = set(route_tokens)
    has_form_flow = (
        "<form" in content_lower
        or "useform" in content_lower
        or "form" in item.path.stem.lower()
        or "textarea" in content_lower
    )

    for hints, description in ROUTE_ROLE_PATTERNS:
        if token_set & hints:
            if description.endswith("contact form flow.") and not has_form_flow:
                return "Implements the contact page and user-facing outreach flow."
            return description

    is_root_page = rel.endswith("app/page.tsx") or rel.endswith("app/page.jsx") or item.path.name.lower() == "index.php"
    marketing_clues = ("hero", "navbar", "footer", "cta", "testimonial", "marketing", "landing")
    if is_root_page:
        if any(clue in content_lower for clue in marketing_clues):
            return "Implements the main landing page and composes the core marketing sections."
        return "Implements the main landing page or primary user-facing entry flow."

    route_label = humanize_route_tokens(route_tokens)
    if route_label:
        return f"Implements the routed {route_label} page within the application."
    return "Acts as a user-facing page entry within the application."


def infer_component_role(item: FileInsight) -> str | None:
    rel = item.relpath.as_posix().lower()
    stem = item.path.stem.lower()
    content_lower = item.content.lower()
    is_frontend_component = item.lang in {"tsx", "jsx", "vue", "svelte"}

    if stem == "layout" or rel.endswith("/layout.tsx") or rel.endswith("/layout.jsx"):
        return "Defines the shared application layout and page chrome for routed screens."
    if "localecontext" in stem or ((("locale" in stem) or ("locale" in content_lower)) and "createcontext" in content_lower):
        return "Provides locale state and translation hooks used across the app."
    if "translation" in stem or "translations" in stem or "i18n" in stem or "/translations/" in rel or "/locales/" in rel:
        return "Defines localization strings and locale-aware content used across the app."
    if ("navbar" in stem or stem in {"nav", "navigation", "header"} or "<nav" in content_lower) and is_frontend_component:
        return "Defines the primary navigation/header component used across user-facing pages."
    if "footer" in stem or "<footer" in content_lower:
        return "Defines the shared footer content used across user-facing pages."
    if "hero" in stem:
        return "Defines the hero section that frames the main marketing message."
    if "provider" in stem and "context" in content_lower:
        return "Provides shared application context and state to descendant components."
    if "/components/" in rel and is_frontend_component:
        if "card" in stem:
            return "Defines a reusable card-style UI building block for frontend screens."
        if "modal" in stem or "dialog" in stem:
            return "Defines a reusable modal or dialog component for focused user interactions."
        return "Defines a reusable UI component used across frontend screens."
    return None


def infer_file_role(item: FileInsight) -> str | None:
    name = item.path.name.lower()
    rel = item.relpath.as_posix().lower()
    content_lower = item.content.lower()

    if name in {"package.json", "composer.json", "pyproject.toml", "cargo.toml", "go.mod", "pom.xml"} or name.endswith(".csproj"):
        return "Declares project dependencies and package metadata."
    if name.startswith("next.config.") or name.startswith("vite.config.") or name == "tsconfig.json":
        return "Defines framework build and runtime configuration."
    component_role = infer_component_role(item)
    if component_role:
        return component_role
    if name.endswith(".css") or name.endswith(".scss") or name.endswith(".sass") or name.endswith(".less"):
        return "Defines the visual styling for the user interface."
    if "service" in name or "/services/" in rel:
        return "Implements service-layer logic that coordinates domain operations."
    if "dao" in name or "repository" in name or "/repositories/" in rel or "/dao/" in rel:
        return "Handles persistence and data access operations."
    page_role = infer_page_role(item)
    if page_role:
        return page_role
    if "form" in name or ("<form" in content_lower and item.lang in {"html", "php", "jsx", "tsx"}):
        return "Implements the create/edit form flow for a domain entity."
    if "/components/" in rel and item.lang in {"tsx", "jsx", "vue", "svelte"}:
        return "Defines a reusable UI component used across frontend screens."
    if "/pages/" in rel or "/views/" in rel:
        return "Implements a user-facing page or routed screen in the application."
    return None


def is_test_file(path: Path) -> bool:
    rel = path.as_posix().lower()
    name = path.name.lower()
    return (
        rel.startswith("tests/")
        or "/tests/" in rel
        or name.startswith("test_")
        or name.endswith("_test.py")
        or name.endswith(".spec.ts")
        or name.endswith(".spec.tsx")
        or name.endswith(".test.ts")
        or name.endswith(".test.tsx")
        or name.endswith(".test.js")
        or name.endswith(".test.jsx")
    )


def collect_file_signals(item: FileInsight) -> FileSignals:
    rel = item.relpath.as_posix().lower()
    content_lower = item.content.lower()
    signals = FileSignals()

    if "createcontext" in content_lower or "usecontext" in content_lower:
        signals.has_react_context = True
        signals.raw_matches.append("react_context")
    if (
        "translations" in content_lower
        or "translation" in content_lower
        or "dictionary" in content_lower
        or "uselocale" in content_lower
        or "usetranslations" in content_lower
        or "/locales/" in rel
        or "/translations/" in rel
    ):
        signals.has_translation_dict = True
        signals.raw_matches.append("translations")
    if "tkinter" in content_lower:
        signals.has_tkinter = True
        signals.raw_matches.append("tkinter")
    if "sys.argv" in content_lower or "argparse" in content_lower:
        signals.has_cli_args = True
        signals.raw_matches.append("cli_args")
    if "require_once" in content_lower or "include_once" in content_lower:
        signals.has_require_once = True
        signals.raw_matches.append("php_require_once")
    if "service" in item.path.stem.lower() or re.search(r"class\s+[a-z0-9_]*service", content_lower):
        signals.has_service_class = True
        signals.raw_matches.append("service_class")
    if (
        "dao" in item.path.stem.lower()
        or "repository" in item.path.stem.lower()
        or "repository" in content_lower
        or "dao" in content_lower
    ):
        signals.has_dao_usage = True
        signals.raw_matches.append("dao_usage")
    if "export default function" in content_lower and rel.endswith(("/page.tsx", "/page.jsx")):
        signals.has_next_page_export = True
        signals.raw_matches.append("next_page")
    if (
        "<form" in content_lower
        or "onsubmit" in content_lower
        or "handlechange" in content_lower
        or "useform" in content_lower
        or "textarea" in content_lower
    ):
        signals.has_form_handling = True
        signals.raw_matches.append("form_handling")
    if "firebase/auth" in content_lower:
        signals.imports_firebase_auth = True
        signals.raw_matches.append("firebase_auth")
    if "next/navigation" in content_lower:
        signals.imports_next_navigation = True
        signals.raw_matches.append("next_navigation")
    return signals


def infer_exact_name_role(item: FileInsight) -> str | None:
    name = item.path.name.lower()
    exact_name_roles = {
        "context_engine.py": "Implements project analysis, scoring, and smart context selection.",
        "renderer.py": "Formats selected analysis into the final context pack output.",
        "scanner.py": "Scans the project tree, applies filters, and reads safe text content.",
        "ui.py": "Implements the desktop GUI and export workflow orchestration.",
        "cli.py": "Implements the command-line workflow for pack generation and output.",
        "theme.py": "Defines GUI theme palettes and widget repaint behavior.",
        "contexta.py": "Acts as the main entrypoint that routes execution into the GUI or CLI flow.",
        "mdcodebrief.py": "Legacy compatibility shim that forwards execution to contexta.main().",
        "utils.py": "Provides small desktop-path and filename helpers used by the app entry points.",
        "package.json": "Declares project dependencies and package metadata.",
        "composer.json": "Declares project dependencies and package metadata.",
        "pyproject.toml": "Declares project dependencies and package metadata.",
        "cargo.toml": "Declares project dependencies and package metadata.",
        "go.mod": "Declares project dependencies and package metadata.",
        "pom.xml": "Declares project dependencies and package metadata.",
        "tsconfig.json": "Defines TypeScript compiler options and project path aliases.",
        "requirements.txt": "Documents Python runtime, packaging, and test-time dependency expectations.",
        "build.bat": "Automates Windows executable packaging through PyInstaller build steps.",
        "build.sh": "Automates Unix-like executable packaging through PyInstaller build steps.",
        "version_info.txt": "Defines Windows version metadata used in packaged executable builds.",
    }
    if name in exact_name_roles:
        return exact_name_roles[name]
    if name.endswith(".spec") and "pyinstaller" in item.content.lower():
        return "Defines the PyInstaller build spec used to package the desktop application."
    if name.startswith("next.config."):
        return "Defines Next.js build and runtime configuration."
    if name.startswith("vite.config."):
        return "Defines Vite build and runtime configuration."
    return None


def infer_frontend_support_role(item: FileInsight, signals: FileSignals) -> str | None:
    name = item.path.name.lower()
    stem = item.path.stem.lower()
    rel = item.relpath.as_posix().lower()
    is_frontend_component = item.lang in {"tsx", "jsx", "vue", "svelte"}

    if stem == "layout" or rel.endswith("/layout.tsx") or rel.endswith("/layout.jsx"):
        return "Defines the shared application layout and page chrome for routed screens."
    if ("localecontext" in stem or (("locale" in stem or "/locale" in rel or "/i18n" in rel) and signals.has_react_context)) and signals.has_translation_dict:
        return "Provides locale state and translation hooks used across the app."
    if "authcontext" in stem or (("auth" in stem or "/auth/" in rel) and signals.has_react_context):
        return "Provides authentication state and auth-related helpers used across the app."
    if "translations" in stem or "translation" in stem or "i18n" in stem or "/translations/" in rel or "/locales/" in rel:
        return "Defines localization strings and locale-aware content used across the app."
    if ("navbar" in stem or stem in {"nav", "navigation", "header"}) and is_frontend_component:
        return "Defines the primary navigation/header component used across user-facing pages."
    if "foot" in stem and is_frontend_component:
        return "Defines the shared footer content used across user-facing pages."
    if "toggle" in stem and "locale" in stem:
        return "Defines the locale-switching UI control used across localized pages."
    if "hero" in stem:
        return "Defines the hero section that frames the main marketing message."
    if "provider" in stem and signals.has_react_context:
        return "Provides shared application context and state to descendant components."
    if "/app/components/" in rel or "/components/" in rel:
        if "card" in stem:
            return "Defines a reusable card-style UI building block for frontend screens."
        if "modal" in stem or "dialog" in stem:
            return "Defines a reusable modal or dialog component for focused user interactions."
        if is_frontend_component:
            return "Defines a reusable UI component used across frontend screens."
    return None


def infer_entrypoint_role(item: FileInsight, project_type: str | None) -> str | None:
    rel = item.relpath.as_posix().lower()
    content_lower = item.content.lower()
    listing_signals = ("listar", "table", "cadastro", "alunos", "students", "records", "dashboard")

    if rel.endswith("/index.php") or item.path.name.lower() == "index.php":
        if project_type == "PHP CRUD web application":
            if any(signal in content_lower for signal in listing_signals):
                return "Implements the main listing page and primary user-facing entry flow."
            return "Implements the main user-facing entry flow."
        if project_type == "Frontend web application":
            return "Implements the main landing page and primary user-facing entry flow."
        return "Acts as the top-level entry point for the application flow."

    is_root_frontend_page = rel.endswith("app/page.tsx") or rel.endswith("app/page.jsx")
    if is_root_frontend_page:
        marketing_clues = ("hero", "navbar", "footer", "cta", "testimonial", "marketing", "landing")
        if any(clue in content_lower for clue in marketing_clues):
            return "Implements the main landing page and composes the core marketing sections."
        if project_type == "Frontend web application" or item.lang in {"tsx", "jsx", "vue", "svelte"}:
            return "Implements the main landing page and primary user-facing entry flow."
    return None


def infer_nextjs_page_role(item: FileInsight) -> str | None:
    rel = item.relpath.as_posix().lower()
    if not rel.endswith(("/page.tsx", "/page.jsx")):
        return None
    if "/contacto/" in rel or "/contact/" in rel or "/contato/" in rel:
        return "Implements the contact page and user-facing contact form flow."
    if "/productos/" in rel or "/products/" in rel or "/produto/" in rel or "/produtos/" in rel:
        return "Implements the product catalog and browsing page."
    if "/cursos/" in rel or "/courses/" in rel:
        return "Implements the courses listing and discovery page."
    if "/faq/" in rel:
        return "Implements the FAQ and user help page."
    if "/dashboard/" in rel:
        return "Implements the authenticated dashboard view."
    if "/register/" in rel or "/signup/" in rel:
        return "Implements the user registration flow."
    if rel.endswith("/app/page.tsx") or rel.endswith("/app/page.jsx"):
        return "Implements the main landing page and primary user-facing entry flow."
    return "Implements a user-facing route in the application."


def infer_path_role(item: FileInsight) -> str | None:
    name = item.path.name.lower()
    stem = item.path.stem.lower()
    rel = item.relpath.as_posix().lower()
    content_lower = item.content.lower()

    if name.endswith(".css") or name.endswith(".scss") or name.endswith(".sass") or name.endswith(".less"):
        return "Defines the visual styling for the user interface."
    if name == "bootstrap.php" or "/bootstrap" in rel:
        return "Initializes shared runtime setup, configuration wiring, and application bootstrap."
    if "service" in name or "/services/" in rel:
        return "Implements service-layer logic that coordinates domain operations."
    if "dao" in name or "repository" in name or "/repositories/" in rel or "/dao/" in rel:
        return "Handles persistence and data access operations."
    if item.lang == "php" and stem in {"save", "salvar", "store", "submit"}:
        return "Handles form submission and record persistence for the user-facing flow."
    if "form" in name or ("<form" in content_lower and item.lang in {"html", "php", "jsx", "tsx"}):
        return "Implements the create/edit form flow for a domain entity."
    if item.lang == "php" and re.search(r"class\s+[A-Z][A-Za-z0-9_]+", item.content):
        compact = re.sub(r"\s+", "", item.content)
        if f"class{item.path.stem}".lower() in compact.lower() and "service" not in stem and "dao" not in stem and "repository" not in stem:
            return "Defines a domain model or entity used across CRUD flows."
    if "/pages/" in rel or "/views/" in rel:
        return "Implements a user-facing page or routed screen in the application."
    return None


def infer_file_role_with_project_context(item: FileInsight, project_type: str | None, signals: FileSignals) -> str | None:
    name = item.path.name.lower()
    rel = item.relpath.as_posix().lower()

    if project_type == "Desktop GUI + CLI developer tool":
        desktop_exact_roles = {
            "context_engine.py": "Implements project analysis, scoring, and smart context selection.",
            "renderer.py": "Formats selected analysis into the final context pack output.",
            "scanner.py": "Scans the project tree, applies filters, and reads safe text content.",
            "ui.py": "Implements the desktop GUI and export workflow orchestration.",
            "cli.py": "Implements the command-line workflow for pack generation and output.",
            "theme.py": "Defines GUI theme palettes and widget repaint behavior.",
        }
        if name in desktop_exact_roles:
            return desktop_exact_roles[name]
        if signals.has_tkinter and name.endswith(".py"):
            return "Implements desktop GUI behavior related to the selected context."

    if project_type == "Frontend web application":
        role = infer_frontend_support_role(item, signals)
        if role:
            return role
        if rel.endswith(("/page.tsx", "/page.jsx")):
            return infer_nextjs_page_role(item)

    if project_type == "PHP CRUD web application":
        entry_role = infer_entrypoint_role(item, project_type)
        if entry_role:
            return entry_role
        if "service" in name or signals.has_service_class:
            return "Implements service-layer logic that coordinates domain operations."
        if "dao" in name or "repository" in name or signals.has_dao_usage:
            return "Handles persistence and data access operations."

    return None


def infer_content_based_role(item: FileInsight, signals: FileSignals) -> str | None:
    name = item.path.name.lower()
    rel = item.relpath.as_posix().lower()

    locale_name_or_path = "locale" in name or "localecontext" in name or "/locale" in rel or "/i18n" in rel or "/translations/" in rel
    if locale_name_or_path and signals.has_react_context and signals.has_translation_dict:
        return "Provides locale state and translation hooks used across the app."
    if ("auth" in name or "/auth/" in rel) and signals.has_react_context:
        return "Provides authentication state and auth-related helpers used across the app."
    if signals.has_form_handling and (rel.endswith(("/page.tsx", "/page.jsx")) or "form" in name):
        return "Implements the create/edit form flow for a domain entity."
    return None


def validate_role_against_project(item: FileInsight, role: str, project_type: str | None) -> str:
    if not role:
        return role
    name = item.path.name.lower()
    rel = item.relpath.as_posix().lower()
    lowered = role.lower()

    if project_type == "Desktop GUI + CLI developer tool":
        locale_like = "locale state and translation hooks" in lowered
        locale_whitelist = {"localecontext.tsx", "translations.ts", "locale.py", "locale_context.py"}
        if locale_like and name not in locale_whitelist:
            desktop_fallbacks = {
                "context_engine.py": "Implements project analysis, scoring, and smart context selection.",
                "renderer.py": "Formats selected analysis into the final context pack output.",
                "scanner.py": "Scans the project tree, applies filters, and reads safe text content.",
                "ui.py": "Implements the desktop GUI and export workflow orchestration.",
                "cli.py": "Implements the command-line workflow for pack generation and output.",
                "theme.py": "Defines GUI theme palettes and widget repaint behavior.",
            }
            return desktop_fallbacks.get(name, "Contains application logic related to the selected context.")

    if project_type == "PHP CRUD web application" and "landing page" in lowered and rel.endswith("/index.php"):
        return "Implements the main listing page and primary user-facing entry flow."

    return role


def infer_file_role_pipeline(item: FileInsight, project_type: str | None = None) -> str:
    if is_test_file(item.relpath):
        if item.path.name.lower() == "__init__.py":
            return "Marks the tests package for discovery and shared imports."
        if item.path.stem.startswith("test_"):
            target = item.path.stem.removeprefix("test_").replace("_", " ")
            return f"Exercises {target} behavior with focused automated checks."
        return "Exercises project behavior through automated tests."

    role = infer_exact_name_role(item)
    if role:
        return validate_role_against_project(item, role, project_type)

    signals = collect_file_signals(item)

    role = infer_file_role_with_project_context(item, project_type, signals)
    if role:
        return validate_role_against_project(item, role, project_type)

    role = infer_entrypoint_role(item, project_type)
    if role:
        return validate_role_against_project(item, role, project_type)

    role = infer_nextjs_page_role(item)
    if role and (project_type == "Frontend web application" or item.lang in {"tsx", "jsx"}):
        return validate_role_against_project(item, role, project_type)

    role = infer_frontend_support_role(item, signals)
    if role and (project_type == "Frontend web application" or item.lang in {"tsx", "jsx", "vue", "svelte"}):
        return validate_role_against_project(item, role, project_type)

    role = infer_path_role(item)
    if role:
        return validate_role_against_project(item, role, project_type)

    role = infer_content_based_role(item, signals)
    if role:
        return validate_role_against_project(item, role, project_type)

    return validate_role_against_project(item, "Contains application logic related to the selected context.", project_type)


def infer_file_role(item: FileInsight, project_type: str | None = None) -> str | None:
    return infer_file_role_pipeline(item, project_type)


def build_embedded_asset_excerpt(item: FileInsight) -> str:
    lines: list[str] = []
    docstring = re.search(r'^\s*"""([^"\n]+)"""', item.content, re.MULTILINE)
    if docstring:
        lines.append(f'"""{docstring.group(1)}"""')
    names = re.findall(r"^\s*([A-Z][A-Z0-9_]{2,})\s*=", item.content, re.MULTILINE)
    for name in names[:4]:
        lines.append(f"{name} = <embedded asset data omitted>")
    if not lines:
        lines.append("<embedded asset data omitted>")
    return "\n".join(lines)


def sanitize_excerpt_lines(item: FileInsight, lines: list[str]) -> tuple[list[str], bool]:
    sanitized: list[str] = []
    omitted_blob = False
    placeholder_open = False
    allow_blob_sanitization = should_sanitize_blob_excerpt(item)

    for line in lines:
        if allow_blob_sanitization and is_blob_like_line(line):
            omitted_blob = True
            if not placeholder_open:
                sanitized.append("<embedded blob omitted>")
                placeholder_open = True
            continue
        placeholder_open = False
        sanitized.append(line)

    return sanitized, omitted_blob


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
    if item.path.resolve() in changed_paths:
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
        return "Stores embedded brand or binary-like asset payloads for the packaged GUI."
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
        return "Drives the desktop interface, user interactions, and presentation logic."
    if "cli" in item.tags:
        return "Handles command-line arguments, execution flow, and output writing."
    if item.path.stem == "context_engine" or "analysis" in item.tags:
        return "Scores files, infers relationships, and chooses which context to export."
    if item.path.stem == "renderer" or "renderer" in item.tags:
        return "Formats the selected analysis into Markdown sections and token guidance."
    if "scanner" in item.tags:
        return "Scans the project tree, applies ignore rules, and reads safe text content."
    if "theme" in item.tags:
        return "Defines theme palettes and repaint helpers for dark/light interface rendering."
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


def parse_json_dependencies(content: str) -> dict[str, str]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return {}
    deps: dict[str, str] = {}
    for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies", "require", "require-dev"):
        section = payload.get(key, {})
        if isinstance(section, dict):
            deps.update({str(name).lower(): str(version) for name, version in section.items()})
    return deps


def parse_json_document(content: str) -> dict:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def parse_package_scripts(content: str) -> list[str]:
    payload = parse_json_document(content)
    scripts = payload.get("scripts", {})
    if not isinstance(scripts, dict):
        return []
    return [str(name) for name in scripts.keys()]


def parse_requirements_dependencies(content: str) -> set[str]:
    deps: set[str] = set()
    for line in content.splitlines():
        raw = line.split("#", 1)[0].strip()
        if not raw or raw.startswith(("-", "--")):
            continue
        token = re.split(r"[<>=!~;\[]", raw, maxsplit=1)[0].strip()
        if token:
            deps.add(token.lower())
    return deps


def parse_pyproject_dependencies(content: str) -> set[str]:
    deps: set[str] = set()
    for match in re.finditer(r'dependencies\s*=\s*\[(.*?)\]', content, re.DOTALL | re.IGNORECASE):
        for raw_dep in re.findall(r'["\']([^"\']+)["\']', match.group(1)):
            token = re.split(r"[<>=!~;\[]", raw_dep, maxsplit=1)[0].strip()
            if token:
                deps.add(token.lower())
    poetry_block = re.search(r"\[tool\.poetry\.dependencies\](.*?)(?:\n\[|$)", content, re.DOTALL | re.IGNORECASE)
    if poetry_block:
        for name in re.findall(r"^\s*([A-Za-z0-9_.-]+)\s*=", poetry_block.group(1), re.MULTILINE):
            if name.lower() != "python":
                deps.add(name.lower())
    return deps


def parse_pyproject_document(content: str) -> dict:
    try:
        payload = tomllib.loads(content)
    except tomllib.TOMLDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def parse_pyproject_scripts(content: str) -> list[str]:
    payload = parse_pyproject_document(content)
    scripts: list[str] = []
    project = payload.get("project", {})
    if isinstance(project, dict) and isinstance(project.get("scripts"), dict):
        scripts.extend(str(name) for name in project["scripts"].keys())
    tool = payload.get("tool", {})
    poetry = tool.get("poetry", {}) if isinstance(tool, dict) else {}
    if isinstance(poetry, dict) and isinstance(poetry.get("scripts"), dict):
        scripts.extend(str(name) for name in poetry["scripts"].keys())
    return list(dict.fromkeys(scripts))


def parse_go_mod_dependencies(content: str) -> set[str]:
    deps: set[str] = set()
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("require "):
            module = line.split()[1] if len(line.split()) > 1 else ""
            if module:
                deps.add(module.lower())
    for module in re.findall(r"^\s*([A-Za-z0-9\./_-]+)\s+v[0-9]", content, re.MULTILINE):
        deps.add(module.lower())
    return deps


def parse_toml_section_keys(content: str, section_name: str) -> set[str]:
    match = re.search(rf"\[{re.escape(section_name)}\](.*?)(?:\n\[|$)", content, re.DOTALL | re.IGNORECASE)
    if not match:
        return set()
    return {
        name.lower()
        for name in re.findall(r"^\s*([A-Za-z0-9_.-]+)\s*=", match.group(1), re.MULTILINE)
    }


def parse_cargo_document(content: str) -> dict:
    try:
        payload = tomllib.loads(content)
    except tomllib.TOMLDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def parse_xml_package_references(content: str) -> set[str]:
    return {
        value.lower()
        for value in re.findall(r'PackageReference[^>]+Include="([^"]+)"', content, re.IGNORECASE)
    } | {
        value.lower()
        for value in re.findall(r"<artifactId>([^<]+)</artifactId>", content, re.IGNORECASE)
    }


def parse_xml_document(content: str) -> ET.Element | None:
    try:
        return ET.fromstring(content)
    except ET.ParseError:
        return None


def parse_csproj_scripts(content: str) -> list[str]:
    root = parse_xml_document(content)
    if root is None:
        return []
    commands: list[str] = []
    for tag in ("Target", "Exec"):
        for node in root.iter():
            if node.tag.endswith(tag):
                name = node.attrib.get("Name") or node.attrib.get("Command")
                if name:
                    commands.append(str(name))
    return list(dict.fromkeys(commands))


def parse_pom_scripts(content: str) -> list[str]:
    root = parse_xml_document(content)
    if root is None:
        return []
    scripts: list[str] = []
    for node in root.iter():
        if node.tag.endswith("goal") and node.text:
            scripts.append(node.text.strip())
    return list(dict.fromkeys(filter(None, scripts)))


def parse_manifest_scripts(item: FileInsight) -> list[str]:
    name = item.path.name.lower()
    if name in {"package.json", "composer.json"}:
        return parse_package_scripts(item.content)
    if name == "pyproject.toml":
        return parse_pyproject_scripts(item.content)
    if name.endswith(".csproj"):
        return parse_csproj_scripts(item.content)
    if name == "pom.xml":
        return parse_pom_scripts(item.content)
    return []


def get_dependency_names(item: FileInsight) -> set[str]:
    name = item.path.name.lower()
    if name in {"package.json", "composer.json"}:
        return set(parse_json_dependencies(item.content))
    if name == "requirements.txt":
        return parse_requirements_dependencies(item.content)
    if name == "pyproject.toml":
        return parse_pyproject_dependencies(item.content)
    if name == "cargo.toml":
        return parse_toml_section_keys(item.content, "dependencies") | parse_toml_section_keys(item.content, "dev-dependencies")
    if name == "go.mod":
        return parse_go_mod_dependencies(item.content)
    if name == "pom.xml" or name.endswith(".csproj"):
        return parse_xml_package_references(item.content)
    return set()


def fingerprint_file_lookup(insights: list[FileInsight]) -> tuple[dict[str, FileInsight], dict[str, FileInsight]]:
    by_rel = {item.relpath.as_posix().lower(): item for item in insights}
    by_name = {item.path.name.lower(): item for item in insights}
    return by_rel, by_name


def identity_weight_for(item: FileInsight) -> tuple[float, str | None]:
    name = item.path.name.lower()
    if name in IDENTITY_FILE_WEIGHTS:
        return IDENTITY_FILE_WEIGHTS[name]
    for suffix, payload in IDENTITY_SUFFIX_WEIGHTS.items():
        if name.endswith(suffix):
            return payload
    for prefix, payload in IDENTITY_PREFIX_WEIGHTS.items():
        if name.startswith(prefix):
            return payload
    return 0.0, None


def prioritize_dependencies(dependency_names: set[str]) -> list[str]:
    priority_order = [
        "next",
        "react",
        "vue",
        "svelte",
        "@sveltejs/kit",
        "typescript",
        "tailwindcss",
        "@tailwindcss/postcss",
        "firebase",
        "fastapi",
        "django",
        "flask",
        "express",
        "laravel/framework",
        "illuminate/database",
    ]
    selected: list[str] = []
    lowered = {dep.lower() for dep in dependency_names}
    for dep in priority_order:
        if dep in lowered and dep not in selected:
            selected.append(dep)
    for dep in sorted(lowered):
        if dep not in selected:
            selected.append(dep)
    return selected[:8]


def signal_evidence_text(signal: str) -> str:
    mapping = {
        "has_next": "`package.json` includes `next`.",
        "has_react": "`package.json` includes `react`.",
        "has_tsx_pages": "Routed TSX/JSX page files were detected.",
        "has_components_dir": "A `components` directory is present.",
        "has_tailwind": "Tailwind CSS tooling was detected.",
        "has_fastapi": "Python dependency manifests include `fastapi`.",
        "has_express": "`package.json` includes `express`.",
        "has_routes_dir": "A `routes` directory is present.",
        "has_controllers": "A `controllers` directory is present.",
        "has_db_models": "Model-like files or directories were detected.",
        "has_php": "PHP source files were detected.",
        "has_composer": "`composer.json` is present.",
        "has_form_pages": "Form-oriented pages or `<form>` markup were detected.",
        "has_service_layer": "Service-layer files were detected.",
        "has_dao_layer": "DAO or repository files were detected.",
        "has_python": "Python source files were detected.",
        "has_tkinter": "Tkinter imports were detected.",
        "has_cli_entrypoint": "CLI entry signals were detected.",
        "has_gui_module": "GUI-oriented modules were detected.",
    }
    return mapping.get(signal, signal.replace("_", " "))


def compute_project_type_signals(
    insights: list[FileInsight],
    frameworks: list[str],
    runtime: list[str],
    package_managers: list[str],
    build_tools: list[str],
    dependency_names: set[str],
    entrypoints: list[FileInsight],
) -> dict[str, bool]:
    lower_dirs = {item.relpath.parts[0].lower() for item in insights if item.relpath.parts}
    relpaths = [item.relpath.as_posix().lower() for item in insights]
    names = [item.path.name.lower() for item in insights]

    return {
        "has_next": "Next.js" in frameworks,
        "has_react": "React" in frameworks,
        "has_tsx_pages": any(path.endswith(("/page.tsx", "/page.jsx")) or "/pages/" in path for path in relpaths),
        "has_components_dir": "components" in lower_dirs or any("/components/" in path for path in relpaths),
        "has_tailwind": "Tailwind CSS" in build_tools,
        "has_fastapi": "FastAPI" in frameworks,
        "has_express": "express" in dependency_names,
        "has_routes_dir": "routes" in lower_dirs or any("/routes/" in path for path in relpaths),
        "has_controllers": "controllers" in lower_dirs or any("/controllers/" in path for path in relpaths),
        "has_db_models": "models" in lower_dirs or any("/models/" in path for path in relpaths),
        "has_php": any(item.lang == "php" for item in insights),
        "has_composer": "Composer" in package_managers,
        "has_form_pages": any("form" in name for name in names) or any("<form" in item.content.lower() for item in insights if item.lang in {"html", "php", "jsx", "tsx"}),
        "has_service_layer": any("service" in name for name in names) or any("/services/" in path for path in relpaths),
        "has_dao_layer": any("dao" in name or "repository" in name for name in names) or any("/repositories/" in path or "/dao/" in path for path in relpaths),
        "has_python": any(item.lang == "python" for item in insights),
        "has_tkinter": "Tkinter" in frameworks,
        "has_cli_entrypoint": any("cli" in item.tags for item in entrypoints + insights),
        "has_gui_module": any("ui" in item.tags for item in insights),
    }


def classify_project_type(signals: dict[str, bool]) -> tuple[str | None, float]:
    scored: list[tuple[int, str]] = []
    for label, rules in PROJECT_TYPE_RULES.items():
        score = sum(weight for signal, weight in rules if signals.get(signal, False))
        if score:
            scored.append((score, label))
    if not scored:
        return None, 0.0
    scored.sort(reverse=True)
    return scored[0][1], float(scored[0][0])


def extract_domain_corpus_tokens(insights: list[FileInsight]) -> list[str]:
    tokens: list[str] = []
    for item in insights[:80]:
        path_tokens = re.findall(r"[A-Za-zÀ-ÿ]{3,}", item.relpath.as_posix().replace("\\", "/"))
        symbol_tokens = []
        for name in item.functions[:12] + item.classes[:8]:
            symbol_tokens.extend(re.findall(r"[A-Z]?[a-zà-ÿ]+|[A-Z]+(?=[A-Z]|$)", name))
        visible_text = []
        visible_text.extend(re.findall(r">([^<]{3,80})<", item.content))
        visible_text.extend(re.findall(r'["\']([^"\']{3,80})["\']', item.content[:6000]))
        for chunk in path_tokens + symbol_tokens + visible_text:
            tokens.extend(re.findall(r"[A-Za-zÀ-ÿ]{3,}", chunk.lower()))
    return tokens


def extract_richer_domain_corpus_tokens(insights: list[FileInsight]) -> list[str]:
    tokens = extract_domain_corpus_tokens(insights)
    for item in insights[:80]:
        for imported in item.imports[:20]:
            tokens.extend(re.findall(r"[A-Za-zÃ€-Ã¿]{3,}", imported.replace("\\", "/").lower()))
        import_mentions = re.findall(
            r"(?:import|from|require|require_once|include|include_once)\s+([A-Za-z_][A-Za-z0-9_]*)",
            item.content[:6000],
            re.IGNORECASE,
        )
        for mention in import_mentions:
            tokens.extend(re.findall(r"[A-Za-zÃ€-Ã¿]{3,}", mention.lower()))
    return tokens


def extract_import_enriched_domain_tokens(insights: list[FileInsight]) -> list[str]:
    tokens = extract_domain_corpus_tokens(insights)
    for item in insights[:80]:
        for imported in item.imports[:20]:
            tokens.extend(re.findall(r"[A-Za-z_]{3,}", imported.replace("\\", "/").lower()))
        import_mentions = re.findall(
            r"(?:import|from|require|require_once|include|include_once)\s+([A-Za-z_][A-Za-z0-9_]*)",
            item.content[:6000],
            re.IGNORECASE,
        )
        for mention in import_mentions:
            tokens.extend(re.findall(r"[A-Za-z_]{3,}", mention.lower()))
    return tokens


def detect_domain_label(insights: list[FileInsight]) -> tuple[str | None, int]:
    tokens = extract_import_enriched_domain_tokens(insights)
    counts = Counter(tokens)
    scored: list[tuple[int, str]] = []
    for label, hints in DOMAIN_HINTS.items():
        score = sum(counts.get(hint.lower(), 0) for hint in hints)
        if score:
            scored.append((score, label))
    if not scored:
        return None, 0
    scored.sort(reverse=True)
    return scored[0][1], scored[0][0]


def infer_probable_purpose(project_type_label: str | None, domain_label: str | None) -> str:
    if project_type_label == "PHP CRUD web application" and domain_label == "education":
        return "Manage student records through listing, form editing, and service or DAO-backed operations."
    if project_type_label == "Frontend web application" and domain_label == "marketing_site":
        return "Present a marketing-focused website with landing sections, navigation, and product or content highlights."
    if project_type_label == "Frontend web application" and domain_label == "ecommerce":
        return "Present a marketing or catalog-oriented frontend with products, browsing flows, and shopping-adjacent experiences."
    if project_type_label == "Backend API service" and domain_label == "admin_panel":
        return "Support administrative or reporting workflows through backend endpoints and data access layers."
    if project_type_label == "Desktop GUI + CLI developer tool":
        return "Scan local repositories and generate curated context packs for AI workflows."
    if project_type_label == "Backend API service":
        return "Expose backend endpoints and supporting application services through API-oriented modules."
    if project_type_label == "Frontend web application":
        return "Deliver a browser-based application with component-driven frontend flows."
    if project_type_label == "PHP CRUD web application":
        return "Manage records through routed pages, forms, and persistence-oriented PHP modules."
    if project_type_label == "Python application" and domain_label == "education":
        return "Support education-related workflows with Python application modules and domain operations."
    return "Organize project structure and expose the most relevant code paths for developer workflows."


def detect_project_fingerprint(
    project_path: Path,
    insights: list[FileInsight],
    entrypoints: list[FileInsight],
) -> ProjectFingerprint:
    by_rel, by_name = fingerprint_file_lookup(insights)
    lower_names = {item.path.name.lower() for item in insights}
    lower_dirs = {item.relpath.parts[0].lower() for item in insights if item.relpath.parts}
    content_blob = "\n".join(item.content.lower() for item in insights[:60])

    language_scores: Counter[str] = Counter()
    frameworks: list[str] = []
    runtime: list[str] = []
    package_managers: list[str] = []
    build_tools: list[str] = []
    evidence: list[str] = []
    evidence_sources: list[str] = []
    evidence_by_topic: dict[str, list[str]] = {"project_type": [], "purpose": [], "technologies": []}
    dependency_names: set[str] = set()
    scripts: list[str] = []

    def push(target: list[str], value: str) -> None:
        if value not in target:
            target.append(value)

    def note(message: str, topic: str = "technologies") -> None:
        if message not in evidence:
            evidence.append(message)
        evidence_by_topic.setdefault(topic, [])
        if message not in evidence_by_topic[topic]:
            evidence_by_topic[topic].append(message)

    def source(marker: str) -> None:
        if marker and marker not in evidence_sources:
            evidence_sources.append(marker)

    for item in insights:
        if not item.lang:
            continue
        language_scores[item.lang] += CODE_LANGUAGE_WEIGHTS.get(item.lang, 0.8)

    if "package.json" in by_name:
        source("package.json")
        deps = parse_json_dependencies(by_name["package.json"].content)
        dependency_names.update(deps)
        for script in parse_manifest_scripts(by_name["package.json"]):
            push(scripts, script)
        package_manager_label = "npm"
        package_manager_value = ""
        try:
            package_manager_value = json.loads(by_name["package.json"].content).get("packageManager", "")
        except json.JSONDecodeError:
            package_manager_value = ""
        if "pnpm-lock.yaml" in lower_names or str(package_manager_value).startswith("pnpm@"):
            package_manager_label = "pnpm"
        elif "yarn.lock" in lower_names or str(package_manager_value).startswith("yarn@"):
            package_manager_label = "Yarn"
        push(package_managers, package_manager_label)
        language_scores["typescript" if ("typescript" in deps or any(item.lang in {"typescript", "tsx"} for item in insights)) else "javascript"] += 10.0
        note(f"`package.json` defines the JavaScript/TypeScript dependency graph via {package_manager_label}.")
        if "next" in deps:
            push(frameworks, "Next.js")
            push(runtime, "Node.js")
            push(runtime, "Browser")
            note("`package.json` includes `next`.", "project_type")
        if "react" in deps:
            push(frameworks, "React")
            push(runtime, "Browser")
            note("`package.json` includes `react`.", "project_type")
        if "vue" in deps:
            push(frameworks, "Vue")
            push(runtime, "Browser")
            note("`package.json` includes `vue`.")
        if "svelte" in deps or "@sveltejs/kit" in deps:
            push(frameworks, "Svelte/SvelteKit")
            push(runtime, "Browser")
            note("`package.json` includes Svelte dependencies.")
        if "vite" in deps or any(name.startswith("vite.config.") for name in lower_names):
            push(build_tools, "Vite")
            note("Vite config or dependency was detected.")
        if "typescript" in deps or "tsconfig.json" in lower_names:
            push(build_tools, "TypeScript compiler")
            note("TypeScript tooling is configured.")
        if "tailwindcss" in deps or "@tailwindcss/postcss" in deps or any(name.startswith("tailwind.config.") for name in lower_names):
            push(build_tools, "Tailwind CSS")
            note("Tailwind CSS is configured in the frontend toolchain.")
        if "firebase" in deps:
            push(build_tools, "Firebase")
            note("`package.json` includes `firebase`.")

    if "composer.json" in by_name:
        source("composer.json")
        deps = parse_json_dependencies(by_name["composer.json"].content)
        dependency_names.update(deps)
        for script in parse_manifest_scripts(by_name["composer.json"]):
            push(scripts, script)
        push(package_managers, "Composer")
        push(runtime, "PHP")
        language_scores["php"] += 10.0
        note("`composer.json` defines the PHP dependency graph.", "project_type")
        if "laravel/framework" in deps or {"app", "routes"} <= lower_dirs or "artisan" in lower_names:
            push(frameworks, "Laravel")
            push(runtime, "Server")
            note("Laravel structure was detected from `composer.json`, `artisan`, or standard app folders.", "project_type")
        if "illuminate/database" in deps:
            push(build_tools, "Illuminate Database")
            note("`composer.json` includes `illuminate/database`.")

    if "requirements.txt" in by_name:
        source("requirements.txt")
        deps = parse_requirements_dependencies(by_name["requirements.txt"].content)
        dependency_names.update(deps)
        push(package_managers, "pip-style requirements")
        push(runtime, "Python")
        language_scores["python"] += 10.0
        note("`requirements.txt` defines Python dependencies.", "project_type")
        if "fastapi" in deps:
            push(frameworks, "FastAPI")
            push(runtime, "Server")
            note("`requirements.txt` includes `fastapi`.", "project_type")
        if "django" in deps:
            push(frameworks, "Django")
            push(runtime, "Server")
            note("`requirements.txt` includes `django`.")
        if "flask" in deps:
            push(frameworks, "Flask")
            push(runtime, "Server")
            note("`requirements.txt` includes `flask`.")
        if "pyinstaller" in deps:
            push(build_tools, "PyInstaller")
            note("`requirements.txt` includes `pyinstaller`.")

    if "pyproject.toml" in by_name:
        source("pyproject.toml")
        deps = parse_pyproject_dependencies(by_name["pyproject.toml"].content)
        dependency_names.update(deps)
        for script in parse_manifest_scripts(by_name["pyproject.toml"]):
            push(scripts, script)
        push(package_managers, "pyproject-based Python packaging")
        push(runtime, "Python")
        language_scores["python"] += 10.0
        note("`pyproject.toml` defines Python project metadata.", "project_type")
        if re.search(r"\[tool\.poetry\]", by_name["pyproject.toml"].content, re.IGNORECASE):
            push(package_managers, "Poetry")
            note("`pyproject.toml` includes Poetry configuration.")
        if "fastapi" in deps:
            push(frameworks, "FastAPI")
            push(runtime, "Server")
            note("`pyproject.toml` includes `fastapi`.")
        if "django" in deps:
            push(frameworks, "Django")
            push(runtime, "Server")
            note("`pyproject.toml` includes `django`.")
        if "flask" in deps:
            push(frameworks, "Flask")
            push(runtime, "Server")
            note("`pyproject.toml` includes `flask`.")
        if "pyinstaller" in deps:
            push(build_tools, "PyInstaller")
            note("`pyproject.toml` includes `pyinstaller`.")

    if "cargo.toml" in by_name:
        source("Cargo.toml")
        dependency_names.update(get_dependency_names(by_name["cargo.toml"]))
        for script in parse_manifest_scripts(by_name["cargo.toml"]):
            push(scripts, script)
        push(package_managers, "Cargo")
        push(runtime, "Rust")
        language_scores["rust"] += 10.0
        note("`Cargo.toml` defines the Rust package manifest.")

    if "go.mod" in by_name:
        source("go.mod")
        dependency_names.update(get_dependency_names(by_name["go.mod"]))
        push(package_managers, "Go modules")
        push(runtime, "Go")
        language_scores["go"] += 10.0
        note("`go.mod` defines the Go module graph.")

    for name in lower_names:
        if name.endswith(".csproj"):
            source(name)
            for script in parse_manifest_scripts(by_name[name]):
                push(scripts, script)
            push(package_managers, "NuGet")
            push(runtime, ".NET")
            language_scores["csharp"] += 10.0
            note(f"`{name}` defines a .NET project.")
            break

    if "pom.xml" in lower_names:
        source("pom.xml")
        dependency_names.update(get_dependency_names(by_name["pom.xml"]))
        for script in parse_manifest_scripts(by_name["pom.xml"]):
            push(scripts, script)
        push(package_managers, "Maven")
        push(runtime, "JVM")
        language_scores["java"] += 10.0
        note("`pom.xml` defines the Maven build graph.")

    if any("tkinter" in item.content.lower() for item in insights if item.lang == "python"):
        push(frameworks, "Tkinter")
        push(runtime, "Desktop GUI")
        language_scores["python"] += 4.0
        note("Tkinter imports were detected in Python source files.", "project_type")
        source("Tkinter imports")
    if any("cli" in item.tags for item in insights) or "argparse" in content_blob or "sys.argv" in content_blob:
        push(runtime, "CLI")
        note("CLI-oriented files or argparse/sys.argv usage were detected.", "project_type")
    if "dockerfile" in lower_names:
        push(build_tools, "Docker")
        note("A `Dockerfile` is present.")
    if any("pyinstaller" in item.content.lower() for item in insights if item.path.suffix.lower() in {".txt", ".toml", ".bat", ".sh", ".spec"}):
        push(build_tools, "PyInstaller")
        note("PyInstaller was detected in build-related files.")

    for name in sorted(lower_names):
        if name.startswith("next.config."):
            source(name)
        elif name.startswith("vite.config."):
            source(name)
        elif name in {"tsconfig.json", "dockerfile", ".env.example"}:
            source(name)

    if "app" in lower_dirs:
        source("app/")
    if "pages" in lower_dirs:
        source("pages/")
    if "components" in lower_dirs:
        source("components/")
    if "lib" in lower_dirs:
        source("lib/")
    if "routes" in lower_dirs:
        source("routes/")
    if "tests" in lower_dirs:
        source("tests/")

    signals = compute_project_type_signals(
        insights,
        frameworks,
        runtime,
        package_managers,
        build_tools,
        dependency_names,
        entrypoints,
    )
    project_type_key, project_type_score = classify_project_type(signals)
    domain_label, domain_score = detect_domain_label(insights)

    project_type = PROJECT_TYPE_LABELS.get(project_type_key)
    probable_purpose = infer_probable_purpose(project_type, domain_label)
    if project_type_key:
        for signal, _weight in PROJECT_TYPE_RULES[project_type_key]:
            if signals.get(signal):
                note(signal_evidence_text(signal), "project_type")

    stems = {item.path.stem.lower() for item in insights}
    if "python" in language_scores and {"scanner", "renderer", "ui", "cli"} <= stems:
        project_type = "Desktop GUI + CLI developer tool"
        probable_purpose = "Scan local repositories and generate curated context packs for AI workflows."
        note("Core files like `scanner.py`, `renderer.py`, `ui.py`, and `cli.py` were all detected together.", "project_type")
        for marker in ("contexta.py", "ui.py", "cli.py", "renderer.py", "scanner.py"):
            if marker in by_name:
                source(marker)
    elif not project_type:
        if "Laravel" in frameworks:
            project_type = "Laravel web application"
        elif "FastAPI" in frameworks:
            project_type = "Backend API service"
        elif "Django" in frameworks:
            project_type = "Django web application"
        elif "Flask" in frameworks:
            project_type = "Python web application"
        elif "php" in language_scores and "Composer" in package_managers:
            project_type = "PHP application"
        elif "typescript" in language_scores or "javascript" in language_scores:
            project_type = "JavaScript/TypeScript application"
        elif "python" in language_scores:
            project_type = "Python application"
        else:
            project_type = "Developer-facing software project"

    if domain_label and domain_score >= 2:
        note(f"Domain vocabulary suggests `{domain_label}` behavior.", "purpose")

    if project_type == "PHP CRUD web application":
        for item in sorted(insights, key=lambda entry: (-entry.score, entry.relpath.as_posix())):
            role = infer_file_role_pipeline(item, project_type).lower()
            rel = item.relpath.as_posix()
            if item.path.name.lower() == "composer.json":
                source(rel)
            elif "main listing page" in role or "main user-facing entry flow" in role:
                source(rel)
            elif "create/edit form flow" in role:
                source(rel)
            elif "service-layer" in role:
                source(rel)
            elif "data access" in role:
                source(rel)
            elif "bootstrap" in role:
                source(rel)
            if len(evidence_sources) >= 8:
                break

    for item in insights:
        rel = item.relpath.as_posix()
        lowered_rel = rel.lower()
        if any(token in lowered_rel for token in ("translations", "localecontext", "authcontext")):
            source(rel)
        if len(evidence_sources) >= 8:
            break

    primary_language = None
    if language_scores:
        preferred = max(language_scores.items(), key=lambda item: item[1])
        primary_language = TECH_LABELS.get(preferred[0], preferred[0].title())
        if primary_language in {"React", "Next.js", "Vue", "Laravel"}:
            primary_language = "TypeScript" if any(item.lang in {"typescript", "tsx"} for item in insights) else "JavaScript"

    confidence = min(
        0.98,
        0.35
        + (0.06 * min(len(evidence), 6))
        + (0.05 * min(len(frameworks), 3))
        + (0.04 * min(len(package_managers), 2))
        + (0.03 * min(len(build_tools), 3)),
    )
    confidence = min(0.98, confidence + min(project_type_score * 0.02, 0.12))
    confidence = min(0.98, confidence + min(domain_score * 0.01, 0.05))
    if entrypoints:
        confidence = min(0.98, confidence + 0.05)

    return ProjectFingerprint(
        primary_language=primary_language,
        frameworks=frameworks[:6],
        runtime=runtime[:6],
        package_managers=package_managers[:4],
        build_tools=build_tools[:6],
        main_dependencies=prioritize_dependencies(dependency_names),
        scripts=scripts[:8],
        project_type=project_type,
        probable_purpose=probable_purpose,
        confidence=round(confidence, 2),
        evidence=evidence[:8],
        evidence_sources=evidence_sources[:8],
        summary_evidence={key: value[:6] for key, value in evidence_by_topic.items() if value},
    )


def normalize_supporting_technologies(raw: list[str]) -> list[str]:
    replacements = {
        "pip-style requirements": "Python standard library",
        "desktop gui runtime": "Tkinter desktop interface",
        "desktop gui interface": "Tkinter desktop interface",
        "cli workflow": "CLI workflow",
        "pyinstaller": "optional PyInstaller packaging",
        "typescript compiler": "TypeScript",
        "npm": "npm-based workflow",
        "pnpm": "pnpm-based workflow",
        "yarn": "Yarn-based workflow",
        "pyproject-based python packaging": "pyproject packaging workflow",
        "css": "CSS styling layer",
    }
    normalized: list[str] = []
    seen: set[str] = set()
    for item in raw:
        key = item.strip().lower()
        value = replacements.get(key, item)
        lowered = value.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        normalized.append(value)
    return normalized


def detect_supporting_technologies(insights: list[FileInsight], fingerprint: ProjectFingerprint) -> list[str]:
    raw: list[str] = []

    def push(value: str) -> None:
        if value not in raw:
            raw.append(value)

    if fingerprint.primary_language == "Python":
        push("Python standard library")
    if fingerprint.primary_language in {"TypeScript", "JavaScript"} and any(pm in {"npm", "pnpm", "Yarn"} for pm in fingerprint.package_managers):
        push("npm-based workflow")
    if "Desktop GUI" in fingerprint.runtime:
        push("Tkinter desktop interface" if "Tkinter" in fingerprint.frameworks else "Desktop GUI interface")
    if "CLI" in fingerprint.runtime:
        push("CLI workflow")
    for manager in fingerprint.package_managers:
        if manager in {"Composer", "Poetry", "Cargo", "Go modules", "NuGet", "Maven"}:
            push(manager)
    for entry in fingerprint.build_tools:
        push(entry)

    if any(item.lang in {"css", "scss"} for item in insights):
        push("CSS styling layer")
    if any("git diff" in item.content.lower() or "gitignore" in item.content.lower() for item in insights[:40]):
        push("Git-aware file analysis")
    normalized = normalize_supporting_technologies(raw)
    frameworks_lower = {framework.lower() for framework in fingerprint.frameworks}
    primary_lower = (fingerprint.primary_language or "").lower()
    filtered: list[str] = []
    seen: set[str] = set()
    for item in normalized:
        lowered = item.lower()
        if lowered == primary_lower:
            continue
        if lowered in frameworks_lower:
            continue
        if "tkinter" in lowered and "tkinter" in frameworks_lower:
            continue
        if lowered in seen:
            continue
        seen.add(lowered)
        filtered.append(item)
    return filtered[:6]


def detect_quality_signals(insights: list[FileInsight]) -> list[str]:
    signals: list[str] = []

    def push(value: str) -> None:
        if value not in signals:
            signals.append(value)

    if any("unittest" in item.content.lower() for item in insights[:40]):
        push("unittest-based test suite")
    if any("pytest" in item.content.lower() for item in insights[:40]):
        push("pytest-based test coverage")
    return signals[:4]


def pick_core_module_names(items: list[FileInsight]) -> list[str]:
    names: list[str] = []
    for item in items:
        if is_test_file(item.relpath):
            continue
        lang = item.lang or ""
        name = item.path.name.lower()
        if lang in {"json", "yaml", "toml", "xml", "markdown", "text", "css", "scss"}:
            continue
        if name in IDENTITY_FILE_WEIGHTS or any(name.endswith(suffix) for suffix in IDENTITY_SUFFIX_WEIGHTS):
            continue
        if any(name.startswith(prefix) for prefix in IDENTITY_PREFIX_WEIGHTS):
            continue
        names.append(item.path.stem)
    return names[:4]


def infer_core_module_label(item: FileInsight, project_type: str | None = None) -> str | None:
    name = item.path.name.lower()
    stem = item.path.stem.lower()
    exact_labels = {
        "ui.py": "GUI layer",
        "renderer.py": "rendering layer",
        "context_engine.py": "analysis engine",
        "scanner.py": "scanning layer",
        "cli.py": "CLI layer",
        "theme.py": "theming layer",
        "contexta.py": "application entrypoint",
        "mdcodebrief.py": "compatibility launcher",
        "utils.py": "utility layer",
    }
    if name in exact_labels:
        return exact_labels[name]

    if name == "bootstrap.php" or "bootstrap" in stem:
        return "bootstrap/runtime setup"

    role = infer_file_role_pipeline(item, project_type).lower()
    if "main listing page" in role:
        return "main listing flow"
    if "create/edit form flow" in role:
        return "form flow"
    if "record persistence" in role or "submission" in role:
        return "submission flow"
    if "domain model or entity" in role:
        return "domain model"
    if "desktop gui" in role or "gui and export workflow" in role:
        return "GUI layer"
    if "command-line" in role or "cli flow" in role:
        return "CLI layer"
    if "analysis" in role or "context selection" in role:
        return "analysis engine"
    if "final context pack output" in role or "render" in role:
        return "rendering layer"
    if "scans the project tree" in role or "scanning" in role:
        return "scanning layer"
    if "theme palettes" in role or "theming" in role:
        return "theming layer"
    if "service-layer" in role:
        return "service layer"
    if "data access" in role or "persistence" in role:
        return "data access layer"
    if "translation hooks" in role or "localization" in role:
        return "localization layer"
    if "navigation/header" in role:
        return "navigation layer"
    if "footer" in role:
        return "footer layer"
    if "reusable ui component" in role:
        return "UI component layer"
    if "entrypoint" in role or "entry point" in role or "launcher" in role:
        return "application entrypoint"
    return None


def pick_core_module_labels(items: list[FileInsight], project_type: str | None = None) -> list[str]:
    labels: list[tuple[str, int]] = []
    seen: set[str] = set()
    priority = {
        "application entrypoint": 0,
        "GUI layer": 10,
        "CLI layer": 15,
        "analysis engine": 20,
        "rendering layer": 30,
        "scanning layer": 40,
        "theming layer": 50,
        "navigation layer": 60,
        "UI component layer": 70,
        "localization layer": 80,
        "main listing flow": 85,
        "form flow": 86,
        "submission flow": 87,
        "bootstrap/runtime setup": 88,
        "service layer": 90,
        "data access layer": 100,
        "domain model": 105,
        "utility layer": 110,
        "compatibility launcher": 120,
    }
    for item in items:
        if is_test_file(item.relpath):
            continue
        lang = item.lang or ""
        name = item.path.name.lower()
        if lang in {"json", "yaml", "toml", "xml", "markdown", "text", "css", "scss"}:
            continue
        if name in IDENTITY_FILE_WEIGHTS or any(name.endswith(suffix) for suffix in IDENTITY_SUFFIX_WEIGHTS):
            continue
        if any(name.startswith(prefix) for prefix in IDENTITY_PREFIX_WEIGHTS):
            continue
        label = infer_core_module_label(item, project_type) or item.path.stem.replace("_", " ")
        key = label.lower()
        if key in seen:
            continue
        seen.add(key)
        labels.append((label, priority.get(label, 1000 + len(labels))))
    ordered = [label for label, _rank in sorted(labels, key=lambda pair: (pair[1], pair[0].lower()))]
    return ordered[:6]


def pick_core_module_descriptors(items: list[FileInsight], project_type: str | None = None) -> list[str]:
    descriptors: list[tuple[str, int]] = []
    seen: set[str] = set()
    priority = {
        "application entrypoint": 0,
        "GUI layer": 10,
        "CLI layer": 15,
        "analysis engine": 20,
        "rendering layer": 30,
        "scanning layer": 40,
        "theming layer": 50,
        "navigation layer": 60,
        "UI component layer": 70,
        "localization layer": 80,
        "main listing flow": 85,
        "form flow": 86,
        "submission flow": 87,
        "bootstrap/runtime setup": 88,
        "service layer": 90,
        "data access layer": 100,
        "domain model": 105,
        "utility layer": 110,
        "compatibility launcher": 120,
    }
    for item in items:
        if is_test_file(item.relpath):
            continue
        lang = item.lang or ""
        name = item.path.name.lower()
        if lang in {"json", "yaml", "toml", "xml", "markdown", "text", "css", "scss"}:
            continue
        if name in IDENTITY_FILE_WEIGHTS or any(name.endswith(suffix) for suffix in IDENTITY_SUFFIX_WEIGHTS):
            continue
        if any(name.startswith(prefix) for prefix in IDENTITY_PREFIX_WEIGHTS):
            continue
        label = infer_core_module_label(item, project_type) or item.path.stem.replace("_", " ")
        key = label.lower()
        if key in seen:
            continue
        seen.add(key)
        descriptors.append((f"{label} (`{item.relpath.as_posix()}`)", priority.get(label, 1000 + len(descriptors))))
    ordered = [label for label, _rank in sorted(descriptors, key=lambda pair: (pair[1], pair[0].lower()))]
    return ordered[:6]


def join_natural_list(values: list[str]) -> str:
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    if len(values) == 2:
        return f"{values[0]} and {values[1]}"
    return f"{', '.join(values[:-1])}, and {values[-1]}"


def confidence_band(confidence: float) -> str:
    if confidence >= 0.85:
        return "high"
    if confidence >= 0.65:
        return "moderate"
    return "tentative"


def prioritize_evidence_sources(sources: list[str]) -> list[str]:
    priority = {
        "package.json": 0,
        "composer.json": 0,
        "pyproject.toml": 0,
        "requirements.txt": 0,
        "cargo.toml": 0,
        "go.mod": 0,
        "pom.xml": 0,
        "contexta.py": 5,
        "ui.py": 6,
        "cli.py": 7,
        "tkinter imports": 8,
        "renderer.py": 9,
        "context_engine.py": 10,
        "scanner.py": 11,
        "next.config.ts": 12,
        "next.config.js": 12,
        "vite.config.ts": 12,
        "vite.config.js": 12,
        "tsconfig.json": 13,
        "app/": 20,
        "pages/": 21,
        "components/": 22,
        "lib/": 23,
        "routes/": 24,
        "tests/": 90,
    }
    deduped: list[str] = []
    seen: set[str] = set()
    for item in sources:
        if item.lower() in seen:
            continue
        seen.add(item.lower())
        deduped.append(item)

    def rank(item: str) -> tuple[int, str]:
        lowered = item.lower()
        if lowered in priority:
            return priority[lowered], lowered
        if lowered.endswith("/index.php"):
            return 14, lowered
        if lowered.endswith("/form.php"):
            return 15, lowered
        if "/service/" in lowered or lowered.endswith("service.php"):
            return 16, lowered
        if "/dao/" in lowered or "dao.php" in lowered or "repository.php" in lowered:
            return 17, lowered
        if "bootstrap.php" in lowered:
            return 18, lowered
        return 50, lowered

    return sorted(deduped, key=lambda item: rank(item))


def build_project_summary_intro(project_path: Path, fingerprint: ProjectFingerprint) -> str:
    project_type = detect_project_shape(fingerprint)
    if project_type == "Frontend web application":
        return f"`{project_path.name}` looks like a frontend web application built around routed pages, shared UI components, and client-side tooling."
    if project_type == "PHP CRUD web application":
        return f"`{project_path.name}` looks like a PHP CRUD web application built around listings, forms, and persistence-oriented modules."
    if project_type == "Desktop GUI + CLI developer tool":
        return f"`{project_path.name}` looks like a desktop GUI + CLI developer tool built around repository analysis and export workflows."
    if project_type == "Backend API service":
        return f"`{project_path.name}` looks like a backend API service built around routes, services, and integration-heavy modules."
    if "library" in project_type.lower() or "package" in project_type.lower():
        return f"`{project_path.name}` looks like a reusable library/package with exported modules and supporting configuration."
    return f"`{project_path.name}` looks like a {project_type}."


def build_detection_evidence_line(fingerprint: ProjectFingerprint) -> str | None:
    sources = prioritize_evidence_sources(fingerprint.evidence_sources)[:5]
    if not sources:
        return None
    return f"Detection confidence: {confidence_band(fingerprint.confidence)}. Detected from: {join_natural_list(sources)}"


def build_architecture_overview(
    project_path: Path,
    insights: list[FileInsight],
    entrypoints: list[FileInsight],
    technologies: list[str],
    fingerprint: ProjectFingerprint,
    quality_signals: list[str],
) -> list[str]:
    lines: list[str] = []
    project_type = fingerprint.project_type or "developer-facing software project"
    primary = fingerprint.primary_language or "a mixed language stack"
    if project_type == "Frontend web application":
        lines.append(f"This project appears to be a frontend web application written primarily in {primary}, with routed screens and shared UI layers.")
    elif project_type == "PHP CRUD web application":
        lines.append(f"This project appears to be a PHP CRUD web application written primarily in {primary}, with listing, form, and persistence-oriented flows.")
    elif project_type == "Desktop GUI + CLI developer tool":
        lines.append(f"This project appears to be a desktop GUI + CLI developer tool written primarily in {primary}, with scanning, analysis, and export workflows.")
    elif project_type == "Backend API service":
        lines.append(f"This project appears to be a backend API service written primarily in {primary}, with route, service, and integration layers.")
    else:
        lines.append(f"This project appears to be a {project_type} written primarily in {primary}.")

    evidence_line = build_detection_evidence_line(fingerprint)
    if evidence_line:
        lines.append(evidence_line)

    if entrypoints:
        listed = ", ".join(f"`{item.relpath.as_posix()}`" for item in entrypoints[:3])
        lines.append(f"Likely entry points include {listed}.")

    core_modules = pick_core_module_descriptors(
        sorted(insights, key=lambda item: (-item.score, item.relpath.as_posix())),
        fingerprint.project_type,
    )
    if core_modules:
        lines.append(f"Core modules appear to center around {join_natural_list(core_modules)}.")

    if fingerprint.frameworks:
        lines.append(f"Detected frameworks: {', '.join(fingerprint.frameworks[:4])}.")
    if technologies:
        lines.append(f"Supporting technologies: {', '.join(technologies[:4])}.")
    if quality_signals:
        lines.append(f"Quality signals: {', '.join(quality_signals[:3])}.")
    if fingerprint.main_dependencies:
        lines.append(f"Manifest dependencies point to: {', '.join(fingerprint.main_dependencies[:5])}.")

    if fingerprint.probable_purpose:
        lines.append(f"Likely purpose: {fingerprint.probable_purpose}")
    return lines[:8]


def build_summary_lines(
    project_path: Path,
    selected_files: list[FileInsight],
    entrypoints: list[FileInsight],
    important_files: list[FileInsight],
    technologies: list[str],
    fingerprint: ProjectFingerprint,
    quality_signals: list[str],
) -> list[str]:
    lines = [build_project_summary_intro(project_path, fingerprint)]
    evidence_line = build_detection_evidence_line(fingerprint)
    if evidence_line:
        lines.append(evidence_line)
    if fingerprint.probable_purpose:
        lines.append(f"Likely purpose: {fingerprint.probable_purpose}")
    if fingerprint.primary_language:
        lines.append(f"Primary language: {fingerprint.primary_language}")
    if fingerprint.frameworks:
        lines.append(f"Frameworks: {', '.join(fingerprint.frameworks[:4])}")
    if technologies:
        lines.append(f"Supporting technologies: {', '.join(technologies[:4])}")
    if quality_signals:
        lines.append(f"Quality signals: {', '.join(quality_signals[:3])}")
    if fingerprint.main_dependencies:
        lines.append(f"Manifest dependencies: {', '.join(fingerprint.main_dependencies[:5])}")
    if entrypoints:
        lines.append(f"Main entry point: `{entrypoints[0].relpath.as_posix()}`")
    if fingerprint.scripts:
        lines.append(f"Manifest scripts: {', '.join(fingerprint.scripts[:4])}")
    if important_files:
        core_names = pick_core_module_descriptors(important_files, fingerprint.project_type)
        fallback_core = [
            f"{item.path.stem.replace('_', ' ')} (`{item.relpath.as_posix()}`)"
            for item in important_files
            if not is_test_file(item.relpath)
        ]
        core = join_natural_list(core_names) if core_names else join_natural_list(fallback_core[:4])
        lines.append(f"Core modules: {core}")
    if any("test" in item.tags for item in selected_files):
        tested = [item.path.name for item in selected_files if "test" in item.tags and item.path.stem.startswith("test")]
        lines.append(f"Tests found in: {', '.join(tested)}")
    return lines[:10]


def detect_project_shape(fingerprint: ProjectFingerprint) -> str:
    return fingerprint.project_type or "developer-facing software project"


def is_packaging_helper(item: FileInsight) -> bool:
    name = item.path.name.lower()
    if name in {"build.bat", "build.sh", "version_info.txt"}:
        return True
    if name.endswith(".spec"):
        return True
    return False


def has_related_project_test(item: FileInsight, tests: list[FileInsight]) -> bool:
    if "test" in item.tags:
        return False
    for candidate in tests:
        if test_relation_score(item, candidate) >= 4:
            return True
    return False


def compute_risk_score(
    item: FileInsight,
    all_files: list[FileInsight],
    changed_paths: set[Path],
    reverse_index: dict[str, set[str]],
    fingerprint: ProjectFingerprint | None = None,
) -> RiskInsight:
    risk = RiskInsight()
    path = item.relpath.as_posix().lower()
    content = item.content.lower()
    role = item.summary.lower()
    tests = [candidate for candidate in all_files if "test" in candidate.tags]
    changed = item.path.resolve() in changed_paths
    dependents = len(reverse_index.get(item.relpath.as_posix(), set()))
    packaging_helper = is_packaging_helper(item)

    def add(points: float, reason: str, flag: str | None = None) -> None:
        risk.score += points
        risk.reasons.append(reason)
        if flag and flag not in risk.risk_flags:
            risk.risk_flags.append(flag)

    size = item.line_count or 0
    if size > 1200:
        add(4.0, "very large file", "size")
    elif size > 900:
        add(3.0, "large file", "size")
    elif size > 600:
        add(2.0, "moderately large file", "size")
    elif size > 300:
        add(1.0, "non-trivial file size", "size")

    if changed:
        add(4.0, "changed file", "changed")

    if dependents >= 4:
        add(3.0, "shared dependency", "shared_impact")
    elif dependents >= 2:
        add(2.0, "used by multiple selected files", "shared_impact")

    if (
        "entrypoint" in item.tags
        or path.endswith("/page.tsx")
        or path.endswith("/page.jsx")
        or path.endswith("/index.php")
    ):
        add(1.5, "user-facing entry flow", "user_flow")

    path_submission_hint = any(token in path for token in ("/form", "/contact", "/checkout", "/register", "/signup", "/salvar", "/save", "/submit"))
    content_submission_hint = (
        "<form" in content
        or "onsubmit" in content
        or "handlechange" in content
        or "request.method == 'post'" in content
        or "$_post" in content
        or "htmlspecialchars($_post" in content
        or "header('location:" in content
    )
    if not packaging_helper and (path_submission_hint or content_submission_hint):
        add(2.0, "input or submission flow", "input_flow")

    if any(token in path for token in ("auth", "locale", "translations", "settings", "config")):
        add(2.0, "shared app-wide behavior", "shared_state")
    elif "translation hooks" in role or "localization" in role:
        add(2.0, "shared app-wide behavior", "shared_state")

    if (
        "service-layer" in role
        or "service layer" in role
        or "service" in path
        or "dao" in path
        or "repository" in path
        or "persistence" in role
        or "business" in role
    ):
        add(2.0, "business or persistence logic", "business_logic")

    if not packaging_helper and not has_related_project_test(item, tests) and "test" not in item.tags and "docs" not in item.tags:
        add(2.0, "no obvious nearby test coverage", "coverage_gap")

    if "embedded_asset" in item.tags:
        add(1.0, "embedded asset payload", "embedded_asset")

    if not packaging_helper and (
        (item.lang in {"tsx", "jsx"} and size >= 220 and ("<" in item.content and ("return (" in content or "return <" in content)))
        or ("ui" in item.tags and ("threading" in content or "subprocess" in content))
        or (item.lang == "php" and "<html" in content and ("service" in content or "require_once" in content))
    ):
        add(2.0, "mixed responsibilities", "mixed_concerns")

    if fingerprint and fingerprint.project_type == "Desktop GUI + CLI developer tool":
        if "ui" in item.tags and "threading" in content:
            add(1.5, "GUI and background coordination", "mixed_concerns")
        if {"analysis", "scanner"} & item.tags and ("re." in item.content or "re.search" in item.content or "re.findall" in item.content):
            add(1.5, "regex-heavy heuristics", "heuristics")
        if item.path.name.lower() == "context_engine.py":
            add(1.5, "broad analysis engine impact", "shared_impact")
        if item.path.name.lower() == "renderer.py":
            add(1.5, "output-shaping module", "shared_impact")

    if packaging_helper and not changed:
        risk.score = max(0.0, risk.score - 1.5)

    return RiskInsight(
        score=round(risk.score, 2),
        reasons=list(dict.fromkeys(risk.reasons))[:6],
        risk_flags=risk.risk_flags[:6],
    )


def build_risks(
    insights: list[FileInsight],
    reverse_index: dict[str, set[str]],
    all_insights: list[FileInsight] | None = None,
    fingerprint: ProjectFingerprint | None = None,
) -> list[str]:
    risks: list[str] = []
    scope = all_insights or insights
    for item in sorted(insights, key=lambda entry: (-entry.line_count, entry.relpath.as_posix()))[:3]:
        if item.line_count >= 220:
            dependents = len(reverse_index[item.relpath.as_posix()])
            if dependents >= 2:
                risks.append(f"`{item.relpath.as_posix()}` is both large ({item.line_count} lines) and central to the graph, so regressions here can spread quickly.")
            else:
                risks.append(f"`{item.relpath.as_posix()}` is relatively large ({item.line_count} lines) and may be a change hotspot.")

    for item in sorted(insights, key=lambda entry: (-len(reverse_index[entry.relpath.as_posix()]), entry.relpath.as_posix()))[:3]:
        dependents = len(reverse_index[item.relpath.as_posix()])
        if dependents >= 2:
            risks.append(f"`{item.relpath.as_posix()}` sits on a central path and is depended on by {dependents} file(s).")

    for item in insights:
        if "async" in item.tags or ("ui" in item.tags and "threading" in item.content):
            risks.append(f"`{item.relpath.as_posix()}` mixes UI and background work, so race conditions or state sync bugs are worth watching.")
        if "integration" in item.tags and "test" not in item.tags:
            risks.append(f"`{item.relpath.as_posix()}` touches process or git integration, which is often sensitive to environment differences.")
        if {"analysis", "scanner"} & item.tags and ("re." in item.content or "re.findall" in item.content or "re.search" in item.content):
            risks.append(f"`{item.relpath.as_posix()}` relies on regex-heavy heuristics, so false positives or false negatives are a realistic maintenance risk.")
        if len(risks) >= 5:
            break

    if not any("test" in item.tags for item in scope):
        risks.append("No obvious automated tests were detected in the scanned project, so behavior changes may be harder to verify safely.")

    config_like_count = sum(
        1
        for item in scope
        if "config" in item.tags
        or item.path.name.lower() in IDENTITY_FILE_WEIGHTS
        or any(item.path.name.lower().endswith(suffix) for suffix in IDENTITY_SUFFIX_WEIGHTS)
    )
    if config_like_count >= 4 and config_like_count >= max(4, len(scope) // 3):
        risks.append("This project is relatively config-heavy, so small manifest or environment changes can have outsized runtime impact.")

    translation_candidates = [
        item for item in scope
        if "translation" in item.summary.lower() or "locale" in item.summary.lower() or "translations" in item.path.name.lower()
    ]
    for item in translation_candidates:
        if item.line_count >= 180:
            risks.append(f"`{item.relpath.as_posix()}` is a large localization dictionary, so copy changes or missing keys can ripple across many screens.")
            break

    provider_candidates = [
        item for item in scope
        if ("context" in item.path.stem.lower() or "provider" in item.path.stem.lower())
        and item.lang in {"tsx", "jsx", "ts", "js"}
        and len(reverse_index[item.relpath.as_posix()]) >= 3
    ]
    for item in provider_candidates:
        dependent_pages = [
            dep for dep in reverse_index[item.relpath.as_posix()]
            if dep.endswith(("/page.tsx", "/page.jsx"))
        ]
        if len(dependent_pages) >= 2:
            risks.append(
                f"`{item.relpath.as_posix()}` feeds state into multiple routed pages, so changes here can affect several user-facing flows at once."
            )
            break

    if fingerprint and fingerprint.project_type == "Desktop GUI + CLI developer tool":
        gui_count = sum(1 for item in scope if "ui" in item.tags or "theme" in item.tags)
        if gui_count >= 2 and any("cli" in item.tags for item in scope):
            risks.append("The project spans both GUI and CLI flows, so changes in shared helpers can break more than one execution path.")

    return list(dict.fromkeys(risks))[:7]


def build_relationship_map(selected_files: list[FileInsight], reverse_index: dict[str, set[str]]) -> list[str]:
    rels: list[str] = []
    selected_lookup = {item.relpath.as_posix(): item for item in selected_files}
    selected_tests = [item for item in selected_files if "test" in item.tags]
    for item in selected_files:
        for target in item.local_imports[:3]:
            if target in selected_lookup:
                target_item = selected_lookup[target]
                if "config" in target_item.tags:
                    rels.append(f"`{item.relpath.as_posix()}` uses config from `{target}`")
                else:
                    rels.append(f"`{item.relpath.as_posix()}` imports directly from `{target}`")
        if "test" in item.tags:
            continue
        related_tests = [
            candidate.relpath.as_posix()
            for candidate in selected_tests
            if is_explicit_test_cover(item, candidate)
        ]
        for test_path in sorted(related_tests)[:2]:
            rels.append(f"`{item.relpath.as_posix()}` is likely tested by `{test_path}`")
    return list(dict.fromkeys(rels))[:10]


def infer_selection_reasons(
    item: FileInsight,
    selected_files: list[FileInsight],
    config: ExportConfig,
    changed_paths: set[Path],
    reverse_index: dict[str, set[str]],
    diff_fallback: bool = False,
) -> list[str]:
    reasons: list[str] = []
    changed_relpaths = {
        selected.relpath.as_posix()
        for selected in selected_files
        if selected.path.resolve() in changed_paths
    }
    selected_tests = [candidate for candidate in selected_files if "test" in candidate.tags]

    if "entrypoint" in item.tags:
        reasons.append("entrypoint")
    if item.path.resolve() in changed_paths:
        reasons.append("changed file")
    if item.matched_focus:
        reasons.append("matched focus")
    if "test" in item.tags:
        if any(test_relation_score(other, item) >= 4 for other in selected_files if "test" not in other.tags):
            reasons.append("related test")
    if "docs" in item.tags:
        reasons.append("documentation")
    if item.dependents >= 2 and "test" not in item.tags and "docs" not in item.tags:
        reasons.append("central dependency")

    if changed_relpaths and item.relpath.as_posix() not in changed_relpaths:
        touches_changed = any(target in changed_relpaths for target in item.local_imports)
        touched_by_changed = any(dep in changed_relpaths for dep in reverse_index.get(item.relpath.as_posix(), set()))
        if touches_changed or touched_by_changed:
            reasons.append("related to changed files")

    if diff_fallback and not changed_relpaths:
        if "test" in item.tags:
            reasons.append("diff fallback related test")
        elif "docs" in item.tags:
            reasons.append("diff fallback supporting context")
        elif "entrypoint" in item.tags or item.dependents >= 2:
            reasons.append("diff fallback central file")
        else:
            reasons.append("diff fallback nearby context")

    if config.context_mode == "onboarding" and not reasons and "docs" not in item.tags:
        reasons.append("onboarding mode picked central file")
    elif config.task_profile == "risk_analysis" and not reasons:
        if item.risk_score >= 6:
            reasons.append("risk hotspot")
        elif any(flag in item.risk_flags for flag in ("shared_impact", "shared_state")):
            reasons.append("broad impact area")
        elif "test" in item.tags:
            reasons.append("risk verification path")
        else:
            reasons.append("maintenance weak spot")
    elif config.context_mode == "feature" and not reasons:
        reasons.append("supports the focused area")
    elif config.context_mode == "refactor" and not reasons:
        reasons.append("high-leverage refactor candidate")
    elif config.context_mode == "debug" and not reasons:
        reasons.append("debug context support")
    elif config.context_mode == "full" and not reasons:
        reasons.append("full context keeps the complete project payload")

    if not reasons and "test" in item.tags and selected_tests:
        reasons.append("selected test coverage")
    if not reasons:
        reasons.append("high score")

    return list(dict.fromkeys(reasons))[:3]


def build_folder_summaries(selected_files: list[FileInsight]) -> list[str]:
    groups: dict[str, list[FileInsight]] = defaultdict(list)
    for item in selected_files:
        top = item.relpath.parts[0] if len(item.relpath.parts) > 1 else "."
        groups[top].append(item)

    summaries: list[str] = []
    for folder, items in sorted(groups.items()):
        if folder == ".":
            focus = ", ".join(entry.path.name for entry in items[:3])
            summaries.append(f"root: contains key top-level files such as {focus}.")
            continue
        tags = Counter(tag for item in items for tag in item.tags)
        if "test" in tags:
            summaries.append(f"{folder}/: groups {len(items)} selected file(s) and mainly handles automated coverage.")
        elif "ui" in tags:
            summaries.append(f"{folder}/: groups {len(items)} selected file(s) focused on interface and presentation.")
        elif "config" in tags:
            summaries.append(f"{folder}/: groups {len(items)} selected file(s) with config and environment setup.")
        else:
            names = ", ".join(entry.path.name for entry in items[:3])
            summaries.append(f"{folder}/: contains {len(items)} selected file(s), including {names}.")
    return summaries[:6]


def select_files(
    insights: list[FileInsight],
    config: ExportConfig,
    changed_paths: set[Path],
    reverse_index: dict[str, set[str]],
) -> list[FileInsight]:
    lookup = {item.relpath.as_posix(): item for item in insights}
    docs = [item for item in insights if "docs" in item.tags]
    tests = [item for item in insights if "test" in item.tags]
    important = sorted(insights, key=lambda item: (-item.score, item.relpath.as_posix()))
    focus_matches = [item for item in important if item.matched_focus]
    changed = [item for item in important if item.path.resolve() in changed_paths]

    if config.task_profile == "risk_analysis":
        return select_risk_files(config, lookup, important, changed, tests, reverse_index)
    if config.task_profile == "write_tests":
        return select_write_tests_files(config, lookup, important, focus_matches, tests)
    if config.task_profile == "find_dead_code":
        return select_dead_code_files(config, lookup, important, docs, tests)
    if config.context_mode == "diff":
        return select_diff_files(insights, config, changed_paths, reverse_index, lookup, changed, tests)
    if config.context_mode == "onboarding":
        return select_onboarding_files(insights, config, lookup, important, docs, tests, reverse_index)
    if config.context_mode == "debug":
        return select_debug_files(config, lookup, important, focus_matches, changed, tests, reverse_index)
    if config.context_mode == "feature":
        return select_feature_files(config, lookup, important, focus_matches, docs, tests, reverse_index)
    if config.context_mode == "refactor":
        return select_refactor_files(config, lookup, important, tests, reverse_index)
    if config.context_mode == "full":
        return important

    selected: set[str] = {item.relpath.as_posix() for item in important[:12]}
    selected = add_related_tests(selected, lookup, tests)
    ordered = [lookup[rel] for rel in selected if rel in lookup]
    ordered.sort(key=lambda item: (-item.score, item.relpath.as_posix()))
    return ordered[:20]


def add_related_tests(
    selected: set[str],
    lookup: dict[str, FileInsight],
    tests: list[FileInsight],
    limit: int = 4,
    min_score: int = 4,
    allow_token_fallback: bool = True,
) -> set[str]:
    related_targets = [lookup[rel] for rel in selected if rel in lookup and "test" not in lookup[rel].tags]
    ranked_tests = sorted(
        tests,
        key=lambda candidate: max((test_relation_score(target, candidate) for target in related_targets), default=0),
        reverse=True,
    )
    for item in ranked_tests[:limit]:
        best_score = max((test_relation_score(target, item) for target in related_targets), default=0)
        if best_score >= min_score or (
            allow_token_fallback and any(token in item.relpath.as_posix().lower() for token in derive_selected_tokens(selected))
        ):
            selected.add(item.relpath.as_posix())
    return selected


def select_onboarding_files(
    insights: list[FileInsight],
    config: ExportConfig,
    lookup: dict[str, FileInsight],
    important: list[FileInsight],
    docs: list[FileInsight],
    tests: list[FileInsight],
    reverse_index: dict[str, set[str]],
) -> list[FileInsight]:
    selected: set[str] = set()
    non_test_core = [item for item in important if "test" not in item.tags and "docs" not in item.tags]
    for item in docs[:2] + detect_entrypoints(insights)[:2] + non_test_core[:5]:
        selected.add(item.relpath.as_posix())
    selected = expand_with_related(selected, lookup, reverse_index, include_dependents=False)
    selected = add_related_tests(selected, lookup, tests, limit=2, min_score=5, allow_token_fallback=False)
    ordered = [lookup[rel] for rel in selected if rel in lookup]
    ordered.sort(
        key=lambda item: (
            "docs" in item.tags,
            "test" in item.tags,
            -item.score,
            item.relpath.as_posix(),
        )
    )
    return ordered[:11]


def select_debug_files(
    config: ExportConfig,
    lookup: dict[str, FileInsight],
    important: list[FileInsight],
    focus_matches: list[FileInsight],
    changed: list[FileInsight],
    tests: list[FileInsight],
    reverse_index: dict[str, set[str]],
) -> list[FileInsight]:
    selected: set[str] = {
        item.relpath.as_posix()
        for item in (changed[:6] + focus_matches[:6] + [entry for entry in important if {"async", "integration", "analysis", "scanner"} & entry.tags][:4])
    }
    selected = expand_with_related(selected, lookup, reverse_index, include_dependents=True)
    selected = add_related_tests(selected, lookup, tests, limit=4)
    ordered = [lookup[rel] for rel in selected if rel in lookup]
    ordered.sort(
        key=lambda item: (
            item.path.resolve() not in {candidate.path.resolve() for candidate in changed},
            not item.matched_focus,
            -item.score,
            item.relpath.as_posix(),
        )
    )
    return ordered[:16]


def select_feature_files(
    config: ExportConfig,
    lookup: dict[str, FileInsight],
    important: list[FileInsight],
    focus_matches: list[FileInsight],
    docs: list[FileInsight],
    tests: list[FileInsight],
    reverse_index: dict[str, set[str]],
) -> list[FileInsight]:
    selected: set[str] = {item.relpath.as_posix() for item in (focus_matches[:8] or important[:6])}
    if not focus_matches and docs:
        selected.add(docs[0].relpath.as_posix())
    selected = expand_with_related(selected, lookup, reverse_index, include_dependents=True)
    selected = add_related_tests(selected, lookup, tests, limit=4)
    ordered = [lookup[rel] for rel in selected if rel in lookup]
    ordered.sort(key=lambda item: (not item.matched_focus, -item.score, item.relpath.as_posix()))
    return ordered[:14]


def select_refactor_files(
    config: ExportConfig,
    lookup: dict[str, FileInsight],
    important: list[FileInsight],
    tests: list[FileInsight],
    reverse_index: dict[str, set[str]],
) -> list[FileInsight]:
    central = [item for item in important if "test" not in item.tags and "docs" not in item.tags][:10]
    selected: set[str] = {item.relpath.as_posix() for item in central}
    selected = expand_with_related(selected, lookup, reverse_index, include_dependents=True)
    selected = add_related_tests(selected, lookup, tests, limit=4)
    ordered = [lookup[rel] for rel in selected if rel in lookup]
    ordered.sort(key=lambda item: (-item.dependents, -item.score, item.relpath.as_posix()))
    return ordered[:16]


def select_write_tests_files(
    config: ExportConfig,
    lookup: dict[str, FileInsight],
    important: list[FileInsight],
    focus_matches: list[FileInsight],
    tests: list[FileInsight],
) -> list[FileInsight]:
    behavior_heavy = [
        item for item in important
        if "test" not in item.tags and ("integration" in item.tags or "analysis" in item.tags or item.line_count >= 80)
    ]
    selected: set[str] = {
        item.relpath.as_posix()
        for item in (focus_matches[:4] + behavior_heavy[:8] + [item for item in important if "entrypoint" in item.tags][:2])
    }
    selected = add_related_tests(selected, lookup, tests, limit=6)
    ordered = [lookup[rel] for rel in selected if rel in lookup]
    ordered.sort(key=lambda item: ("test" in item.tags, -item.score, item.relpath.as_posix()))
    return ordered[:16]


def select_risk_files(
    config: ExportConfig,
    lookup: dict[str, FileInsight],
    important: list[FileInsight],
    changed: list[FileInsight],
    tests: list[FileInsight],
    reverse_index: dict[str, set[str]],
) -> list[FileInsight]:
    ranked_by_risk = sorted(
        [item for item in important if "docs" not in item.tags],
        key=lambda item: (
            item.path.resolve() not in {candidate.path.resolve() for candidate in changed},
            -item.risk_score,
            -item.score,
            item.relpath.as_posix(),
        ),
    )
    selected: set[str] = set()

    if changed:
        for item in ranked_by_risk[:10]:
            if item.path.resolve() in {candidate.path.resolve() for candidate in changed}:
                selected.add(item.relpath.as_posix())
        for item in changed[:8]:
            for target in item.local_imports[:3]:
                target_item = lookup.get(target)
                if target_item and "docs" not in target_item.tags and target_item.risk_score >= 2:
                    selected.add(target)
            for dependent in sorted(reverse_index.get(item.relpath.as_posix(), set())):
                dependent_item = lookup.get(dependent)
                if dependent_item and "docs" not in dependent_item.tags and dependent_item.risk_score >= 2:
                    selected.add(dependent)
                if len(selected) >= 12:
                    break
    else:
        for item in ranked_by_risk[:10]:
            if "test" not in item.tags:
                selected.add(item.relpath.as_posix())
        for item in ranked_by_risk:
            if any(flag in item.risk_flags for flag in ("shared_impact", "shared_state", "business_logic", "input_flow")):
                selected.add(item.relpath.as_posix())
            if len(selected) >= 12:
                break

    selected = add_related_tests(selected, lookup, tests, limit=4, min_score=4, allow_token_fallback=False)
    ordered = [lookup[rel] for rel in selected if rel in lookup]
    ordered.sort(
        key=lambda item: (
            item.path.resolve() not in {candidate.path.resolve() for candidate in changed},
            "test" in item.tags,
            "docs" in item.tags,
            -item.risk_score,
            -item.score,
            item.relpath.as_posix(),
        )
    )
    return ordered[:14]


def select_dead_code_files(
    config: ExportConfig,
    lookup: dict[str, FileInsight],
    important: list[FileInsight],
    docs: list[FileInsight],
    tests: list[FileInsight],
) -> list[FileInsight]:
    low_signal = sorted(
        [item for item in important if "docs" not in item.tags and "test" not in item.tags],
        key=lambda item: (
            "entrypoint" in item.tags,
            item.dependents,
            item.score,
            item.relpath.as_posix(),
        ),
    )
    selected: set[str] = {item.relpath.as_posix() for item in low_signal[:10]}
    for item in docs[:1] + tests[:1]:
        selected.add(item.relpath.as_posix())
    ordered = [lookup[rel] for rel in selected if rel in lookup]
    ordered.sort(key=lambda item: (item.dependents, item.score, item.relpath.as_posix()))
    return ordered[:14]


def select_diff_files(
    insights: list[FileInsight],
    config: ExportConfig,
    changed_paths: set[Path],
    reverse_index: dict[str, set[str]],
    lookup: dict[str, FileInsight],
    changed: list[FileInsight],
    tests: list[FileInsight],
) -> list[FileInsight]:
    if not changed:
        return []

    selected: set[str] = {item.relpath.as_posix() for item in changed[:10]}
    changed_relpaths = set(selected)

    for item in changed[:8]:
        for target in item.local_imports[:2]:
            target_item = lookup.get(target)
            if not target_item or "docs" in target_item.tags:
                continue
            selected.add(target)
        for dependent in sorted(reverse_index.get(item.relpath.as_posix(), set())):
            dependent_item = lookup.get(dependent)
            if not dependent_item or "docs" in dependent_item.tags:
                continue
            if dependent_item.score >= 5 or dependent_item.matched_focus:
                selected.add(dependent)
            if len([rel for rel in selected if rel not in changed_relpaths]) >= 6:
                break

    related_targets = [lookup[rel] for rel in selected if rel in lookup and "test" not in lookup[rel].tags]
    ranked_tests = sorted(
        tests,
        key=lambda candidate: max((test_relation_score(target, candidate) for target in related_targets), default=0),
        reverse=True,
    )
    for item in ranked_tests[:4]:
        best_score = max((test_relation_score(target, item) for target in related_targets), default=0)
        if best_score >= 4:
            selected.add(item.relpath.as_posix())

    if config.task_profile in {"code_review", "pr_summary"}:
        cap = 12
    else:
        cap = 14

    ordered = [lookup[rel] for rel in selected if rel in lookup]
    ordered.sort(key=lambda item: (-item.score, item.relpath.as_posix()))
    return ordered[:cap]


def select_diff_fallback_files(
    insights: list[FileInsight],
    lookup: dict[str, FileInsight],
    reverse_index: dict[str, set[str]],
    tests: list[FileInsight],
) -> list[FileInsight]:
    important = sorted(insights, key=lambda item: (-item.score, item.relpath.as_posix()))
    selected: set[str] = set()

    for item in detect_entrypoints(insights)[:2]:
        selected.add(item.relpath.as_posix())

    for item in important:
        if "test" in item.tags or "docs" in item.tags:
            continue
        selected.add(item.relpath.as_posix())
        if len(selected) >= 8:
            break

    selected = add_related_tests(selected, lookup, tests, limit=2, min_score=4, allow_token_fallback=False)

    if not any(rel.lower().endswith("readme.md") for rel in selected):
        readme = next((item for item in important if item.path.name.lower() == "readme.md"), None)
        if readme:
            selected.add(readme.relpath.as_posix())

    ordered = [lookup[rel] for rel in selected if rel in lookup]
    ordered.sort(
        key=lambda item: (
            "entrypoint" not in item.tags,
            "docs" in item.tags,
            item.path.name.lower().startswith("test_"),
            -item.score,
            item.relpath.as_posix(),
        )
    )
    return ordered[:10]


def derive_selected_tokens(selected: set[str]) -> set[str]:
    tokens: set[str] = set()
    for rel in selected:
        path = Path(rel)
        tokens.add(path.stem.lower().replace("test_", ""))
    return tokens


def expand_with_related(
    selected: set[str],
    lookup: dict[str, FileInsight],
    reverse_index: dict[str, set[str]],
    include_dependents: bool = False,
) -> set[str]:
    expanded = set(selected)
    for rel in list(selected):
        item = lookup.get(rel)
        if not item:
            continue
        for target in item.local_imports[:4]:
            expanded.add(target)
        if include_dependents:
            for dependent in list(reverse_index.get(rel, set()))[:3]:
                expanded.add(dependent)
    return expanded


def build_task_prompt(project_path: Path, config: ExportConfig) -> str:
    task_guidance = TASK_GUIDANCE.get(config.task_profile, TASK_GUIDANCE["general"])
    user_goal = config.system_prompt.strip()
    focus = config.focus_query.strip()

    prompt = f"You are reviewing the {project_path.name} project. {task_guidance}"
    if config.task_profile == "explain_project":
        prompt += " Start from the architecture summary and main execution flow before diving into file details."
    elif config.task_profile == "bug_report":
        prompt += " Prioritize changed files, hotspots, subprocess or threading risks, and the most likely failure path."
    elif config.task_profile == "code_review":
        prompt += " Lead with bugs, regressions, missing tests, and risky assumptions before proposing improvements."
    elif config.task_profile == "pr_summary":
        prompt += " Start with what changed, then explain the local impact, review surface, and any important follow-up concerns."
    elif config.task_profile == "risk_analysis":
        prompt += " Prioritize likely regression hotspots, shared dependencies, missing tests, mixed responsibilities, and user-facing flows. Treat findings as risk hints, not confirmed defects."
    elif config.task_profile == "write_tests":
        prompt += " Look for uncovered behaviors, boundary cases, and central modules without obvious direct test coverage."
    elif config.task_profile == "refactor_request":
        prompt += " Focus on coupling, central modules, safer refactor seams, and the smallest sequence of changes that would reduce risk."
    elif config.task_profile == "find_dead_code":
        prompt += " Treat dead-code signals as hypotheses, show the evidence, and call out likely false positives before suggesting removal."
    elif config.task_profile == "ai_handoff":
        prompt += " Use the handoff summary, read-this-first list, and file selection reasons before reading the raw payload."
    if focus:
        prompt += f" Focus especially on: {focus}."
    if user_goal:
        prompt += f" User goal: {user_goal}."
    return prompt.strip()


def extract_signatures(item: FileInsight) -> list[str]:
    signatures: list[str] = []
    lines = item.content.splitlines()

    if item.lang == "python":
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("def ") or stripped.startswith("async def ") or stripped.startswith("class "):
                signatures.append(stripped)
    elif item.lang in {"javascript", "jsx", "typescript", "tsx"}:
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("export ") or stripped.startswith("function ") or stripped.startswith("class "):
                signatures.append(stripped)

    return signatures[:18]


def extract_relevant_excerpt(item: FileInsight, query: str, max_lines: int = 90) -> tuple[str, str]:
    lines = item.content.splitlines()
    keywords = extract_keywords(query)
    if not lines:
        return "", "No textual content available."

    if "embedded_asset" in item.tags:
        excerpt = build_embedded_asset_excerpt(item)
        reason = "Embedded asset payload omitted because the file mostly stores inline binary/base64 data."
        return excerpt, reason

    if not keywords:
        excerpt, omitted_blob = sanitize_excerpt_lines(item, lines[:max_lines])
        if not excerpt:
            return "<excerpt omitted>", "Opening excerpt omitted because the file content is not useful as readable source."
        reason = "Opening excerpt shown because no focus keywords were provided."
        if omitted_blob:
            reason += " Embedded blob lines were omitted."
        return "\n".join(excerpt), reason

    matches: list[int] = []
    for idx, line in enumerate(lines):
        lower = line.lower()
        if any(keyword in lower for keyword in keywords):
            matches.append(idx)

    if not matches:
        symbol_matches = [
            symbol
            for symbol in item.functions[:8] + item.classes[:6]
            if any(keyword in symbol.lower() for keyword in keywords)
        ]
        if symbol_matches:
            excerpt_lines = [
                stripped
                for stripped in extract_signatures(item)
                if any(symbol in stripped for symbol in symbol_matches)
            ]
            if excerpt_lines:
                return "\n".join(excerpt_lines[:max_lines]), f"Focused excerpt based on matching symbols: {', '.join(symbol_matches[:4])}."
        excerpt, omitted_blob = sanitize_excerpt_lines(item, lines[:max_lines])
        if not excerpt:
            return "<excerpt omitted>", "Opening excerpt omitted because the file content is not useful as readable source."
        reason = "Opening excerpt shown because no focus match was found in the file."
        if omitted_blob:
            reason += " Embedded blob lines were omitted."
        return "\n".join(excerpt), reason

    gathered: list[str] = []
    used: set[int] = set()
    for idx in matches[:8]:
        start = max(0, idx - 2)
        end = min(len(lines), idx + 3)
        for line_no in range(start, end):
            if line_no not in used:
                gathered.append(lines[line_no])
                used.add(line_no)
            if len(gathered) >= max_lines:
                break
        if len(gathered) >= max_lines:
            break
    gathered, omitted_blob = sanitize_excerpt_lines(item, gathered[:max_lines])
    if not gathered:
        return "<excerpt omitted>", "Focused excerpt omitted because the matching content was not useful as readable source."
    reason = f"Focused excerpt based on keywords: {', '.join(keywords[:4])}."
    if omitted_blob:
        reason += " Embedded blob lines were omitted."
    return "\n".join(gathered[:max_lines]), reason
