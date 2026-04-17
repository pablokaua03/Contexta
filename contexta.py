"""
Contexta - curated context packs for developer workflows.
"""

from __future__ import annotations

import sys


def main() -> None:
    if len(sys.argv) > 1:
        from contexta_app.cli import run_cli

        run_cli()
    else:
        from contexta_app.ui import App

        app = App()
        app.mainloop()


if __name__ == "__main__":
    main()
