"""Command-line entry point shared by the `contexta` console script, `python -m contexta_app` and the
legacy `contexta.py` launcher.

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

import sys


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "serve":
        from contexta_app.mcp_server import configure_roots, mcp, parse_serve_args

        roots = parse_serve_args(sys.argv[2:])
        sys.argv = [sys.argv[0]]
        if roots:
            configure_roots(roots)
        mcp.run()
    elif len(sys.argv) > 1 and sys.argv[1] == "graph":
        from contexta_app.graph_cli import run_graph

        raise SystemExit(run_graph(sys.argv[2:]))
    elif len(sys.argv) > 1 and sys.argv[1] == "install":
        from contexta_app.install import run_install

        raise SystemExit(run_install(sys.argv[2:]))
    elif len(sys.argv) > 1:
        from contexta_app.cli import run_cli

        run_cli()
    else:
        try:
            from contexta_app.ui import App
        except ImportError as exc:
            if "tkinter" not in str(exc) and "_tkinter" not in str(exc):
                raise
            sys.stderr.write(
                "The desktop GUI needs Tk, and this Python was built without it.\n"
                "  Debian/Ubuntu: sudo apt install python3-tk     Fedora: sudo dnf install python3-tkinter\n"
                "  macOS (Homebrew): brew install python-tk\n"
                "Everything else works without it: contexta --help, contexta <project>, contexta graph, contexta serve.\n"
            )
            raise SystemExit(1)

        app = App()
        app.mainloop()


if __name__ == "__main__":
    main()
