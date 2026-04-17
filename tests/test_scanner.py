"""
tests/test_scanner.py — Unit tests for scanner.py
Run with: python -m unittest discover tests/
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

TEST_TMP_ROOT = Path(__file__).parent / ".tmp"
TEST_TMP_ROOT.mkdir(exist_ok=True)

from contexta_app.scanner import (
    count_files,
    build_tree,
    get_language,
    load_gitignore_patterns,
    matches_gitignore,
    read_file_safe,
    should_ignore_dir,
    should_ignore_file,
)


def _noop_log(msg, tag=""):
    pass


class TestGetLanguage(unittest.TestCase):
    def test_python(self):
        self.assertEqual(get_language(Path("main.py")), "python")

    def test_typescript(self):
        self.assertEqual(get_language(Path("app.ts")), "typescript")

    def test_dockerfile(self):
        self.assertEqual(get_language(Path("Dockerfile")), "dockerfile")

    def test_unknown(self):
        self.assertIsNone(get_language(Path("file.unknownext")))

    def test_case_insensitive(self):
        self.assertEqual(get_language(Path("Main.PY")), "python")


class TestShouldIgnoreDir(unittest.TestCase):
    def test_ignores_node_modules(self):
        self.assertTrue(should_ignore_dir("node_modules", False))

    def test_ignores_pycache(self):
        self.assertTrue(should_ignore_dir("__pycache__", False))

    def test_ignores_hidden_when_flag_false(self):
        self.assertTrue(should_ignore_dir(".secret", False))

    def test_allows_hidden_when_flag_true(self):
        self.assertFalse(should_ignore_dir(".secret", True))

    def test_allows_normal_dir(self):
        self.assertFalse(should_ignore_dir("src", False))


class TestReadFileSafe(unittest.TestCase):
    def test_reads_utf8(self):
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                         suffix=".txt", delete=False,
                                         dir=TEST_TMP_ROOT) as f:
            f.write("hello world\n")
            path = Path(f.name)
        content, truncated, total_lines = read_file_safe(path)
        self.assertIn("hello world", content)
        self.assertFalse(truncated)
        self.assertEqual(total_lines, 1)
        path.unlink()

    def test_truncates_long_file(self):
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                         suffix=".txt", delete=False,
                                         dir=TEST_TMP_ROOT) as f:
            for i in range(1100):
                f.write(f"line {i}\n")
            path = Path(f.name)
        content, truncated, total_lines = read_file_safe(path)
        self.assertTrue(truncated)
        self.assertEqual(total_lines, 1100)
        path.unlink()

    def test_reads_latin1_bytes(self):
        # latin-1 can read any byte sequence — no file is truly unreadable
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, dir=TEST_TMP_ROOT) as f:
            f.write(bytes(range(256)))
            path = Path(f.name)
        content, truncated, total_lines = read_file_safe(path)
        self.assertIsInstance(content, str)
        self.assertFalse(truncated)
        self.assertGreaterEqual(total_lines, 1)
        path.unlink()


class TestGitignorePatterns(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(dir=TEST_TMP_ROOT))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_loads_patterns(self):
        (self.tmp / ".gitignore").write_text("*.log\nbuild/\n# comment\n\n")
        patterns = load_gitignore_patterns(self.tmp)
        self.assertIn("*.log", patterns)
        self.assertIn("build/", patterns)
        self.assertNotIn("# comment", patterns)

    def test_returns_empty_when_no_gitignore(self):
        patterns = load_gitignore_patterns(self.tmp)
        self.assertEqual(patterns, [])

    def test_matches_simple_glob(self):
        root = self.tmp
        f = root / "debug.log"
        f.touch()
        self.assertTrue(matches_gitignore(f, root, ["*.log"]))

    def test_no_match(self):
        root = self.tmp
        f = root / "main.py"
        f.touch()
        self.assertFalse(matches_gitignore(f, root, ["*.log"]))

    def test_negation_reinclude(self):
        root = self.tmp
        f = root / "important.log"
        f.touch()
        # *.log ignores all logs, !important.log re-includes it
        patterns = ["*.log", "!important.log"]
        self.assertFalse(matches_gitignore(f, root, patterns))

    def test_directory_pattern(self):
        root  = self.tmp
        build = root / "build"
        build.mkdir()
        self.assertTrue(matches_gitignore(build, root, ["build/"]))


class TestBuildTree(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(dir=TEST_TMP_ROOT))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_counts_files(self):
        (self.tmp / "main.py").write_text("print('hello')")
        (self.tmp / "utils.py").write_text("pass")
        counter = [0]
        tree = build_tree(self.tmp, False, False, _noop_log, counter, [], self.tmp)
        self.assertEqual(count_files(tree), 2)

    def test_ignores_pycache(self):
        cache = self.tmp / "__pycache__"
        cache.mkdir()
        (cache / "main.cpython-311.pyc").write_bytes(b"\x00" * 10)
        counter = [0]
        tree = build_tree(self.tmp, False, False, _noop_log, counter, [], self.tmp)
        self.assertEqual(count_files(tree), 0)

    def test_nested_structure(self):
        src = self.tmp / "src"
        src.mkdir()
        (src / "app.py").write_text("# app")
        (self.tmp / "README.md").write_text("# readme")
        counter = [0]
        tree = build_tree(self.tmp, False, False, _noop_log, counter, [], self.tmp)
        self.assertEqual(count_files(tree), 2)

    def test_hidden_files_stay_out_by_default(self):
        (self.tmp / ".env").write_text("SECRET=1", encoding="utf-8")
        counter = [0]
        tree = build_tree(self.tmp, False, False, _noop_log, counter, [], self.tmp)
        self.assertEqual(count_files(tree), 0)

    def test_hidden_files_can_be_included(self):
        (self.tmp / ".env").write_text("SECRET=1", encoding="utf-8")
        counter = [0]
        tree = build_tree(self.tmp, True, False, _noop_log, counter, [], self.tmp)
        self.assertEqual(count_files(tree), 1)


if __name__ == "__main__":
    unittest.main()
