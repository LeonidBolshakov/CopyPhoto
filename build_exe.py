"""Проверка файлов и сборка одного EXE с внешними настройками."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
SPEC_PATH = PROJECT_DIR / "CopyPhoto.spec"
SETTINGS_PATH = PROJECT_DIR / "settings.ini"
DISTRIBUTION_DIR = PROJECT_DIR / "dist"
EXECUTABLE_PATH = DISTRIBUTION_DIR / "CopyPhoto.exe"
DISTRIBUTION_SETTINGS_PATH = DISTRIBUTION_DIR / "settings.ini"


def _check_required_file(path: Path, description: str) -> bool:
    """Сообщить об отсутствии обязательного файла сборки."""
    if path.is_file():
        return True
    print(f"ОШИБКА: отсутствует {description}: {path}")
    return False


def main() -> int:
    """Собрать CopyPhoto.exe и скопировать рядом внешний settings.ini."""
    required_files = (
        (SPEC_PATH, "файл задания PyInstaller"),
        (SETTINGS_PATH, "внешний файл настроек"),
    )
    if not all(
        _check_required_file(path, description)
        for path, description in required_files
    ):
        return 1

    result = subprocess.run(
        (
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            str(SPEC_PATH),
        ),
        cwd=PROJECT_DIR,
        check=False,
    )
    if result.returncode != 0:
        print(f"ОШИБКА: PyInstaller завершил работу с кодом {result.returncode}")
        return result.returncode

    try:
        shutil.copy2(SETTINGS_PATH, DISTRIBUTION_SETTINGS_PATH)
    except OSError as error:
        print(
            "ОШИБКА: ошибка копирования settings.ini "
            f"в каталог dist: {error}"
        )
        return 1

    print(f"Сборка завершена: {EXECUTABLE_PATH}")
    print(f"Внешние настройки: {DISTRIBUTION_SETTINGS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
