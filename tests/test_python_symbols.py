"""Python files are read with ``ast``, so a pack is the same with or without the optional tree-sitter."""

from __future__ import annotations

from pathlib import Path

import pytest

from contexta_app.engine import insight
from contexta_app.engine.focus import compute_focus_raw
from contexta_app.engine.insight import extract_symbols, make_file_insight, python_imported_names

SOURCE = (
    "import os\n"
    "import json as j\n"
    "from . import sibling\n"
    "from .util import slugify, other\n"
    "from ..up import thing\n"
    "from pkg.core import build\n"
    "from pkg import *\n"
    "\n"
    "def top():\n    import late\n    return 1\n\n"
    "async def atop():\n    pass\n\n"
    "class Engine:\n    def method(self):\n        pass\n"
)


@pytest.fixture(autouse=True)
def tree_sitter_must_not_be_needed(monkeypatch):
    insight._python_ast_symbols.cache_clear()

    def boom(*_a, **_k):
        raise AssertionError("Python must not go through tree-sitter")

    monkeypatch.setattr(insight, "extract_symbols_with_treesitter", boom)


def test_functions_classes_and_module_paths():
    functions, classes, imports = extract_symbols(SOURCE, "python")
    assert functions == ["top", "atop"]  # top level only: methods are not listed
    assert classes == ["Engine"]
    assert imports == ["os", "json", ".", ".util", "..up", "pkg.core", "pkg", "late"]


def test_imported_names_are_kept_apart_from_modules():
    assert python_imported_names(SOURCE) == ["sibling", "slugify", "other", "thing", "build"]
    _f, _c, imports = extract_symbols(SOURCE, "python")
    assert "slugify" not in imports  # a name is not a module: it would count as an external dependency


def test_a_file_that_does_not_parse_falls_back_to_the_regex_reader(monkeypatch):
    monkeypatch.setattr(insight, "extract_symbols_with_treesitter", lambda *_a: None)
    functions, _classes, imports = extract_symbols("import os\ndef broken(:\n", "python")
    assert imports == ["os"]
    assert functions == ["broken"]
    assert python_imported_names("def broken(:\n") == []


def test_focus_finds_the_files_that_import_the_name(tmp_path: Path):
    (tmp_path / "pkg").mkdir()
    core = tmp_path / "pkg" / "core.py"
    core.write_text("from .util import slugify\n\n\nclass Engine:\n    pass\n", encoding="utf-8")
    item = make_file_insight(tmp_path, core)
    assert item.imports == [".util"] and item.imported_names == ["slugify"]
    assert compute_focus_raw(item, "slugify") >= 2.0  # strong enough to be picked by --focus
    assert compute_focus_raw(item, "unrelated") == 0.0
