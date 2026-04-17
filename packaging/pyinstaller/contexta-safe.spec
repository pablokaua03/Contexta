# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

IS_WINDOWS = sys.platform.startswith('win')
ROOT = Path(SPECPATH).resolve().parents[1]
ICON_PATH = ROOT / 'assets' / 'icon.ico'
VERSION_PATH = ROOT / 'packaging' / 'version_info.txt'

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
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='contexta',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=str(VERSION_PATH) if IS_WINDOWS else None,
    icon=[str(ICON_PATH)],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='contexta',
)
