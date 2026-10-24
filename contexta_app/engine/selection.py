"""contexta_app.engine.selection: split out of context_engine.py. Bodies are unchanged."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from pathlib import Path

from contexta_app.engine.constants import (
    TASK_GUIDANCE,
)
from contexta_app.engine.models import (
    ExportConfig,
    FileInsight,
)
from contexta_app.engine.relations import (
    RelatedSourceIndex,
    related_test_score,
)
from contexta_app.engine.scoring import (
    detect_entrypoints,
)

@dataclass
class SelectionContext:
    """Work shared by every ``infer_selection_reasons`` call for one pack.

    Building it once keeps reason inference linear in the number of selected
    files instead of re-deriving the same sets for every file.
    """

    changed_relpaths: set[str]
    has_selected_tests: bool
    source_index: RelatedSourceIndex

def build_selection_context(selected_files: list[FileInsight], changed_paths: set[Path]) -> SelectionContext:
    changed_relpaths: set[str] = set()
    has_tests = False
    sources: list[FileInsight] = []
    for candidate in selected_files:
        if candidate.resolved in changed_paths:
            changed_relpaths.add(candidate.relpath.as_posix())
        if "test" in candidate.tags:
            has_tests = True
        else:
            sources.append(candidate)
    return SelectionContext(changed_relpaths, has_tests, RelatedSourceIndex(sources))

def infer_selection_reasons(
    item: FileInsight,
    selected_files: list[FileInsight],
    config: ExportConfig,
    changed_paths: set[Path],
    reverse_index: dict[str, set[str]],
    diff_fallback: bool = False,
    ctx: SelectionContext | None = None,
) -> list[str]:
    reasons: list[str] = []
    if ctx is None:
        ctx = build_selection_context(selected_files, changed_paths)
    changed_relpaths = ctx.changed_relpaths

    if "entrypoint" in item.tags:
        reasons.append("entrypoint")
    if item.resolved in changed_paths:
        reasons.append("changed file")
    if item.matched_focus:
        reasons.append("matched focus")
    if "test" in item.tags:
        if ctx.source_index.has_related(item):
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
        if config.focus_query.strip():
            reasons.append("supports the focused area")
        else:
            reasons.append("full context keeps the complete project payload")

    if not reasons and "test" in item.tags and ctx.has_selected_tests:
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
    changed = [item for item in important if item.resolved in changed_paths]

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
        if config.focus_query.strip():
            focused = select_focus_files(insights, config, lookup, tests, reverse_index)
            if focused:
                return focused
        return important

    selected: set[str] = {item.relpath.as_posix() for item in important[:12]}
    selected = add_related_tests(selected, lookup, tests)
    ordered = [lookup[rel] for rel in selected if rel in lookup]
    ordered.sort(key=lambda item: (-item.score, item.relpath.as_posix()))
    return ordered[:20]

FOCUS_MIN_TOP_SCORE = 2.0

FOCUS_MAX_FILES = 16

def select_focus_files(
    insights: list[FileInsight],
    config: ExportConfig,
    lookup: dict[str, FileInsight],
    tests: list[FileInsight],
    reverse_index: dict[str, set[str]],
) -> list[FileInsight]:
    """A small pack around ``--focus``: matches first, then what they import, then their tests.

    Returns an empty list when nothing matches strongly, and the caller keeps
    the normal full selection.
    """
    ranked = sorted(
        (item for item in insights if item.focus_raw > 0),
        key=lambda item: (-item.focus_raw, -item.score, item.relpath.as_posix()),
    )
    if not ranked or ranked[0].focus_raw < FOCUS_MIN_TOP_SCORE:
        return []
    top = ranked[0].focus_raw
    cutoff = max(FOCUS_MIN_TOP_SCORE, top * 0.4)
    primary = [item for item in ranked if item.focus_raw >= cutoff and "test" not in item.tags and "docs" not in item.tags]
    focus_tests = [item for item in ranked if item.focus_raw >= cutoff and "test" in item.tags]
    if not primary and not focus_tests:
        primary = [item for item in ranked if item.focus_raw >= cutoff]
    selected: set[str] = {item.relpath.as_posix() for item in primary[:8]}
    selected.update(item.relpath.as_posix() for item in focus_tests[:3])
    for item in primary[:3]:
        for target in item.local_imports[:3]:
            if target in lookup and "docs" not in lookup[target].tags and "test" not in lookup[target].tags:
                selected.add(target)
    selected = add_related_tests(selected, lookup, tests, limit=3, min_score=4, allow_token_fallback=False)
    ordered = [lookup[rel] for rel in selected if rel in lookup]
    ordered.sort(
        key=lambda item: (
            "test" in item.tags,
            "docs" in item.tags,
            -item.focus_raw,
            -item.score,
            item.relpath.as_posix(),
        )
    )
    return ordered[:FOCUS_MAX_FILES]

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
        key=lambda candidate: max((related_test_score(target, candidate) for target in related_targets), default=0),
        reverse=True,
    )
    for item in ranked_tests[:limit]:
        best_score = max((related_test_score(target, item) for target in related_targets), default=0)
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
    if not selected:
        fallback = [item for item in important if "test" not in item.tags and "docs" not in item.tags][:6]
        selected = {item.relpath.as_posix() for item in (fallback or important[:6])}
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
        if len(selected) < 3:
            for item in ranked_by_risk[:4]:
                if "test" not in item.tags and "docs" not in item.tags:
                    selected.add(item.relpath.as_posix())
                if len(selected) >= 4:
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
        key=lambda candidate: max((related_test_score(target, candidate) for target in related_targets), default=0),
        reverse=True,
    )
    for item in ranked_tests[:4]:
        best_score = max((related_test_score(target, item) for target in related_targets), default=0)
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
