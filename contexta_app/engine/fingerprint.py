"""contexta_app.engine.fingerprint: split out of context_engine.py. Bodies are unchanged."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from contexta_app.project_meta import read_project_description

from contexta_app.engine.constants import (
    CAMEL_CASE_TOKEN_RE,
    CODE_LANGUAGE_WEIGHTS,
    DOMAIN_HINTS,
    PROJECT_TYPE_LABELS,
    PROJECT_TYPE_RULES,
    TECH_LABELS,
    extract_alpha_tokens,
)
from contexta_app.engine.models import (
    FileInsight,
    ProjectFingerprint,
)
from contexta_app.engine.manifests import (
    get_dependency_names,
    parse_json_dependencies,
    parse_manifest_scripts,
    parse_pyproject_dependencies,
    parse_requirements_dependencies,
)
from contexta_app.engine.roles import (
    infer_file_role_pipeline,
)

def fingerprint_file_lookup(insights: list[FileInsight]) -> tuple[dict[str, FileInsight], dict[str, FileInsight]]:
    by_rel = {item.relpath.as_posix().lower(): item for item in insights}
    by_name = {item.path.name.lower(): item for item in insights}
    return by_rel, by_name

def prioritize_dependencies(dependency_names: set[str]) -> list[str]:
    priority_order = [
        "next",
        "react",
        "nuxt",
        "@angular/core",
        "vue",
        "svelte",
        "@sveltejs/kit",
        "@remix-run/dev",
        "astro",
        "typescript",
        "tailwindcss",
        "@tailwindcss/postcss",
        "firebase",
        "fastapi",
        "django",
        "djangorestframework",
        "flask",
        "sqlalchemy",
        "celery",
        "express",
        "@nestjs/core",
        "rails",
        "phoenix",
        "flutter",
        "electron",
        "laravel/framework",
        "illuminate/database",
        "microsoft.aspnetcore.app",
        "microsoft.aspnetcore.mvc",
        "gin",
        "github.com/gin-gonic/gin",
        "github.com/gofiber/fiber",
        "github.com/labstack/echo",
        "spring-boot-starter-web",
        "spring-boot-starter",
        "spring-core",
        "spring-web",
        "hibernate-core",
        "spring-data-jpa",
        "actix-web",
        "axum",
        "rocket",
        "tauri",
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
        "has_nest": "`package.json` includes NestJS core dependencies.",
        "has_routes_dir": "A `routes` directory is present.",
        "has_controllers": "A `controllers` directory is present.",
        "has_db_models": "Model-like files or directories were detected.",
        "has_php": "PHP source files were detected.",
        "has_composer": "`composer.json` is present.",
        "has_php_forms": "PHP form-oriented pages or `<form>` markup were detected.",
        "has_php_service_layer": "PHP service-layer files were detected.",
        "has_php_dao_layer": "PHP DAO or repository files were detected.",
        "has_django": "Django framework was detected in Python dependencies.",
        "has_flask": "Flask framework was detected in Python dependencies.",
        "has_manage_py": "`manage.py` Django management script is present.",
        "has_spring_boot": "Spring Boot was detected in Java dependencies.",
        "has_aspnet": "ASP.NET Core signals were detected from NuGet dependencies or Program.cs.",
        "has_java": "Java or Kotlin source files were detected.",
        "has_kotlin": "Kotlin source files were detected.",
        "has_csharp": "C# source files were detected.",
        "has_ruby": "Ruby source files were detected.",
        "has_elixir": "Elixir source files were detected.",
        "has_dart": "Dart source files were detected.",
        "has_maven": "`pom.xml` Maven build descriptor is present.",
        "has_gradle": "Gradle build files were detected.",
        "has_android_manifest": "`AndroidManifest.xml` was detected.",
        "has_rails": "Rails conventions were detected from `Gemfile`, `config/routes.rb`, or `bin/rails`.",
        "has_phoenix": "Phoenix conventions were detected from `mix.exs` or router files.",
        "has_flutter": "`pubspec.yaml` or `lib/main.dart` indicates a Flutter application.",
        "has_electron": "`package.json` includes Electron dependencies.",
        "has_laravel": "Laravel framework or standard Laravel structure was detected.",
        "has_form_pages": "Form-oriented pages or `<form>` markup were detected.",
        "has_service_layer": "Service-layer files were detected.",
        "has_dao_layer": "DAO or repository files were detected.",
        "has_python": "Python source files were detected.",
        "has_go": "Go source files were detected.",
        "has_go_modules": "`go.mod` is present.",
        "has_go_cmd_dir": "A `cmd/` directory is present.",
        "has_rust": "Rust source files were detected.",
        "has_cargo": "`Cargo.toml` is present.",
        "has_rust_web": "Rust web framework dependencies were detected.",
        "has_tkinter": "Tkinter imports were detected.",
        "has_cli_entrypoint": "CLI entry signals were detected.",
        "has_gui_module": "GUI-oriented modules were detected.",
        "has_javascript_runtime": "Node.js-style runtime entry signals were detected.",
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
    content_blob = "\n".join(item.content.lower()[:4000] for item in insights[:80])

    has_php = any(item.lang == "php" for item in insights)
    has_java = any(item.lang == "java" for item in insights)
    has_kotlin = any(item.lang == "kotlin" for item in insights)
    has_csharp = any(item.lang == "csharp" for item in insights)
    has_go = any(item.lang == "go" for item in insights)
    has_rust = any(item.lang == "rust" for item in insights)
    has_ruby = any(item.lang == "ruby" for item in insights)
    has_elixir = any(item.lang == "elixir" for item in insights)
    has_dart = any(item.lang == "dart" for item in insights)
    php_names = [item.path.name.lower() for item in insights if item.lang == "php"]
    php_relpaths = [item.relpath.as_posix().lower() for item in insights if item.lang == "php"]

    return {
        "has_next": "Next.js" in frameworks,
        "has_react": "React" in frameworks,
        "has_tsx_pages": any(path.endswith(("/page.tsx", "/page.jsx")) or "/pages/" in path for path in relpaths),
        "has_components_dir": "components" in lower_dirs or any("/components/" in path for path in relpaths),
        "has_tailwind": "Tailwind CSS" in build_tools,
        "has_fastapi": "FastAPI" in frameworks,
        "has_django": "Django" in frameworks,
        "has_flask": "Flask" in frameworks,
        "has_nest": "NestJS" in frameworks,
        "has_manage_py": any(name == "manage.py" for name in names),
        "has_spring_boot": "Spring Boot" in frameworks,
        "has_aspnet": "ASP.NET Core" in frameworks or "webapplication.createbuilder" in content_blob or "mapcontrollers()" in content_blob,
        "has_java": has_java or has_kotlin,   # Kotlin projects are JVM-based too
        "has_kotlin": has_kotlin,
        "has_csharp": has_csharp,
        "has_ruby": has_ruby,
        "has_elixir": has_elixir,
        "has_dart": has_dart,
        "has_maven": "Maven" in package_managers,
        "has_gradle": "Gradle" in package_managers,
        "has_android_manifest": any(name == "androidmanifest.xml" for name in names),
        "has_rails": "Rails" in frameworks,
        "has_phoenix": "Phoenix" in frameworks,
        "has_flutter": "Flutter" in frameworks,
        "has_electron": "Electron" in frameworks,
        "has_express": "express" in dependency_names,
        "has_routes_dir": "routes" in lower_dirs or any("/routes/" in path for path in relpaths),
        "has_controllers": "controllers" in lower_dirs or any("/controllers/" in path for path in relpaths),
        "has_db_models": "models" in lower_dirs or any("/models/" in path for path in relpaths),
        "has_php": has_php,
        "has_composer": "Composer" in package_managers,
        "has_laravel": "Laravel" in frameworks,
        # PHP-specific signals (prevent false positives on Python/Java projects)
        "has_php_forms": has_php and (
            any("form" in n for n in php_names)
            or any("<form" in item.content.lower() for item in insights if item.lang == "php")
        ),
        "has_php_service_layer": has_php and (
            any("service" in n for n in php_names) or any("/services/" in p for p in php_relpaths)
        ),
        "has_php_dao_layer": has_php and (
            any("dao" in n or "repository" in n for n in php_names)
            or any("/repositories/" in p or "/dao/" in p for p in php_relpaths)
        ),
        # Keep generic signals for backend_api detection (non-PHP projects)
        "has_form_pages": any("form" in name for name in names) or any("<form" in item.content.lower() for item in insights if item.lang in {"html", "jsx", "tsx"}),
        "has_service_layer": any("service" in name for name in names) or any("/services/" in path for path in relpaths),
        "has_dao_layer": any("dao" in name or "repository" in name for name in names) or any("/repositories/" in path or "/dao/" in path for path in relpaths),
        "has_python": any(item.lang == "python" for item in insights),
        "has_go": has_go,
        "has_go_modules": "Go modules" in package_managers,
        "has_go_cmd_dir": "cmd" in lower_dirs or any(path.startswith("cmd/") for path in relpaths),
        "has_rust": has_rust,
        "has_cargo": "Cargo" in package_managers,
        "has_rust_web": any(framework in frameworks for framework in {"Actix Web", "Axum", "Rocket"}),
        "has_tkinter": "Tkinter" in frameworks,
        "has_cli_entrypoint": any("cli" in item.tags for item in entrypoints + insights),
        "has_gui_module": any("ui" in item.tags for item in insights),
        "has_nuget": "NuGet" in package_managers,
        "has_javascript_runtime": "Node.js" in runtime,
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
        path_tokens = extract_alpha_tokens(item.relpath.as_posix().replace("\\", "/"))
        symbol_tokens = []
        for name in item.functions[:12] + item.classes[:8]:
            symbol_tokens.extend(CAMEL_CASE_TOKEN_RE.findall(name))
        visible_text = []
        visible_text.extend(re.findall(r">([^<]{3,80})<", item.content))
        visible_text.extend(re.findall(r'["\']([^"\']{3,80})["\']', item.content[:6000]))
        xml_tokens = re.findall(r"</?([A-Za-z0-9:_-]{3,})", item.content[:6000])
        attr_names = re.findall(r'([A-Za-z0-9:_-]{3,})\s*=', item.content[:6000])
        for chunk in path_tokens + symbol_tokens + visible_text + xml_tokens + attr_names:
            tokens.extend(extract_alpha_tokens(chunk.lower()))
    return tokens

def extract_richer_domain_corpus_tokens(insights: list[FileInsight]) -> list[str]:
    tokens = extract_domain_corpus_tokens(insights)
    for item in insights[:80]:
        for imported in item.imports[:20]:
            tokens.extend(extract_alpha_tokens(imported.replace("\\", "/").lower()))
        import_mentions = re.findall(
            r"(?:import|from|require|require_once|include|include_once)\s+([A-Za-z_][A-Za-z0-9_]*)",
            item.content[:6000],
            re.IGNORECASE,
        )
        for mention in import_mentions:
            tokens.extend(extract_alpha_tokens(mention.lower()))
    return tokens

def extract_import_enriched_domain_tokens(insights: list[FileInsight]) -> list[str]:
    tokens = extract_domain_corpus_tokens(insights)
    for item in insights[:80]:
        for imported in item.imports[:20]:
            tokens.extend(extract_alpha_tokens(imported.replace("\\", "/").lower()))
        import_mentions = re.findall(
            r"(?:import|from|require|require_once|include|include_once)\s+([A-Za-z_][A-Za-z0-9_]*)",
            item.content[:6000],
            re.IGNORECASE,
        )
        for mention in import_mentions:
            tokens.extend(extract_alpha_tokens(mention.lower()))
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
    purpose_by_pair = {
        ("PHP CRUD web application", "education"): "Manage student records through listing, form editing, and service or DAO-backed operations.",
        ("Frontend web application", "marketing_site"): "Present a marketing-focused website with landing sections, navigation, and product or content highlights.",
        ("Frontend web application", "ecommerce"): "Present a marketing or catalog-oriented frontend with products, browsing, pricing, and shopping-adjacent flows.",
        ("Frontend web application", "task_management"): "Deliver a task or kanban-style interface with boards, assignees, priorities, and workflow status tracking.",
        ("Backend API service", "task_management"): "Expose backend services for task or kanban workflows with assignment, status, and workflow logic.",
        ("Django web application", "task_management"): "Support task or kanban workflows through Django views, models, and template-driven UI flows.",
        ("Django web application", "education"): "Manage academic records and educational workflows through Django views, models, and admin interfaces.",
        ("Flask web application", "task_management"): "Support task or workflow-oriented routes through lightweight Flask services and Python application logic.",
        ("Spring Boot application", "task_management"): "Implement Java backend services for task or kanban workflows with controllers, services, and persistence logic.",
        ("Spring Boot application", "ecommerce"): "Provide Java backend services for an e-commerce platform with product, order, and payment-oriented flows.",
        ("ASP.NET Core application", "task_management"): "Expose ASP.NET Core endpoints and backend logic for task, board, and workflow management features.",
        ("Laravel web application", "education"): "Manage education-related records through Laravel routes, controllers, models, and persistence-backed forms.",
        ("Laravel web application", "ecommerce"): "Deliver a full-stack commerce application with Laravel controllers, models, and storefront or admin flows.",
        ("Ruby on Rails application", "education"): "Deliver a Rails application for academic records, enrollment, or classroom-oriented workflows.",
        ("Ruby on Rails application", "ecommerce"): "Deliver a Rails application with storefront, catalog, ordering, and admin workflows.",
        ("Phoenix web application", "task_management"): "Support workflow or board-oriented features through Phoenix routers, controllers, and Elixir-backed services.",
        ("Flutter application", "task_management"): "Deliver a Flutter application for task, board, or status-tracking workflows across mobile or desktop surfaces.",
        ("Electron desktop application", "image_editing"): "Provide desktop image or asset-editing workflows through a web-powered desktop shell.",
        ("Go application", "task_management"): "Provide Go-based services or tooling for task, board, and workflow management operations.",
        ("Rust application", "graph_analysis"): "Analyze, transform, or serve graph and network data with performance-oriented Rust modules.",
        ("Desktop GUI + CLI developer tool", "developer_tooling"): "Scan local repositories and generate curated context packs for AI workflows.",
        ("Desktop GUI + CLI developer tool", "image_editing"): "Provide desktop editing workflows for image or asset manipulation through GUI and command-driven tooling.",
    }
    if project_type_label == "Desktop GUI + CLI developer tool":
        return "Scan local repositories and generate curated context packs for AI workflows."
    if (project_type_label, domain_label) in purpose_by_pair:
        return purpose_by_pair[(project_type_label, domain_label)]

    domain_fragments = {
        "education": "education, student, or academic workflows",
        "ecommerce": "product, catalog, ordering, or storefront workflows",
        "marketing_site": "marketing, landing-page, or content-presentation flows",
        "admin_panel": "administrative dashboards, settings, and reporting workflows",
        "task_management": "task, kanban, sprint, or workflow management",
        "finance": "payments, billing, accounting, or financial record flows",
        "healthcare": "patient, appointment, or medical-record workflows",
        "social": "feeds, profiles, messaging, or social interaction flows",
        "image_editing": "image editing, asset manipulation, or visual design workflows",
        "graph_analysis": "graph, network, or relationship-analysis workflows",
        "content_management": "content editing, publishing, and page management workflows",
        "developer_tooling": "developer tooling, automation, or repository-analysis workflows",
    }
    project_fragments = {
        "Django web application": "through Django views, models, URL routing, and template rendering",
        "Flask web application": "through Flask routes and Python application logic",
        "Spring Boot application": "through Spring Boot controllers, services, and repositories",
        "Spring web application": "through Java web modules, services, and persistence layers",
        "Java application": "through Java classes, services, and persistence-oriented modules",
        "ASP.NET Core application": "through ASP.NET Core controllers, middleware, and service layers",
        "Laravel web application": "through Laravel controllers, models, migrations, and Blade views",
        "Ruby on Rails application": "through Rails routes, controllers, models, and server-rendered views",
        "Phoenix web application": "through Phoenix routers, controllers, LiveView or template flows, and Elixir services",
        "Flutter application": "through Dart widgets, screens, and mobile or desktop runtime integrations",
        "Electron desktop application": "through Electron entrypoints, renderer processes, and desktop packaging workflows",
        "Backend API service": "through API-oriented routes, services, and integration layers",
        "Frontend web application": "through routed pages, shared UI components, and frontend tooling",
        "PHP CRUD web application": "through routed pages, forms, and persistence-oriented PHP modules",
        "Python application": "through Python modules and supporting application logic",
        "Go application": "through Go packages, modules, and entrypoint-driven services or tools",
        "Rust application": "through Rust crates, modules, and Cargo-managed binaries or services",
        ".NET application": "through C# modules and NuGet-managed application services",
        "Android application": "through Android activities, manifests, resources, and SDK integrations",
    }

    if project_type_label and domain_label in domain_fragments:
        fragment = project_fragments.get(project_type_label, f"through the detected {project_type_label.lower()}")
        return f"Support {domain_fragments[domain_label]} {fragment}."

    if project_type_label == "Django web application":
        return "Deliver a full-stack web application with Django views, models, URL routing, and template rendering."
    if project_type_label == "Flask web application":
        return "Serve a lightweight web application or API through Flask routes and Python application logic."
    if project_type_label == "Spring Boot application":
        return "Expose REST APIs and backend services through Spring Boot controllers, services, and repositories."
    if project_type_label == "ASP.NET Core application":
        return "Expose web application or API functionality through ASP.NET Core controllers, middleware, and dependency-injected services."
    if project_type_label == "Ruby on Rails application":
        return "Deliver a full-stack Rails application through routes, controllers, models, and convention-driven server rendering."
    if project_type_label == "Phoenix web application":
        return "Deliver a Phoenix application through routers, controllers, LiveView or template flows, and Elixir services."
    if project_type_label == "Flutter application":
        return "Deliver a Flutter application through Dart widgets, screens, and cross-platform runtime integrations."
    if project_type_label == "Electron desktop application":
        return "Deliver a desktop application through Electron main-process orchestration and renderer-based UI flows."
    if project_type_label in {"Spring web application", "Java application"}:
        return "Implement backend application logic with Java classes, services, and persistence layers."
    if project_type_label == "Android application":
        return "Deliver a native Android application with activities, fragments, and Android SDK integrations."
    if project_type_label == "Laravel web application":
        return "Build a full-stack web application using Laravel controllers, models, migrations, and Blade views."
    if project_type_label == "Backend API service":
        return "Expose backend endpoints and supporting application services through API-oriented modules."
    if project_type_label == "Frontend web application":
        return "Deliver a browser-based application with component-driven frontend flows."
    if project_type_label == "PHP CRUD web application":
        return "Manage records through routed pages, forms, and persistence-oriented PHP modules."
    if project_type_label == "Rust application":
        return "Implement a performant systems, desktop, or CLI application using Rust modules and Cargo packages."
    if project_type_label == "Go application":
        return "Deliver efficient backend services or tooling using Go packages and module-based organization."
    if project_type_label == ".NET application":
        return "Build application functionality using C# and the .NET runtime with NuGet-managed dependencies."
    if project_type_label == "Kotlin application":
        return "Build a JVM or Android application using Kotlin modules and Gradle or Maven build tooling."
    if project_type_label == "Swift application":
        return "Develop an iOS, macOS, or cross-Apple-platform application using Swift modules and Xcode tooling."
    if project_type_label == "C/C++ application":
        return "Implement systems-level, native, or performance-critical application logic using C or C++ modules."
    if project_type_label == "Scala application":
        return "Build JVM-based application logic using Scala and functional or object-oriented patterns."
    if project_type_label == "PHP application":
        return "Deliver web application functionality using PHP modules and associated server-side tooling."
    if project_type_label == "Python application":
        return "Organize Python modules, scripts, and supporting logic into a runnable application."
    if project_type_label == "JavaScript/TypeScript application":
        return "Deliver application functionality using JavaScript or TypeScript modules and supporting tooling."
    if project_type_label == "Developer-facing software project":
        return "Provide developer tooling, libraries, or utilities organized for software engineering workflows."
    return "Organize project structure and expose the most relevant code paths for developer workflows."

def fingerprint_runtime_scope(insights: list[FileInsight]) -> list[FileInsight]:
    scope = [
        item
        for item in insights
        if "test" not in item.tags and "docs" not in item.tags and "embedded_asset" not in item.tags
    ]
    if scope:
        return scope
    scope = [item for item in insights if "docs" not in item.tags]
    return scope or insights

def join_content_blob(insights: list[FileInsight], *, lang: str | None = None, limit: int = 60) -> str:
    parts: list[str] = []
    for item in insights:
        if lang and item.lang != lang:
            continue
        parts.append(item.content.lower())
        if len(parts) >= limit:
            break
    return "\n".join(parts)

def detect_project_fingerprint(
    project_path: Path,
    insights: list[FileInsight],
    entrypoints: list[FileInsight],
) -> ProjectFingerprint:
    scope = fingerprint_runtime_scope(insights)
    by_rel, by_name = fingerprint_file_lookup(scope)
    lower_names = {item.path.name.lower() for item in scope}
    lower_dirs = {item.relpath.parts[0].lower() for item in scope if item.relpath.parts}
    content_blob = join_content_blob(scope)
    python_blob = join_content_blob(scope, lang="python")
    java_blob = join_content_blob(scope, lang="java")
    csharp_blob = join_content_blob(scope, lang="csharp")

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

    for item in scope:
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
        language_scores["typescript" if ("typescript" in deps or any(item.lang in {"typescript", "tsx"} for item in scope)) else "javascript"] += 10.0
        note(f"`package.json` defines the JavaScript/TypeScript dependency graph via {package_manager_label}.")
        if "next" in deps:
            push(frameworks, "Next.js")
            push(runtime, "Node.js")
            push(runtime, "Browser")
            note("`package.json` includes `next`.", "project_type")
        if "nuxt" in deps or any(name.startswith("nuxt.config.") for name in lower_names):
            push(frameworks, "Nuxt")
            push(runtime, "Node.js")
            push(runtime, "Browser")
            note("`package.json` or `nuxt.config` indicates a Nuxt application.", "project_type")
        if "react" in deps:
            push(frameworks, "React")
            push(runtime, "Browser")
            note("`package.json` includes `react`.", "project_type")
        if "@angular/core" in deps or "angular.json" in lower_names:
            push(frameworks, "Angular")
            push(runtime, "Browser")
            note("Angular workspace files or dependencies were detected.", "project_type")
        if "vue" in deps:
            push(frameworks, "Vue")
            push(runtime, "Browser")
            note("`package.json` includes `vue`.")
        if "svelte" in deps or "@sveltejs/kit" in deps:
            push(frameworks, "Svelte/SvelteKit")
            push(runtime, "Browser")
            note("`package.json` includes Svelte dependencies.")
        if "@remix-run/dev" in deps or any(name.startswith("remix.config.") for name in lower_names):
            push(frameworks, "Remix")
            push(runtime, "Node.js")
            push(runtime, "Browser")
            note("Remix dependencies or config files were detected.", "project_type")
        if "astro" in deps or any(name.startswith("astro.config.") for name in lower_names):
            push(frameworks, "Astro")
            push(runtime, "Node.js")
            push(runtime, "Browser")
            note("Astro dependencies or config files were detected.", "project_type")
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
        if "@nestjs/core" in deps or "@nestjs/common" in deps:
            push(frameworks, "NestJS")
            push(runtime, "Node.js")
            push(runtime, "Server")
            note("`package.json` includes NestJS core dependencies.", "project_type")
        if "electron" in deps or "electron-builder" in deps:
            push(frameworks, "Electron")
            push(runtime, "Node.js")
            push(runtime, "Desktop GUI")
            note("`package.json` includes Electron dependencies.", "project_type")

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

    if "gemfile" in by_name:
        source("Gemfile")
        deps = get_dependency_names(by_name["gemfile"])
        dependency_names.update(deps)
        push(package_managers, "Bundler")
        push(runtime, "Ruby")
        language_scores["ruby"] += 10.0
        note("`Gemfile` defines the Ruby dependency graph.", "project_type")
        if "rails" in deps or "config/routes.rb" in by_rel or "bin/rails" in by_rel:
            push(frameworks, "Rails")
            push(runtime, "Server")
            note("Rails structure was detected from `Gemfile`, `config/routes.rb`, or `bin/rails`.", "project_type")

    if "mix.exs" in by_name:
        source("mix.exs")
        deps = get_dependency_names(by_name["mix.exs"])
        dependency_names.update(deps)
        push(package_managers, "Mix")
        push(runtime, "BEAM")
        language_scores["elixir"] += 10.0
        note("`mix.exs` defines the Elixir application and dependency graph.", "project_type")
        if "phoenix" in deps or any(path.endswith("/router.ex") for path in by_rel):
            push(frameworks, "Phoenix")
            push(runtime, "Server")
            note("Phoenix router or dependencies were detected.", "project_type")

    if "pubspec.yaml" in by_name or "pubspec.yml" in by_name:
        pubspec_item = by_name.get("pubspec.yaml") or by_name.get("pubspec.yml")
        if pubspec_item:
            source(pubspec_item.path.name)
            deps = get_dependency_names(pubspec_item)
            dependency_names.update(deps)
            push(package_managers, "pub")
            push(runtime, "Dart")
            language_scores["dart"] += 10.0
            note("`pubspec.yaml` defines Dart or Flutter package metadata.", "project_type")
            if "flutter" in deps or "flutter:" in pubspec_item.content.lower() or "lib/main.dart" in by_rel:
                push(frameworks, "Flutter")
                push(runtime, "Mobile")
                note("Flutter project structure was detected from `pubspec.yaml` or `lib/main.dart`.", "project_type")

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
            note("`requirements.txt` includes `django`.", "project_type")
        if "djangorestframework" in deps or "django-rest-framework" in deps:
            push(frameworks, "Django REST Framework")
            push(runtime, "Server")
            note("`requirements.txt` includes Django REST Framework.", "project_type")
        if "channels" in deps:
            push(build_tools, "Django Channels")
            note("`requirements.txt` includes Django Channels (WebSocket support).")
        if "celery" in deps:
            push(build_tools, "Celery")
            note("`requirements.txt` includes Celery (async task queue).")
        if "flask" in deps:
            push(frameworks, "Flask")
            push(runtime, "Server")
            note("`requirements.txt` includes `flask`.", "project_type")
        if "flask-restful" in deps or "flask-restx" in deps or "flasgger" in deps:
            push(build_tools, "Flask REST extension")
            note("`requirements.txt` includes a Flask REST extension.")
        if "sqlalchemy" in deps:
            push(build_tools, "SQLAlchemy")
            note("`requirements.txt` includes SQLAlchemy ORM.")
        if "alembic" in deps:
            push(build_tools, "Alembic migrations")
            note("`requirements.txt` includes Alembic database migrations.")
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
            note("`pyproject.toml` includes `fastapi`.", "project_type")
        if "django" in deps:
            push(frameworks, "Django")
            push(runtime, "Server")
            note("`pyproject.toml` includes `django`.", "project_type")
        if "djangorestframework" in deps or "django-rest-framework" in deps:
            push(frameworks, "Django REST Framework")
            push(runtime, "Server")
            note("`pyproject.toml` includes Django REST Framework.", "project_type")
        if "flask" in deps:
            push(frameworks, "Flask")
            push(runtime, "Server")
            note("`pyproject.toml` includes `flask`.", "project_type")
        if "sqlalchemy" in deps:
            push(build_tools, "SQLAlchemy")
            note("`pyproject.toml` includes SQLAlchemy ORM.")
        if "celery" in deps:
            push(build_tools, "Celery")
            note("`pyproject.toml` includes Celery (async task queue).")
        if "pyinstaller" in deps:
            push(build_tools, "PyInstaller")
            note("`pyproject.toml` includes `pyinstaller`.")

    if "cargo.toml" in by_name:
        source("Cargo.toml")
        cargo_deps = get_dependency_names(by_name["cargo.toml"])
        dependency_names.update(cargo_deps)
        for script in parse_manifest_scripts(by_name["cargo.toml"]):
            push(scripts, script)
        push(package_managers, "Cargo")
        push(runtime, "Rust")
        language_scores["rust"] += 10.0
        note("`Cargo.toml` defines the Rust package manifest.")
        if "actix-web" in cargo_deps:
            push(frameworks, "Actix Web")
            push(runtime, "Server")
            note("`Cargo.toml` includes `actix-web`.", "project_type")
        if "axum" in cargo_deps:
            push(frameworks, "Axum")
            push(runtime, "Server")
            note("`Cargo.toml` includes `axum`.", "project_type")
        if "rocket" in cargo_deps:
            push(frameworks, "Rocket")
            push(runtime, "Server")
            note("`Cargo.toml` includes `rocket`.", "project_type")
        if "tauri" in cargo_deps:
            push(frameworks, "Tauri")
            push(runtime, "Desktop GUI")
            note("`Cargo.toml` includes `tauri`.")
        if "clap" in cargo_deps:
            push(build_tools, "Clap CLI")
            note("`Cargo.toml` includes `clap`.")

    if "go.mod" in by_name:
        source("go.mod")
        go_deps = get_dependency_names(by_name["go.mod"])
        dependency_names.update(go_deps)
        push(package_managers, "Go modules")
        push(runtime, "Go")
        language_scores["go"] += 10.0
        note("`go.mod` defines the Go module graph.")
        if any(dep in go_deps for dep in {"github.com/gin-gonic/gin", "gin"}):
            push(frameworks, "Gin")
            push(runtime, "Server")
            note("`go.mod` includes Gin router dependencies.", "project_type")
        if any(dep in go_deps for dep in {"github.com/gofiber/fiber", "fiber"}):
            push(frameworks, "Fiber")
            push(runtime, "Server")
            note("`go.mod` includes Fiber router dependencies.", "project_type")
        if any(dep in go_deps for dep in {"github.com/labstack/echo", "echo"}):
            push(frameworks, "Echo")
            push(runtime, "Server")
            note("`go.mod` includes Echo router dependencies.", "project_type")
        if any(dep in go_deps for dep in {"github.com/spf13/cobra", "cobra"}):
            push(build_tools, "Cobra CLI")
            note("`go.mod` includes Cobra CLI tooling.")

    for name in lower_names:
        if name.endswith(".csproj"):
            source(name)
            csproj_deps = get_dependency_names(by_name[name])
            dependency_names.update(csproj_deps)
            for script in parse_manifest_scripts(by_name[name]):
                push(scripts, script)
            push(package_managers, "NuGet")
            push(runtime, ".NET")
            language_scores["csharp"] += 10.0
            note(f"`{name}` defines a .NET project.")
            if any(dep.startswith("microsoft.aspnetcore") for dep in csproj_deps) or "webapplication.createbuilder" in content_blob:
                push(frameworks, "ASP.NET Core")
                push(runtime, "Server")
                note(f"`{name}` includes ASP.NET Core dependencies.", "project_type")
            csproj_content = by_name[name].content.lower()
            if "<usewpf>true</usewpf>" in csproj_content or "<usewindowsforms>true</usewindowsforms>" in csproj_content:
                push(frameworks, ".NET desktop UI")
                push(runtime, "Desktop GUI")
                note(f"`{name}` enables desktop UI build settings.")
            break

    if "pom.xml" in lower_names:
        source("pom.xml")
        pom_deps = get_dependency_names(by_name["pom.xml"])
        dependency_names.update(pom_deps)
        for script in parse_manifest_scripts(by_name["pom.xml"]):
            push(scripts, script)
        push(package_managers, "Maven")
        push(runtime, "JVM")
        language_scores["java"] += 10.0
        note("`pom.xml` defines the Maven build graph.")
        if any(dep.startswith("spring-boot") for dep in pom_deps):
            push(frameworks, "Spring Boot")
            push(runtime, "Server")
            note("`pom.xml` includes Spring Boot dependencies.", "project_type")
        elif any(dep in pom_deps for dep in {"spring-core", "spring-web", "spring-webmvc", "spring-context"}):
            push(frameworks, "Spring Framework")
            push(runtime, "Server")
            note("`pom.xml` includes Spring Framework dependencies.", "project_type")
        if any(dep in pom_deps for dep in {"hibernate-core", "spring-data-jpa", "spring-boot-starter-data-jpa", "jakarta.persistence-api"}):
            push(build_tools, "JPA/Hibernate")
            note("`pom.xml` includes JPA/Hibernate persistence.", "project_type")

    for gradle_name in ("build.gradle", "build.gradle.kts"):
        if gradle_name in lower_names:
            source(gradle_name)
            gradle_content = by_name[gradle_name].content.lower()
            gradle_deps = get_dependency_names(by_name[gradle_name])
            dependency_names.update(gradle_deps)
            for script in parse_manifest_scripts(by_name[gradle_name]):
                push(scripts, script)
            push(package_managers, "Gradle")
            push(runtime, "JVM")
            language_scores["java"] += 10.0
            note(f"`{gradle_name}` defines a Gradle build.", "project_type")
            if "org.springframework.boot" in gradle_content or "spring-boot-starter" in gradle_content or any(dep.startswith("org.springframework.boot:spring-boot") or dep.startswith("spring-boot-starter") for dep in gradle_deps):
                push(frameworks, "Spring Boot")
                push(runtime, "Server")
                note("`build.gradle` includes Spring Boot plugin.", "project_type")
            elif "springframework" in gradle_content or any(dep.startswith("org.springframework") for dep in gradle_deps):
                push(frameworks, "Spring Framework")
                push(runtime, "Server")
                note("`build.gradle` includes Spring Framework.", "project_type")
            if "com.android.application" in gradle_content or "com.android.library" in gradle_content:
                push(frameworks, "Android SDK")
                push(runtime, "Android")
                note("`build.gradle` defines an Android application.", "project_type")
            if "hibernate" in gradle_content or "jpa" in gradle_content or any(dep.endswith(":hibernate-core") or dep.endswith(":spring-data-jpa") or dep.endswith(":spring-boot-starter-data-jpa") for dep in gradle_deps):
                push(build_tools, "JPA/Hibernate")
            break

    if "manage.py" in lower_names:
        source("manage.py")
        if "Django" not in frameworks:
            push(frameworks, "Django")
            push(runtime, "Server")
            language_scores["python"] += 6.0
            note("`manage.py` Django management script was detected.", "project_type")
    if {"settings.py", "urls.py"} & lower_names:
        if "Django" not in frameworks and any(name in lower_names for name in {"settings.py", "urls.py", "wsgi.py", "asgi.py"}):
            push(frameworks, "Django")
            push(runtime, "Server")
            language_scores["python"] += 4.0
            note("Django structure was inferred from settings, URL routing, or WSGI/ASGI files.", "project_type")
        if "settings.py" in lower_names:
            source("settings.py")
        if "urls.py" in lower_names:
            source("urls.py")

    # Content-based Python framework detection (when no manifest is present)
    if "Django" not in frameworks:
        django_patterns = (
            r"from\s+django[.\s]",
            r"import\s+django\b",
            r"django\.db\.models",
            r"models\.Model",
        )
        if any(re.search(p, item.content, re.MULTILINE) for item in scope if item.lang == "python" for p in django_patterns):
            push(frameworks, "Django")
            push(runtime, "Server")
            language_scores["python"] += 3.0
            note("Django imports were detected in Python source files.", "project_type")

    if "@app.route" in python_blob or "flask(" in python_blob or "blueprint(" in python_blob:
        if "Flask" not in frameworks:
            push(frameworks, "Flask")
            push(runtime, "Server")
            language_scores["python"] += 4.0
            note("Flask route decorators or Blueprint patterns were detected.", "project_type")

    if "program.cs" in lower_names:
        source("Program.cs")
    if "appsettings.json" in lower_names:
        source("appsettings.json")
        if "ASP.NET Core" not in frameworks and ("webapplication.createbuilder" in csharp_blob or "mapcontrollers()" in csharp_blob):
            push(frameworks, "ASP.NET Core")
            push(runtime, "Server")
            note("Program.cs and appsettings.json suggest an ASP.NET Core application.", "project_type")

    if "@springbootapplication" in java_blob or "@restcontroller" in java_blob:
        if "Spring Boot" not in frameworks and "Spring Framework" not in frameworks:
            push(frameworks, "Spring Boot")
            push(runtime, "Server")
            language_scores["java"] += 4.0
            note("Spring Boot annotations were detected in Java source files.", "project_type")

    if any("androidmanifest.xml" == name for name in lower_names):
        source("AndroidManifest.xml")
        if "Android SDK" not in frameworks:
            push(frameworks, "Android SDK")
            push(runtime, "Android")
            note("`AndroidManifest.xml` was detected.", "project_type")

    if any("tkinter" in item.content.lower() for item in scope if item.lang == "python"):
        push(frameworks, "Tkinter")
        push(runtime, "Desktop GUI")
        language_scores["python"] += 4.0
        note("Tkinter imports were detected in Python source files.", "project_type")
        source("Tkinter imports")
    if any("cli" in item.tags for item in scope) or "argparse" in content_blob or "sys.argv" in content_blob:
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
        elif name.startswith("nuxt.config."):
            source(name)
        elif name.startswith("vite.config."):
            source(name)
        elif name.startswith("astro.config.") or name.startswith("remix.config."):
            source(name)
        elif name in {"tsconfig.json", "dockerfile", ".env.example", "application.properties", "application.yml", "application.yaml", "main.go", "main.rs", "angular.json", "gemfile", "pubspec.yaml", "pubspec.yml"}:
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
    if "config" in lower_dirs and any(path.startswith("config/routes.rb") for path in by_rel):
        source("config/routes.rb")
    if "cmd" in lower_dirs:
        source("cmd/")
    if any(path.startswith("src/main/java/") for path in by_rel):
        source("src/main/java/")
    if any(path.startswith("src/test/java/") for path in by_rel):
        source("src/test/java/")
    if any(path.startswith("lib/main.dart") for path in by_rel):
        source("lib/main.dart")
    if "tests" in lower_dirs:
        source("tests/")

    signals = compute_project_type_signals(
        scope,
        frameworks,
        runtime,
        package_managers,
        build_tools,
        dependency_names,
        entrypoints,
    )
    project_type_key, project_type_score = classify_project_type(signals)
    domain_label, domain_score = detect_domain_label(scope)

    project_type = PROJECT_TYPE_LABELS.get(project_type_key)
    probable_purpose = infer_probable_purpose(project_type, domain_label)
    if project_type_key:
        for signal, _weight in PROJECT_TYPE_RULES[project_type_key]:
            if signals.get(signal):
                note(signal_evidence_text(signal), "project_type")

    stems = {item.path.stem.lower() for item in scope}
    if "python" in language_scores and {"scanner", "renderer", "ui", "cli"} <= stems and ("contexta_app" in lower_dirs or "contexta.py" in by_name):
        project_type = "Desktop GUI + CLI developer tool"
        probable_purpose = "Scan local repositories and generate curated context packs for AI workflows."
        note("Core files like `scanner.py`, `renderer.py`, `ui.py`, and `cli.py` were all detected together.", "project_type")
        for marker in ("contexta.py", "ui.py", "cli.py", "renderer.py", "scanner.py"):
            if marker in by_name:
                source(marker)
    elif not project_type:
        if "Laravel" in frameworks:
            project_type = "Laravel web application"
        elif "Rails" in frameworks:
            project_type = "Ruby on Rails application"
        elif "Phoenix" in frameworks:
            project_type = "Phoenix web application"
        elif "Flutter" in frameworks:
            project_type = "Flutter application"
        elif "Electron" in frameworks:
            project_type = "Electron desktop application"
        elif "FastAPI" in frameworks:
            project_type = "Backend API service"
        elif "Django" in frameworks:
            project_type = "Django web application"
        elif "Flask" in frameworks:
            project_type = "Flask web application"
        elif "NestJS" in frameworks:
            project_type = "Backend API service"
        elif "ASP.NET Core" in frameworks:
            project_type = "ASP.NET Core application"
        elif "Spring Boot" in frameworks:
            project_type = "Spring Boot application"
        elif "Spring Framework" in frameworks:
            project_type = "Spring web application"
        elif "Android SDK" in frameworks:
            project_type = "Android application"
        elif any(framework in frameworks for framework in {"Nuxt", "Angular", "Astro", "Remix"}):
            project_type = "Frontend web application"
        elif any(framework in frameworks for framework in {"Gin", "Fiber", "Echo"}):
            project_type = "Go application"
        elif any(framework in frameworks for framework in {"Actix Web", "Axum", "Rocket"}):
            project_type = "Rust application"
        elif ("java" in language_scores or "kotlin" in language_scores) and ("Maven" in package_managers or "Gradle" in package_managers):
            project_type = "Kotlin application" if "kotlin" in language_scores and "java" not in language_scores else "Java application"
        elif "kotlin" in language_scores:
            project_type = "Kotlin application"
        elif "php" in language_scores and "Composer" in package_managers:
            project_type = "PHP application"
        elif "swift" in language_scores:
            project_type = "Swift application"
        elif "typescript" in language_scores or "javascript" in language_scores:
            project_type = "JavaScript/TypeScript application"
        elif "python" in language_scores:
            project_type = "Python application"
        elif "rust" in language_scores:
            project_type = "Rust application"
        elif "go" in language_scores:
            project_type = "Go application"
        elif "csharp" in language_scores:
            project_type = ".NET application"
        elif "cpp" in language_scores or "c" in language_scores:
            project_type = "C/C++ application"
        elif "scala" in language_scores:
            project_type = "Scala application"
        else:
            project_type = "Developer-facing software project"

    # Boost domain detection from directory names (for projects where content alone isn't enough)
    if not domain_label or domain_score < 3:
        dir_domain_hints = {
            "task_management": {"kanban", "boards", "board", "tasks", "sprints", "backlog", "tickets", "issues", "workflow"},
            "ecommerce": {"cart", "checkout", "products", "catalog", "orders", "payments", "inventory", "store"},
            "education": {"students", "alunos", "courses", "cursos", "classroom", "enrollment", "grades", "lessons"},
            "admin_panel": {"dashboard", "admin", "reports", "analytics", "permissions"},
            "healthcare": {"patients", "appointments", "medical", "hospital", "clinic", "prescriptions"},
            "finance": {"invoices", "payments", "transactions", "billing", "ledger", "accounting"},
            "social": {"feeds", "posts", "comments", "messages", "notifications", "profiles"},
            "image_editing": {"layers", "canvas", "filters", "brushes", "palettes", "raster"},
            "graph_analysis": {"graphs", "nodes", "edges", "networks", "layouts", "clustering"},
        }
        for dlabel, keywords in dir_domain_hints.items():
            if keywords & lower_dirs:
                matching = keywords & lower_dirs
                note(f"Directory structure suggests `{dlabel}` behavior (found: {', '.join(sorted(matching))}).", "purpose")
                if not domain_label or domain_score < 3:
                    domain_label = dlabel
                    domain_score = max(domain_score, 3)
                    probable_purpose = infer_probable_purpose(project_type, domain_label)
                break

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
            primary_language = "TypeScript" if any(item.lang in {"typescript", "tsx"} for item in scope) else "JavaScript"
        # If both Java and Kotlin exist, surface Kotlin as primary when it dominates
        if primary_language == "Java" and "kotlin" in language_scores and language_scores["kotlin"] > language_scores.get("java", 0):
            primary_language = "Kotlin"

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

    declared_purpose = read_project_description(project_path)
    if declared_purpose:
        probable_purpose = declared_purpose
        note("Purpose taken from the project's own metadata or README.", "purpose")

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
