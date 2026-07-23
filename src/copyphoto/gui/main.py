"""Создание и запуск графического приложения CopyPhoto."""

from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from copyphoto.gui.main_window import APP_TITLE, MainWindow


def main() -> int:
    """Создать QApplication, показать главное окно и запустить цикл событий."""
    application = QApplication(sys.argv)
    application.setApplicationName(APP_TITLE)
    window = MainWindow()
    window.show()
    return application.exec()
