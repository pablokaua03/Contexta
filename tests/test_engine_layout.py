"""The engine is split into modules and still imports cleanly from the facade."""

import ast
import importlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENGINE = ROOT / "contexta_app" / "engine"
MODULES = sorted(p.stem for p in ENGINE.glob("*.py") if p.stem != "__init__")


def test_each_module_imports_on_its_own():
    for name in MODULES:
        result = subprocess.run(
            [sys.executable, "-c", f"import contexta_app.engine.{name}"],
            capture_output=True, text=True, cwd=ROOT,
        )
        assert result.returncode == 0, f"{name}: {result.stderr[-300:]}"


def test_facade_re_exports_every_public_engine_name():
    facade = importlib.import_module("contexta_app.context_engine")
    for name in MODULES:
        module = importlib.import_module(f"contexta_app.engine.{name}")
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                assert hasattr(facade, node.name), f"{name}.{node.name} missing from context_engine"


def test_no_module_defines_the_same_function_twice():
    for name in MODULES:
        tree = ast.parse((ENGINE / f"{name}.py").read_text(encoding="utf-8"))
        seen = set()
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                assert node.name not in seen, f"{name} defines {node.name} twice"
                seen.add(node.name)


def test_modules_stay_reasonably_small():
    for name in MODULES:
        lines = (ENGINE / f"{name}.py").read_text(encoding="utf-8").count("\n")
        assert lines < 1300, f"{name} has {lines} lines"
