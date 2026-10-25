"""
context_engine.py - Public facade for the analysis engine.

The code lives in ``contexta_app.engine.*``:

    constants     tables and tuning data
    models        ExportConfig, FileInsight, ProjectAnalysis and friends
    blobs         embedded-asset and blob detection, excerpt sanitizing
    focus         ``--focus`` matching and scoring
    manifests     package manifest parsing and dependency names
    relations     import resolution, test <-> source matching
    insight       reading a file into a FileInsight
    roles         what each file is for, in words
    surfaces      request boundary, schema, config... classifiers
    fingerprint   project type, stack and purpose
    summary       project summary and architecture text
    scoring       file classification and scoring
    risk          risk scores and relationship maps
    selection     which files go in the pack
    excerpts      signatures and relevant excerpts
    pipeline      build_analysis, which ties it together

Every name that used to live here is re-exported, so existing imports keep working.
"""

from __future__ import annotations

from contexta_app.engine.constants import (  # noqa: F401
    AI_PROFILE_OPTIONS,
    APP_NAME,
    CAMEL_CASE_TOKEN_RE,
    CODE_LANGUAGE_WEIGHTS,
    COMPRESSION_OPTIONS,
    CONTEXT_MODE_OPTIONS,
    DOC_FILENAMES,
    DOMAIN_HINTS,
    FRONTEND_PAGE_LANGS,
    IDENTITY_FILE_WEIGHTS,
    IDENTITY_PREFIX_WEIGHTS,
    IDENTITY_SUFFIX_WEIGHTS,
    MODEL_PROMPT_GUIDANCE,
    PACK_DEFAULTS,
    PACK_OPTIONS,
    PROJECT_TYPE_LABELS,
    PROJECT_TYPE_RULES,
    ROUTE_ROLE_PATTERNS,
    ROUTE_STOPWORDS,
    STOPWORDS,
    TASK_GUIDANCE,
    TASK_PROFILE_OPTIONS,
    TECH_LABELS,
    UNICODE_ALPHA_TOKEN_RE,
    extract_alpha_tokens,
    normalized_name_similarity,
)
from contexta_app.engine.models import (  # noqa: F401
    ExportConfig,
    FileInsight,
    FileSignals,
    ProjectAnalysis,
    ProjectFingerprint,
    RiskInsight,
)
from contexta_app.engine.blobs import (  # noqa: F401
    _strip_wrapping_quotes,
    build_embedded_asset_excerpt,
    has_embedded_asset_payload,
    is_blob_like_line,
    sanitize_excerpt_lines,
    should_sanitize_blob_excerpt,
)
from contexta_app.engine.focus import (  # noqa: F401
    _keyword_forms,
    compute_focus_raw,
    compute_focus_score,
    extract_keywords,
    matches_focus,
)
from contexta_app.engine.manifests import (  # noqa: F401
    get_dependency_names,
    identity_weight_for,
    parse_cargo_document,
    parse_csproj_scripts,
    parse_gemfile_dependencies,
    parse_go_mod_dependencies,
    parse_gradle_dependencies,
    parse_gradle_scripts,
    parse_json_dependencies,
    parse_json_document,
    parse_manifest_scripts,
    parse_mix_dependencies,
    parse_package_scripts,
    parse_pom_scripts,
    parse_pubspec_dependencies,
    parse_pyproject_dependencies,
    parse_pyproject_document,
    parse_pyproject_scripts,
    parse_requirements_dependencies,
    parse_toml_section_keys,
    parse_xml_document,
    parse_xml_package_references,
)
from contexta_app.engine.relations import (  # noqa: F401
    RelatedSourceIndex,
    RelatedTestIndex,
    _TAGGED_TESTS_CACHE,
    _TEST_INDEX_CACHE,
    _dotted_suffixes,
    _module_name,
    _symbol_names,
    _tagged_tests,
    _test_target_stems,
    build_module_map,
    has_related_project_test,
    is_explicit_test_cover,
    is_named_test_for,
    is_related_test_for,
    is_test_file,
    related_test_index,
    related_test_score,
    resolve_local_import,
    resolve_local_relationships,
    resolve_related_tests,
    test_relation_score,
)
from contexta_app.engine.insight import (  # noqa: F401
    _python_ast_symbols,
    collect_file_signals,
    extract_symbols,
    flatten_tree,
    make_file_insight,
    python_imported_names,
)
from contexta_app.engine.roles import (  # noqa: F401
    _CONTEXTA_MODULE_ROLES,
    _CONTEXTA_ROOT_FILES,
    _CONTEXTA_ROOT_ROLES,
    extract_route_tokens,
    humanize_route_tokens,
    infer_component_role,
    infer_content_based_role,
    infer_entrypoint_role,
    infer_exact_name_role,
    infer_file_role,
    infer_file_role_pipeline,
    infer_file_role_with_project_context,
    infer_frontend_support_role,
    infer_nextjs_page_role,
    infer_page_role,
    infer_path_role,
    is_contexta_self_file,
    summarize_doc_file,
    summarize_support_file,
    validate_role_against_project,
)
from contexta_app.engine.surfaces import (  # noqa: F401
    detect_project_shape,
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
    project_stack_tokens,
)
from contexta_app.engine.fingerprint import (  # noqa: F401
    classify_project_type,
    compute_project_type_signals,
    detect_domain_label,
    detect_project_fingerprint,
    extract_domain_corpus_tokens,
    extract_import_enriched_domain_tokens,
    extract_richer_domain_corpus_tokens,
    fingerprint_file_lookup,
    fingerprint_runtime_scope,
    infer_probable_purpose,
    join_content_blob,
    prioritize_dependencies,
    signal_evidence_text,
)
from contexta_app.engine.summary import (  # noqa: F401
    build_architecture_overview,
    build_detection_evidence_line,
    build_project_summary_intro,
    build_summary_lines,
    confidence_band,
    detect_quality_signals,
    detect_supporting_technologies,
    infer_core_module_label,
    join_natural_list,
    normalize_supporting_technologies,
    pick_core_module_descriptors,
    pick_core_module_labels,
    pick_core_module_names,
    prioritize_evidence_sources,
)
from contexta_app.engine.scoring import (  # noqa: F401
    classify_file,
    detect_entrypoints,
    score_file,
    summarize_file,
)
from contexta_app.engine.risk import (  # noqa: F401
    build_relationship_map,
    build_risks,
    compute_risk_score,
)
from contexta_app.engine.selection import (  # noqa: F401
    FOCUS_MAX_FILES,
    FOCUS_MIN_TOP_SCORE,
    SelectionContext,
    add_related_tests,
    build_folder_summaries,
    build_selection_context,
    build_task_prompt,
    derive_selected_tokens,
    expand_with_related,
    infer_selection_reasons,
    select_dead_code_files,
    select_debug_files,
    select_diff_fallback_files,
    select_diff_files,
    select_feature_files,
    select_files,
    select_focus_files,
    select_onboarding_files,
    select_refactor_files,
    select_risk_files,
    select_write_tests_files,
)
from contexta_app.engine.excerpts import (  # noqa: F401
    extract_relevant_excerpt,
    extract_signatures,
)
from contexta_app.engine.pipeline import (  # noqa: F401
    build_analysis,
    resolve_config,
)
