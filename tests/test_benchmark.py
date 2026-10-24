"""The benchmark script: its scoring and its pinned inputs, not the tools it compares."""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("bench", ROOT / "benchmarks" / "bench.py")
bench = importlib.util.module_from_spec(spec)
sys.modules["bench"] = bench
spec.loader.exec_module(bench)


def test_recall_needs_the_path_and_the_signature():
    expected = [("a/x.py", "def run"), ("b/y.py", "class Y")]
    assert bench.recall("a/x.py\ndef run():", expected) == (1, ["b/y.py"])
    assert bench.recall("a/x.py only", expected)[0] == 0
    assert bench.recall("a/x.py def run b/y.py class Y", expected) == (2, [])


def test_cases_are_pinned_and_complete():
    names = {case.name for case in bench.CASES}
    assert names == {"flask", "requests", "fastapi"}
    for case in bench.CASES:
        assert re.fullmatch(r"[0-9a-f]{40}", case.commit)
        assert case.expected and case.task and case.package_glob


def test_every_config_writes_to_the_output_placeholder():
    for case in bench.CASES:
        configs = bench.configs(case, 20000)
        assert len(configs) == 7
        for label, argv, _ in configs:
            assert "{out}" in " ".join(argv) and "{repo}" in " ".join(argv), label


def test_readme_table_matches_results_file():
    table = (ROOT / "benchmarks" / "results.md").read_text(encoding="utf-8").strip()
    assert table in (ROOT / "benchmarks" / "README.md").read_text(encoding="utf-8")
