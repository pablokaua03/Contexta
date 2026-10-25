"""Directory symlinks must not be walked twice or forever."""

from __future__ import annotations

import pytest

from contexta_app.engine.insight import flatten_tree
from contexta_app.scanner import build_tree


def _symlink(link, target, **kwargs):
    try:
        link.symlink_to(target, **kwargs)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available on this system")


def _scan(root):
    return [p.relative_to(root).as_posix() for p in flatten_tree(build_tree(root, False, False, lambda *_a, **_k: None, [0], [], root))]


def test_self_loop_lists_each_file_once(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    _symlink(tmp_path / "self", ".", target_is_directory=True)
    assert _scan(tmp_path) == ["a.py"]


def test_link_to_parent_does_not_recurse(tmp_path):
    sub = tmp_path / "pkg"
    sub.mkdir()
    (sub / "m.py").write_text("y = 2\n", encoding="utf-8")
    _symlink(sub / "up", "..", target_is_directory=True)
    assert _scan(tmp_path) == ["pkg/m.py"]


def test_link_to_sibling_is_not_listed_twice(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    (real / "m.py").write_text("z = 3\n", encoding="utf-8")
    _symlink(tmp_path / "alias", real, target_is_directory=True)
    assert _scan(tmp_path) == ["real/m.py"]


def test_file_symlink_inside_project_is_still_scanned(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    _symlink(tmp_path / "b.py", tmp_path / "a.py")
    assert sorted(_scan(tmp_path)) == ["a.py", "b.py"]
