"""
Contexta — AI-native codebase context engine.

Usage:
    contexta serve [--root DIR]  Start the MCP server (for Claude Code, Cursor, etc.).
                                 Tools only read inside --root (repeatable), CONTEXTA_ROOT,
                                 or the current directory
    contexta <project> [opts]   Generate a context pack (CLI mode)
    contexta                    Launch the desktop GUI
    contexta --configure-ai     Set up AI API keys
"""

from __future__ import annotations

import sys


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "serve":
        from contexta_app.mcp_server import configure_roots, mcp, parse_serve_args

        roots = parse_serve_args(sys.argv[2:])
        sys.argv = [sys.argv[0]]
        if roots:
            configure_roots(roots)
        mcp.run()
    elif len(sys.argv) > 1:
        from contexta_app.cli import run_cli

        run_cli()
    else:
        from contexta_app.ui import App

        app = App()
        app.mainloop()


if __name__ == "__main__":
    main()
