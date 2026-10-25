"""contexta_app.engine.models: split out of context_engine.py. Bodies are unchanged."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from functools import cached_property
from pathlib import Path

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
    locked_fields: tuple[str, ...] = ()
    token_budget: int | None = None
    graph_signals: dict | None = None  # per-file rank / churn / focus hints from the project graph

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
    imported_names: list[str] = field(default_factory=list)  # Python: names from `from x import name`
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
    focus_raw: float = 0.0
    selection_reasons: list[str] = field(default_factory=list)
    render_compression: str | None = None
    graph_rank: float = 0.0
    graph_hot: float = 0.0
    graph_focus: float = 0.0

    @property
    def name(self) -> str:
        return self.path.name

    @cached_property
    def resolved(self) -> Path:
        """``path.resolve()`` once. It hits the filesystem, so never call it in a loop."""
        return self.path.resolve()

    @cached_property
    def content_lower(self) -> str:
        return self.content.lower()

    @cached_property
    def content_words(self) -> frozenset[str]:
        """Every maximal ``\\w+`` token in the lowercased content.

        ``re.search(r"\\bname\\b", text)`` for a word-character ``name`` is the same
        as ``name in content_words``.
        """
        return frozenset(re.findall(r"\w+", self.content_lower))

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
    dropped_files: list[FileInsight] = field(default_factory=list)
    budget_report: dict = field(default_factory=dict)
