#!/usr/bin/env python3
"""
One version number. contexta_app/__init__.py owns it; everything else is read from there.

    python packaging/sync_version.py           # print the version, refresh packaging/version_info.txt
    python packaging/sync_version.py --check   # exit 1 if version_info.txt is stale

The build scripts call this first, so the Windows version resource, the installer
(`/DMyAppVersion=...`) and the banner always show the version the app reports.
Uses no imports from the package, so it runs before dependencies are installed.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INIT = ROOT / "contexta_app" / "__init__.py"
VERSION_INFO = ROOT / "packaging" / "version_info.txt"


def read_version() -> str:
    match = re.search(r'^__version__\s*=\s*"(\d+\.\d+\.\d+)"', INIT.read_text(encoding="utf-8"), re.M)
    if not match:
        raise SystemExit(f"No __version__ = \"X.Y.Z\" in {INIT}")
    return match.group(1)


def render_version_info(version: str) -> str:
    text = VERSION_INFO.read_text(encoding="utf-8")
    quad = ", ".join(version.split(".") + ["0"])
    text = re.sub(r"(filevers|prodvers)=\([^)]*\)", lambda m: f"{m.group(1)}=({quad})", text)
    return re.sub(r"(StringStruct\('(?:FileVersion|ProductVersion)', ')[^']*(')", lambda m: f"{m.group(1)}{version}{m.group(2)}", text)


def main() -> int:
    version = read_version()
    fresh = render_version_info(version)
    if "--check" in sys.argv:
        if VERSION_INFO.read_text(encoding="utf-8") != fresh:
            print(f"packaging/version_info.txt is not {version}. Run python packaging/sync_version.py", file=sys.stderr)
            return 1
        return 0
    if VERSION_INFO.read_text(encoding="utf-8") != fresh:
        VERSION_INFO.write_text(fresh, encoding="utf-8")
    print(version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
