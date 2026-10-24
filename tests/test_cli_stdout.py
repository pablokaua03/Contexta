"""stdout must carry only the pack. Banner, colors and progress go to stderr."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class StdoutIsOnlyThePackTests(unittest.TestCase):
    def test_forced_color_never_reaches_stdout(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "demo"
            project.mkdir()
            (project / "app.py").write_text("def hello():\n    return 1\n", encoding="utf-8")
            env = {**os.environ, "CONTEXTA_COLOR": "always", "PYTHONPATH": str(ROOT)}
            proc = subprocess.run(
                [sys.executable, "-m", "contexta_app.cli", str(project), "--stdout"],
                capture_output=True, text=True, env=env, cwd=tmp, timeout=120,
            )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("\x1b[", proc.stdout)
        self.assertNotIn("contexta  v", proc.stdout)
        self.assertIn("app.py", proc.stdout)
        self.assertIn("\x1b[", proc.stderr)


if __name__ == "__main__":
    unittest.main()
