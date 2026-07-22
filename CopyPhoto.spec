# -*- mode: python ; coding: utf-8 -*-
"""Сборочное задание PyInstaller для одного графического EXE-файла."""


analysis = Analysis(
    ["gui.py"],
    pathex=[],
    binaries=[],
    # settings.ini остаётся внешним; Qt Designer-форма входит в EXE.
    datas=[("settings_form.ui", ".")],
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
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    version="CopyPhoto.version_info",
    codesign_identity=None,
    entitlements_file=None,
)
