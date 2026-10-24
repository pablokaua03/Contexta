"""One version number everywhere."""

import re
import tomllib
from pathlib import Path

import contexta_app
from contexta_app import renderer

ROOT = Path(__file__).resolve().parent.parent
VERSION = contexta_app.__version__


def test_pyproject_matches_package():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["version"] == VERSION


def test_renderer_reexports_package_version():
    assert renderer.__version__ == VERSION


def test_readme_badges_match():
    for name in ("README.md", "README.pt-BR.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert re.search(rf"vers(?:%C3%A3o|ion)-{re.escape(VERSION)}-", text), name


def test_changelog_leads_with_current_version_and_has_2_0_0():
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    headings = re.findall(r"^## \[([^\]]+)\]", text, re.M)
    assert headings[0] == VERSION
    assert "2.0.0" in headings
    assert headings.index(VERSION) < headings.index("2.0.0")


def test_windows_version_resource_matches():
    text = (ROOT / "packaging" / "version_info.txt").read_text(encoding="utf-8")
    assert f"'ProductVersion', '{VERSION}'" in text


def test_readme_has_no_before_after_section():
    for name in ("README.md", "README.pt-BR.md"):
        text = (ROOT / name).read_text(encoding="utf-8").lower()
        assert "before and after" not in text and "docs/images/before-" not in text
    assert not (ROOT / "docs" / "images" / "before-dark.png").exists()
