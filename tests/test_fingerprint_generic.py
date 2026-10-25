"""A generic Tk app must not be described as Contexta."""

from __future__ import annotations

from pathlib import Path

from contexta_app.engine.fingerprint import infer_probable_purpose
from contexta_app.context_engine import ExportConfig, build_analysis
from contexta_app.scanner import build_tree

LABEL = "Desktop GUI + CLI developer tool"
SELF_TEXT = "curated context packs"


def test_generic_label_has_a_generic_purpose():
    for domain in (None, "developer_tooling", "education"):
        assert SELF_TEXT not in infer_probable_purpose(LABEL, domain)


def test_small_tk_project_is_not_called_contexta(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text("import tkinter as tk\nfrom utils import slugify\n\ndef main():\n    tk.Tk().mainloop()\n\nif __name__ == '__main__':\n    main()\n", encoding="utf-8")
    (src / "utils.py").write_text("def slugify(s):\n    return s.lower()\n", encoding="utf-8")
    (src / "db.py").write_text("import sqlite3\n", encoding="utf-8")
    tree = build_tree(tmp_path, False, False, lambda *_a, **_k: None, [0], [], tmp_path)
    analysis = build_analysis(tmp_path, tree, [], ExportConfig(context_mode="onboarding", task_profile="explain_project"), lambda *_a, **_k: None)
    assert SELF_TEXT not in (analysis.fingerprint.probable_purpose or "")
    assert SELF_TEXT not in "\n".join(analysis.summary_lines)
