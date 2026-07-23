"""Фоновый запуск консольной обработки и передача её вывода в GUI."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import TextIOBase
from typing import Any

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot


class _SignalStream(TextIOBase):
    """Текстовый поток, отправляющий готовые строки через Qt-сигнал."""

    def __init__(self, output: Any) -> None:
        """Сохранить сигнал вывода и подготовить буфер неполной строки."""
        self._output = output
        self._buffer = ""

    def write(self, text: str) -> int:
        """Добавить текст в буфер и отправить каждую завершённую строку."""
        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self._output.emit(line.rstrip("\r"))
        return len(text)

    def flush(self) -> None:
        """Отправить оставшуюся незавершённую строку и очистить буфер."""
        if self._buffer:
            self._output.emit(self._buffer)
            self._buffer = ""


class ProcessingWorker(QObject):
    """Запуск консольной обработки вне потока интерфейса."""

    output = pyqtSignal(str)
    finished = pyqtSignal(int)

    @pyqtSlot()
    def run(self) -> None:
        """Выполнить консольную обработку и передать вывод и код завершения."""
        from copyphoto.cli import main as console_main

        stream = _SignalStream(self.output)
        try:
            with redirect_stdout(stream), redirect_stderr(stream):
                exit_code = console_main()
        except Exception as error:  # Защита GUI от необработанной ошибки ядра.
            self.output.emit(f"НЕОБРАБОТАННАЯ ОШИБКА: {error}")
            exit_code = 1
        finally:
            stream.flush()
        self.finished.emit(exit_code)
