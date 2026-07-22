"""Точка запуска графического интерфейса CopyPhoto."""

from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from directory_widget import DirectoryWidget, ImagePreview
from main_window import APP_TITLE, MainWindow
from settings_widget import SettingsWidget

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
    application.setOrganizationName("CopyPhoto")
    window = MainWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
