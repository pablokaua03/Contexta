"""
tests/test_scanner.py - Focused tests for scanning and file reading helpers.
"""

import tempfile
import unittest
from pathlib import Path

from contexta_app.scanner import load_gitignore_patterns, matches_gitignore, read_file_safe


TEST_TMP_ROOT = Path(__file__).parent / ".tmp"
TEST_TMP_ROOT.mkdir(exist_ok=True)


class TestScannerHelpers(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(dir=TEST_TMP_ROOT))

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_pathspec_gitignore_keeps_negated_file(self):
        (self.tmp / ".gitignore").write_text(
            "\n".join([
                "dist/",
                "*.log",
                "!important.log",
            ]),
            encoding="utf-8",
        )
        dist_dir = self.tmp / "dist"
        dist_dir.mkdir()
        ignored_log = self.tmp / "debug.log"
        ignored_log.write_text("debug", encoding="utf-8")
        kept_log = self.tmp / "important.log"
        kept_log.write_text("keep", encoding="utf-8")

        patterns = load_gitignore_patterns(self.tmp)
        self.assertTrue(matches_gitignore(dist_dir, self.tmp, patterns))
        self.assertTrue(matches_gitignore(ignored_log, self.tmp, patterns))
        self.assertFalse(matches_gitignore(kept_log, self.tmp, patterns))

    def test_read_file_safe_uses_charset_normalizer_for_cp1252(self):
        source = self.tmp / "legacy.txt"
        source.write_bytes("ação e revisão".encode("cp1252"))

        content, truncated, line_count = read_file_safe(source)

        self.assertEqual(content, "ação e revisão")
        self.assertFalse(truncated)
        self.assertEqual(line_count, 1)

    def test_read_file_safe_truncates_large_text_files(self):
        source = self.tmp / "large.txt"
        source.write_text("\n".join(f"line {index}" for index in range(1105)), encoding="utf-8")

        content, truncated, line_count = read_file_safe(source)

        self.assertTrue(truncated)
        self.assertEqual(line_count, 1105)
        self.assertEqual(len(content.splitlines()), 1000)
