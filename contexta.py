"""
Contexta — AI-native codebase context engine.

Usage:
    contexta serve [--root DIR]  Start the MCP server (for Claude Code, Cursor, etc.).
                                 Tools only read inside --root (repeatable), CONTEXTA_ROOT,
                                 or the current directory
    contexta graph <command>    Ask the project graph: dependents, impact, hot files, repo map
    contexta install <target>   Write agent rules or MCP config (cursor, claude, copilot, mcp)
    contexta <project> [opts]   Generate a context pack (CLI mode)
    contexta                    Launch the desktop GUI
    contexta --configure-ai     Set up AI API keys
"""

from __future__ import annotations

from contexta_app.entry import main

if __name__ == "__main__":
    main()
