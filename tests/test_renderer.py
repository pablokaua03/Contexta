"""
tests/test_renderer.py — Unit tests for renderer.py
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

TEST_TMP_ROOT = Path(__file__).parent / ".tmp"
TEST_TMP_ROOT.mkdir(exist_ok=True)

from renderer import (
    __version__,
    estimate_tokens,
    generate_markdown,
    render_tree_ascii,
    section_titles_for_preview,
    token_label,
)


class TestTokenEstimation(unittest.TestCase):
    def test_estimate_basic(self):
        self.assertEqual(estimate_tokens("abcd"), 1)
        self.assertEqual(estimate_tokens("a" * 4000), 1000)

    def test_token_label_small(self):
        label = token_label(5_000)
        self.assertIn("rough estimate", label)
        self.assertIn("fits most chat and coding models", label)

    def test_token_label_medium(self):
        label = token_label(20_000)
        self.assertIn("rough estimate", label)
        self.assertIn("ChatGPT-class", label)

    def test_token_label_large(self):
        label = token_label(100_000)
        self.assertIn("latency", label)
        self.assertIn("larger-context", label)

    def test_section_titles_for_preview_match_full_philosophy(self):
        titles = section_titles_for_preview("full", "general", False)
        self.assertIn("Project Summary", titles)
        self.assertIn("Context Payload", titles)
        self.assertIn("Supporting Files", titles)
        self.assertIn("Documentation Included", titles)
        self.assertNotIn("AI Handoff", titles)
        self.assertNotIn("Suggested Prompts for AI", titles)

    def test_section_titles_for_pr_review_are_review_first(self):
        titles = section_titles_for_preview("diff", "code_review", False)
        self.assertEqual(
            titles[:5],
            [
                "Review Objective",
                "Changed Files + Context",
                "Key Risks / Review Notes",
                "Related Tests / Missing Tests",
                "Missing Coverage / Gaps",
            ],
        )
        self.assertNotIn("Project Summary", titles)
        self.assertNotIn("Architecture Overview", titles)

    def test_section_titles_for_other_modes_have_distinct_personality(self):
        self.assertEqual(
            section_titles_for_preview("diff", "general", False),
            [
                "Changed Files + Context",
                "Relationship Map",
                "Potential Risks / Hotspots",
                "Selected Context",
                "Context Payload",
            ],
        )
        self.assertEqual(
            section_titles_for_preview("debug", "bug_report", False)[:4],
            ["Bug Focus / Report Lens", "Suspect Files", "Changed Files + Context", "Failure Path / Main Flow"],
        )
        self.assertEqual(
            section_titles_for_preview("feature", "general", False)[:4],
            ["Focus Summary", "Matched Files", "Main Flow for Focus Area", "Related Files"],
        )
        self.assertEqual(
            section_titles_for_preview("refactor", "refactor_request", False)[:4],
            ["Refactor Goal", "Core Modules", "Coupling / Relationship Map", "Potential Risks / Hotspots"],
        )
        self.assertEqual(
            section_titles_for_preview("full", "write_tests", False)[:4],
            ["Testing Lens", "Core Modules Worth Testing", "Existing Related Tests", "Missing Coverage / Gaps"],
        )
        self.assertEqual(
            section_titles_for_preview("full", "find_dead_code", False)[:4],
            ["Dead Code Lens", "Low-Signal Files", "Weakly Connected Modules", "Possible False Positives"],
        )
        self.assertEqual(
            section_titles_for_preview("debug", "risk_analysis", False)[:4],
            ["Risk Objective", "High-Risk Files", "Potential Regression Signals", "Missing Coverage / Testing Gaps"],
        )


class TestRenderTreeAscii(unittest.TestCase):
    def _make_node(self, name, files=None, dirs=None):
        return {
            "name": name,
            "path": Path("/fake") / name,
            "files": [{"name": f, "path": Path(f), "lang": None} for f in (files or [])],
            "dirs":  dirs or [],
        }

    def test_root_shown(self):
        node = self._make_node("myproject", files=["main.py"])
        result = render_tree_ascii(node)
        self.assertIn("myproject", result)
        self.assertIn("main.py", result)

    def test_nested_dir(self):
        child = self._make_node("src", files=["app.py"])
        root  = self._make_node("project", dirs=[child])
        result = render_tree_ascii(root)
        self.assertIn("src", result)
        self.assertIn("app.py", result)


class TestGenerateMarkdown(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(dir=TEST_TMP_ROOT))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_basic_output(self):
        (self.tmp / "main.py").write_text("print('hello')", encoding="utf-8")
        md = generate_markdown(self.tmp)
        self.assertIn("Project Context", md)
        self.assertIn("Project Summary", md)
        self.assertIn("main.py", md)
        self.assertIn("print('hello')", md)

    def test_system_prompt_injected(self):
        (self.tmp / "app.py").write_text("x = 1", encoding="utf-8")
        md = generate_markdown(self.tmp, system_prompt="Find the bug")
        self.assertIn("Find the bug", md)

    def test_version_in_footer(self):
        (self.tmp / "app.py").write_text("x = 1", encoding="utf-8")
        md = generate_markdown(self.tmp)
        self.assertIn(__version__, md)

    def test_token_estimate_in_footer(self):
        (self.tmp / "app.py").write_text("x = 1", encoding="utf-8")
        md = generate_markdown(self.tmp)
        self.assertIn("tokens", md)

    def test_empty_project(self):
        md = generate_markdown(self.tmp)
        self.assertIn("Files: **0**", md)

    @patch("renderer.get_git_changed_files", return_value=[])
    def test_diff_mode_falls_back_to_central_context_when_no_changed_files_exist(self, _mock_changed):
        (self.tmp / "main.py").write_text("print('hello')", encoding="utf-8")
        md = generate_markdown(self.tmp, diff_mode=True)
        self.assertIn("Mode: **Git diff**", md)
        self.assertIn("fell back to central files and nearby tests", md)
        self.assertIn("Files: **1**", md)
        self.assertIn("Fallback Context:", md)

    def test_context_summary_sections_present(self):
        (self.tmp / "ui.py").write_text("import tkinter as tk\n", encoding="utf-8")
        (self.tmp / "cli.py").write_text("import argparse\nfrom ui import tk\n", encoding="utf-8")
        md = generate_markdown(self.tmp, context_mode="onboarding", task_profile="explain_project")
        self.assertIn("Project Summary", md)
        self.assertIn("Read This First", md)
        self.assertIn("Main Flow", md)
        self.assertIn("Where To Change What", md)
        self.assertIn("Suggested Prompts for AI", md)
        self.assertIn("Architecture Overview", md)
        self.assertIn("Relationship Map", md)

    def test_full_mode_omits_explanatory_sections_by_default(self):
        (self.tmp / "contexta.py").write_text("__name__ = '__main__'\n", encoding="utf-8")
        (self.tmp / "README.md").write_text("# Contexta\n", encoding="utf-8")
        (self.tmp / "helper.py").write_text("x = 1\n", encoding="utf-8")
        md = generate_markdown(self.tmp, context_mode="full", compression="full")
        self.assertIn("Project Summary", md)
        self.assertIn("Read This First", md)
        self.assertIn("## Documentation Included", md)
        self.assertIn("## File Summaries", md)
        self.assertIn("Context Payload", md)
        self.assertNotIn("## AI Task Brief", md)
        self.assertNotIn("## Task Lens", md)
        self.assertNotIn("## AI Handoff", md)
        self.assertNotIn("## Suggested Prompts for AI", md)
        self.assertNotIn("## What Can Be Ignored", md)

    def test_onboarding_payload_prefers_guided_excerpts_over_full_dump(self):
        content = "\n".join(
            ["def launch_app():", "    return True", ""]
            + [f"line_{i} = {i}" for i in range(120)]
        )
        (self.tmp / "contexta.py").write_text(content, encoding="utf-8")
        md = generate_markdown(self.tmp, context_mode="onboarding", task_profile="explain_project", compression="balanced")
        self.assertIn("Guided onboarding excerpt", md)
        self.assertIn("def launch_app()", md)
        self.assertNotIn("line_119 = 119", md)

    def test_onboarding_payload_keeps_core_files_ahead_of_tests(self):
        (self.tmp / "contexta.py").write_text("__name__ = '__main__'\n", encoding="utf-8")
        (self.tmp / "ui.py").write_text("import tkinter as tk\n", encoding="utf-8")
        tests_dir = self.tmp / "tests"
        tests_dir.mkdir(exist_ok=True)
        (tests_dir / "test_ui.py").write_text("from ui import tk\n\ndef test_ui_boot():\n    assert tk\n", encoding="utf-8")
        md = generate_markdown(self.tmp, context_mode="onboarding", task_profile="explain_project", compression="balanced")
        self.assertLess(md.index("### 📄 `contexta.py`"), md.index("### 📄 `tests/test_ui.py`"))

    def test_signatures_only_mode_avoids_full_payload_for_large_file(self):
        content = "\n".join([
            "def alpha():",
            "    return 1",
            "",
            "class Beta:",
            "    pass",
            "",
        ] + [f"line_{i} = {i}" for i in range(40)])
        (self.tmp / "main.py").write_text(content, encoding="utf-8")
        md = generate_markdown(self.tmp, compression="signatures")
        self.assertIn("def alpha()", md)
        self.assertIn("class Beta", md)
        self.assertNotIn("line_39 = 39", md)

    def test_embedded_asset_payload_is_not_dumped_even_in_full_mode(self):
        blob = "A" * 180
        content = '\n'.join([
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
        ])
        (self.tmp / "brand_assets.py").write_text(content, encoding="utf-8")
        md = generate_markdown(self.tmp, compression="full")
        self.assertIn("Embedded asset payload omitted", md)
        self.assertIn("<embedded asset data omitted>", md)
        self.assertNotIn(blob, md)

    def test_large_file_reports_total_and_exported_lines(self):
        content = "\n".join(f"line {i}" for i in range(1100))
        (self.tmp / "large.py").write_text(content, encoding="utf-8")
        md = generate_markdown(self.tmp, compression="full")
        self.assertIn("1100 total lines (1000 exported)", md)
        self.assertIn("exported the first 1000 lines", md)

    def test_payload_shows_selection_reasons(self):
        (self.tmp / "contexta.py").write_text("__name__ = '__main__'\n", encoding="utf-8")
        (self.tmp / "renderer.py").write_text("def generate_markdown():\n    return ''\n", encoding="utf-8")
        md = generate_markdown(self.tmp, compression="full")
        self.assertIn("Selected because:", md)
        self.assertIn("entrypoint", md)
        self.assertNotIn("Score breakdown:", md)

    @patch("renderer.get_git_changed_files")
    def test_onboarding_selection_reasons_do_not_use_diff_language(self, mock_changed):
        main_file = self.tmp / "contexta.py"
        ui_file = self.tmp / "ui.py"
        main_file.write_text("__name__ = '__main__'\nfrom ui import launch\n", encoding="utf-8")
        ui_file.write_text("import tkinter as tk\n\ndef launch():\n    return tk.Tk()\n", encoding="utf-8")
        mock_changed.return_value = [ui_file]
        md = generate_markdown(self.tmp, context_mode="onboarding", task_profile="explain_project", compression="balanced")
        self.assertNotIn("current diff", md)
        self.assertNotIn("changed surface", md)
        self.assertIn("part of the current working context", md)
        self.assertNotIn("current workspace file", md)
        self.assertNotIn("nearby workspace context", md)

    def test_onboarding_where_to_change_surfaces_localization_targets(self):
        app_dir = self.tmp / "app"
        lib_dir = self.tmp / "lib"
        components_dir = self.tmp / "components"
        app_dir.mkdir(exist_ok=True)
        lib_dir.mkdir(exist_ok=True)
        components_dir.mkdir(exist_ok=True)
        (self.tmp / "package.json").write_text('{"dependencies":{"next":"15.0.0","react":"19.0.0"}}', encoding="utf-8")
        (app_dir / "page.tsx").write_text("export default function Page() { return <main />; }\n", encoding="utf-8")
        (lib_dir / "LocaleContext.tsx").write_text("const LocaleContext = createContext(undefined);\n", encoding="utf-8")
        (lib_dir / "translations.ts").write_text("export const translations = {};\n", encoding="utf-8")
        (components_dir / "LocaleToggle.tsx").write_text("export function LocaleToggle() { return <button />; }\n", encoding="utf-8")
        md = generate_markdown(self.tmp, context_mode="onboarding", task_profile="explain_project")
        self.assertIn("Localization changes ->", md)
        self.assertIn("lib/LocaleContext.tsx", md)

    def test_full_context_keeps_important_files_first(self):
        (self.tmp / "contexta.py").write_text("__name__ = '__main__'\n", encoding="utf-8")
        (self.tmp / "helper.py").write_text("x = 1\n", encoding="utf-8")
        md = generate_markdown(self.tmp, context_mode="full", compression="full")
        self.assertLess(md.index("### 📄 `contexta.py`"), md.index("### 📄 `helper.py`"))

    @patch("renderer.get_git_changed_files")
    def test_changed_files_context_section_is_rendered(self, mock_changed):
        main_file = self.tmp / "contexta.py"
        helper_file = self.tmp / "renderer.py"
        main_file.write_text("__name__ = '__main__'\n", encoding="utf-8")
        helper_file.write_text("def generate_markdown():\n    return ''\n", encoding="utf-8")
        mock_changed.return_value = [main_file]
        md = generate_markdown(self.tmp, diff_mode=True)
        self.assertIn("Changed Files + Context", md)
        self.assertIn("Changed Files:", md)
        self.assertIn("contexta.py", md)

    @patch("renderer.get_git_changed_files")
    def test_pr_review_diff_mode_is_review_first(self, mock_changed):
        main_file = self.tmp / "contexta.py"
        renderer_file = self.tmp / "renderer.py"
        test_file = self.tmp / "tests" / "test_renderer.py"
        test_file.parent.mkdir(exist_ok=True)
        main_file.write_text("__name__ = '__main__'\n", encoding="utf-8")
        renderer_file.write_text(
            "from context_engine import build_analysis\n\ndef generate_markdown():\n    return build_analysis()\n",
            encoding="utf-8",
        )
        test_file.write_text("from renderer import generate_markdown\n\ndef test_render():\n    assert generate_markdown\n", encoding="utf-8")
        mock_changed.return_value = [renderer_file]
        md = generate_markdown(self.tmp, context_mode="diff", task_profile="code_review", compression="focused")
        self.assertIn("## Review Objective", md)
        self.assertLess(md.index("## Changed Files + Context"), md.index("## Context Payload"))
        self.assertNotIn("## Project Summary", md)
        self.assertNotIn("## Architecture Overview", md)
        self.assertIn("## Selection Reason Score Breakdown", md)

    def test_ai_handoff_task_changes_brief(self):
        (self.tmp / "contexta.py").write_text("__name__ = '__main__'\n", encoding="utf-8")
        md = generate_markdown(self.tmp, task_profile="ai_handoff")
        self.assertIn("Task mode: **AI Handoff**", md)
        self.assertIn("another AI", md)
        self.assertIn("## Model Guidance", md)
        self.assertIn("## Suggested Prompts for AI", md)

    def test_write_tests_mode_surfaces_coverage_sections(self):
        (self.tmp / "scanner.py").write_text("def build_tree():\n    return {}\n", encoding="utf-8")
        md = generate_markdown(self.tmp, task_profile="write_tests")
        self.assertIn("## Testing Lens", md)
        self.assertIn("## Core Modules Worth Testing", md)
        self.assertIn("## Missing Coverage / Gaps", md)

    def test_risk_analysis_mode_surfaces_risk_sections(self):
        (self.tmp / "app").mkdir(exist_ok=True)
        (self.tmp / "app" / "page.tsx").write_text(
            "\n".join(
                ["export default function Page() {", "  return <form onSubmit={handleSubmit}>Hi</form>;", "}"]
                + [f"const line_{i} = {i}" for i in range(650)]
            ),
            encoding="utf-8",
        )
        (self.tmp / "lib").mkdir(exist_ok=True)
        (self.tmp / "lib" / "LocaleContext.tsx").write_text(
            "export const LocaleContext = createContext(undefined)\nexport function useLocale() { return LocaleContext }\n",
            encoding="utf-8",
        )
        md = generate_markdown(self.tmp, context_mode="debug", task_profile="risk_analysis", compression="focused")
        self.assertIn("## Risk Objective", md)
        self.assertIn("## High-Risk Files", md)
        self.assertIn("## Potential Regression Signals", md)
        self.assertIn("## Missing Coverage / Testing Gaps", md)
        self.assertIn("## Shared Dependencies / Broad Impact Areas", md)
        self.assertIn("## Weak Spots / Maintenance Risks", md)

    def test_risk_analysis_uses_specific_engine_risk_language(self):
        (self.tmp / "context_engine.py").write_text("def build_analysis():\n    return None\n", encoding="utf-8")
        (self.tmp / "renderer.py").write_text("def generate_markdown():\n    return ''\n", encoding="utf-8")
        md = generate_markdown(self.tmp, context_mode="debug", task_profile="risk_analysis", compression="focused")
        self.assertIn("context selection", md)
        self.assertIn("output structure and presentation", md)
        self.assertNotIn("context_engine.py` handles input or submission flow", md)
        self.assertNotIn("renderer.py` handles input or submission flow", md)

    def test_dead_code_mode_surfaces_verification_sections(self):
        (self.tmp / "utils.py").write_text("def helper():\n    return True\n", encoding="utf-8")
        md = generate_markdown(self.tmp, task_profile="find_dead_code")
        self.assertIn("## Dead Code Lens", md)
        self.assertIn("## Possible False Positives", md)
        self.assertIn("## Safe Verification Checklist", md)


if __name__ == "__main__":
    unittest.main()
