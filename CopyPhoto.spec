# -*- mode: python ; coding: utf-8 -*-
"""Сборочное задание PyInstaller для одного графического EXE-файла."""

import tomllib
from pathlib import Path

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)


project_path = Path(SPECPATH) / "pyproject.toml"
source_path = Path(SPECPATH) / "src"
gui_entry_path = source_path / "copyphoto" / "gui" / "__main__.py"
directory_form_path = source_path / "copyphoto" / "gui" / "directory_widget.ui"
main_window_form_path = source_path / "copyphoto" / "gui" / "main_window.ui"
settings_form_path = source_path / "copyphoto" / "gui" / "settings_form.ui"
with project_path.open("rb") as stream:
    project = tomllib.load(stream)["project"]

version_text = project["version"]
version_parts = tuple(int(part) for part in version_text.split("."))
if len(version_parts) != 3:
    raise ValueError(
        "Версия в pyproject.toml должна состоять из трёх чисел: X.Y.Z"
    )
windows_version = (*version_parts, 0)
author = project["authors"][0]["name"]

version_info = VSVersionInfo(
    ffi=FixedFileInfo(
        filevers=windows_version,
        prodvers=windows_version,
        mask=0x3F,
        flags=0x0,
        OS=0x40004,
        fileType=0x1,
        subtype=0x0,
        date=(0, 0),
    ),
    kids=[
        StringFileInfo(
            [
                StringTable(
                    "040904E4",
                    [
                        StringStruct("CompanyName", author),
                        StringStruct(
                            "FileDescription",
                            "CopyPhoto paper photograph processor",
                        ),
                        StringStruct("FileVersion", f"{version_text}.0"),
                        StringStruct("InternalName", "CopyPhoto"),
                        StringStruct(
                            "LegalCopyright",
                            f"Copyright (c) 2026 {author}",
                        ),
                        StringStruct("OriginalFilename", "CopyPhoto.exe"),
                        StringStruct("ProductName", "CopyPhoto"),
                        StringStruct("ProductVersion", version_text),
                    ],
                )
            ]
        ),
        VarFileInfo([VarStruct("Translation", [1033, 1252])]),
    ],
)


analysis = Analysis(
    [str(gui_entry_path)],
    pathex=[str(source_path)],
    binaries=[],
    # settings.ini остаётся внешним; Qt Designer-формы входят в EXE.
    datas=[
        (str(directory_form_path), "copyphoto/gui"),
        (str(main_window_form_path), "copyphoto/gui"),
        (str(settings_form_path), "copyphoto/gui"),
    ],
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
    version=version_info,
    codesign_identity=None,
    entitlements_file=None,
)
