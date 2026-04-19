"""
tests/test_context_engine.py - Focused tests for analysis heuristics.
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

TEST_TMP_ROOT = Path(__file__).parent / ".tmp"
TEST_TMP_ROOT.mkdir(exist_ok=True)

from contexta_app.context_engine import (
    ExportConfig,
    ProjectFingerprint,
    build_analysis,
    build_relationship_map,
    build_task_prompt,
    classify_file,
    compute_risk_score,
    extract_alpha_tokens,
    extract_import_enriched_domain_tokens,
    extract_relevant_excerpt,
    infer_file_role_pipeline,
    make_file_insight,
    pick_core_module_labels,
    pick_core_module_names,
    summarize_file,
    test_relation_score,
)
from contexta_app.scanner import build_tree
from contexta_app.ui import resolve_pack_focus


class TestAnalysisHeuristics(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(dir=TEST_TMP_ROOT))

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def _insight(self, relpath: str, content: str):
        path = self.tmp / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        item = make_file_insight(self.tmp, path)
        item.tags.update(classify_file(item))
        return item

    def _fingerprint(self, project_type: str, primary_language: str, frameworks: list[str] | None = None):
        return ProjectFingerprint(
            primary_language=primary_language,
            frameworks=frameworks or [],
            runtime=[],
            package_managers=[],
            build_tools=[],
            main_dependencies=[],
            scripts=[],
            project_type=project_type,
            probable_purpose=None,
            confidence=0.9,
            evidence=[],
        )

    def test_markdown_docs_stay_as_docs(self):
        item = self._insight("README.pt-BR.md", "# Contexta\n\nFerramenta desktop.\n")
        summary = summarize_file(item, {})
        self.assertIn("docs", item.tags)
        self.assertIn("project", summary.lower())
        self.assertNotIn("traverses", summary.lower())

    def test_test_package_init_gets_small_summary(self):
        item = self._insight("tests/__init__.py", "# tests package\n")
        summary = summarize_file(item, {})
        self.assertIn("init", item.tags)
        self.assertIn("tests package", summary.lower())
        self.assertNotIn("coverage", summary.lower())

    def test_version_info_gets_specific_summary(self):
        item = self._insight("version_info.txt", "VSVersionInfo(\n)\n")
        summary = summarize_file(item, {})
        self.assertEqual(summary, "Defines Windows version metadata used in packaged executable builds.")

    def test_embedded_asset_excerpt_omits_blob(self):
        blob = "A" * 180
        item = self._insight(
            "brand_assets.py",
            '\n'.join([
                '"""Embedded brand assets for Contexta."""',
                "",
                "ICON_PNG_B64 = (",
                f'    "{blob}"',
                f'    "{blob}"',
                f'    "{blob}"',
                f'    "{blob}"',
                f'    "{blob}"',
                f'    "{blob}"',
                f'    "{blob}"',
                f'    "{blob}"',
                ")",
            ]),
        )
        excerpt, reason = extract_relevant_excerpt(item, "icon brand")
        self.assertIn("embedded_asset", item.tags)
        self.assertIn("omitted", reason.lower())
        self.assertIn("<embedded asset data omitted>", excerpt)
        self.assertNotIn(blob, excerpt)

    def test_markdown_with_dense_line_is_not_classified_as_embedded_asset(self):
        long_line = "A" * 180
        item = self._insight(
            "CHANGELOG.md",
            "\n".join([
                "# Changelog",
                "",
                "## [1.6.0] - 2026-04-17",
                long_line,
            ]),
        )
        summary = summarize_file(item, {})
        self.assertIn("docs", item.tags)
        self.assertNotIn("embedded_asset", item.tags)
        self.assertNotIn("assets", item.tags)
        self.assertIn("releases", summary.lower())

    def test_renderer_summary_wins_over_analysis_overlap(self):
        item = self._insight(
            "renderer.py",
            "\n".join([
                "from context_engine import build_analysis",
                "",
                "def generate_markdown():",
                "    return build_analysis",
            ]),
        )
        summary = summarize_file(item, {})
        self.assertIn("renderer", item.tags)
        self.assertEqual(summary, "Formats selected analysis into the final context pack output.")

    def test_context_engine_keeps_analysis_summary(self):
        item = self._insight(
            "context_engine.py",
            "\n".join([
                "class ProjectAnalysis:",
                "    pass",
                "",
                "def build_analysis():",
                "    return ProjectAnalysis",
                "",
                "example = 'def generate_markdown('",
            ]),
        )
        summary = summarize_file(item, {}, "Desktop GUI + CLI developer tool")
        self.assertIn("analysis", item.tags)
        self.assertNotIn("renderer", item.tags)
        self.assertEqual(summary, "Implements project analysis, scoring, and smart context selection.")

    def test_theme_summary_wins_over_generic_ui_summary(self):
        item = self._insight(
            "theme.py",
            "\n".join([
                "import tkinter as tk",
                "",
                "def apply_theme(theme):",
                "    return theme",
                "",
                "def toggle_theme():",
                "    return True",
            ]),
        )
        summary = summarize_file(item, {})
        self.assertIn("theme", item.tags)
        self.assertNotIn("ui", item.tags)
        self.assertEqual(summary, "Defines GUI theme palettes and widget repaint behavior.")

    def test_support_file_summaries_are_specific(self):
        requirements = self._insight("requirements.txt", "pathspec\ntiktoken\n")
        build_requirements = self._insight("requirements-build.txt", "nuitka\npyinstaller\n")
        build_bat = self._insight("build.bat", "@echo off\npy -m nuitka contexta.py\n")
        build_sh = self._insight("build.sh", "#!/usr/bin/env bash\npython3 -m PyInstaller contexta.py\ntar -czf dist/contexta-linux.tar.gz dist/contexta\n")
        self.assertIn("runtime dependencies", summarize_file(requirements, {}).lower())
        self.assertIn("build-time tooling", summarize_file(build_requirements, {}).lower())
        self.assertIn("nuitka-based build pipeline", summarize_file(build_bat, {}).lower())
        self.assertIn("linux install bundle", summarize_file(build_sh, {}).lower())

    def test_mdcodebrief_summary_mentions_compatibility_shim(self):
        item = self._insight("mdcodebrief.py", "from contexta import main\n\nmain()\n")
        summary = summarize_file(item, {})
        self.assertIn("compatibility shim", summary.lower())
        self.assertIn("contexta.main()", summary)

    def test_contexta_summary_uses_main_entrypoint_wording(self):
        item = self._insight("contexta.py", "from ui import App\n\nApp()\n")
        summary = summarize_file(item, {})
        self.assertEqual(summary, "Acts as the main entrypoint that routes execution into the GUI or CLI flow.")

    def test_syntax_summary_mentions_tree_sitter_role(self):
        item = self._insight("syntax.py", "from tree_sitter_language_pack import get_parser\n")
        summary = summarize_file(item, {})
        self.assertIn("syntax-aware symbols", summary.lower())
        self.assertIn("tree-sitter", summary.lower())

    def test_make_file_insight_extracts_go_symbols(self):
        path = self.tmp / "cmd" / "main.go"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join([
                "package main",
                "",
                'import "fmt"',
                "",
                "type Server struct{}",
                "",
                "func main() {",
                '    fmt.Println("ok")',
                "}",
            ]),
            encoding="utf-8",
        )
        item = make_file_insight(self.tmp, path)
        self.assertIn("main", item.functions)
        self.assertIn("Server", item.classes)
        self.assertIn("fmt", item.imports)

    def test_make_file_insight_extracts_rust_symbols(self):
        path = self.tmp / "src" / "lib.rs"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join([
                "use crate::graph::Node;",
                "",
                "struct Graph;",
                "",
                "fn run() {}",
            ]),
            encoding="utf-8",
        )
        item = make_file_insight(self.tmp, path)
        self.assertIn("run", item.functions)
        self.assertIn("Graph", item.classes)
        self.assertTrue(any("crate::graph::Node" in imported for imported in item.imports))

    def test_project_fingerprint_detects_python_desktop_gui_cli_tool(self):
        (self.tmp / "contexta.py").write_text("__name__ = '__main__'\n", encoding="utf-8")
        (self.tmp / "ui.py").write_text("import tkinter as tk\n", encoding="utf-8")
        (self.tmp / "cli.py").write_text("import argparse\n", encoding="utf-8")
        (self.tmp / "renderer.py").write_text("def generate_markdown():\n    return ''\n", encoding="utf-8")
        (self.tmp / "scanner.py").write_text("def build_tree():\n    return {}\n", encoding="utf-8")
        (self.tmp / "requirements.txt").write_text(
            "\n".join(["pathspec", "charset-normalizer", "tiktoken", "tree-sitter", "tree-sitter-language-pack", "rapidfuzz"]),
            encoding="utf-8",
        )

        tree = build_tree(self.tmp, False, False, lambda *_args, **_kwargs: None, [0], [], self.tmp)
        analysis = build_analysis(
            self.tmp,
            tree,
            [],
            ExportConfig(context_mode="onboarding", task_profile="explain_project"),
            lambda *_args, **_kwargs: None,
        )

        self.assertEqual(analysis.fingerprint.primary_language, "Python")
        self.assertEqual(analysis.fingerprint.project_type, "Desktop GUI + CLI developer tool")
        self.assertIn("Tkinter", analysis.fingerprint.frameworks)
        self.assertIn("CLI", analysis.fingerprint.runtime)
        self.assertIn("Python standard library", analysis.technologies)
        self.assertIn("syntax-aware parsing", analysis.technologies)
        self.assertIn("token-aware pack sizing", analysis.technologies)
        self.assertNotIn("Tkinter desktop interface", analysis.technologies)
        self.assertNotIn("pip-style requirements", [entry.lower() for entry in analysis.technologies])
        self.assertIn("desktop GUI + CLI developer tool built around repository analysis and export workflows", analysis.summary_lines[0])
        self.assertTrue(any("Primary language: Python" in line for line in analysis.summary_lines))
        self.assertTrue(any("Detection confidence:" in line for line in analysis.summary_lines))
        self.assertTrue(any("Detected from:" in line for line in analysis.summary_lines))
        evidence_line = next(line for line in analysis.summary_lines if "Detected from:" in line)
        self.assertIn("contexta.py", evidence_line)
        self.assertIn("ui.py", evidence_line)
        self.assertIn("cli.py", evidence_line)
        self.assertIn("requirements.txt", evidence_line)
        self.assertIn("Tkinter imports", evidence_line)

    def test_project_fingerprint_detects_nextjs_stack_from_manifest(self):
        (self.tmp / "package.json").write_text(
            "\n".join([
                "{",
                '  "dependencies": {',
                '    "next": "15.0.0",',
                '    "react": "19.0.0",',
                '    "firebase": "11.0.0"',
                "  },",
                '  "scripts": {',
                '    "dev": "next dev",',
                '    "build": "next build"',
                "  },",
                '  "devDependencies": {',
                '    "typescript": "5.0.0",',
                '    "tailwindcss": "4.0.0"',
                "  }",
                "}",
            ]),
            encoding="utf-8",
        )
        (self.tmp / "tsconfig.json").write_text('{"compilerOptions":{"jsx":"preserve"}}\n', encoding="utf-8")
        app_dir = self.tmp / "app"
        app_dir.mkdir(exist_ok=True)
        (app_dir / "page.tsx").write_text("export default function Page() { return <main>Hello</main>; }\n", encoding="utf-8")
        (self.tmp / "styles.css").write_text("body { color: black; }\n", encoding="utf-8")

        tree = build_tree(self.tmp, False, False, lambda *_args, **_kwargs: None, [0], [], self.tmp)
        analysis = build_analysis(
            self.tmp,
            tree,
            [],
            ExportConfig(context_mode="full", task_profile="general"),
            lambda *_args, **_kwargs: None,
        )

        self.assertEqual(analysis.fingerprint.primary_language, "TypeScript")
        self.assertIn("Next.js", analysis.fingerprint.frameworks)
        self.assertIn("React", analysis.fingerprint.frameworks)
        self.assertIn("Tailwind CSS", analysis.technologies)
        self.assertIn("Firebase", analysis.technologies)
        self.assertEqual(analysis.fingerprint.project_type, "Frontend web application")
        self.assertIn("next", analysis.fingerprint.main_dependencies)
        self.assertIn("dev", analysis.fingerprint.scripts)
        self.assertTrue(analysis.fingerprint.summary_evidence.get("project_type"))
        self.assertIn("frontend web application built around routed pages, shared UI components, and client-side tooling", analysis.summary_lines[0])
        self.assertTrue(any("Frameworks: Next.js, React" in line for line in analysis.summary_lines))
        self.assertTrue(any("manifest dependencies: next, react" in line.lower() for line in analysis.summary_lines))
        self.assertTrue(any("Detected from:" in line and "package.json" in line for line in analysis.summary_lines))

    def test_project_fingerprint_detects_django_kanban_project(self):
        (self.tmp / "pyproject.toml").write_text(
            "\n".join([
                "[project]",
                'name = "kanbanflow"',
                'dependencies = ["django>=5.0", "djangorestframework>=3.15"]',
            ]),
            encoding="utf-8",
        )
        (self.tmp / "manage.py").write_text("from django.core.management import execute_from_command_line\n", encoding="utf-8")
        (self.tmp / "project" / "settings.py").parent.mkdir(parents=True, exist_ok=True)
        (self.tmp / "project" / "settings.py").write_text("INSTALLED_APPS = ['boards']\n", encoding="utf-8")
        (self.tmp / "project" / "urls.py").write_text("from django.urls import path\nurlpatterns = []\n", encoding="utf-8")
        (self.tmp / "boards" / "models.py").parent.mkdir(parents=True, exist_ok=True)
        (self.tmp / "boards" / "models.py").write_text(
            "\n".join([
                "from django.db import models",
                "class BoardCard(models.Model):",
                "    title = models.CharField(max_length=120)",
                "    status = models.CharField(max_length=32)",
                "    assignee = models.CharField(max_length=80)",
            ]),
            encoding="utf-8",
        )
        (self.tmp / "templates" / "boards" / "index.html").parent.mkdir(parents=True, exist_ok=True)
        (self.tmp / "templates" / "boards" / "index.html").write_text("<h1>Kanban Board</h1><div>Backlog</div>", encoding="utf-8")

        tree = build_tree(self.tmp, False, False, lambda *_args, **_kwargs: None, [0], [], self.tmp)
        analysis = build_analysis(
            self.tmp,
            tree,
            [],
            ExportConfig(context_mode="onboarding", task_profile="explain_project"),
            lambda *_args, **_kwargs: None,
        )

        self.assertEqual(analysis.fingerprint.primary_language, "Python")
        self.assertEqual(analysis.fingerprint.project_type, "Django web application")
        self.assertIn("Django", analysis.fingerprint.frameworks)
        self.assertIn("task or kanban", analysis.likely_purpose.lower())
        evidence_line = next(line for line in analysis.summary_lines if "Detected from:" in line)
        self.assertIn("pyproject.toml", evidence_line)
        self.assertIn("manage.py", evidence_line)

    def test_project_fingerprint_detects_spring_boot_from_pom_xml(self):
        (self.tmp / "pom.xml").write_text(
            "\n".join([
                "<project>",
                "  <modelVersion>4.0.0</modelVersion>",
                "  <groupId>com.example</groupId>",
                "  <artifactId>kanban-service</artifactId>",
                "  <dependencies>",
                '    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-web</artifactId></dependency>',
                '    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-data-jpa</artifactId></dependency>',
                "  </dependencies>",
                "</project>",
            ]),
            encoding="utf-8",
        )
        (self.tmp / "src" / "main" / "java" / "com" / "example" / "KanbanApplication.java").parent.mkdir(parents=True, exist_ok=True)
        (self.tmp / "src" / "main" / "java" / "com" / "example" / "KanbanApplication.java").write_text(
            "\n".join([
                "import org.springframework.boot.autoconfigure.SpringBootApplication;",
                "@SpringBootApplication",
                "public class KanbanApplication {}",
            ]),
            encoding="utf-8",
        )
        (self.tmp / "src" / "main" / "java" / "com" / "example" / "controllers" / "BoardController.java").parent.mkdir(parents=True, exist_ok=True)
        (self.tmp / "src" / "main" / "java" / "com" / "example" / "controllers" / "BoardController.java").write_text(
            "public class BoardController { String workflow = \"kanban\"; }",
            encoding="utf-8",
        )
        (self.tmp / "src" / "main" / "java" / "com" / "example" / "models" / "TaskCard.java").parent.mkdir(parents=True, exist_ok=True)
        (self.tmp / "src" / "main" / "java" / "com" / "example" / "models" / "TaskCard.java").write_text(
            "public class TaskCard { String status; String assignee; }",
            encoding="utf-8",
        )
        (self.tmp / "src" / "main" / "resources" / "application.properties").parent.mkdir(parents=True, exist_ok=True)
        (self.tmp / "src" / "main" / "resources" / "application.properties").write_text("spring.application.name=kanban-service\n", encoding="utf-8")

        tree = build_tree(self.tmp, False, False, lambda *_args, **_kwargs: None, [0], [], self.tmp)
        analysis = build_analysis(
            self.tmp,
            tree,
            [],
            ExportConfig(context_mode="full", task_profile="general"),
            lambda *_args, **_kwargs: None,
        )

        self.assertEqual(analysis.fingerprint.primary_language, "Java")
        self.assertEqual(analysis.fingerprint.project_type, "Spring Boot application")
        self.assertIn("Spring Boot", analysis.fingerprint.frameworks)
        self.assertIn("JPA/Hibernate", analysis.technologies)
        self.assertIn("task or kanban", analysis.likely_purpose.lower())
        evidence_line = next(line for line in analysis.summary_lines if "Detected from:" in line)
        self.assertIn("pom.xml", evidence_line)

    def test_project_fingerprint_detects_aspnet_core_project(self):
        (self.tmp / "KanbanApp.csproj").write_text(
            "\n".join([
                "<Project Sdk=\"Microsoft.NET.Sdk.Web\">",
                "  <ItemGroup>",
                "    <PackageReference Include=\"Microsoft.AspNetCore.Mvc.NewtonsoftJson\" Version=\"8.0.0\" />",
                "  </ItemGroup>",
                "</Project>",
            ]),
            encoding="utf-8",
        )
        (self.tmp / "Program.cs").write_text(
            "\n".join([
                "var builder = WebApplication.CreateBuilder(args);",
                "builder.Services.AddControllers();",
                "var app = builder.Build();",
                "app.MapControllers();",
                "app.Run();",
            ]),
            encoding="utf-8",
        )
        (self.tmp / "appsettings.json").write_text('{"Logging":{"LogLevel":{"Default":"Information"}}}', encoding="utf-8")
        (self.tmp / "Controllers" / "BoardController.cs").parent.mkdir(parents=True, exist_ok=True)
        (self.tmp / "Controllers" / "BoardController.cs").write_text(
            "\n".join([
                "[ApiController]",
                "[Route(\"api/board\")]",
                "public class BoardController : ControllerBase {",
                "  public string Get() => \"kanban workflow\";",
                "}",
            ]),
            encoding="utf-8",
        )

        tree = build_tree(self.tmp, False, False, lambda *_args, **_kwargs: None, [0], [], self.tmp)
        analysis = build_analysis(
            self.tmp,
            tree,
            [],
            ExportConfig(context_mode="full", task_profile="general"),
            lambda *_args, **_kwargs: None,
        )

        self.assertEqual(analysis.fingerprint.project_type, "ASP.NET Core application")
        self.assertIn("ASP.NET Core", analysis.fingerprint.frameworks)
        self.assertEqual(analysis.fingerprint.primary_language, "C#")
        self.assertIn("task", analysis.likely_purpose.lower())

    def test_project_fingerprint_detects_go_kanban_service(self):
        (self.tmp / "go.mod").write_text(
            "\n".join([
                "module github.com/example/kanban",
                "",
                "go 1.23",
                "",
                "require github.com/gin-gonic/gin v1.10.0",
            ]),
            encoding="utf-8",
        )
        (self.tmp / "cmd" / "server" / "main.go").parent.mkdir(parents=True, exist_ok=True)
        (self.tmp / "cmd" / "server" / "main.go").write_text(
            "\n".join([
                "package main",
                'import "github.com/gin-gonic/gin"',
                "func main() {",
                "  r := gin.Default()",
                '  r.GET("/boards", func(c *gin.Context) {})',
                "}",
            ]),
            encoding="utf-8",
        )
        (self.tmp / "internal" / "kanban" / "service.go").parent.mkdir(parents=True, exist_ok=True)
        (self.tmp / "internal" / "kanban" / "service.go").write_text(
            "package kanban\n\ntype TaskCard struct { Status string; Assignee string }\n",
            encoding="utf-8",
        )

        tree = build_tree(self.tmp, False, False, lambda *_args, **_kwargs: None, [0], [], self.tmp)
        analysis = build_analysis(
            self.tmp,
            tree,
            [],
            ExportConfig(context_mode="full", task_profile="general"),
            lambda *_args, **_kwargs: None,
        )

        self.assertEqual(analysis.fingerprint.project_type, "Go application")
        self.assertEqual(analysis.fingerprint.primary_language, "Go")
        self.assertIn("Gin", analysis.fingerprint.frameworks)
        self.assertIn("task", analysis.likely_purpose.lower())

    def test_project_fingerprint_detects_nuxt_frontend(self):
        (self.tmp / "package.json").write_text(
            '{"dependencies":{"nuxt":"4.0.0","vue":"3.5.0"}}\n',
            encoding="utf-8",
        )
        (self.tmp / "nuxt.config.ts").write_text("export default defineNuxtConfig({})\n", encoding="utf-8")
        (self.tmp / "app" / "pages" / "index.vue").parent.mkdir(parents=True, exist_ok=True)
        (self.tmp / "app" / "pages" / "index.vue").write_text("<template><HeroSection /></template>\n", encoding="utf-8")

        tree = build_tree(self.tmp, False, False, lambda *_args, **_kwargs: None, [0], [], self.tmp)
        analysis = build_analysis(
            self.tmp,
            tree,
            [],
            ExportConfig(context_mode="onboarding", task_profile="explain_project"),
            lambda *_args, **_kwargs: None,
        )

        self.assertEqual(analysis.fingerprint.project_type, "Frontend web application")
        self.assertIn("Nuxt", analysis.fingerprint.frameworks)
        self.assertIn("Vue", analysis.fingerprint.frameworks)
        self.assertEqual(analysis.fingerprint.primary_language, "TypeScript")

    def test_project_fingerprint_detects_nest_backend(self):
        (self.tmp / "package.json").write_text(
            '{"dependencies":{"@nestjs/core":"11.0.0","@nestjs/common":"11.0.0","reflect-metadata":"0.2.0","rxjs":"7.8.0"}}\n',
            encoding="utf-8",
        )
        (self.tmp / "src" / "main.ts").parent.mkdir(parents=True, exist_ok=True)
        (self.tmp / "src" / "main.ts").write_text("import { NestFactory } from '@nestjs/core'\n", encoding="utf-8")
        (self.tmp / "src" / "controllers" / "board.controller.ts").parent.mkdir(parents=True, exist_ok=True)
        (self.tmp / "src" / "controllers" / "board.controller.ts").write_text("export class BoardController {}\n", encoding="utf-8")

        tree = build_tree(self.tmp, False, False, lambda *_args, **_kwargs: None, [0], [], self.tmp)
        analysis = build_analysis(
            self.tmp,
            tree,
            [],
            ExportConfig(context_mode="full", task_profile="general"),
            lambda *_args, **_kwargs: None,
        )

        self.assertEqual(analysis.fingerprint.project_type, "Backend API service")
        self.assertIn("NestJS", analysis.fingerprint.frameworks)

    def test_project_fingerprint_detects_rails_application(self):
        (self.tmp / "Gemfile").write_text(
            "\n".join([
                'source "https://rubygems.org"',
                'gem "rails"',
                'gem "pg"',
            ]),
            encoding="utf-8",
        )
        (self.tmp / "config" / "routes.rb").parent.mkdir(parents=True, exist_ok=True)
        (self.tmp / "config" / "routes.rb").write_text("Rails.application.routes.draw do\n  root 'products#index'\nend\n", encoding="utf-8")
        (self.tmp / "app" / "controllers" / "products_controller.rb").parent.mkdir(parents=True, exist_ok=True)
        (self.tmp / "app" / "controllers" / "products_controller.rb").write_text("class ProductsController < ApplicationController\nend\n", encoding="utf-8")
        (self.tmp / "app" / "models" / "product.rb").parent.mkdir(parents=True, exist_ok=True)
        (self.tmp / "app" / "models" / "product.rb").write_text("class Product < ApplicationRecord\nend\n", encoding="utf-8")

        tree = build_tree(self.tmp, False, False, lambda *_args, **_kwargs: None, [0], [], self.tmp)
        analysis = build_analysis(
            self.tmp,
            tree,
            [],
            ExportConfig(context_mode="onboarding", task_profile="explain_project"),
            lambda *_args, **_kwargs: None,
        )

        self.assertEqual(analysis.fingerprint.project_type, "Ruby on Rails application")
        self.assertIn("Rails", analysis.fingerprint.frameworks)
        self.assertEqual(analysis.fingerprint.primary_language, "Ruby")
        evidence_line = next(line for line in analysis.summary_lines if "Detected from:" in line)
        self.assertIn("Gemfile", evidence_line)
        self.assertIn("config/routes.rb", evidence_line)

    def test_project_fingerprint_detects_flutter_application(self):
        (self.tmp / "pubspec.yaml").write_text(
            "\n".join([
                "name: kanban_mobile",
                "dependencies:",
                "  flutter:",
                "    sdk: flutter",
            ]),
            encoding="utf-8",
        )
        (self.tmp / "lib").mkdir(exist_ok=True)
        (self.tmp / "lib" / "main.dart").write_text(
            "\n".join([
                "import 'package:flutter/material.dart';",
                "void main() => runApp(const KanbanApp());",
                "class KanbanApp extends StatelessWidget {",
                "  const KanbanApp({super.key});",
                "}",
            ]),
            encoding="utf-8",
        )

        tree = build_tree(self.tmp, False, False, lambda *_args, **_kwargs: None, [0], [], self.tmp)
        analysis = build_analysis(
            self.tmp,
            tree,
            [],
            ExportConfig(context_mode="onboarding", task_profile="explain_project"),
            lambda *_args, **_kwargs: None,
        )

        self.assertEqual(analysis.fingerprint.project_type, "Flutter application")
        self.assertIn("Flutter", analysis.fingerprint.frameworks)
        self.assertEqual(analysis.fingerprint.primary_language, "Dart")

    def test_risks_warn_when_no_obvious_tests_are_detected(self):
        (self.tmp / "contexta.py").write_text("__name__ = '__main__'\n", encoding="utf-8")
        (self.tmp / "ui.py").write_text("import tkinter as tk\n", encoding="utf-8")
        (self.tmp / "renderer.py").write_text("def generate_markdown():\n    return ''\n", encoding="utf-8")
        tree = build_tree(self.tmp, False, False, lambda *_args, **_kwargs: None, [0], [], self.tmp)
        analysis = build_analysis(
            self.tmp,
            tree,
            [],
            ExportConfig(context_mode="full", task_profile="general"),
            lambda *_args, **_kwargs: None,
        )
        self.assertTrue(any("No obvious automated tests were detected" in line for line in analysis.risks))

    def test_identity_files_outscore_low_signal_assets(self):
        (self.tmp / "package.json").write_text(
            '{"dependencies":{"react":"19.0.0"},"devDependencies":{"vite":"6.0.0","typescript":"5.0.0"}}\n',
            encoding="utf-8",
        )
        (self.tmp / "main.tsx").write_text("export function App() { return <div />; }\n", encoding="utf-8")
        (self.tmp / "styles.css").write_text("body { color: black; }\n", encoding="utf-8")

        tree = build_tree(self.tmp, False, False, lambda *_args, **_kwargs: None, [0], [], self.tmp)
        analysis = build_analysis(
            self.tmp,
            tree,
            [],
            ExportConfig(context_mode="full", task_profile="general"),
            lambda *_args, **_kwargs: None,
        )

        ranked = [item.relpath.as_posix() for item in analysis.important_files]
        self.assertLess(ranked.index("package.json"), ranked.index("styles.css"))

    def test_php_crud_project_type_and_domain_purpose_are_inferred(self):
        (self.tmp / "composer.json").write_text(
            "\n".join([
                "{",
                '  "require": {',
                '    "php": "^8.2",',
                '    "illuminate/database": "^12.0"',
                "  }",
                "}",
            ]),
            encoding="utf-8",
        )
        alunos_dir = self.tmp / "alunos"
        service_dir = self.tmp / "service"
        dao_dir = self.tmp / "dao"
        alunos_dir.mkdir(exist_ok=True)
        service_dir.mkdir(exist_ok=True)
        dao_dir.mkdir(exist_ok=True)
        (alunos_dir / "index.php").write_text("<h1>Sistema Escolar</h1>\n<?php echo 'Cadastro de Alunos'; ?>\n", encoding="utf-8")
        (alunos_dir / "form.php").write_text("<form><input name='matricula'></form>", encoding="utf-8")
        (service_dir / "AlunoService.php").write_text("<?php class AlunoService { public function listarTodos() {} }", encoding="utf-8")
        (dao_dir / "AlunoDao.php").write_text("<?php class AlunoDao { public function buscarPorId() {} }", encoding="utf-8")
        (self.tmp / "bootstrap.php").write_text("<?php $app = []; return $app;\n", encoding="utf-8")

        tree = build_tree(self.tmp, False, False, lambda *_args, **_kwargs: None, [0], [], self.tmp)
        analysis = build_analysis(
            self.tmp,
            tree,
            [],
            ExportConfig(context_mode="full", task_profile="general"),
            lambda *_args, **_kwargs: None,
        )

        self.assertEqual(analysis.fingerprint.project_type, "PHP CRUD web application")
        self.assertIn("Composer", analysis.technologies)
        self.assertIn("Illuminate Database", analysis.technologies)
        self.assertIn("student records", analysis.fingerprint.probable_purpose.lower())
        evidence_line = next(line for line in analysis.summary_lines if "Detected from:" in line)
        self.assertIn("composer.json", evidence_line)
        self.assertIn("alunos/index.php", evidence_line)
        self.assertIn("alunos/form.php", evidence_line)
        self.assertIn("service/AlunoService.php", evidence_line)

    def test_infer_file_role_covers_service_repository_form_and_styles(self):
        service = self._insight("services/student_service.py", "class StudentService:\n    pass\n")
        repository = self._insight("repositories/student_repository.py", "class StudentRepository:\n    pass\n")
        form = self._insight("student_form.php", "<form><input name='student'></form>")
        styles = self._insight("styles/app.css", "body { color: black; }")
        manifest = self._insight("package.json", '{"dependencies":{"react":"19.0.0"}}')

        self.assertIn("service-layer", summarize_file(service, {}).lower())
        self.assertIn("data access", summarize_file(repository, {}).lower())
        self.assertIn("create/edit form flow", summarize_file(form, {}).lower())
        self.assertIn("visual styling", summarize_file(styles, {}).lower())
        self.assertIn("dependencies and package metadata", summarize_file(manifest, {}).lower())

    def test_php_crud_roles_cover_bootstrap_submission_and_domain_model(self):
        bootstrap = self._insight("bootstrap.php", "<?php $app = []; return $app;")
        save = self._insight("alunos/salvar.php", "<?php $_POST['nome'] ?? ''; header('Location: index.php');")
        model = self._insight("model/Aluno.php", "<?php class Aluno { public string $nome; }")

        self.assertIn("bootstrap", summarize_file(bootstrap, {}, "PHP CRUD web application").lower())
        self.assertIn("record persistence", summarize_file(save, {}, "PHP CRUD web application").lower())
        self.assertIn("domain model", summarize_file(model, {}, "PHP CRUD web application").lower())

    def test_php_crud_core_modules_use_semantic_flow_labels(self):
        items = [
            self._insight("alunos/index.php", "<?php echo 'Cadastro de Alunos'; ?>"),
            self._insight("alunos/form.php", "<form><input name='nome'></form>"),
            self._insight("bootstrap.php", "<?php return [];"),
            self._insight("service/AlunoService.php", "<?php class AlunoService {}"),
            self._insight("dao/AlunoDAO.php", "<?php class AlunoDAO {}"),
            self._insight("model/Aluno.php", "<?php class Aluno {}"),
        ]
        labels = pick_core_module_labels(items, "PHP CRUD web application")
        self.assertIn("main listing flow", labels)
        self.assertIn("form flow", labels)
        self.assertIn("service layer", labels)
        self.assertIn("bootstrap/runtime setup", labels)

    def test_infer_file_role_describes_semantic_frontend_pages(self):
        landing = self._insight(
            "app/page.tsx",
            "\n".join([
                "import MarketingNavbar from '@/components/MarketingNavbar';",
                "import SiteFooter from '@/components/SiteFooter';",
                "import HeroSection from '@/components/HeroSection';",
                "export default function Page() {",
                "  return <main><MarketingNavbar /><HeroSection /><SiteFooter /></main>;",
                "}",
            ]),
        )
        contact = self._insight(
            "app/contacto/page.tsx",
            "export default function ContactoPage() { return <form><input name='email' /><textarea /></form>; }",
        )
        products = self._insight(
            "app/productos/page.tsx",
            "export default function ProductosPage() { return <section>catalog products</section>; }",
        )
        courses = self._insight(
            "app/cursos/page.tsx",
            "export default function CursosPage() { return <section>courses academy</section>; }",
        )
        faq = self._insight(
            "app/faq/page.tsx",
            "export default function FAQPage() { return <section>faq help support</section>; }",
        )
        register = self._insight(
            "app/(auth)/register/page.tsx",
            "export default function RegisterPage() { return <form><input name='password' /></form>; }",
        )
        dashboard = self._insight(
            "app/dashboard/page.tsx",
            "export default function DashboardPage() { return <section>dashboard stats</section>; }",
        )

        self.assertIn("main landing page and composes the core marketing sections", summarize_file(landing, {}).lower())
        self.assertIn("contact page and user-facing contact form flow", summarize_file(contact, {}).lower())
        self.assertIn("product catalog and browsing page", summarize_file(products, {}).lower())
        self.assertIn("courses listing and discovery page", summarize_file(courses, {}).lower())
        self.assertIn("faq and user help page", summarize_file(faq, {}).lower())
        self.assertIn("user registration flow", summarize_file(register, {}).lower())
        self.assertIn("authenticated dashboard view", summarize_file(dashboard, {}).lower())

    def test_infer_file_role_describes_context_and_shell_components(self):
        locale_context = self._insight(
            "lib/LocaleContext.tsx",
            "\n".join([
                "import { createContext, useContext } from 'react';",
                "const LocaleContext = createContext(null);",
                "export function useLocale() { return useContext(LocaleContext); }",
            ]),
        )
        navbar = self._insight(
            "components/MarketingNavbar.tsx",
            "export function MarketingNavbar() { return <nav><a href='/'>Home</a></nav>; }",
        )
        footer = self._insight(
            "components/SiteFooter.tsx",
            "export function SiteFooter() { return <footer>Footer</footer>; }",
        )

        self.assertIn("locale state and translation hooks", summarize_file(locale_context, {}).lower())
        self.assertIn("primary navigation/header component", summarize_file(navbar, {}).lower())
        self.assertIn("shared footer content", summarize_file(footer, {}).lower())

    def test_context_engine_role_stays_analysis_engine(self):
        item = self._insight(
            "context_engine.py",
            "\n".join([
                "from scanner import get_language",
                "",
                "class ProjectFingerprint:",
                "    pass",
                "",
                "def build_analysis():",
                "    return ProjectFingerprint()",
                "",
                "sample = 'translations createContext useTranslations'",
            ]),
        )
        role = infer_file_role_pipeline(item, "Desktop GUI + CLI developer tool")
        self.assertEqual(role, "Implements project analysis, scoring, and smart context selection.")

    def test_php_crud_index_is_listing_page_not_landing_page(self):
        item = self._insight(
            "alunos/index.php",
            "\n".join([
                "<?php",
                "$service = new AlunoService();",
                "$alunos = $service->listarTodos();",
                "?>",
                "<h1>Sistema Escolar</h1>",
                "<table><tr><td>Aluno</td></tr></table>",
            ]),
        )
        role = infer_file_role_pipeline(item, "PHP CRUD web application")
        self.assertIn("listing page", role.lower())
        self.assertNotIn("landing page", role.lower())

    def test_next_contact_page_role_is_specific(self):
        item = self._insight(
            "app/contacto/page.tsx",
            "\n".join([
                "export default function ContactoPage() {",
                "  return <form><input /><textarea /></form>;",
                "}",
            ]),
        )
        role = infer_file_role_pipeline(item, "Frontend web application")
        self.assertEqual(role, "Implements the contact page and user-facing contact form flow.")

    def test_locale_context_role_is_specific(self):
        item = self._insight(
            "lib/LocaleContext.tsx",
            "\n".join([
                "const LocaleContext = createContext(undefined);",
                "export function useLocale() {}",
                "export function useTranslations() {}",
            ]),
        )
        role = infer_file_role_pipeline(item, "Frontend web application")
        self.assertEqual(role, "Provides locale state and translation hooks used across the app.")

    def test_test_files_do_not_appear_as_core_modules(self):
        source = self._insight("context_engine.py", "def build_analysis():\n    return None\n")
        test_file = self._insight("tests/test_context_engine.py", "def test_build_analysis():\n    assert True\n")
        core = pick_core_module_names([source, test_file])
        self.assertIn("context_engine", core)
        self.assertNotIn("test_context_engine", core)

    def test_core_module_labels_use_semantic_layer_names(self):
        items = [
            self._insight("contexta.py", "__name__ = '__main__'\n"),
            self._insight("ui.py", "import tkinter as tk\n\ndef launch_ui():\n    return tk.Tk()\n"),
            self._insight("cli.py", "import argparse\n"),
            self._insight("renderer.py", "def generate_markdown():\n    return ''\n"),
            self._insight("context_engine.py", "def build_analysis():\n    return None\n"),
            self._insight("scanner.py", "def build_tree():\n    return {}\n"),
        ]
        labels = pick_core_module_labels(items, "Desktop GUI + CLI developer tool")
        self.assertEqual(labels, ["application entrypoint", "GUI layer", "CLI layer", "analysis engine", "rendering layer", "scanning layer"])

    def test_summary_and_architecture_use_semantic_core_module_labels(self):
        (self.tmp / "contexta.py").write_text("__name__ = '__main__'\n", encoding="utf-8")
        (self.tmp / "ui.py").write_text("import tkinter as tk\n\ndef launch_ui():\n    return tk.Tk()\n", encoding="utf-8")
        (self.tmp / "cli.py").write_text("import argparse\n", encoding="utf-8")
        (self.tmp / "renderer.py").write_text("def generate_markdown():\n    return ''\n", encoding="utf-8")
        (self.tmp / "context_engine.py").write_text("def build_analysis():\n    return None\n", encoding="utf-8")
        (self.tmp / "scanner.py").write_text("def build_tree():\n    return {}\n", encoding="utf-8")

        tree = build_tree(self.tmp, False, False, lambda *_args, **_kwargs: None, [0], [], self.tmp)
        analysis = build_analysis(
            self.tmp,
            tree,
            [],
            ExportConfig(context_mode="full", task_profile="general"),
            lambda *_args, **_kwargs: None,
        )

        summary_blob = "\n".join(analysis.summary_lines)
        architecture_blob = "\n".join(analysis.architecture_lines)
        self.assertIn(
            "Core modules: application entrypoint (`contexta.py`), GUI layer (`ui.py`), CLI layer (`cli.py`), analysis engine (`context_engine.py`), rendering layer (`renderer.py`), and scanning layer (`scanner.py`)",
            summary_blob,
        )
        self.assertIn(
            "Core modules appear to center around application entrypoint (`contexta.py`), GUI layer (`ui.py`), CLI layer (`cli.py`), analysis engine (`context_engine.py`), rendering layer (`renderer.py`), and scanning layer (`scanner.py`).",
            architecture_blob,
        )

    def test_summary_uses_quality_signals_instead_of_supporting_tech_for_unittest(self):
        (self.tmp / "contexta.py").write_text("__name__ = '__main__'\n", encoding="utf-8")
        (self.tmp / "ui.py").write_text("import tkinter as tk\n\ndef launch_ui():\n    return tk.Tk()\n", encoding="utf-8")
        tests_dir = self.tmp / "tests"
        tests_dir.mkdir(exist_ok=True)
        (tests_dir / "test_ui.py").write_text("import unittest\n\nclass TestUI(unittest.TestCase):\n    pass\n", encoding="utf-8")

        tree = build_tree(self.tmp, False, False, lambda *_args, **_kwargs: None, [0], [], self.tmp)
        analysis = build_analysis(
            self.tmp,
            tree,
            [],
            ExportConfig(context_mode="onboarding", task_profile="explain_project"),
            lambda *_args, **_kwargs: None,
        )

        summary_blob = "\n".join(analysis.summary_lines)
        self.assertIn("Quality signals: unittest-based test suite", summary_blob)
        self.assertNotIn("Supporting technologies: unittest-based test suite", summary_blob)

    def test_contexta_style_self_analysis_ignores_test_fixture_framework_strings(self):
        app_dir = self.tmp / "contexta_app"
        app_dir.mkdir(exist_ok=True)
        (self.tmp / "requirements.txt").write_text(
            "\n".join([
                "pathspec>=0.12",
                "charset-normalizer>=3.4",
                "tiktoken>=0.12",
                "tree-sitter>=0.25",
                "tree-sitter-language-pack>=1.6",
                "rapidfuzz>=3.14",
            ]),
            encoding="utf-8",
        )
        (self.tmp / "contexta.py").write_text(
            "\n".join([
                "from __future__ import annotations",
                "import sys",
                "",
                "def main() -> None:",
                "    if len(sys.argv) > 1:",
                "        from contexta_app.cli import run_cli",
                "        run_cli()",
                "    else:",
                "        from contexta_app.ui import App",
                "        App().mainloop()",
            ]),
            encoding="utf-8",
        )
        (app_dir / "ui.py").write_text(
            "\n".join([
                "from __future__ import annotations",
                "import tkinter as tk",
                "from contexta_app.context_engine import build_analysis",
                "",
                "class App(tk.Tk):",
                "    pass",
            ]),
            encoding="utf-8",
        )
        (app_dir / "cli.py").write_text(
            "\n".join([
                "from __future__ import annotations",
                "import sys",
                "",
                "def run_cli() -> None:",
                "    print(sys.argv)",
            ]),
            encoding="utf-8",
        )
        (app_dir / "renderer.py").write_text(
            "\n".join([
                "from contexta_app.context_engine import build_analysis",
                "",
                "def generate_markdown():",
                "    return build_analysis()",
            ]),
            encoding="utf-8",
        )
        (app_dir / "scanner.py").write_text(
            "\n".join([
                "from pathlib import Path",
                "",
                "def read_file_safe(path: Path):",
                "    return path.read_text(encoding='utf-8'), False, 0",
            ]),
            encoding="utf-8",
        )
        (app_dir / "context_engine.py").write_text(
            "\n".join([
                "from contexta_app.scanner import read_file_safe",
                "",
                "def build_analysis():",
                "    return {",
                "        'summary': 'Scan local repositories and generate curated context packs for AI workflows.',",
                "        'quality_label': 'pytest-based test coverage',",
                "        'fixture': 'Spring Boot application',",
                "    }",
            ]),
            encoding="utf-8",
        )
        tests_dir = self.tmp / "tests"
        tests_dir.mkdir(exist_ok=True)
        (tests_dir / "test_context_engine.py").write_text(
            "\n".join([
                "import unittest",
                "",
                "class TestFixtures(unittest.TestCase):",
                "    def test_spring_fixture(self):",
                "        fixture = '@SpringBootApplication\\napplication.properties\\norg.springframework.boot'",
                "        self.assertTrue(fixture)",
            ]),
            encoding="utf-8",
        )

        tree = build_tree(self.tmp, False, False, lambda *_args, **_kwargs: None, [0], [], self.tmp)
        analysis = build_analysis(
            self.tmp,
            tree,
            [],
            ExportConfig(context_mode="onboarding", task_profile="explain_project"),
            lambda *_args, **_kwargs: None,
        )

        summary_blob = "\n".join(analysis.summary_lines)
        self.assertEqual(analysis.fingerprint.project_type, "Desktop GUI + CLI developer tool")
        self.assertIn("Tkinter", analysis.fingerprint.frameworks)
        self.assertNotIn("Spring Boot", analysis.fingerprint.frameworks)
        self.assertIn("Quality signals: unittest-based test suite", summary_blob)
        self.assertNotIn("Spring Boot", summary_blob)
        self.assertNotIn("pytest-based test coverage", summary_blob)

    def test_quality_signals_detect_real_pytest_usage(self):
        (self.tmp / "contexta.py").write_text("__name__ = '__main__'\n", encoding="utf-8")
        tests_dir = self.tmp / "tests"
        tests_dir.mkdir(exist_ok=True)
        (tests_dir / "test_cli.py").write_text(
            "\n".join([
                "import pytest",
                "",
                "@pytest.mark.parametrize('value', [1, 2])",
                "def test_cli(value):",
                "    assert value",
            ]),
            encoding="utf-8",
        )
        (self.tmp / "pytest.ini").write_text("[pytest]\naddopts = -q\n", encoding="utf-8")

        tree = build_tree(self.tmp, False, False, lambda *_args, **_kwargs: None, [0], [], self.tmp)
        analysis = build_analysis(
            self.tmp,
            tree,
            [],
            ExportConfig(context_mode="onboarding", task_profile="explain_project"),
            lambda *_args, **_kwargs: None,
        )

        self.assertIn("Quality signals: pytest-based test coverage", "\n".join(analysis.summary_lines))

    def test_unicode_domain_token_extraction_handles_imports_without_broad_ranges(self):
        item = self._insight(
            "src/localizacao/painel.py",
            "\n".join([
                "from aplicacao.modulos.gestao import PainelEducacional",
                "",
                "def carregar_visao_principal():",
                "    return 'gestão acadêmica'",
            ]),
        )

        self.assertEqual(
            extract_alpha_tokens("gestão acadêmica painel"),
            ["gestão", "acadêmica", "painel"],
        )
        tokens = extract_import_enriched_domain_tokens([item])
        self.assertIn("localizacao", tokens)
        self.assertIn("aplicacao", tokens)
        self.assertIn("gestão", tokens)

    def test_risk_analysis_prompt_mentions_hotspots_and_hints(self):
        prompt = build_task_prompt(Path("demo"), ExportConfig(task_profile="risk_analysis"))
        self.assertIn("regression hotspots", prompt)
        self.assertIn("risk hints", prompt)

    def test_js_local_imports_resolve_alias_and_relative_paths(self):
        app_dir = self.tmp / "app"
        components_dir = self.tmp / "components"
        lib_dir = self.tmp / "lib"
        app_dir.mkdir(exist_ok=True)
        components_dir.mkdir(exist_ok=True)
        lib_dir.mkdir(exist_ok=True)
        (app_dir / "page.tsx").write_text(
            "\n".join([
                "import MarketingNavbar from '@/components/MarketingNavbar';",
                "import { useTranslations } from '../lib/useTranslations';",
                "export default function Page() { return <MarketingNavbar />; }",
            ]),
            encoding="utf-8",
        )
        (components_dir / "MarketingNavbar.tsx").write_text("export default function MarketingNavbar() { return <nav />; }\n", encoding="utf-8")
        (lib_dir / "useTranslations.ts").write_text("export function useTranslations() { return {}; }\n", encoding="utf-8")

        tree = build_tree(self.tmp, False, False, lambda *_args, **_kwargs: None, [0], [], self.tmp)
        analysis = build_analysis(
            self.tmp,
            tree,
            [],
            ExportConfig(context_mode="feature", focus_query="marketing translations"),
            lambda *_args, **_kwargs: None,
        )

        page_item = next(item for item in analysis.all_files if item.relpath.as_posix() == "app/page.tsx")
        self.assertIn("components/MarketingNavbar.tsx", page_item.local_imports)
        self.assertIn("lib/useTranslations.ts", page_item.local_imports)

    def test_php_require_once_resolves_local_service_dependency(self):
        services = self.tmp / "services"
        services.mkdir(exist_ok=True)
        (self.tmp / "index.php").write_text(
            "\n".join([
                "<?php",
                "require_once 'services/AlunoService.php';",
                "echo 'Cadastro de Alunos';",
            ]),
            encoding="utf-8",
        )
        (services / "AlunoService.php").write_text(
            "<?php class AlunoService { public function listarTodos() {} }",
            encoding="utf-8",
        )

        tree = build_tree(self.tmp, False, False, lambda *_args, **_kwargs: None, [0], [], self.tmp)
        analysis = build_analysis(
            self.tmp,
            tree,
            [],
            ExportConfig(context_mode="full", task_profile="general"),
            lambda *_args, **_kwargs: None,
        )

        index_item = next(item for item in analysis.all_files if item.relpath.as_posix() == "index.php")
        self.assertIn("services/AlunoService.php", index_item.local_imports)

    def test_compute_risk_score_rises_for_changed_shared_form_without_tests(self):
        form_item = self._insight(
            "app/contact/page.tsx",
            "\n".join([
                "export default function ContactPage() {",
                "  return <form onSubmit={handleSubmit}>Contact</form>;",
                "}",
            ]),
        )
        consumer_a = self._insight(
            "app/page.tsx",
            "import ContactPage from './contact/page'\nexport default function Page() { return <ContactPage /> }\n",
        )
        consumer_b = self._insight(
            "app/dashboard/page.tsx",
            "import ContactPage from '../contact/page'\nexport default function Dashboard() { return <ContactPage /> }\n",
        )
        changed = {form_item.path.resolve()}
        reverse_index = {form_item.relpath.as_posix(): {consumer_a.relpath.as_posix(), consumer_b.relpath.as_posix()}}
        risk = compute_risk_score(form_item, [form_item, consumer_a, consumer_b], changed, reverse_index)
        self.assertGreaterEqual(risk.score, 8.0)
        self.assertIn("changed file", risk.reasons)
        self.assertIn("used by multiple selected files", risk.reasons)
        self.assertIn("input or submission flow", risk.reasons)
        self.assertIn("no obvious nearby test coverage", risk.reasons)

    def test_compute_risk_score_does_not_mark_context_engine_as_input_flow(self):
        item = self._insight(
            "context_engine.py",
            "def build_analysis():\n    return None\n\ndef build_task_prompt():\n    return 'submit the pack summary'\n",
        )
        risk = compute_risk_score(item, [item], set(), {})
        self.assertNotIn("input or submission flow", risk.reasons)

    def test_compute_risk_score_marks_django_settings_as_runtime_config(self):
        item = self._insight(
            "project/settings.py",
            "INSTALLED_APPS = ['app']\nDATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3'}}\n",
        )
        item.summary = summarize_file(item, {}, "Django web application")
        risk = compute_risk_score(
            item,
            [item],
            set(),
            {},
            self._fingerprint("Django web application", "Python", ["Django"]),
        )
        self.assertIn("runtime or environment configuration", risk.reasons)
        self.assertIn("config_surface", risk.risk_flags)

    def test_compute_risk_score_marks_spring_controller_as_request_boundary(self):
        item = self._insight(
            "src/main/java/demo/UserController.java",
            "\n".join([
                "@RestController",
                "@PostMapping(\"/users\")",
                "class UserController { }",
            ]),
        )
        item.summary = summarize_file(item, {}, "Spring Boot application")
        risk = compute_risk_score(
            item,
            [item],
            set(),
            {},
            self._fingerprint("Spring Boot application", "Java", ["Spring Boot"]),
        )
        self.assertIn("request or routing boundary", risk.reasons)
        self.assertIn("request_boundary", risk.risk_flags)

    def test_compute_risk_score_marks_flutter_provider_as_shared_state(self):
        item = self._insight(
            "lib/providers/auth_provider.dart",
            "\n".join([
                "class AuthProvider extends ChangeNotifier {",
                "  void setUser(String id) { notifyListeners(); }",
                "}",
            ]),
        )
        item.summary = summarize_file(item, {}, "Flutter application")
        risk = compute_risk_score(
            item,
            [item],
            set(),
            {},
            self._fingerprint("Flutter application", "Dart", ["Flutter"]),
        )
        self.assertIn("shared app-wide behavior", risk.reasons)
        self.assertIn("shared_state", risk.risk_flags)

    def test_compute_risk_score_marks_rails_migration_as_schema_surface(self):
        item = self._insight(
            "db/migrate/202604170001_create_users.rb",
            "\n".join([
                "class CreateUsers < ActiveRecord::Migration[7.1]",
                "  def change",
                "    create_table :users do |t|",
                "    end",
                "  end",
                "end",
            ]),
        )
        item.summary = summarize_file(item, {}, "Ruby on Rails application")
        risk = compute_risk_score(
            item,
            [item],
            set(),
            {},
            self._fingerprint("Ruby on Rails application", "Ruby", ["Rails"]),
        )
        self.assertIn("schema or data model surface", risk.reasons)
        self.assertIn("schema_surface", risk.risk_flags)

    def test_compute_risk_score_marks_package_manifest_as_dependency_surface(self):
        item = self._insight(
            "package.json",
            '{"dependencies":{"next":"15.0.0","react":"19.0.0"}}\n',
        )
        risk = compute_risk_score(
            item,
            [item],
            {item.path.resolve()},
            {},
            self._fingerprint("Frontend web application", "TypeScript", ["Next.js", "React"]),
        )
        self.assertIn("dependency or build surface", risk.reasons)
        self.assertIn("changed dependency or build config", risk.reasons)
        self.assertIn("dependency_surface", risk.risk_flags)

    def test_marketing_domain_can_be_inferred_from_imports_and_visible_strings(self):
        (self.tmp / "package.json").write_text(
            '{"dependencies":{"next":"15.0.0","react":"19.0.0"}}\n',
            encoding="utf-8",
        )
        app_dir = self.tmp / "app"
        app_dir.mkdir(exist_ok=True)
        (app_dir / "page.tsx").write_text(
            "\n".join([
                "import MarketingNavbar from '@/components/MarketingNavbar';",
                "import SiteFooter from '@/components/SiteFooter';",
                "export default function Page() {",
                "  return <main><h1>Products and Courses</h1><p>Contact our team</p></main>;",
                "}",
            ]),
            encoding="utf-8",
        )
        tree = build_tree(self.tmp, False, False, lambda *_args, **_kwargs: None, [0], [], self.tmp)
        analysis = build_analysis(
            self.tmp,
            tree,
            [],
            ExportConfig(context_mode="onboarding", task_profile="explain_project"),
            lambda *_args, **_kwargs: None,
        )

        self.assertEqual(analysis.fingerprint.project_type, "Frontend web application")
        self.assertIn("marketing", analysis.fingerprint.probable_purpose.lower())

    def test_risk_analysis_selection_prefers_high_risk_files(self):
        app_dir = self.tmp / "app"
        app_dir.mkdir(exist_ok=True)
        (app_dir / "page.tsx").write_text(
            "\n".join(
                ["export default function Page() {", "  return <form onSubmit={handleSubmit}>Hi</form>;", "}"]
                + [f"const line_{i} = {i}" for i in range(650)]
            ),
            encoding="utf-8",
        )
        lib_dir = self.tmp / "lib"
        lib_dir.mkdir(exist_ok=True)
        (lib_dir / "LocaleContext.tsx").write_text(
            "export const LocaleContext = createContext(undefined)\nexport function useLocale() { return LocaleContext }\n",
            encoding="utf-8",
        )
        tests_dir = self.tmp / "tests"
        tests_dir.mkdir(exist_ok=True)
        (tests_dir / "test_renderer.py").write_text("def test_renderer():\n    assert True\n", encoding="utf-8")

        tree = build_tree(self.tmp, False, False, lambda *_args, **_kwargs: None, [0], [], self.tmp)
        analysis = build_analysis(
            self.tmp,
            tree,
            [],
            ExportConfig(task_profile="risk_analysis", context_mode="debug", compression="focused"),
            lambda *_args, **_kwargs: None,
        )

        selected_relpaths = {item.relpath.as_posix() for item in analysis.selected_files}
        self.assertIn("app/page.tsx", selected_relpaths)
        self.assertIn("lib/LocaleContext.tsx", selected_relpaths)

    def test_relationship_map_does_not_claim_unrelated_test_covers_ui(self):
        ui_item = self._insight("ui.py", "def render_ui():\n    return True\n")
        test_item = self._insight(
            "tests/test_context_engine.py",
            "\n".join([
                "from ui import render_ui",
                "",
                "def test_pack_focus_switch():",
                "    assert render_ui() is True",
            ]),
        )
        relationships = build_relationship_map([ui_item, test_item], {ui_item.relpath.as_posix(): {test_item.relpath.as_posix()}})
        self.assertFalse(any("is likely tested by `tests/test_context_engine.py`" in line for line in relationships))

    def test_relationship_map_requires_explicit_test_name_for_likely_test_relation(self):
        scanner_item = self._insight(
            "scanner.py",
            "\n".join([
                "def build_tree():",
                "    return {}",
                "",
                "def read_file_safe(path):",
                "    return '', False, 0",
            ]),
        )
        broad_test = self._insight(
            "tests/test_context_engine.py",
            "\n".join([
                "from scanner import build_tree",
                "",
                "def test_general_analysis():",
                "    assert build_tree() == {}",
            ]),
        )
        dedicated_test = self._insight(
            "tests/test_scanner_behavior.py",
            "\n".join([
                "from scanner import build_tree, read_file_safe",
                "",
                "def test_scanner_paths():",
                "    assert build_tree() == {}",
                "    assert read_file_safe('x')[1] is False",
            ]),
        )
        relationships = build_relationship_map(
            [scanner_item, broad_test, dedicated_test],
            {scanner_item.relpath.as_posix(): {broad_test.relpath.as_posix(), dedicated_test.relpath.as_posix()}},
        )
        self.assertFalse(any("`scanner.py` is likely tested by `tests/test_context_engine.py`" in line for line in relationships))
        self.assertTrue(any("`scanner.py` is likely tested by `tests/test_scanner_behavior.py`" in line for line in relationships))

    def test_relationship_map_uses_stronger_import_wording(self):
        page_item = self._insight(
            "app/page.tsx",
            "\n".join([
                "import LocaleContext from '../lib/LocaleContext';",
                "export default function Page() { return <main />; }",
            ]),
        )
        locale_item = self._insight(
            "lib/LocaleContext.tsx",
            "\n".join([
                "const LocaleContext = createContext(undefined);",
                "export default LocaleContext;",
            ]),
        )
        page_item.local_imports = ["lib/LocaleContext.tsx"]
        relationships = build_relationship_map([page_item, locale_item], {})
        self.assertIn("`app/page.tsx` imports directly from `lib/LocaleContext.tsx`", relationships)

    def test_test_files_do_not_accumulate_module_tags_from_snippets(self):
        item = self._insight(
            "tests/test_context_engine.py",
            "\n".join([
                "def test_classifier_noise():",
                "    sample = 'def generate_markdown('",
                "    sample2 = 'class ProjectAnalysis'",
                "    sample3 = 'toggle_theme and apply_theme'",
            ]),
        )
        self.assertEqual(item.tags, {"test"})

    def test_normal_source_excerpt_keeps_dense_import_lines(self):
        item = self._insight(
            "renderer.py",
            "from context_engine import APP_NAME, AI_PROFILE_OPTIONS, COMPRESSION_OPTIONS, CONTEXT_MODE_OPTIONS, PACK_OPTIONS, TASK_PROFILE_OPTIONS, ExportConfig, build_analysis, extract_relevant_excerpt, extract_signatures\n",
        )
        excerpt, reason = extract_relevant_excerpt(item, "")
        self.assertIn("from context_engine import", excerpt)
        self.assertNotIn("<embedded blob omitted>", excerpt)
        self.assertNotIn("omitted", reason.lower())

    def test_related_test_detection_accepts_import_plus_symbol_signal(self):
        item = self._insight(
            "scanner.py",
            "\n".join([
                "def build_tree():",
                "    return {}",
                "",
                "def read_file_safe(path):",
                "    return '', False, 0",
            ]),
        )
        candidate = self._insight(
            "tests/test_scanner_behavior.py",
            "\n".join([
                "from scanner import build_tree, read_file_safe",
                "",
                "def test_tree_scan():",
                "    assert build_tree() == {}",
                "    assert read_file_safe('x')[1] is False",
            ]),
        )
        self.assertGreaterEqual(test_relation_score(item, candidate), 3)

    def test_summary_lists_only_selected_tests(self):
        (self.tmp / "contexta.py").write_text("__name__ = '__main__'\n", encoding="utf-8")
        (self.tmp / "context_engine.py").write_text("class ProjectAnalysis:\n    pass\n", encoding="utf-8")
        (self.tmp / "renderer.py").write_text("def generate_markdown():\n    return ''\n", encoding="utf-8")
        (self.tmp / "scanner.py").write_text("def build_tree():\n    return {}\n", encoding="utf-8")
        for index in range(12):
            (self.tmp / f"module_{index}.py").write_text(f"def helper_{index}():\n    return {index}\n", encoding="utf-8")
        tests_dir = self.tmp / "tests"
        tests_dir.mkdir(exist_ok=True)
        (tests_dir / "test_context_engine.py").write_text("def test_a():\n    assert True\n", encoding="utf-8")
        (tests_dir / "test_renderer.py").write_text("def test_b():\n    assert True\n", encoding="utf-8")
        (tests_dir / "test_scanner.py").write_text("def test_c():\n    assert True\n", encoding="utf-8")
        (tests_dir / "test_utils.py").write_text("def test_d():\n    assert True\n", encoding="utf-8")

        tree = build_tree(self.tmp, False, False, lambda *_args, **_kwargs: None, [0], [], self.tmp)
        analysis = build_analysis(
            self.tmp,
            tree,
            [],
            ExportConfig(context_mode="feature", focus_query="context_engine renderer scanner"),
            lambda *_args, **_kwargs: None,
        )
        summary_blob = "\n".join(analysis.summary_lines)

        self.assertIn("test_context_engine.py", summary_blob)
        self.assertIn("test_renderer.py", summary_blob)
        self.assertNotIn("test_utils.py", summary_blob)

    def test_diff_code_review_selection_stays_surgical(self):
        (self.tmp / "renderer.py").write_text("from context_engine import build_analysis\n\ndef generate_markdown():\n    return build_analysis()\n", encoding="utf-8")
        (self.tmp / "context_engine.py").write_text("class ProjectAnalysis:\n    pass\n\ndef build_analysis():\n    return ProjectAnalysis\n", encoding="utf-8")
        (self.tmp / "ui.py").write_text("def launch_ui():\n    return True\n", encoding="utf-8")
        (self.tmp / "README.md").write_text("# Contexta\n", encoding="utf-8")
        tests_dir = self.tmp / "tests"
        tests_dir.mkdir(exist_ok=True)
        (tests_dir / "test_renderer.py").write_text("from renderer import generate_markdown\n\ndef test_render():\n    assert generate_markdown\n", encoding="utf-8")
        for index in range(15):
            (self.tmp / f"module_{index}.py").write_text(f"def helper_{index}():\n    return {index}\n", encoding="utf-8")

        tree = build_tree(self.tmp, False, False, lambda *_args, **_kwargs: None, [0], [], self.tmp)
        analysis = build_analysis(
            self.tmp,
            tree,
            [self.tmp / "renderer.py"],
            ExportConfig(context_mode="diff", task_profile="code_review"),
            lambda *_args, **_kwargs: None,
        )

        self.assertLessEqual(len(analysis.selected_files), 12)
        self.assertIn("renderer.py", [item.relpath.as_posix() for item in analysis.selected_files])
        self.assertNotIn("README.md", [item.relpath.as_posix() for item in analysis.selected_files])

    def test_onboarding_selection_stays_compact(self):
        (self.tmp / "contexta.py").write_text("__name__ = '__main__'\n", encoding="utf-8")
        (self.tmp / "ui.py").write_text("import tkinter as tk\n", encoding="utf-8")
        (self.tmp / "cli.py").write_text("import argparse\n", encoding="utf-8")
        (self.tmp / "renderer.py").write_text("def generate_markdown():\n    return ''\n", encoding="utf-8")
        (self.tmp / "context_engine.py").write_text("class ProjectAnalysis:\n    pass\n\ndef build_analysis():\n    return ProjectAnalysis\n", encoding="utf-8")
        (self.tmp / "scanner.py").write_text("def build_tree():\n    return {}\n", encoding="utf-8")
        (self.tmp / "README.md").write_text("# Contexta\n", encoding="utf-8")
        tests_dir = self.tmp / "tests"
        tests_dir.mkdir(exist_ok=True)
        (tests_dir / "test_ui.py").write_text("from ui import tk\n\ndef test_ui_boot():\n    assert tk\n", encoding="utf-8")
        for index in range(20):
            (self.tmp / f"module_{index}.py").write_text(f"def helper_{index}():\n    return {index}\n", encoding="utf-8")

        tree = build_tree(self.tmp, False, False, lambda *_args, **_kwargs: None, [0], [], self.tmp)
        analysis = build_analysis(
            self.tmp,
            tree,
            [],
            ExportConfig(context_mode="onboarding", task_profile="explain_project"),
            lambda *_args, **_kwargs: None,
        )
        self.assertLessEqual(len(analysis.selected_files), 12)
        relpaths = [item.relpath.as_posix() for item in analysis.selected_files]
        self.assertIn("README.md", relpaths)
        self.assertLessEqual(sum(1 for path in relpaths if path.startswith("tests/")), 2)

    def test_task_prompt_stays_task_focused_without_model_guidance(self):
        prompt = build_task_prompt(Path("demo"), ExportConfig(task_profile="code_review", ai_profile="claude"))
        self.assertIn("Prioritize correctness risks", prompt)
        self.assertNotIn("Usually works well", prompt)

    def test_write_tests_selection_brings_existing_tests(self):
        (self.tmp / "scanner.py").write_text(
            "\n".join([
                "def build_tree():",
                "    return {}",
                "",
                "def read_file_safe(path):",
                "    return '', False, 0",
            ]),
            encoding="utf-8",
        )
        tests_dir = self.tmp / "tests"
        tests_dir.mkdir(exist_ok=True)
        (tests_dir / "test_scanner.py").write_text(
            "\n".join([
                "from scanner import build_tree, read_file_safe",
                "",
                "def test_tree():",
                "    assert build_tree() == {}",
                "    assert read_file_safe('x')[1] is False",
            ]),
            encoding="utf-8",
        )
        tree = build_tree(self.tmp, False, False, lambda *_args, **_kwargs: None, [0], [], self.tmp)
        analysis = build_analysis(
            self.tmp,
            tree,
            [],
            ExportConfig(task_profile="write_tests"),
            lambda *_args, **_kwargs: None,
        )
        relpaths = [item.relpath.as_posix() for item in analysis.selected_files]
        self.assertIn("scanner.py", relpaths)
        self.assertIn("tests/test_scanner.py", relpaths)

    def test_dead_code_selection_prefers_low_signal_files(self):
        (self.tmp / "contexta.py").write_text("__name__ = '__main__'\n", encoding="utf-8")
        (self.tmp / "utils.py").write_text("def helper():\n    return True\n", encoding="utf-8")
        (self.tmp / "orphan_helper.py").write_text("def orphan():\n    return 1\n", encoding="utf-8")
        tree = build_tree(self.tmp, False, False, lambda *_args, **_kwargs: None, [0], [], self.tmp)
        analysis = build_analysis(
            self.tmp,
            tree,
            [],
            ExportConfig(task_profile="find_dead_code"),
            lambda *_args, **_kwargs: None,
        )
        relpaths = [item.relpath.as_posix() for item in analysis.selected_files]
        self.assertIn("orphan_helper.py", relpaths)

    def test_pack_focus_switch_replaces_previous_auto_value(self):
        focus, auto = resolve_pack_focus("", "", "backend api server")
        self.assertEqual((focus, auto), ("backend api server", "backend api server"))

        focus, auto = resolve_pack_focus(focus, auto, "frontend ui screen")
        self.assertEqual((focus, auto), ("frontend ui screen", "frontend ui screen"))

    def test_pack_focus_switch_preserves_manual_value(self):
        focus, auto = resolve_pack_focus("custom auth flow", "backend api server", "frontend ui screen")
        self.assertEqual((focus, auto), ("custom auth flow", "backend api server"))


    # ------------------------------------------------------------------
    # New detection tests: real-world project scenarios
    # ------------------------------------------------------------------

    def test_project_fingerprint_detects_kotlin_android_app(self):
        """Kotlin-only Android app should be detected as Android (not Java/PHP)."""
        (self.tmp / "app" / "src" / "main").mkdir(parents=True, exist_ok=True)
        (self.tmp / "app" / "src" / "main" / "AndroidManifest.xml").write_text(
            '<?xml version="1.0"?><manifest package="com.example.tasks"><application android:label="KanbanApp"/></manifest>',
            encoding="utf-8",
        )
        (self.tmp / "app" / "build.gradle").write_text(
            "apply plugin: 'com.android.application'\n"
            "android { compileSdk 34 }\n"
            "dependencies { implementation 'org.jetbrains.kotlin:kotlin-stdlib:1.9.0' }\n",
            encoding="utf-8",
        )
        (self.tmp / "app" / "src" / "main" / "java" / "com" / "example").mkdir(parents=True, exist_ok=True)
        (self.tmp / "app" / "src" / "main" / "java" / "com" / "example" / "MainActivity.kt").write_text(
            "class MainActivity : AppCompatActivity() { override fun onCreate() {} }",
            encoding="utf-8",
        )
        tree = build_tree(self.tmp, False, False, lambda *_a, **_kw: None, [0], [], self.tmp)
        analysis = build_analysis(
            self.tmp, tree, [],
            ExportConfig(context_mode="full", task_profile="general"),
            lambda *_a, **_kw: None,
        )
        self.assertEqual(analysis.fingerprint.project_type, "Android application")
        self.assertTrue(any("android" in f.lower() for f in analysis.fingerprint.frameworks))

    def test_project_fingerprint_detects_django_without_manage_py(self):
        """Django projects identified via settings.py + urls.py when manage.py is absent."""
        (self.tmp / "myapp").mkdir()
        (self.tmp / "myapp" / "settings.py").write_text(
            "INSTALLED_APPS = ['django.contrib.admin', 'tasks']\nDATABASES = {}\n",
            encoding="utf-8",
        )
        (self.tmp / "myapp" / "urls.py").write_text(
            "from django.urls import path\nurlpatterns = []\n",
            encoding="utf-8",
        )
        (self.tmp / "tasks" / "models.py").parent.mkdir(parents=True, exist_ok=True)
        (self.tmp / "tasks" / "models.py").write_text(
            "from django.db import models\nclass Task(models.Model):\n    title = models.CharField(max_length=120)\n",
            encoding="utf-8",
        )
        tree = build_tree(self.tmp, False, False, lambda *_a, **_kw: None, [0], [], self.tmp)
        analysis = build_analysis(
            self.tmp, tree, [],
            ExportConfig(context_mode="full", task_profile="general"),
            lambda *_a, **_kw: None,
        )
        self.assertEqual(analysis.fingerprint.project_type, "Django web application")
        self.assertIn("Django", analysis.fingerprint.frameworks)

    def test_project_fingerprint_detects_django_from_imports_only(self):
        """Django detected purely from Python import patterns when no manifest exists."""
        (self.tmp / "app").mkdir()
        (self.tmp / "app" / "views.py").write_text(
            "from django.shortcuts import render\nfrom django.http import HttpResponse\n\ndef index(request):\n    return render(request, 'index.html', {})\n",
            encoding="utf-8",
        )
        (self.tmp / "app" / "models.py").write_text(
            "from django.db import models\nclass Article(models.Model):\n    title = models.CharField(max_length=200)\n",
            encoding="utf-8",
        )
        tree = build_tree(self.tmp, False, False, lambda *_a, **_kw: None, [0], [], self.tmp)
        analysis = build_analysis(
            self.tmp, tree, [],
            ExportConfig(context_mode="full", task_profile="general"),
            lambda *_a, **_kw: None,
        )
        self.assertIn("Django", analysis.fingerprint.frameworks)
        self.assertEqual(analysis.fingerprint.project_type, "Django web application")

    def test_domain_detection_from_directory_names(self):
        """Domain inferred from directory structure even without code vocabulary."""
        (self.tmp / "boards").mkdir()
        (self.tmp / "boards" / "board.py").write_text("class Board:\n    pass\n", encoding="utf-8")
        (self.tmp / "sprints").mkdir()
        (self.tmp / "sprints" / "sprint.py").write_text("class Sprint:\n    pass\n", encoding="utf-8")
        (self.tmp / "requirements.txt").write_text("django>=4.0\n", encoding="utf-8")
        tree = build_tree(self.tmp, False, False, lambda *_a, **_kw: None, [0], [], self.tmp)
        analysis = build_analysis(
            self.tmp, tree, [],
            ExportConfig(context_mode="onboarding", task_profile="explain_project"),
            lambda *_a, **_kw: None,
        )
        self.assertIn("task", analysis.likely_purpose.lower())

    def test_requirements_txt_role_is_generic_for_non_contexta_projects(self):
        """requirements.txt should NOT say 'Contexta' for a generic Django project."""
        req = self._insight("requirements.txt", "django>=4.0\npsycopg2>=2.9\n")
        role = summarize_file(req, {})
        self.assertNotIn("contexta", role.lower())
        self.assertNotIn("token estimation", role.lower())
        self.assertIn("runtime", role.lower())

    def test_build_bat_role_is_generic_without_nuitka(self):
        """build.bat without nuitka content gets a generic description."""
        build = self._insight("build.bat", "@echo off\ncall mvn clean package\n")
        role = summarize_file(build, {})
        self.assertNotIn("nuitka", role.lower())
        self.assertIn("windows", role.lower())

    def test_build_bat_role_is_specific_with_nuitka(self):
        """build.bat with nuitka content gets the specific Nuitka description."""
        build = self._insight("build.bat", "@echo off\npy -m nuitka --onefile contexta.py\n")
        role = summarize_file(build, {})
        self.assertIn("nuitka", role.lower())

    def test_spring_boot_gradle_without_pom_xml(self):
        """Spring Boot project using Gradle (not Maven) is correctly detected."""
        (self.tmp / "build.gradle").write_text(
            "plugins { id 'org.springframework.boot' version '3.2.0' }\n"
            "dependencies {\n"
            "    implementation 'org.springframework.boot:spring-boot-starter-web'\n"
            "    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'\n"
            "}\n",
            encoding="utf-8",
        )
        (self.tmp / "src" / "main" / "java" / "com" / "example").mkdir(parents=True, exist_ok=True)
        (self.tmp / "src" / "main" / "java" / "com" / "example" / "TaskController.java").write_text(
            "@RestController\npublic class TaskController {\n    @GetMapping('/tasks')\n    public List<Task> list() { return null; }\n}",
            encoding="utf-8",
        )
        tree = build_tree(self.tmp, False, False, lambda *_a, **_kw: None, [0], [], self.tmp)
        analysis = build_analysis(
            self.tmp, tree, [],
            ExportConfig(context_mode="full", task_profile="general"),
            lambda *_a, **_kw: None,
        )
        self.assertEqual(analysis.fingerprint.project_type, "Spring Boot application")
        self.assertIn("Spring Boot", analysis.fingerprint.frameworks)
        self.assertIn("Gradle", analysis.fingerprint.package_managers)

    def test_python_project_not_classified_as_php_crud(self):
        """A Python project with service and repository layers must NOT be classified as PHP CRUD."""
        (self.tmp / "requirements.txt").write_text("fastapi>=0.110\nsqlalchemy>=2.0\n", encoding="utf-8")
        (self.tmp / "services" / "task_service.py").parent.mkdir(parents=True, exist_ok=True)
        (self.tmp / "services" / "task_service.py").write_text("class TaskService:\n    pass\n", encoding="utf-8")
        (self.tmp / "repositories" / "task_repository.py").parent.mkdir(parents=True, exist_ok=True)
        (self.tmp / "repositories" / "task_repository.py").write_text("class TaskRepository:\n    pass\n", encoding="utf-8")
        (self.tmp / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8")
        tree = build_tree(self.tmp, False, False, lambda *_a, **_kw: None, [0], [], self.tmp)
        analysis = build_analysis(
            self.tmp, tree, [],
            ExportConfig(context_mode="full", task_profile="general"),
            lambda *_a, **_kw: None,
        )
        self.assertNotEqual(analysis.fingerprint.project_type, "PHP CRUD web application")
        self.assertNotIn("PHP", analysis.fingerprint.primary_language or "")

    def test_xml_android_manifest_role_is_specific(self):
        """AndroidManifest.xml gets a meaningful role description."""
        manifest = self._insight("AndroidManifest.xml",
            '<?xml version="1.0"?><manifest package="com.example"><application android:label="App"/></manifest>')
        role = summarize_file(manifest, {})
        self.assertIn("android", role.lower())


if __name__ == "__main__":
    unittest.main()
