"""The project graph is not limited to the 2000 files a pack scans."""

from __future__ import annotations

from contexta_app.graph import ProjectGraph, graph_max_files
from contexta_app.graph_cli import format_status


def _project(root, count):
    for i in range(count):
        d = root / f"pkg{i // 100}"
        d.mkdir(exist_ok=True)
        (d / f"m{i}.py").write_text(f"def f{i}():\n    return {i}\n", encoding="utf-8")


def test_graph_indexes_more_than_a_pack_would(tmp_path, monkeypatch):
    monkeypatch.delenv("CONTEXTA_GRAPH_MAX_FILES", raising=False)
    monkeypatch.delenv("CONTEXTA_MAX_FILES", raising=False)
    _project(tmp_path, 2100)
    g = ProjectGraph(tmp_path)
    try:
        stats = g.update(use_git=False)
        assert stats.total == 2100
        assert stats.truncated is False
        assert g.has_file("pkg20/m2099.py")
        assert g.stats()["truncated"] is False
    finally:
        g.close()


def test_graph_says_so_when_it_hits_its_own_limit(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTEXTA_GRAPH_MAX_FILES", "5")
    _project(tmp_path, 12)
    g = ProjectGraph(tmp_path)
    try:
        stats = g.update(use_git=False)
        assert stats.total == 5
        assert stats.truncated is True
        assert "CONTEXTA_GRAPH_MAX_FILES" in stats.summary()
        info = g.stats()
        assert info["truncated"] is True
        assert "incomplete" in format_status(info, "demo")
    finally:
        g.close()


def test_bad_values_fall_back_to_the_default(monkeypatch):
    for bad in ("", "abc", "-3", "0"):
        monkeypatch.setenv("CONTEXTA_GRAPH_MAX_FILES", bad)
        assert graph_max_files() == 50000
