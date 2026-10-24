"""Linear-time test/source matching and the configurable file cap."""

from __future__ import annotations

import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from contexta_app import context_engine as ce
from contexta_app.cli import build_parser, build_plan
from contexta_app.scanner import DEFAULT_MAX_FILES, build_tree, count_files, resolve_max_files

QUIET = lambda *_a, **_kw: None  # noqa: E731


def make_project(root: Path, modules: int) -> None:
    for i in range(modules):
        pkg = root / "src" / f"pkg{i % 10}"
        pkg.mkdir(parents=True, exist_ok=True)
        (pkg / f"mod{i}.py").write_text(
            f"def feature_{i}_run():\n    return {i}\n\nclass Feature{i}Handler:\n    pass\n", encoding="utf-8"
        )
        tests = root / "tests"
        tests.mkdir(exist_ok=True)
        # named, import-linked, mention-linked, and unrelated tests
        if i % 3 == 0:
            (tests / f"test_mod{i}.py").write_text(f"def test_it():\n    assert True\n", encoding="utf-8")
        elif i % 3 == 1:
            (tests / f"test_case_{i}.py").write_text(
                f"from src.pkg{i % 10}.mod{i} import feature_{i}_run\n\ndef test_it():\n    feature_{i}_run()\n", encoding="utf-8"
            )
        else:
            (tests / f"test_misc_{i}.py").write_text(
                f"def test_it():\n    Feature{i}Handler\n    feature_{i}_run\n", encoding="utf-8"
            )


class IndexMatchesBruteForceTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        make_project(self.root, 40)
        tree = build_tree(self.root, False, False, QUIET, [0], [], self.root)
        self.insights: list[ce.FileInsight] = []
        spy = ce.resolve_local_relationships

        def capture(insights, module_map):
            self.insights = insights
            return spy(insights, module_map)

        with patch.object(ce, "resolve_local_relationships", capture):
            ce.build_analysis(self.root, tree, [], ce.ExportConfig(context_mode="full"), QUIET)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_related_tests_are_the_same_as_scoring_every_pair(self):
        self.assertGreater(len(self.insights), 60)
        for item in self.insights:
            brute = {c.relpath.as_posix() for c in self.insights if ce.related_test_score(item, c) >= 4}
            self.assertEqual(brute, ce.resolve_related_tests(item, self.insights), item.relpath)

    def test_reverse_lookup_is_the_same_as_scoring_every_pair(self):
        tests = [i for i in self.insights if "test" in i.tags]
        sources = [i for i in self.insights if "test" not in i.tags]
        index = ce.RelatedSourceIndex(sources)
        for test in tests:
            brute = any(ce.related_test_score(s, test) >= 4 for s in sources)
            self.assertEqual(brute, index.has_related(test), test.relpath)

    def test_related_test_reason_is_still_reported(self):
        selected = list(self.insights)
        ctx = ce.build_selection_context(selected, set())
        target = next(i for i in selected if i.relpath.name == "test_mod0.py")
        reasons = ce.infer_selection_reasons(target, selected, ce.ExportConfig(), set(), {}, ctx=ctx)
        self.assertIn("related test", reasons)

    def test_legacy_alias_still_scores(self):
        a = next(i for i in self.insights if i.relpath.name == "mod0.py")
        b = next(i for i in self.insights if i.relpath.name == "test_mod0.py")
        self.assertEqual(ce.test_relation_score(a, b), ce.related_test_score(a, b))


class ScaleTests(unittest.TestCase):
    def test_a_thousand_file_project_analyzes_quickly(self):
        root = Path(tempfile.mkdtemp())
        try:
            make_project(root, 500)
            tree = build_tree(root, False, False, QUIET, [0], [], root)
            started = time.perf_counter()
            analysis = ce.build_analysis(root, tree, [], ce.ExportConfig(context_mode="full"), QUIET)
            elapsed = time.perf_counter() - started
            self.assertEqual(len(analysis.selected_files), 1000)
            self.assertLess(elapsed, 20.0)
        finally:
            shutil.rmtree(root, ignore_errors=True)


class MaxFilesTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        make_project(self.root, 10)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_default_cap_is_2000(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CONTEXTA_MAX_FILES", None)
            self.assertEqual(resolve_max_files(), DEFAULT_MAX_FILES)
            self.assertEqual(DEFAULT_MAX_FILES, 2000)

    def test_explicit_value_and_env_override_the_default(self):
        self.assertEqual(resolve_max_files(7), 7)
        with patch.dict(os.environ, {"CONTEXTA_MAX_FILES": "12"}):
            self.assertEqual(resolve_max_files(), 12)
            self.assertEqual(resolve_max_files(3), 3)
        with patch.dict(os.environ, {"CONTEXTA_MAX_FILES": "nope"}):
            self.assertEqual(resolve_max_files(), DEFAULT_MAX_FILES)

    def test_scan_stops_at_the_cap(self):
        messages: list[str] = []
        tree = build_tree(self.root, False, False, lambda m, t="": messages.append(m), [0], [], self.root, max_files=5)
        self.assertEqual(count_files(tree), 5)
        self.assertTrue(any("5-file limit" in m for m in messages))

    def test_cli_flag_reaches_the_plan(self):
        args = build_parser().parse_args([str(self.root), "--max-files", "9"])
        plan = build_plan(args, self.root, stdout_isatty=True)
        self.assertEqual(plan.max_files, 9)


if __name__ == "__main__":
    unittest.main()
