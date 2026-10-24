"""contexta_app.engine.constants: split out of context_engine.py. Bodies are unchanged."""

from __future__ import annotations

import re
from rapidfuzz.fuzz import ratio

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
    "lean": "Token-Lean",
}

PACK_OPTIONS: dict[str, str] = {
    "custom": "Custom Pack",
    "chatgpt": "ChatGPT Pack",
    "onboarding": "Onboarding Pack",
    "pr_review": "PR Review Pack",
    "risk_review": "Risk Review Pack",
    "debug": "Debug Pack",
    "bugfix": "Bugfix Pack",
    "backend": "Backend Pack",
    "frontend": "Frontend Pack",
    "changes_related": "Changes + Related",
    "refactor": "Refactor Pack",
    "raw_files": "Raw Files Dump",
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
    "bugfix": {
        "ai_profile": "claude",
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
    "refactor": {
        "ai_profile": "generic",
        "context_mode": "refactor",
        "task_profile": "refactor_request",
        "compression": "focused",
    },
    "raw_files": {
        "ai_profile": "generic",
        "context_mode": "full",
        "task_profile": "general",
        "compression": "full",
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

UNICODE_ALPHA_TOKEN_RE = re.compile(r"[^\W\d_]{3,}", re.UNICODE)

CAMEL_CASE_TOKEN_RE = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)")

def extract_alpha_tokens(text: str) -> list[str]:
    return UNICODE_ALPHA_TOKEN_RE.findall(text)

def normalized_name_similarity(left: str, right: str) -> int:
    left_key = re.sub(r"[^a-z0-9]+", "", left.lower())
    right_key = re.sub(r"[^a-z0-9]+", "", right.lower())
    if not left_key or not right_key:
        return 0
    return int(ratio(left_key, right_key))

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
    "ruby": "Ruby",
    "elixir": "Elixir",
    "dart": "Dart",
    "java": "Java",
    "kotlin": "Kotlin",
    "scala": "Scala",
    "csharp": "C#",
    "go": "Go",
    "rust": "Rust",
    "cpp": "C++",
    "c": "C",
    "swift": "Swift",
    "lua": "Lua",
    "r": "R",
    "nim": "Nim",
    "zig": "Zig",
    "html": "HTML",
    "css": "CSS",
    "scss": "SCSS",
    "vue": "Vue",
    "svelte": "Svelte",
    "json": "JSON config",
    "yaml": "YAML",
    "toml": "TOML",
    "xml": "XML",
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
    "kotlin": 1.2,
    "scala": 1.1,
    "swift": 1.2,
    "cpp": 1.1,
    "c": 1.0,
    "lua": 0.9,
    "r": 0.9,
    "nim": 0.9,
    "zig": 0.9,
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
    "build.gradle": (8.0, "build manifest"),
    "build.gradle.kts": (8.0, "build manifest"),
    "settings.gradle": (6.0, "gradle settings"),
    "settings.gradle.kts": (6.0, "gradle settings"),
    "gemfile": (8.0, "ruby dependency manifest"),
    "angular.json": (8.0, "angular workspace"),
    "pubspec.yaml": (8.0, "dart/flutter manifest"),
    "pubspec.yml": (8.0, "dart/flutter manifest"),
    "mix.exs": (8.0, "elixir manifest"),
    "manage.py": (7.0, "django management"),
    "settings.py": (6.0, "django settings"),
    "urls.py": (6.0, "django routing"),
    "program.cs": (7.0, "dotnet entrypoint"),
    "appsettings.json": (6.0, "dotnet config"),
    "application.properties": (6.0, "spring config"),
    "application.yml": (6.0, "spring config"),
    "application.yaml": (6.0, "spring config"),
    "main.go": (7.0, "go entrypoint"),
    "main.rs": (7.0, "rust entrypoint"),
    "router.ex": (7.0, "phoenix routing"),
    "androidmanifest.xml": (8.0, "android manifest"),
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
    "nuxt.config.": (6.5, "framework config"),
    "vite.config.": (6.0, "bundler config"),
    "astro.config.": (6.0, "framework config"),
    "remix.config.": (6.0, "framework config"),
    "tailwind.config.": (5.0, "styling config"),
    "application.": (4.0, "spring boot config"),
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
        ("has_nest", 5),
        ("has_routes_dir", 3),
        ("has_controllers", 2),
        ("has_db_models", 2),
    ],
    "django_app": [
        ("has_django", 8),
        ("has_manage_py", 5),
        ("has_python", 2),
        ("has_db_models", 1),
    ],
    "flask_app": [
        ("has_flask", 8),
        ("has_python", 2),
        ("has_routes_dir", 2),
    ],
    "spring_boot_app": [
        ("has_spring_boot", 8),
        ("has_java", 3),
        ("has_maven", 2),
        ("has_gradle", 2),
    ],
    "aspnet_app": [
        ("has_csharp", 5),
        ("has_nuget", 4),
        ("has_aspnet", 6),
        ("has_controllers", 2),
    ],
    "java_app": [
        ("has_java", 4),
        ("has_maven", 4),
        ("has_gradle", 4),
        ("has_controllers", 2),
        ("has_db_models", 1),
    ],
    "android_app": [
        ("has_android_manifest", 8),
        ("has_java", 3),
        ("has_gradle", 3),
    ],
    "rails_app": [
        ("has_rails", 8),
        ("has_ruby", 3),
        ("has_routes_dir", 2),
    ],
    "phoenix_app": [
        ("has_phoenix", 8),
        ("has_elixir", 3),
        ("has_routes_dir", 2),
    ],
    "flutter_app": [
        ("has_flutter", 8),
        ("has_dart", 3),
    ],
    "desktop_js_app": [
        ("has_electron", 7),
        ("has_javascript_runtime", 2),
    ],
    "laravel_app": [
        ("has_laravel", 8),
        ("has_php", 2),
        ("has_composer", 2),
        ("has_routes_dir", 1),
    ],
    "php_crud_app": [
        ("has_php", 5),
        ("has_composer", 4),
        ("has_php_forms", 3),
        ("has_php_service_layer", 2),
        ("has_php_dao_layer", 3),
    ],
    "go_app": [
        ("has_go", 5),
        ("has_go_modules", 4),
        ("has_go_cmd_dir", 2),
        ("has_routes_dir", 1),
    ],
    "rust_app": [
        ("has_rust", 5),
        ("has_cargo", 4),
        ("has_rust_web", 3),
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
    "django_app": "Django web application",
    "flask_app": "Flask web application",
    "spring_boot_app": "Spring Boot application",
    "aspnet_app": "ASP.NET Core application",
    "java_app": "Java application",
    "android_app": "Android application",
    "rails_app": "Ruby on Rails application",
    "phoenix_app": "Phoenix web application",
    "flutter_app": "Flutter application",
    "desktop_js_app": "Electron desktop application",
    "laravel_app": "Laravel web application",
    "php_crud_app": "PHP CRUD web application",
    "go_app": "Go application",
    "rust_app": "Rust application",
    "desktop_python_app": "Desktop GUI + CLI developer tool",
}

DOMAIN_HINTS = {
    "education": ["aluno", "alunos", "escola", "matricula", "matrícula", "professor", "turma", "student", "students", "school", "course", "classroom", "grade", "lesson", "enrollment"],
    "ecommerce": ["cart", "checkout", "product", "products", "catalog", "catalogo", "catálogo", "price", "pricing", "order", "inventory", "payment", "shipping", "store"],
    "marketing_site": ["hero", "navbar", "footer", "cta", "landing", "testimonial", "marketing", "campaign", "banner", "newsletter", "conversion"],
    "admin_panel": ["dashboard", "users", "settings", "reports", "admin", "management", "analytics", "permission", "role", "audit", "log"],
    "task_management": ["task", "tasks", "kanban", "board", "sprint", "backlog", "ticket", "issue", "workflow", "todo", "milestone", "assignee", "priority", "status", "column", "card"],
    "finance": ["invoice", "payment", "transaction", "balance", "account", "ledger", "budget", "expense", "revenue", "billing", "tax", "receipt"],
    "healthcare": ["patient", "medical", "hospital", "diagnosis", "appointment", "doctor", "prescription", "clinic", "health", "record"],
    "social": ["feed", "post", "comment", "like", "follow", "friend", "message", "notification", "profile", "mention"],
    "image_editing": ["image", "editor", "editing", "photo", "photoshop", "layer", "layers", "brush", "filter", "canvas", "pixel", "crop", "mask", "raster", "palette"],
    "graph_analysis": ["graph", "graphs", "network", "networks", "node", "nodes", "edge", "edges", "gephi", "layout", "centrality", "community", "visualization", "visualisation", "cluster"],
    "content_management": ["cms", "article", "articles", "editorial", "publish", "published", "draft", "slug", "author", "contentful", "storyblok", "sanity"],
    "developer_tooling": ["cli", "command", "repo", "repository", "plugin", "build", "export", "analysis", "scanner", "renderer", "pack", "prompt", "workflow"],
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
