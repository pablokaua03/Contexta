"""contexta_app.engine.pipeline: split out of context_engine.py. Bodies are unchanged."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

from contexta_app.engine.constants import (
    PACK_DEFAULTS,
)
from contexta_app.engine.models import (
    ExportConfig,
    FileInsight,
    ProjectAnalysis,
)
from contexta_app.engine.focus import (
    compute_focus_raw,
)
from contexta_app.engine.relations import (
    build_module_map,
    resolve_local_relationships,
)
from contexta_app.engine.insight import (
    flatten_tree,
    make_file_insight,
)
from contexta_app.engine.fingerprint import (
    detect_project_fingerprint,
)
from contexta_app.engine.summary import (
    build_architecture_overview,
    build_summary_lines,
    detect_quality_signals,
    detect_supporting_technologies,
)
from contexta_app.engine.scoring import (
    classify_file,
    detect_entrypoints,
    score_file,
    summarize_file,
)
from contexta_app.engine.risk import (
    build_relationship_map,
    build_risks,
    compute_risk_score,
)
from contexta_app.engine.selection import (
    build_folder_summaries,
    build_selection_context,
    build_task_prompt,
    infer_selection_reasons,
    select_diff_fallback_files,
    select_files,
)

def resolve_config(config: ExportConfig) -> ExportConfig:
    resolved = replace(config)
    locked = set(resolved.locked_fields)
    if resolved.pack_profile in PACK_DEFAULTS:
        for key, value in PACK_DEFAULTS[resolved.pack_profile].items():
            if key in locked:
                continue
            setattr(resolved, key, value)
    if resolved.diff_mode and resolved.context_mode == "full" and "context_mode" not in locked:
        resolved.context_mode = "diff"
    return resolved

def build_analysis(
    project_path: Path,
    full_tree: dict,
    changed_files: list[Path] | None,
    config: ExportConfig,
    log_cb=None,
    fit_selection=None,
) -> ProjectAnalysis:
    """Analyze a scanned project.

    ``fit_selection(selected_files)`` may be passed to cut the selection down
    to a token budget. It returns ``(kept, dropped, report)`` with ``kept`` in
    rank order.
    """
    if log_cb is None:
        log_cb = lambda msg, tag="": None

    config = resolve_config(config)
    file_paths = flatten_tree(full_tree)
    insights = [make_file_insight(project_path, path) for path in file_paths]
    module_map = build_module_map(insights)
    rel_index, reverse_index = resolve_local_relationships(insights, module_map)
    changed_set = {path.resolve() for path in changed_files or []}

    signals = config.graph_signals or {}
    for insight in insights:
        insight.local_imports = sorted(rel_index[insight.relpath.as_posix()])
        insight.dependents = len(reverse_index[insight.relpath.as_posix()])
        insight.focus_raw = compute_focus_raw(insight, config.focus_query or config.system_prompt)
        hint = signals.get(insight.relpath.as_posix())
        if hint:
            insight.graph_rank = hint.get("rank", 0.0)
            insight.graph_hot = hint.get("hot", 0.0)
            insight.graph_focus = hint.get("focus", 0.0)
            if config.focus_query and insight.graph_focus:
                insight.focus_raw += 1.5 * insight.graph_focus
        insight.focus_score = round(min(insight.focus_raw, 6.0), 2)
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
    dropped_files: list[FileInsight] = []
    budget_report: dict = {}
    if fit_selection is not None and selected_files:
        selected_files, dropped_files, budget_report = fit_selection(selected_files)
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

    selection_ctx = build_selection_context(selected_files, changed_set)
    for item in selected_files:
        item.selection_reasons = infer_selection_reasons(
            item,
            selected_files,
            config,
            changed_set,
            reverse_index,
            diff_fallback=bool(diff_fallback_notice),
            ctx=selection_ctx,
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
        dropped_files=dropped_files,
        budget_report=budget_report,
    )
