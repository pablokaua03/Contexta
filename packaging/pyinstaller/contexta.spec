# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

IS_WINDOWS = sys.platform.startswith('win')
ROOT = Path(SPECPATH).resolve().parents[1]
ICON_PATH = ROOT / 'assets' / 'icon.ico'
VERSION_PATH = ROOT / 'packaging' / 'version_info.txt'


def _trim_tk_payload(datas):
    trimmed = []
    for entry in datas:
        dest_name, src_name, typecode = entry
        norm = str(dest_name).replace("\\", "/").lower()

        if norm.startswith("_tcl_data/tzdata/"):
            continue
        if norm.startswith("_tcl_data/msgs/") and not norm.endswith(("/en.msg", "/pt.msg", "/pt_br.msg")):
            continue
        if norm.startswith("_tk_data/msgs/") and not norm.endswith(("/en.msg", "/pt.msg")):
            continue
        if norm.startswith("_tk_data/images/"):
            continue
        if norm.startswith("tcl8/8.4/") or norm.startswith("tcl8/8.5/"):
            continue

        trimmed.append(entry)
    return trimmed

a = Analysis(
    [str(ROOT / 'contexta.py')],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[(str(ICON_PATH), '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['brand_assets', 'assets.brand_assets'],
    noarchive=False,
    optimize=0,
)
a.datas = _trim_tk_payload(a.datas)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='contexta',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=str(VERSION_PATH) if IS_WINDOWS else None,
    icon=[str(ICON_PATH)],
)
