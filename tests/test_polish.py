import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _run(project: Path, *args: str):
    return subprocess.run(
        [sys.executable, "-m", "contexta_app.cli", str(project), *args],
        capture_output=True, text=True, cwd=ROOT, timeout=120,
    )


def test_scan_log_shows_each_folder_once_with_its_project_relative_path(tmp_path):
    (tmp_path / "assets" / "assets").mkdir(parents=True)
    (tmp_path / "assets" / "assets" / "a.py").write_text("x = 1\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "b.py").write_text("y = 2\n")
    result = _run(tmp_path, "--stdout")
    lines = [line for line in result.stderr.splitlines() if "Scanning directory" in line]
    assert any(line.endswith("assets") for line in lines)
    assert any(line.endswith("assets/assets") for line in lines)
    assert sum(1 for line in lines if line.endswith("src")) == 1
    assert not any("assets/assets/assets" in line for line in lines)


def test_pack_date_is_iso(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    result = _run(tmp_path, "--stdout")
    match = re.search(r"Date: \*\*(.+?)\*\*", result.stdout)
    assert match, result.stdout[:300]
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", match.group(1))
