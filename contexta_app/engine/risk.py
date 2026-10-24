"""contexta_app.engine.risk: split out of context_engine.py. Bodies are unchanged."""

from __future__ import annotations

from pathlib import Path

from contexta_app.engine.constants import (
    IDENTITY_FILE_WEIGHTS,
    IDENTITY_SUFFIX_WEIGHTS,
)
from contexta_app.engine.models import (
    FileInsight,
    ProjectFingerprint,
    RiskInsight,
)
from contexta_app.engine.relations import (
    _tagged_tests,
    has_related_project_test,
    is_explicit_test_cover,
)
from contexta_app.engine.roles import (
    infer_file_role,
)
from contexta_app.engine.surfaces import (
    is_background_coordination_surface,
    is_dependency_manifest_surface,
    is_packaging_helper,
    is_public_api_surface,
    is_request_boundary_surface,
    is_runtime_config_surface,
    is_runtime_entry_surface,
    is_schema_surface,
    is_shared_state_surface,
    is_user_facing_surface,
    looks_like_input_flow,
)

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
    role = (item.summary or infer_file_role(item, fingerprint.project_type if fingerprint else None)).lower()
    tests = _tagged_tests(all_files)
    changed = item.resolved in changed_paths
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

    if is_user_facing_surface(item, fingerprint):
        add(1.5, "user-facing entry flow", "user_flow")
    elif is_request_boundary_surface(item, fingerprint):
        add(1.5, "request or routing boundary", "request_boundary")
    elif is_runtime_entry_surface(item, fingerprint):
        add(1.5, "runtime entry or bootstrapping surface", "entry_surface")

    if not packaging_helper and looks_like_input_flow(item):
        add(2.0, "input or submission flow", "input_flow")

    if is_runtime_config_surface(item):
        add(2.0, "runtime or environment configuration", "config_surface")

    if is_dependency_manifest_surface(item):
        add(1.5, "dependency or build surface", "dependency_surface")
        if changed:
            add(1.0, "changed dependency or build config", "dependency_surface")

    if is_schema_surface(item, fingerprint):
        add(2.5, "schema or data model surface", "schema_surface")

    if is_shared_state_surface(item, fingerprint):
        add(2.0, "shared app-wide behavior", "shared_state")

    if is_public_api_surface(item, fingerprint):
        add(2.0, "public API surface", "public_api")

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

    if not packaging_helper and is_background_coordination_surface(item):
        add(1.5, "background or integration coordination", "async_boundary")

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

    schema_candidates = [item for item in scope if "schema_surface" in item.risk_flags]
    for item in sorted(schema_candidates, key=lambda entry: (-entry.risk_score, entry.relpath.as_posix()))[:2]:
        risks.append(
            f"`{item.relpath.as_posix()}` touches schema or data-shape behavior, so regressions here may affect persistence, compatibility, or stored data correctness."
        )

    config_candidates = [item for item in scope if any(flag in item.risk_flags for flag in ("config_surface", "dependency_surface"))]
    for item in sorted(config_candidates, key=lambda entry: (-entry.risk_score, entry.relpath.as_posix()))[:2]:
        risks.append(
            f"`{item.relpath.as_posix()}` governs runtime or dependency configuration, so small changes here can shift broad application behavior."
        )

    boundary_candidates = [item for item in scope if any(flag in item.risk_flags for flag in ("request_boundary", "user_flow"))]
    for item in sorted(boundary_candidates, key=lambda entry: (-entry.risk_score, entry.relpath.as_posix()))[:2]:
        risks.append(
            f"`{item.relpath.as_posix()}` sits on an exposed request or user-facing boundary, so regressions here are likely to surface quickly."
        )

    background_candidates = [item for item in scope if "async_boundary" in item.risk_flags]
    for item in sorted(background_candidates, key=lambda entry: (-entry.risk_score, entry.relpath.as_posix()))[:2]:
        risks.append(
            f"`{item.relpath.as_posix()}` coordinates background, async, or integration-heavy work, which can be harder to verify safely than straight-line code."
        )

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
