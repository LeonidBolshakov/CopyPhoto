"""Главное окно графического интерфейса CopyPhoto."""

from __future__ import annotations

from datetime import datetime
from importlib.resources import as_file, files
from pathlib import Path
from typing import TypeVar

from PyQt6 import uic
from PyQt6.QtCore import (
    QThread,
    pyqtSlot,
)
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import (
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QWidget,
)

from copyphoto.album_processor.settings import (
    APPLICATION_DIR,
    SETTINGS_PATH,
    ApplicationSettings,
    SettingsError,
    load_settings,
)
from copyphoto.album_processor.settings_editor import (
    DEFAULT_OPERATOR_SETTINGS,
    read_operator_settings,
    replace_invalid_text_with_defaults,
    save_operator_settings,
)
from copyphoto.file_transfer import (
    TransferResult,
    move_files_to_final,
    transfer_prefix,
)
from copyphoto.gui.directory_widget import DirectoryWidget
from copyphoto.gui.processing_worker import ProcessingWorker
from copyphoto.gui.settings_widget import SettingsWidget


APP_TITLE = "CopyPhoto"
MAIN_WINDOW_FORM_NAME = "main_window.ui"
MAIN_WINDOW_FORM = files("copyphoto.gui").joinpath(MAIN_WINDOW_FORM_NAME)
_WidgetT = TypeVar("_WidgetT", bound=QWidget)


class MainWindow(QMainWindow):
    """Главное окно управления CopyPhoto."""

    def __init__(self) -> None:
        """Загрузить форму окна, подключить действия и прочитать настройки."""
        super().__init__()
        self._thread: QThread | None = None
        self._worker: ProcessingWorker | None = None
        self._last_settings_error = ""
        self._load_form()
        self._configure_directory_widgets()
        self._connect_form_actions()
        self._configure_status_bar()
        self._load_settings_from_disk()

    def _load_form(self) -> None:
        """Загрузить main_window.ui и связать именованные элементы с атрибутами."""
        with as_file(MAIN_WINDOW_FORM) as form_path:
            loaded = uic.loadUi(str(form_path), self)
        if loaded is not self:
            raise RuntimeError(f"не удалось загрузить форму {MAIN_WINDOW_FORM_NAME}")
        self.tabs = self._find(QTabWidget, "tabs")
        self.settings_widget = self._find(SettingsWidget, "settingsWidget")
        self.input_files = self._find(DirectoryWidget, "inputFiles")
        self.output_files = self._find(DirectoryWidget, "outputFiles")
        self.final_files = self._find(DirectoryWidget, "finalFiles")
        self.diagnostic_files = self._find(DirectoryWidget, "diagnosticFiles")
        self.restore_button = self._find(QPushButton, "restoreButton")
        self.run_button = self._find(QPushButton, "runButton")
        self.clear_log_button = self._find(QPushButton, "clearLogButton")
        self.save_log_button = self._find(QPushButton, "saveLogButton")
        self.log = self._find(QPlainTextEdit, "log")

    def _find(self, widget_type: type[_WidgetT], name: str) -> _WidgetT:
        """Найти обязательный элемент загруженной формы по имени объекта."""
        widget = self.findChild(widget_type, name)
        if widget is None:
            raise RuntimeError(
                f"в форме {MAIN_WINDOW_FORM_NAME} отсутствует объект "
                f"{widget_type.__name__} с objectName={name!r}"
            )
        return widget

    def _configure_directory_widgets(self) -> None:
        """Назначить файловым вкладкам тексты, ограничения и действия."""
        self.input_files.configure(
            "Во входном каталоге нет изображений",
            move_to_final=lambda: self._confirm_move_to_final("input"),
        )
        self.output_files.configure(
            "В каталоге результатов нет изображений",
            move_to_final=lambda: self._confirm_move_to_final("output"),
        )
        self.final_files.configure(
            "В итоговом каталоге нет изображений", allow_cleanup=False
        )
        self.diagnostic_files.configure(
            "В диагностическом каталоге нет изображений"
        )

    def _connect_form_actions(self) -> None:
        """Подключить сигналы элементов основной формы к обработчикам окна."""
        self.restore_button.clicked.connect(lambda: self.restore_defaults())
        self.run_button.clicked.connect(self.start_processing)
        self.clear_log_button.clicked.connect(self._clear_log)
        self.save_log_button.clicked.connect(self._save_log)
        self.settings_widget.settings_changed.connect(self._save_changed_settings)

    def _configure_status_bar(self) -> None:
        """Настроить строку состояния главного окна."""
        status_bar = self.statusBar()
        assert status_bar is not None
        self.status_bar = status_bar
        self.status_bar.showMessage(f"Настройки: {SETTINGS_PATH}")

    def _load_settings_from_disk(self) -> None:
        """Загрузить настройки в форму и назначить каталоги файловым вкладкам."""
        try:
            editor_settings = read_operator_settings(SETTINGS_PATH)
            application_settings = load_settings(SETTINGS_PATH, APPLICATION_DIR)
        except SettingsError as error:
            self._last_settings_error = str(error)
            self._show_error("Не удалось загрузить настройки", str(error))
            return
        self.settings_widget.set_settings(editor_settings)
        self._last_settings_error = ""
        self._apply_directory_paths(application_settings)

    def _apply_directory_paths(self, settings: ApplicationSettings) -> None:
        """Назначить файловым вкладкам каталоги из проверенных настроек."""
        self.input_files.set_directory(
            settings.detector_config.input_dir
        )
        self.output_files.set_directory(
            settings.export_config.output_dir
        )
        self.final_files.set_directory(settings.final_directory)
        self.diagnostic_files.set_directory(
            settings.diagnostics_config.output_dir
        )

    def save_settings(
        self,
        *,
        show_success: bool = True,
        show_error: bool = True,
    ) -> bool:
        """Проверить и сохранить форму, при необходимости показав результат."""
        try:
            save_operator_settings(
                SETTINGS_PATH,
                self.settings_widget.settings(),
                APPLICATION_DIR,
            )
            application_settings = load_settings(SETTINGS_PATH, APPLICATION_DIR)
        except SettingsError as error:
            self._last_settings_error = str(error)
            if show_error:
                self._show_error("Настройки не сохранены", str(error))
            else:
                self.status_bar.showMessage(
                    f"Настройки пока не сохранены: {error}", 8000
                )
            return False
        self._last_settings_error = ""
        self._apply_directory_paths(application_settings)
        if show_success:
            self.status_bar.showMessage("Настройки сохранены автоматически", 3000)
        return True

    @pyqtSlot()
    def _save_changed_settings(self) -> None:
        """Сразу проверить и сохранить законченное изменение формы."""
        self.save_settings(show_success=True, show_error=False)

    def restore_defaults(self) -> None:
        """Запросить подтверждение восстановления стандартных настроек."""
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Question)
        dialog.setWindowTitle("Восстановить настройки")
        dialog.setText("Заменить текущие параметры стандартными значениями CopyPhoto?")
        restore_button = dialog.addButton(
            "Восстановить",
            QMessageBox.ButtonRole.AcceptRole,
        )
        cancel_button = dialog.addButton(
            "Отмена",
            QMessageBox.ButtonRole.RejectRole,
        )
        dialog.setDefaultButton(cancel_button)
        dialog.exec()
        if dialog.clickedButton() is not restore_button:
            return
        self._apply_defaults()

    def _apply_defaults(self) -> None:
        """Установить стандартные значения и сразу записать их."""
        self.settings_widget.set_settings(DEFAULT_OPERATOR_SETTINGS)
        self.save_settings(show_success=True, show_error=True)

    def _confirm_move_to_final(self, source_kind: str) -> None:
        """Подтвердить перенос выбранных входных или готовых файлов в итоговые."""
        source_widget, source_title, prefix_letter = self._move_source_context(
            source_kind
        )
        sources = source_widget.selected_paths()
        if not sources:
            self._show_message(
                QMessageBox.Icon.Information,
                "Фотографии не выбраны",
                f"Выберите одну или несколько фотографий во вкладке «{source_title}».",
            )
            return
        try:
            source_directory, final_directory = self._move_directories(source_kind)
        except SettingsError as error:
            self._show_error("Не удалось прочитать настройки", str(error))
            return

        if source_directory == final_directory:
            self._show_error(
                "Каталоги совпадают",
                "Исходный и итоговый каталоги должны отличаться.",
            )
            return
        if not self._confirm_move_dialog(
            sources,
            source_directory,
            final_directory,
            version_collisions=source_kind == "output",
        ):
            return

        result = move_files_to_final(
            sources,
            source_directory,
            final_directory,
            (
                transfer_prefix(prefix_letter, datetime.now())
                if prefix_letter
                else ""
            ),
            version_collisions=source_kind == "output",
        )
        source_widget.refresh()
        self.final_files.refresh()
        self._show_move_result(result)

    def _move_source_context(
        self,
        source_kind: str,
    ) -> tuple[DirectoryWidget, str, str]:
        """Вернуть виджет, название вкладки и букву префикса источника."""
        if source_kind == "input":
            return self.input_files, "Входные", "В"
        return self.output_files, "Готовые", ""

    def _move_directories(self, source_kind: str) -> tuple[Path, Path]:
        """Получить проверенные исходный и итоговый каталоги переноса."""
        settings = load_settings(SETTINGS_PATH, APPLICATION_DIR)
        source_directory = (
            settings.detector_config.input_dir.resolve()
            if source_kind == "input"
            else settings.export_config.output_dir.resolve()
        )
        return source_directory, settings.final_directory.resolve()

    def _confirm_move_dialog(
        self,
        sources: list[Path],
        source_directory: Path,
        final_directory: Path,
        *,
        version_collisions: bool,
    ) -> bool:
        """Показать условия переноса и вернуть подтверждение пользователя."""
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Question)
        dialog.setWindowTitle("Переместить в итоговые")
        dialog.setText(f"Переместить выбранных фотографий: {len(sources)}?")
        collision_text = (
            "Свободные исходные имена будут сохранены. При совпадении "
            "к исходному имени будет добавлен номер версии."
            if version_collisions
            else "Существующие файлы не будут перезаписаны."
        )
        dialog.setInformativeText(
            f"Из: {source_directory}\nВ: {final_directory}\n\n{collision_text}"
        )
        move_button = dialog.addButton(
            "Переместить",
            QMessageBox.ButtonRole.AcceptRole,
        )
        cancel_button = dialog.addButton(
            "Отмена",
            QMessageBox.ButtonRole.RejectRole,
        )
        dialog.setDefaultButton(cancel_button)
        dialog.exec()
        return dialog.clickedButton() is move_button

    def _show_move_result(self, result: TransferResult) -> None:
        """Показать итог полного или частичного переноса фотографий."""
        if result.failures:
            descriptions = "\n".join(result.failures[:5])
            if len(result.failures) > 5:
                descriptions += f"\n…и ещё {len(result.failures) - 5}"
            self._show_message(
                QMessageBox.Icon.Warning,
                "Перенос завершён не полностью",
                f"Перемещено: {result.moved}.\n\n{descriptions}",
            )
        else:
            self._show_message(
                QMessageBox.Icon.Information,
                "Фотографии перемещены",
                f"Перемещено в итоговый каталог: {result.moved}.",
            )

    def start_processing(self) -> None:
        """Сохранить настройки и запустить обработку в отдельном потоке Qt."""
        if self._thread is not None:
            return
        if not self.save_settings(show_success=False, show_error=True):
            return

        self.tabs.setCurrentIndex(2)
        moment = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        if self.log.toPlainText():
            self.log.appendPlainText("")
        self.log.appendPlainText(f"===== Запуск {moment} =====")
        self._set_processing_state(True)

        thread = QThread(self)
        worker = ProcessingWorker()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.output.connect(self._append_log_line)
        worker.finished.connect(self._processing_finished)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._thread_finished)
        self._thread = thread
        self._worker = worker
        thread.start()

    def _set_processing_state(self, processing: bool) -> None:
        """Обновить доступность действий и надписи для состояния обработки."""
        self.run_button.setDisabled(processing)
        self.restore_button.setDisabled(processing)
        self.settings_widget.setDisabled(processing)
        self.input_files.set_cleanup_enabled(not processing)
        self.output_files.set_cleanup_enabled(not processing)
        self.diagnostic_files.set_cleanup_enabled(not processing)
        self.input_files.move_to_final_button.setDisabled(processing)
        self.output_files.move_to_final_button.setDisabled(processing)
        self.run_button.setText(
            "Обработка…" if processing else "Запустить обработку"
        )
        self.status_bar.showMessage(
            "Идёт обработка изображений…" if processing else "Готово"
        )

    @pyqtSlot(str)
    def _append_log_line(self, line: str) -> None:
        """Добавить строку в журнал и прокрутить его к последней записи."""
        self.log.appendPlainText(line)
        scrollbar = self.log.verticalScrollBar()
        assert scrollbar is not None
        scrollbar.setValue(scrollbar.maximum())

    @pyqtSlot(int)
    def _processing_finished(self, exit_code: int) -> None:
        """Отразить код завершения и обновить содержимое всех каталогов."""
        self.log.appendPlainText(f"===== Завершено, код {exit_code} =====")
        self._set_processing_state(False)
        self.input_files.refresh()
        self.output_files.refresh()
        self.final_files.refresh()
        self.diagnostic_files.refresh()
        if exit_code == 0:
            self.status_bar.showMessage("Обработка успешно завершена", 8000)
        else:
            self.status_bar.showMessage(
                f"Обработка завершена с кодом {exit_code}", 8000
            )

    @pyqtSlot()
    def _thread_finished(self) -> None:
        """Удалить ссылки на завершившиеся рабочий объект и поток."""
        self._thread = None
        self._worker = None

    def _clear_log(self) -> None:
        """Очистить журнал, если обработка сейчас не выполняется."""
        if self._thread is None:
            self.log.clear()

    def _save_log(self) -> None:
        """Предложить имя файла и сохранить текущий текст журнала в UTF-8."""
        default_name = APPLICATION_DIR / (
            f"CopyPhoto-{datetime.now():%Y%m%d-%H%M%S}.log"
        )
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить журнал",
            str(default_name),
            "Журналы (*.log);;Текстовые файлы (*.txt);;Все файлы (*)",
        )
        if not selected:
            return
        try:
            Path(selected).write_text(self.log.toPlainText(), encoding="utf-8")
        except OSError as error:
            self._show_error("Не удалось сохранить журнал", str(error))

    def _show_error(self, title: str, text: str) -> None:
        """Показать сообщение об ошибке в строке состояния и диалоге."""
        self.status_bar.showMessage(title, 8000)
        self._show_message(QMessageBox.Icon.Critical, title, text)

    def _show_message(
        self,
        icon: QMessageBox.Icon,
        title: str,
        text: str,
    ) -> None:
        """Показать сообщение с русской кнопкой закрытия."""
        dialog = QMessageBox(self)
        dialog.setIcon(icon)
        dialog.setWindowTitle(title)
        dialog.setText(text)
        close_button = dialog.addButton(
            "Закрыть",
            QMessageBox.ButtonRole.AcceptRole,
        )
        dialog.setDefaultButton(close_button)
        dialog.exec()

    def _confirm_exit_with_defaults(self) -> bool:
        """Предложить исправить настройки или выйти с безопасными значениями."""
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setWindowTitle("Настройки не сохранены")
        dialog.setText(self._last_settings_error)
        dialog.setInformativeText(
            "Можно продолжить редактирование или выйти. При выходе "
            "некорректные поля будут заменены стандартными значениями."
        )
        continue_button = dialog.addButton(
            "Продолжить редактирование",
            QMessageBox.ButtonRole.RejectRole,
        )
        exit_button = dialog.addButton(
            "Выйти и восстановить",
            QMessageBox.ButtonRole.DestructiveRole,
        )
        dialog.setDefaultButton(continue_button)
        dialog.exec()
        if dialog.clickedButton() is not exit_button:
            return False

        fallback = replace_invalid_text_with_defaults(
            self.settings_widget.settings()
        )
        self.settings_widget.set_settings(fallback)
        self.save_settings(show_success=False, show_error=False)
        return True

    def closeEvent(self, event: QCloseEvent | None) -> None:
        """Не закрывать окно во время обработки и сохранить ожидающие настройки."""
        if event is None:
            return
        if self._thread is not None:
            dialog = QMessageBox(self)
            dialog.setIcon(QMessageBox.Icon.Information)
            dialog.setWindowTitle("Обработка ещё выполняется")
            dialog.setText(
                "Дождитесь завершения обработки перед закрытием CopyPhoto."
            )
            close_button = dialog.addButton(
                "Понятно",
                QMessageBox.ButtonRole.AcceptRole,
            )
            dialog.setDefaultButton(close_button)
            dialog.exec()
            event.ignore()
            return
        if not self.save_settings(
            show_success=False,
            show_error=False,
        ):
            if self._confirm_exit_with_defaults():
                event.accept()
            else:
                event.ignore()
            return
        event.accept()
