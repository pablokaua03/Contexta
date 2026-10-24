"""contexta_app.engine.roles: split out of context_engine.py. Bodies are unchanged."""

from __future__ import annotations

import re

from contexta_app.engine.constants import (
    ROUTE_ROLE_PATTERNS,
    ROUTE_STOPWORDS,
)
from contexta_app.engine.models import (
    FileInsight,
    FileSignals,
)
from contexta_app.engine.relations import (
    is_test_file,
)
from contexta_app.engine.insight import (
    collect_file_signals,
)

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
        content_lower = item.content.lower()
        _contexta_deps = {"pathspec", "tiktoken", "rapidfuzz", "charset-normalizer", "chardet"}
        if len(item.relpath.parts) == 1 and "tiktoken" in content_lower and "pathspec" in content_lower:
            return "Declares runtime dependencies for parsing, token estimation, and repository analysis."
        return "Declares runtime dependencies and version constraints for the project."
    if name == "requirements-build.txt":
        return "Declares build-time tooling for packaging the project on Windows and Unix-like systems."
    if name == "version_info.txt":
        return "Defines Windows version metadata used in packaged executable builds."
    if name == "build.bat":
        if "nuitka" in item.content.lower():
            return "Automates Windows executable packaging through the Nuitka-based build pipeline."
        return "Automates Windows build or packaging steps for the project."
    if name == "build.sh":
        content_lower = item.content.lower()
        if "linux" in content_lower and ("tar" in content_lower or "install" in content_lower):
            return "Automates Unix-like executable packaging and Linux install bundle generation."
        if "nuitka" in content_lower:
            return "Automates Unix-like executable packaging through the Nuitka-based build pipeline."
        return "Automates Unix-like build, packaging, or deployment steps for the project."
    if name.endswith(".spec") and "pyinstaller" in item.content.lower():
        return "Defines the PyInstaller build spec used to package the desktop application."
    if is_contexta_self_file(item):
        role = (_CONTEXTA_MODULE_ROLES if item.relpath.parts[0] == "contexta_app" else _CONTEXTA_ROOT_ROLES).get(name)
        if role:
            return role
    if name == "cli.py":
        return "Defines the command-line interface and its commands."
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

_CONTEXTA_ROOT_FILES = frozenset({
    "contexta.py", "mdcodebrief.py", "contexta.iss", "install-contexta.sh", "version_info.txt",
})

_CONTEXTA_MODULE_ROLES = {
    "context_engine.py": "Implements project analysis, scoring, and smart context selection.",
    "renderer.py": "Formats selected analysis into the final context pack output.",
    "scanner.py": "Scans the project tree, applies filters, and reads safe text content.",
    "syntax.py": "Extracts syntax-aware symbols and imports through tree-sitter-backed parsing helpers.",
    "ui.py": "Implements the desktop GUI and export workflow orchestration.",
    "cli.py": "Implements the command-line workflow for pack generation and output.",
    "theme.py": "Defines GUI theme palettes and widget repaint behavior.",
    "utils.py": "Provides small desktop-path and filename helpers used by the app entry points.",
}

_CONTEXTA_ROOT_ROLES = {
    "contexta.py": "Acts as the main entrypoint that routes execution into the GUI or CLI flow.",
    "mdcodebrief.py": "Legacy compatibility shim that forwards execution to contexta.main().",
    "contexta.iss": "Defines the Inno Setup installer script for Windows distribution.",
    "install-contexta.sh": "Installs the packaged binary into a user-local application path.",
    "version_info.txt": "Defines Windows version metadata used in packaged executable builds.",
}

def is_contexta_self_file(item: FileInsight) -> bool:
    """True only for Contexta's own sources.

    Role text that names Contexta's internals must never be applied to another
    project that happens to have a ``cli.py`` or ``ui.py``.
    """
    parts = item.relpath.parts
    if not parts:
        return False
    if parts[0] == "contexta_app":
        return True
    return len(parts) == 1 and item.path.name.lower() in _CONTEXTA_ROOT_FILES

def infer_exact_name_role(item: FileInsight) -> str | None:
    name = item.path.name.lower()
    if is_contexta_self_file(item):
        role = _CONTEXTA_MODULE_ROLES.get(name) if item.relpath.parts[0] == "contexta_app" else _CONTEXTA_ROOT_ROLES.get(name)
        if role:
            return role
    exact_name_roles = {
        "cli.py": "Defines the command-line interface and its commands.",
        "package.json": "Declares project dependencies and package metadata.",
        "composer.json": "Declares project dependencies and package metadata.",
        "gemfile": "Declares Ruby dependencies and Bundler-managed package metadata.",
        "pyproject.toml": "Declares project dependencies and package metadata.",
        "mix.exs": "Declares Elixir application metadata, dependencies, and Mix build settings.",
        "pubspec.yaml": "Declares Dart or Flutter package metadata, dependencies, and app configuration.",
        "pubspec.yml": "Declares Dart or Flutter package metadata, dependencies, and app configuration.",
        "cargo.toml": "Declares project dependencies and package metadata.",
        "go.mod": "Declares project dependencies and package metadata.",
        "pom.xml": "Declares project dependencies and package metadata.",
        "angular.json": "Defines Angular workspace configuration, builders, and project targets.",
        "program.cs": "Acts as the .NET application entrypoint and host/bootstrap configuration.",
        "appsettings.json": "Defines ASP.NET Core environment and application settings.",
        "tsconfig.json": "Defines TypeScript compiler options and project path aliases.",
        # requirements.txt, build.bat, build.sh are resolved below with content-aware logic
        "requirements-build.txt": "Declares build-time tooling for packaging the project.",
    }
    if name in exact_name_roles:
        return exact_name_roles[name]
    # Content-aware generic files: requirements.txt, build scripts
    if name == "requirements.txt":
        content_lower = item.content.lower()
        _contexta_deps = {"pathspec", "tiktoken", "rapidfuzz", "charset-normalizer", "chardet"}
        if len(item.relpath.parts) == 1 and "tiktoken" in content_lower and "pathspec" in content_lower:
            return "Declares runtime dependencies for parsing, token estimation, and repository analysis."
        return "Declares runtime dependencies and version constraints for the project."
    if name == "build.bat":
        if "nuitka" in item.content.lower():
            return "Automates Windows executable packaging through the Nuitka-based build pipeline."
        return "Automates Windows build or packaging steps for the project."
    if name == "build.sh":
        content_lower = item.content.lower()
        if "linux" in content_lower and ("tar" in content_lower or "install" in content_lower):
            return "Automates Unix-like executable packaging and Linux install bundle generation."
        if "nuitka" in content_lower:
            return "Automates Unix-like executable packaging through the Nuitka-based build pipeline."
        return "Automates Unix-like build, packaging, or deployment steps for the project."
    if name.endswith(".spec") and "pyinstaller" in item.content.lower():
        return "Defines the PyInstaller build spec used to package the desktop application."
    if name.startswith("next.config."):
        return "Defines Next.js build and runtime configuration."
    if name.startswith("nuxt.config."):
        return "Defines Nuxt build, runtime, and application configuration."
    if name.startswith("vite.config."):
        return "Defines Vite build and runtime configuration."
    if name.startswith("astro.config."):
        return "Defines Astro build and site-generation configuration."
    if name.startswith("remix.config."):
        return "Defines Remix routing and build configuration."
    if name.startswith("tailwind.config."):
        return "Configures Tailwind CSS utility classes, theme tokens, and purge paths."
    # XML-specific files
    if name == "androidmanifest.xml":
        return "Declares Android app components, permissions, features, and entry points."
    if name in {"applicationcontext.xml", "beans.xml"}:
        return "Declares Spring beans, dependency injection wiring, and application context configuration."
    if name == "web.xml":
        return "Configures the Java web application deployment descriptor (servlets, filters, listeners)."
    if name == "struts.xml":
        return "Defines Struts action mappings and MVC flow configuration."
    if name == "hibernate.cfg.xml":
        return "Configures Hibernate ORM connection, dialect, and entity mapping settings."
    if name == "logback.xml" or name == "log4j2.xml" or name == "log4j.xml":
        return "Configures application logging appenders, patterns, and log levels."
    if name in {"docker-compose.yml", "docker-compose.yaml"}:
        return "Defines multi-container Docker service topology, networking, and volumes."
    if name in {"kubernetes.yml", "k8s.yml", ".github/workflows"} or (name.endswith(".yml") and "/workflows/" in item.relpath.as_posix().lower()):
        return "Defines CI/CD pipeline or Kubernetes resource configuration."
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

    if project_type == "Desktop GUI + CLI developer tool" and is_contexta_self_file(item):
        desktop_exact_roles = {
            "context_engine.py": "Implements project analysis, scoring, and smart context selection.",
            "renderer.py": "Formats selected analysis into the final context pack output.",
            "scanner.py": "Scans the project tree, applies filters, and reads safe text content.",
            "syntax.py": "Extracts syntax-aware symbols and imports through tree-sitter-backed parsing helpers.",
            "ui.py": "Implements the desktop GUI and export workflow orchestration.",
            "cli.py": "Implements the command-line workflow for pack generation and output.",
            "theme.py": "Defines GUI theme palettes and widget repaint behavior.",
            "requirements.txt": "Declares runtime dependencies for parsing, token estimation, and repository analysis.",
            "requirements-build.txt": "Declares build-time tooling for packaging the desktop application.",
            "build.bat": "Automates Windows executable packaging through the build pipeline.",
            "build.sh": "Automates Unix-like executable packaging and distribution bundle generation.",
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

    if project_type in {"Django web application", "Flask web application"}:
        if name == "manage.py":
            return "Django management entry point for running commands, migrations, and the dev server."
        if name in {"settings.py", "settings"}:
            return "Configures Django application settings, installed apps, databases, and middleware."
        if name == "urls.py":
            return "Defines URL routing patterns for the Django application."
        if name == "models.py" or "/models/" in rel:
            return "Defines database models and ORM schema for the application domain."
        if name == "views.py" or "/views/" in rel:
            return "Implements view logic that handles HTTP requests and returns responses."
        if name == "serializers.py" or "/serializers/" in rel:
            return "Defines serializers for transforming model instances to/from JSON."
        if name == "admin.py":
            return "Registers models with the Django admin interface."
        if name == "forms.py" or "/forms/" in rel:
            return "Defines form classes for user input validation and processing."
        if "migrations" in rel:
            return "Database migration file tracking schema changes over time."
        if "service" in name or "/services/" in rel:
            return "Implements service-layer logic that coordinates domain operations."
        if "repository" in name or "/repositories/" in rel:
            return "Handles data access and query operations for a domain entity."

    if project_type in {"Spring Boot application", "Spring web application", "Java application"}:
        if "controller" in name or "/controller/" in rel or "/controllers/" in rel:
            return "Implements REST controller endpoints that handle HTTP requests."
        if "service" in name or "/service/" in rel or "/services/" in rel:
            return "Implements business logic in the service layer."
        if "repository" in name or "/repository/" in rel or "dao" in name or "/dao/" in rel:
            return "Handles data access and persistence using JPA/Hibernate repositories."
        if "entity" in name or "model" in name or "/entity/" in rel or "/model/" in rel:
            return "Defines a JPA entity or domain model mapped to a database table."
        if "config" in name or "/config/" in rel:
            return "Configures Spring application context, beans, or security settings."
        if name.endswith("application.java") or ("application" in name and name.endswith(".java")):
            return "Main Spring Boot application entry point with `@SpringBootApplication`."
        if name in {"application.properties", "application.yml", "application.yaml"}:
            return "Configures Spring Boot application properties and environment settings."
        if name == "pom.xml":
            return "Maven build descriptor defining project dependencies, plugins, and build lifecycle."
        if name in {"build.gradle", "build.gradle.kts"}:
            return "Gradle build script defining project dependencies and build tasks."

    if project_type == "ASP.NET Core application":
        if name == "program.cs":
            return "Acts as the ASP.NET Core application entrypoint and host/bootstrap configuration."
        if name == "appsettings.json":
            return "Defines ASP.NET Core environment and application settings."
        if "controller" in name or "/controller" in rel or "/controllers/" in rel:
            return "Implements ASP.NET Core controller endpoints that handle HTTP requests."
        if "service" in name or "/services/" in rel:
            return "Implements service-layer logic used by the ASP.NET Core application."
        if "middleware" in name or "/middleware/" in rel:
            return "Implements ASP.NET Core middleware in the request pipeline."

    if project_type == "Android application":
        if name == "androidmanifest.xml":
            return "Declares Android app components, permissions, and metadata."
        if "activity" in name:
            return "Implements an Android Activity screen."
        if "fragment" in name:
            return "Implements an Android Fragment UI component."
        if "viewmodel" in name:
            return "Implements a ViewModel for managing UI-related data in the Android architecture."
        if "adapter" in name:
            return "Implements a RecyclerView or list adapter for displaying collections."
        if name in {"build.gradle", "build.gradle.kts"}:
            return "Gradle build script for the Android module."

    if project_type == "Ruby on Rails application":
        if name == "gemfile":
            return "Declares Ruby dependencies and Bundler-managed application packages."
        if rel.endswith("config/routes.rb"):
            return "Defines Rails routes that map requests to controller actions."
        if "controller" in name or "/controllers/" in rel:
            return "Implements Rails controller actions for request handling."
        if "model" in name or "/models/" in rel:
            return "Defines an Active Record model used by the application domain."
        if "/views/" in rel:
            return "Defines a Rails view template rendered for user-facing pages."
        if "migration" in rel:
            return "Database migration file tracking schema changes over time."

    if project_type == "Phoenix web application":
        if name == "mix.exs":
            return "Declares Elixir application metadata, dependencies, and Mix build settings."
        if name == "router.ex" or "/router.ex" in rel:
            return "Defines Phoenix routes, pipelines, and controller or LiveView dispatch."
        if "controller" in name or "/controllers/" in rel:
            return "Implements Phoenix controller actions for HTTP request handling."
        if "/live/" in rel or "live" in name:
            return "Implements a Phoenix LiveView or live component."
        if "/templates/" in rel:
            return "Defines Phoenix server-rendered templates or component markup."

    if project_type == "Flutter application":
        if name in {"pubspec.yaml", "pubspec.yml"}:
            return "Declares Flutter package metadata, dependencies, and platform configuration."
        if rel.endswith("lib/main.dart"):
            return "Acts as the Flutter application entrypoint and root widget bootstrap."
        if "widget" in name or "/widgets/" in rel:
            return "Defines a reusable Flutter widget used across screens."
        if "screen" in name or "page" in name or "/screens/" in rel:
            return "Implements a Flutter screen or routed page."

    if project_type == "Electron desktop application":
        if name == "package.json":
            return "Declares Electron dependencies, scripts, and package metadata."
        if name in {"main.js", "main.ts"}:
            return "Acts as the Electron main-process entrypoint and desktop runtime bootstrap."
        if "preload" in name:
            return "Defines the Electron preload bridge between the main process and renderer."
        if "/renderer/" in rel or name in {"index.tsx", "index.jsx", "app.tsx", "app.jsx"}:
            return "Implements renderer-process UI for the Electron desktop application."

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

    if project_type == "Desktop GUI + CLI developer tool" and is_contexta_self_file(item):
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
