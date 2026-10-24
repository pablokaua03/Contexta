"""Editor MCP setup from the desktop app: the config it writes and the dialog it shows."""

from __future__ import annotations

import importlib.util
import json
import sys
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.skipif(importlib.util.find_spec("tkinter") is None, reason="needs Tk")


def _fake_app(ui):
    app = SimpleNamespace(logs=[])
    app._log_write = lambda msg, tag="": app.logs.append((tag, msg))
    app._get_mcp_entry = lambda: ui.App._get_mcp_entry(app)
    return app


def test_write_config_shows_the_dialog_without_crashing(tmp_path, monkeypatch):
    from contexta_app import ui

    shown = []
    monkeypatch.setattr(ui.messagebox, "showinfo", lambda *a, **k: shown.append(a))
    cfg = tmp_path / "home" / ".cursor" / "mcp.json"
    ui.App._write_mcp_config(_fake_app(ui), cfg, "Cursor")
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert "contexta" in data["mcpServers"]
    assert shown and "Cursor" in shown[0][1]


def test_existing_servers_are_kept(tmp_path, monkeypatch):
    from contexta_app import ui

    monkeypatch.setattr(ui.messagebox, "showinfo", lambda *a, **k: None)
    cfg = tmp_path / "mcp.json"
    cfg.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}, "theme": "dark"}), encoding="utf-8")
    ui.App._write_mcp_config(_fake_app(ui), cfg, "Cursor")
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert set(data["mcpServers"]) == {"other", "contexta"} and data["theme"] == "dark"


def test_unreadable_config_is_backed_up_not_lost(tmp_path, monkeypatch):
    from contexta_app import ui

    monkeypatch.setattr(ui.messagebox, "showinfo", lambda *a, **k: None)
    cfg = tmp_path / "mcp.json"
    cfg.write_text('{"mcpServers": {"other": {}}, // a comment\n}', encoding="utf-8")
    app = _fake_app(ui)
    ui.App._write_mcp_config(app, cfg, "Cursor")
    assert (tmp_path / "mcp.json.bak").read_text(encoding="utf-8").startswith('{"mcpServers"')
    assert any(tag == "warn" for tag, _ in app.logs)


def test_entry_for_the_packaged_app_uses_serve(monkeypatch):
    from contexta_app import ui

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", "C:\\Apps\\Contexta\\Contexta.exe")
    assert ui.App._get_mcp_entry(None) == {"command": "C:/Apps/Contexta/Contexta.exe", "args": ["serve"]}


def test_entry_from_a_checkout_points_at_the_script():
    from contexta_app import ui

    entry = ui.App._get_mcp_entry(None)
    assert entry["args"][0].endswith("contexta_mcp.py")
