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

from context_engine import (
    ExportConfig,
    build_analysis,
    build_relationship_map,
    build_task_prompt,
    classify_file,
    compute_risk_score,
    extract_relevant_excerpt,
    infer_file_role_pipeline,
    make_file_insight,
    pick_core_module_labels,
    pick_core_module_names,
    summarize_file,
    test_relation_score,
)
from scanner import build_tree
from ui import resolve_pack_focus


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
                "## [1.5.0] - 2026-04-12",
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
        requirements = self._insight("requirements.txt", "pyinstaller\n")
        build_bat = self._insight("build.bat", "@echo off\npy -m PyInstaller contexta.py\n")
        build_sh = self._insight("build.sh", "#!/usr/bin/env bash\npyinstaller contexta.py\n")
        self.assertIn("dependency expectations", summarize_file(requirements, {}).lower())
        self.assertIn("windows executable packaging", summarize_file(build_bat, {}).lower())
        self.assertIn("unix-like executable packaging", summarize_file(build_sh, {}).lower())

    def test_mdcodebrief_summary_mentions_compatibility_shim(self):
        item = self._insight("mdcodebrief.py", "from contexta import main\n\nmain()\n")
        summary = summarize_file(item, {})
        self.assertIn("compatibility shim", summary.lower())
        self.assertIn("contexta.main()", summary)

    def test_contexta_summary_uses_main_entrypoint_wording(self):
        item = self._insight("contexta.py", "from ui import App\n\nApp()\n")
        summary = summarize_file(item, {})
        self.assertEqual(summary, "Acts as the main entrypoint that routes execution into the GUI or CLI flow.")

    def test_project_fingerprint_detects_python_desktop_gui_cli_tool(self):
        (self.tmp / "contexta.py").write_text("__name__ = '__main__'\n", encoding="utf-8")
        (self.tmp / "ui.py").write_text("import tkinter as tk\n", encoding="utf-8")
        (self.tmp / "cli.py").write_text("import argparse\n", encoding="utf-8")
        (self.tmp / "renderer.py").write_text("def generate_markdown():\n    return ''\n", encoding="utf-8")
        (self.tmp / "scanner.py").write_text("def build_tree():\n    return {}\n", encoding="utf-8")
        (self.tmp / "requirements.txt").write_text("pyinstaller\n", encoding="utf-8")

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
        self.assertIn("optional PyInstaller packaging", analysis.technologies)
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


if __name__ == "__main__":
    unittest.main()
