"""contexta_app.engine.summary: split out of context_engine.py. Bodies are unchanged."""

from __future__ import annotations

import re
from pathlib import Path

from contexta_app.engine.constants import (
    IDENTITY_FILE_WEIGHTS,
    IDENTITY_PREFIX_WEIGHTS,
    IDENTITY_SUFFIX_WEIGHTS,
)
from contexta_app.engine.models import (
    FileInsight,
    ProjectFingerprint,
)
from contexta_app.engine.relations import (
    is_test_file,
)
from contexta_app.engine.roles import (
    infer_file_role_pipeline,
)
from contexta_app.engine.surfaces import (
    detect_project_shape,
)

def normalize_supporting_technologies(raw: list[str]) -> list[str]:
    replacements = {
        "pip-style requirements": "pip requirements workflow",
        "desktop gui runtime": "Tkinter desktop interface",
        "desktop gui interface": "Tkinter desktop interface",
        "cli workflow": "CLI workflow",
        "pyinstaller": "optional PyInstaller packaging",
        "nuitka": "Nuitka Windows packaging",
        "typescript compiler": "TypeScript",
        "npm": "npm-based workflow",
        "pnpm": "pnpm-based workflow",
        "yarn": "Yarn-based workflow",
        "pyproject-based python packaging": "pyproject packaging workflow",
        "css": "CSS styling layer",
        "mix": "Mix build workflow",
        "pub": "pub package workflow",
        "bundler": "Bundler workflow",
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
    main_dependencies = {entry.lower() for entry in fingerprint.main_dependencies}

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
    if "tiktoken" in main_dependencies:
        push("token-aware pack sizing")
    if any(dep.startswith("tree-sitter") for dep in main_dependencies):
        push("syntax-aware parsing")
    if "rapidfuzz" in main_dependencies:
        push("fuzzy relationship scoring")
    if "pathspec" in main_dependencies:
        push("git-style ignore matching")
    if "charset-normalizer" in main_dependencies:
        push("robust charset detection")
    for manager in fingerprint.package_managers:
        if manager in {"Composer", "Poetry", "Cargo", "Go modules", "NuGet", "Maven", "Gradle", "Bundler", "Mix", "pub"}:
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
    test_items = [item for item in insights if "test" in item.tags or is_test_file(item.relpath)]
    config_items = [
        item
        for item in insights
        if item.path.name.lower() in {"pytest.ini", "tox.ini", "setup.cfg", "pyproject.toml"}
    ]

    def push(value: str) -> None:
        if value not in signals:
            signals.append(value)

    if any(
        re.search(r"\bimport\s+unittest\b|\bunittest\.testcase\b|\btestcase\s*\(", item.content, re.IGNORECASE)
        for item in test_items
    ):
        push("unittest-based test suite")
    if any(
        re.search(r"^\s*(?:import\s+pytest\b|from\s+pytest\s+import\b|@pytest\.|\bpytestmark\b)", item.content, re.IGNORECASE | re.MULTILINE)
        for item in test_items
    ) or any(
        re.search(r"\[tool\.pytest\.ini_options\]|\bpytest\b", item.content, re.IGNORECASE)
        for item in config_items
    ):
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
        "gemfile": 0,
        "pyproject.toml": 0,
        "requirements.txt": 0,
        "cargo.toml": 0,
        "go.mod": 0,
        "pom.xml": 0,
        "build.gradle": 0,
        "build.gradle.kts": 0,
        "mix.exs": 0,
        "pubspec.yaml": 0,
        "pubspec.yml": 0,
        "program.cs": 1,
        "appsettings.json": 2,
        "manage.py": 3,
        "settings.py": 4,
        "urls.py": 5,
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
        "angular.json": 13,
        "config/routes.rb": 14,
        "application.properties": 14,
        "application.yml": 14,
        "application.yaml": 14,
        "main.go": 15,
        "main.rs": 15,
        "lib/main.dart": 15,
        "app/": 20,
        "pages/": 21,
        "components/": 22,
        "lib/": 23,
        "routes/": 24,
        "cmd/": 25,
        "src/main/java/": 26,
        "src/test/java/": 27,
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
    if project_type == "Django web application":
        return f"`{project_path.name}` looks like a Django web application built around models, routes, templates, and server-side workflows."
    if project_type == "Flask web application":
        return f"`{project_path.name}` looks like a Flask web application built around lightweight routes, services, and Python-backed flows."
    if project_type == "Spring Boot application":
        return f"`{project_path.name}` looks like a Spring Boot application built around controllers, services, repositories, and JVM-based backend flows."
    if project_type == "ASP.NET Core application":
        return f"`{project_path.name}` looks like an ASP.NET Core application built around controllers, middleware, and service-oriented backend flows."
    if project_type == "Ruby on Rails application":
        return f"`{project_path.name}` looks like a Ruby on Rails application built around routes, controllers, models, and convention-driven server rendering."
    if project_type == "Phoenix web application":
        return f"`{project_path.name}` looks like a Phoenix web application built around routers, controllers, and Elixir-backed web flows."
    if project_type == "Flutter application":
        return f"`{project_path.name}` looks like a Flutter application built around Dart widgets, screens, and cross-platform UI flows."
    if project_type == "Electron desktop application":
        return f"`{project_path.name}` looks like an Electron desktop application built around main-process orchestration and renderer-driven UI flows."
    if project_type == "Laravel web application":
        return f"`{project_path.name}` looks like a Laravel web application built around routes, controllers, models, and full-stack server-rendered flows."
    if project_type == "Go application":
        return f"`{project_path.name}` looks like a Go application built around module-based services, handlers, or CLI-oriented packages."
    if project_type == "Rust application":
        return f"`{project_path.name}` looks like a Rust application built around Cargo-managed crates, modules, and performance-oriented workflows."
    if project_type == "Java application":
        return f"`{project_path.name}` looks like a Java application built around JVM services, domain logic, and build-managed modules."
    if project_type == "Android application":
        return f"`{project_path.name}` looks like an Android application built around manifests, resources, and mobile runtime components."
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
    elif project_type == "Django web application":
        lines.append(f"This project appears to be a Django web application written primarily in {primary}, with models, routes, templates, and server-side workflows.")
    elif project_type == "Flask web application":
        lines.append(f"This project appears to be a Flask web application written primarily in {primary}, with lightweight routes and Python-backed application logic.")
    elif project_type == "Spring Boot application":
        lines.append(f"This project appears to be a Spring Boot application written primarily in {primary}, with controllers, services, repositories, and JVM server flows.")
    elif project_type == "ASP.NET Core application":
        lines.append(f"This project appears to be an ASP.NET Core application written primarily in {primary}, with controllers, middleware, and service-oriented backend flows.")
    elif project_type == "Ruby on Rails application":
        lines.append(f"This project appears to be a Ruby on Rails application written primarily in {primary}, with routes, controllers, models, and convention-driven server rendering.")
    elif project_type == "Phoenix web application":
        lines.append(f"This project appears to be a Phoenix web application written primarily in {primary}, with routers, controllers, and Elixir-backed web flows.")
    elif project_type == "Flutter application":
        lines.append(f"This project appears to be a Flutter application written primarily in {primary}, with widgets, screens, and cross-platform runtime integrations.")
    elif project_type == "Electron desktop application":
        lines.append(f"This project appears to be an Electron desktop application written primarily in {primary}, with main-process orchestration and renderer-based UI flows.")
    elif project_type == "Laravel web application":
        lines.append(f"This project appears to be a Laravel web application written primarily in {primary}, with routes, controllers, models, and full-stack web flows.")
    elif project_type == "Go application":
        lines.append(f"This project appears to be a Go application written primarily in {primary}, with module-based services, handlers, or CLI-oriented entry flows.")
    elif project_type == "Rust application":
        lines.append(f"This project appears to be a Rust application written primarily in {primary}, with Cargo-managed crates and performance-oriented modules.")
    elif project_type == "Java application":
        lines.append(f"This project appears to be a Java application written primarily in {primary}, with JVM services, build-managed modules, and domain logic.")
    elif project_type == "Android application":
        lines.append(f"This project appears to be an Android application written primarily in {primary}, with manifests, resources, and mobile runtime components.")
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
