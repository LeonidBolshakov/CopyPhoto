# -*- mode: python ; coding: utf-8 -*-
"""Сборочное задание PyInstaller для одного консольного EXE-файла."""


analysis = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    # settings.ini намеренно остаётся внешним операторским файлом.
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
python_archive = PYZ(analysis.pure)

executable = EXE(
    python_archive,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name="CopyPhoto",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    version="CopyPhoto.version_info",
    codesign_identity=None,
    entitlements_file=None,
)
