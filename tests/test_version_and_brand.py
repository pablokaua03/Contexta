"""One version number and one logo, everywhere the user can see them."""

from __future__ import annotations

import base64
import importlib.util
import io
import re
import struct
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

import contexta_app
from contexta_app import embedded_icon_data

ROOT = Path(__file__).resolve().parent.parent
VERSION = contexta_app.__version__
HAS_TK = importlib.util.find_spec("tkinter") is not None


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ---- version -----------------------------------------------------------------------------------

def test_pyproject_and_package_agree():
    assert tomllib.loads(read("pyproject.toml"))["project"]["version"] == VERSION


def test_cli_version_flag():
    out = subprocess.run([sys.executable, str(ROOT / "contexta.py"), "--version"], capture_output=True, text=True, timeout=30)
    assert out.stdout.strip() == f"Contexta {VERSION}"


def test_mcp_server_reports_contexta_version_not_the_library_version():
    from contexta_app.mcp_server import mcp

    assert mcp._mcp_server.create_initialization_options().server_version == VERSION


def test_windows_version_resource_is_in_sync():
    result = subprocess.run([sys.executable, str(ROOT / "packaging" / "sync_version.py"), "--check"], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    text = read("packaging/version_info.txt")
    quad = ", ".join(VERSION.split(".") + ["0"])
    assert f"filevers=({quad})" in text and f"prodvers=({quad})" in text


def test_sync_version_prints_the_package_version():
    out = subprocess.run([sys.executable, str(ROOT / "packaging" / "sync_version.py")], capture_output=True, text=True, timeout=30)
    assert out.stdout.strip() == VERSION


def test_installer_reads_the_version_the_build_passes():
    iss = read("packaging/windows/contexta.iss")
    assert re.search(r'#ifndef MyAppVersion\s+#define MyAppVersion "%s"' % re.escape(VERSION), iss)
    assert "/DMyAppVersion=%APP_VERSION%" in read("build.bat")


def test_build_scripts_read_the_version_and_hardcode_none():
    for name in ("build.bat", "build.sh"):
        text = read(name)
        assert "sync_version.py" in text, name
        assert not re.search(r"Contexta \d+\.\d+", text), f"{name} has a hardcoded version in its banner"
    assert "--product-version=%APP_VERSION%" in read("build.bat")


def test_security_policy_lists_the_current_minor():
    major_minor = ".".join(VERSION.split(".")[:2])
    assert f"| {major_minor}.x | Yes |" in read("SECURITY.md")


def test_gui_source_has_no_version_literal():
    source = read("contexta_app/ui.py")
    assert "__version__" in source
    assert not re.search(r"""["']v?\d+\.\d+\.\d+["']""", source)


@pytest.mark.skipif(not HAS_TK, reason="needs Tk")
def test_gui_title_and_badge_show_the_version():
    import tkinter

    from contexta_app import ui

    try:
        app = ui.App()
    except tkinter.TclError:
        pytest.skip("no display")
    try:
        app.update()
        assert app.title() == f"Contexta v{VERSION}"
        assert app._version_badge.cget("text") == f"v{VERSION}"
    finally:
        app.destroy()


# ---- logo --------------------------------------------------------------------------------------

def png_size(blob: bytes) -> tuple[int, int]:
    assert blob.startswith(b"\x89PNG\r\n\x1a\n")
    return struct.unpack(">II", blob[16:24])


def pixel(blob: bytes, x: int, y: int):
    # Pillow is a development dependency (requirements-dev.txt), not a runtime one: skip without it.
    Image = pytest.importorskip("PIL.Image")

    return Image.open(io.BytesIO(blob)).convert("RGBA").getpixel((x, y))


def ico_entries(data: bytes) -> dict[int, bytes]:
    _, kind, count = struct.unpack_from("<HHH", data, 0)
    assert kind == 1
    out = {}
    for i in range(count):
        w, _h, _c, _r, _p, _b, size, offset = struct.unpack_from("<BBBBHHII", data, 6 + 16 * i)
        out[w or 256] = data[offset:offset + size]
    return out


def test_raster_sizes():
    assert png_size((ROOT / "assets" / "logo.png").read_bytes()) == (40, 40)
    assert png_size((ROOT / "assets" / "logo@2x.png").read_bytes()) == (80, 80)
    assert png_size((ROOT / "assets" / "icon.png").read_bytes()) == (256, 256)


def test_icon_ico_is_the_current_logo_at_every_size():
    entries = ico_entries((ROOT / "assets" / "icon.ico").read_bytes())
    assert set(entries) == {16, 24, 32, 48, 64, 128, 256}
    big = entries[256]
    assert png_size(big) == (256, 256)
    r, g, b, a = pixel(big, 180, 212)  # the green check disc of assets/logo.svg
    assert a == 255 and abs(r - 0x3D) < 12 and abs(g - 0xCC) < 12 and abs(b - 0x8E) < 12
    assert pixel(big, 128, 4)[:3] == (0x12, 0x21, 0x1C)  # the dark tile, not the old hexagon icon
    assert pixel(big, 0, 0)[3] == 0  # rounded corner is transparent


def test_svg_and_pngs_use_the_same_brand_colors():
    svg = read("assets/logo.svg")
    assert "#12211c" in svg and "#3dcc8e" in svg
    assert pixel((ROOT / "assets" / "logo@2x.png").read_bytes(), 72, 72)[:3] != (0, 0, 0)


def test_embedded_fallbacks_match_the_files():
    for const, name in (
        (embedded_icon_data.EMBEDDED_ICON_PNG_BASE64, "icon.png"),
        (embedded_icon_data.EMBEDDED_LOGO_PNG_BASE64, "logo.png"),
        (embedded_icon_data.EMBEDDED_LOGO_2X_PNG_BASE64, "logo@2x.png"),
    ):
        assert base64.b64decode(const) == (ROOT / "assets" / name).read_bytes(), name
    legacy = read("assets/brand_assets.py")
    assert embedded_icon_data.EMBEDDED_ICON_PNG_BASE64 == "".join(re.findall(r'"([A-Za-z0-9+/=]+)"', legacy))


def test_installers_ship_the_logo_files():
    for spec in ("contexta.spec", "contexta-safe.spec"):
        text = read(f"packaging/pyinstaller/{spec}")
        assert "logo.png" in text and "logo@2x.png" in text
    assert "assets/logo.png" in read("build.bat")


@pytest.mark.skipif(not HAS_TK, reason="needs Tk")
def test_header_logo_loads_and_falls_back_to_embedded_copy(monkeypatch):
    import tkinter

    from contexta_app import ui

    try:
        root = tkinter.Tk()
    except tkinter.TclError:
        pytest.skip("no display")
    try:
        from_file = ui._load_brand_logo(root)
        assert (from_file.width(), from_file.height()) == (40, 40)
        monkeypatch.setattr(ui, "_asset_roots", lambda: [])
        embedded = ui._load_brand_logo(root)
        assert (embedded.width(), embedded.height()) == (40, 40)
        monkeypatch.setattr(ui, "EMBEDDED_LOGO_PNG_BASE64", "")
        assert ui._load_brand_logo(root) is None  # the header then draws BrandMark
    finally:
        root.destroy()
