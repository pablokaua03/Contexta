"""contexta_app.engine.surfaces: split out of context_engine.py. Bodies are unchanged."""

from __future__ import annotations

import re

from contexta_app.engine.models import (
    FileInsight,
    ProjectFingerprint,
)
from contexta_app.engine.manifests import (
    identity_weight_for,
)
from contexta_app.engine.roles import (
    infer_file_role,
)

def detect_project_shape(fingerprint: ProjectFingerprint) -> str:
    return fingerprint.project_type or "developer-facing software project"

def is_packaging_helper(item: FileInsight) -> bool:
    name = item.path.name.lower()
    if name in {"build.bat", "build.sh", "version_info.txt"}:
        return True
    if name.endswith(".spec"):
        return True
    return False

def project_stack_tokens(fingerprint: ProjectFingerprint | None) -> set[str]:
    if not fingerprint:
        return set()
    tokens: set[str] = set()
    for value in [fingerprint.primary_language or "", fingerprint.project_type or ""]:
        tokens.update(re.findall(r"[a-z0-9]+", value.lower()))
    for bucket in (
        fingerprint.frameworks,
        fingerprint.runtime,
        fingerprint.package_managers,
        fingerprint.build_tools,
        fingerprint.main_dependencies,
    ):
        for value in bucket:
            tokens.update(re.findall(r"[a-z0-9]+", value.lower()))
    return tokens

def is_dependency_manifest_surface(item: FileInsight) -> bool:
    _weight, label = identity_weight_for(item)
    if not label:
        return False
    lowered = label.lower()
    return any(token in lowered for token in ("manifest", "workspace", "build manifest", "module manifest", "project manifest"))

def is_runtime_config_surface(item: FileInsight) -> bool:
    rel = f"/{item.relpath.as_posix().lower()}"
    name = item.path.name.lower()
    _weight, label = identity_weight_for(item)
    lowered = (label or "").lower()
    if any(token in lowered for token in ("config", "settings", "routing", "management", "compiler")):
        return True
    if any(
        token in rel
        for token in (
            "/config/",
            "/configs/",
            "/settings/",
            "/environments/",
            "/resources/",
            "/properties/",
            "/routes/",
        )
    ):
        return True
    return name in {
        ".env",
        ".env.example",
        "manage.py",
        "program.cs",
        "appsettings.json",
        "application.properties",
        "application.yml",
        "application.yaml",
        "angular.json",
        "androidmanifest.xml",
        "router.ex",
        "urls.py",
        "settings.py",
        "config/routes.rb",
    }

def is_schema_surface(item: FileInsight, fingerprint: ProjectFingerprint | None = None) -> bool:
    rel = f"/{item.relpath.as_posix().lower()}"
    name = item.path.name.lower()
    content = item.content.lower()
    stack = project_stack_tokens(fingerprint)

    if any(
        token in rel
        for token in (
            "/migrations/",
            "/migration/",
            "/db/migrate/",
            "/alembic/",
            "schema.prisma",
            "schema.sql",
            "schema.rb",
            "/entities/",
            "/entity/",
        )
    ):
        return True
    if name in {"models.py", "schema.prisma", "schema.sql", "schema.rb"}:
        return True
    if any(token in content for token in ("create table", "alter table", "drop table", "modelbuilder.entity", "db_table")):
        return True
    if "django" in stack and rel.endswith("/models.py"):
        return True
    if ("rails" in stack or "laravel" in stack or "spring" in stack or "asp" in stack) and any(
        token in rel for token in ("/models/", "/entities/", "/entity/")
    ):
        return True
    return False

def is_user_facing_surface(item: FileInsight, fingerprint: ProjectFingerprint | None = None) -> bool:
    rel = f"/{item.relpath.as_posix().lower()}"
    name = item.path.name.lower()
    stack = project_stack_tokens(fingerprint)

    if rel.endswith(("/page.tsx", "/page.jsx", "/page.vue", "/page.svelte", "/index.php")):
        return True
    if any(token in rel for token in ("/templates/", "/screens/", "/screen/", "/activities/", "/fragments/", "/views/")):
        return True
    if "flutter" in stack and any(token in rel for token in ("/screens/", "/pages/", "/widgets/")):
        return True
    if "android" in stack and any(token in name for token in ("activity", "fragment")):
        return True
    return False

def is_request_boundary_surface(item: FileInsight, fingerprint: ProjectFingerprint | None = None) -> bool:
    rel = f"/{item.relpath.as_posix().lower()}"
    name = item.path.name.lower()
    content = item.content.lower()

    if is_user_facing_surface(item, fingerprint):
        return True
    if any(
        token in rel
        for token in (
            "/controllers/",
            "/controller/",
            "/handlers/",
            "/handler/",
            "/routes/",
            "/router",
            "/api/",
            "/middleware/",
            "/views.py",
            "/live/",
            "/endpoints/",
        )
    ):
        return True
    if any(token in name for token in ("controller", "handler", "middleware", "router", "endpoint")):
        return True
    boundary_patterns = (
        "@app.route",
        "@router.",
        "@getmapping",
        "@postmapping",
        "@putmapping",
        "@patchmapping",
        "@deletemapping",
        "@requestmapping",
        "[httpget]",
        "[httppost]",
        "[httpput]",
        "[httppatch]",
        "[httpdelete]",
        "router.get(",
        "router.post(",
        "router.put(",
        "router.patch(",
        "app.get(",
        "app.post(",
        "app.put(",
        "mapget(",
        "mappost(",
        "httphandlefunc(",
        "gin.context",
        "echo.context",
        "fiber.ctx",
    )
    return any(pattern in content for pattern in boundary_patterns)

def is_runtime_entry_surface(item: FileInsight, fingerprint: ProjectFingerprint | None = None) -> bool:
    name = item.path.name.lower()
    if name in {"main.py", "app.py", "server.py", "manage.py", "program.cs", "main.go", "main.rs", "main.dart", "contexta.py"}:
        return True
    if item.path.stem.lower() in {"main", "app", "server"} and len(item.relpath.parts) <= 2:
        return True
    return "entrypoint" in item.tags and not is_user_facing_surface(item, fingerprint)

def is_shared_state_surface(item: FileInsight, fingerprint: ProjectFingerprint | None = None) -> bool:
    rel = f"/{item.relpath.as_posix().lower()}"
    name = item.path.name.lower()
    content = item.content.lower()
    role = (item.summary or infer_file_role(item, fingerprint.project_type if fingerprint else None)).lower()

    path_tokens = ("auth", "locale", "translation", "translations", "provider", "context", "store", "state", "reducer", "session")
    if any(token in rel for token in path_tokens):
        return True
    if any(token in name for token in ("provider", "context", "store", "reducer")):
        return True
    if any(token in role for token in ("translation hooks", "localization", "authentication state", "shared state", "shared behavior")):
        return True
    if any(token in content for token in ("createcontext", "usecontext", "configureservices(", "configure<", "provide(", "inject(")):
        return True
    return False

def looks_like_input_flow(item: FileInsight) -> bool:
    path = f"/{item.relpath.as_posix().lower()}"
    content = item.content.lower()
    path_submission_hint = any(
        token in path
        for token in (
            "/form",
            "/contact",
            "/checkout",
            "/register",
            "/signup",
            "/salvar",
            "/save",
            "/submit",
            "/create",
            "/edit",
            "/update",
            "/store",
        )
    )
    content_submission_hint = any(
        token in content
        for token in (
            "<form",
            "onsubmit",
            "handlechange",
            "react-hook-form",
            "formik",
            "request.method == 'post'",
            'request.method == "post"',
            "request.post",
            "request.form",
            "$_post",
            "@postmapping",
            "[httppost]",
            "router.post(",
            "app.post(",
            "mappost(",
            "validate(",
            "savechanges(",
            "db.session.commit",
        )
    )
    return path_submission_hint or content_submission_hint

def is_background_coordination_surface(item: FileInsight) -> bool:
    rel = f"/{item.relpath.as_posix().lower()}"
    content = item.content.lower()
    if any(token in rel for token in ("/jobs/", "/job/", "/workers/", "/worker/", "/tasks/", "/task/", "/queue/", "/scheduler/")):
        return True
    return any(
        token in content
        for token in (
            "threading",
            "asyncio",
            "subprocess",
            "celery",
            "sidekiq",
            "backgroundservice",
            "task.run(",
            "scheduler",
            "cron",
            "queue",
            "worker",
            "go func(",
            "tokio::spawn",
            "processbuilder(",
        )
    )

def is_public_api_surface(item: FileInsight, fingerprint: ProjectFingerprint | None = None) -> bool:
    if not fingerprint or not fingerprint.project_type or not any(
        token in fingerprint.project_type.lower() for token in ("library", "package")
    ):
        return False
    rel = item.relpath.as_posix().lower()
    name = item.path.name.lower()
    return name in {"__init__.py", "index.ts", "index.js", "index.tsx", "lib.rs", "mod.rs"} or rel in {
        "src/lib.rs",
        "src/index.ts",
        "src/index.js",
        "src/index.tsx",
    }
