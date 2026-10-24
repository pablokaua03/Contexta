"""Descriptions must come from the scanned project, never from Contexta's own text."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from contexta_app.context_engine import ExportConfig, build_analysis, infer_file_role_pipeline, make_file_insight, classify_file, summarize_file
from contexta_app.project_meta import read_project_description
from contexta_app.scanner import build_tree

QUIET = lambda *_a, **_kw: None  # noqa: E731
CONTEXTA_ISMS = ("pack generation", "context pack", "contexta", "output destinations")


class ProjectDescriptionTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, rel: str, text: str):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def analyze(self):
        tree = build_tree(self.root, False, False, QUIET, [0], [], self.root)
        return build_analysis(self.root, tree, [], ExportConfig(context_mode="onboarding"), QUIET)

    def test_pyproject_description_wins(self):
        self.write("pyproject.toml", '[project]\nname = "demo"\ndescription = "A tiny queue for nightly jobs."\n')
        self.write("README.md", "# demo\n\nSomething else entirely.\n")
        self.assertEqual(read_project_description(self.root), "A tiny queue for nightly jobs.")

    def test_package_json_and_cargo_and_composer(self):
        self.write("package.json", '{"name": "x", "description": "Realtime chart widgets"}')
        self.assertEqual(read_project_description(self.root), "Realtime chart widgets")
        (self.root / "package.json").unlink()
        self.write("Cargo.toml", '[package]\nname = "x"\ndescription = "Fast log shipper"\n')
        self.assertEqual(read_project_description(self.root), "Fast log shipper")
        (self.root / "Cargo.toml").unlink()
        self.write("composer.json", '{"description": "Invoice helpers for Laravel"}')
        self.assertEqual(read_project_description(self.root), "Invoice helpers for Laravel")

    def test_readme_first_paragraph_skips_badges_and_headings(self):
        self.write(
            "README.md",
            "# Demo\n\n[![CI](https://img.shields.io/x.svg)](https://x)\n\n"
            "Demo turns CSV exports into tidy invoices. It runs offline.\n\nMore text.\n",
        )
        self.assertEqual(read_project_description(self.root), "Demo turns CSV exports into tidy invoices.")

    def test_no_metadata_returns_empty(self):
        self.assertEqual(read_project_description(self.root), "")

    def test_flask_like_repo_is_not_described_as_social_app(self):
        self.write("pyproject.toml", '[project]\nname = "flask"\ndescription = "A simple framework for building complex web applications."\n')
        self.write("src/flask/app.py", "from flask import Flask\n\nclass Flask:\n    pass\n")
        self.write(
            "src/flask/sessions.py",
            "# feeds profiles messages comments notifications posts\n" * 5 + "class SessionInterface:\n    pass\n",
        )
        analysis = self.analyze()
        self.assertEqual(analysis.likely_purpose, "A simple framework for building complex web applications.")
        self.assertNotIn("feeds", analysis.likely_purpose)

    def test_foreign_cli_py_never_gets_contexta_text(self):
        self.write("src/flask/cli.py", "import click\n\n@click.group()\ndef main():\n    pass\n")
        item = make_file_insight(self.root, self.root / "src/flask/cli.py")
        item.tags.update(classify_file(item))
        for text in (summarize_file(item, {}), infer_file_role_pipeline(item)):
            self.assertTrue(text)
            for needle in CONTEXTA_ISMS:
                self.assertNotIn(needle, text.lower())

    def test_other_contexta_module_names_stay_generic_outside_contexta(self):
        for rel in ("app/renderer.py", "app/scanner.py", "app/ui.py", "app/theme.py", "app/utils.py", "app/syntax.py", "app/context_engine.py"):
            self.write(rel, "def f():\n    return 1\n")
            item = make_file_insight(self.root, self.root / rel)
            item.tags.update(classify_file(item))
            text = summarize_file(item, {}).lower()
            for needle in ("context pack", "tree-sitter", "smart context selection", "gui theme", "desktop-path"):
                self.assertNotIn(needle, text, f"{rel}: {text}")

    def test_contexta_own_cli_keeps_its_specific_text(self):
        self.write("contexta_app/cli.py", "import argparse\n")
        item = make_file_insight(self.root, self.root / "contexta_app/cli.py")
        item.tags.update(classify_file(item))
        self.assertIn("pack generation", summarize_file(item, {}))


if __name__ == "__main__":
    unittest.main()
