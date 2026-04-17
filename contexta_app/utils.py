"""
utils.py - Shared helpers for Contexta.
"""

import os
import sys
from pathlib import Path


def get_desktop() -> Path:
    if sys.platform == "win32":
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders",
            )
            desktop, _ = winreg.QueryValueEx(key, "Desktop")
            return Path(desktop)
        except Exception:
            pass

    xdg = os.environ.get("XDG_DESKTOP_DIR")
    if xdg:
        return Path(xdg)

    return Path.home() / "Desktop"


def safe_project_name(name: str) -> str:
    safe = "".join(c for c in name if c.isalnum() or c in " _-").strip()
    return safe or "project"
