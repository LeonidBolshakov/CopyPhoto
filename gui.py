"""Точка запуска графического интерфейса CopyPhoto."""

from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from copyphoto_gui import (
    APP_TITLE,
    DirectoryWidget,
    ImagePreview,
    MainWindow,
    SettingsWidget,
)

__all__ = [
    "DirectoryWidget",
    "ImagePreview",
    "MainWindow",
    "SettingsWidget",
    "main",
]


def main() -> int:
    """Создать QApplication и показать главное окно."""
    application = QApplication(sys.argv)
    application.setApplicationName(APP_TITLE)
    window = MainWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
