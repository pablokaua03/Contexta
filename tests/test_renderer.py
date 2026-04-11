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
    token_label,
)


class TestTokenEstimation(unittest.TestCase):
    def test_estimate_basic(self):
        self.assertEqual(estimate_tokens("abcd"), 1)
        self.assertEqual(estimate_tokens("a" * 4000), 1000)

    def test_token_label_small(self):
        label = token_label(5_000)
        self.assertIn("fits most models", label)

    def test_token_label_medium(self):
        label = token_label(20_000)
        self.assertIn("GPT-4o", label)

    def test_token_label_large(self):
        label = token_label(100_000)
        self.assertIn("Claude", label)


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
        self.assertIn("Directory Tree", md)
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
    def test_diff_mode_shows_empty_result_without_full_fallback(self, _mock_changed):
        (self.tmp / "main.py").write_text("print('hello')", encoding="utf-8")
        md = generate_markdown(self.tmp, diff_mode=True)
        self.assertIn("Mode: **Git diff**", md)
        self.assertIn("No changed files matched the current filters", md)
        self.assertIn("Files: **0**", md)


if __name__ == "__main__":
    unittest.main()
