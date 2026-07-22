"""Графический интерфейс CopyPhoto на PyQt6."""

from __future__ import annotations

import sys
import shutil
from datetime import datetime
from io import TextIOBase
from pathlib import Path
from typing import Any, TypeVar

from PIL import Image, ImageOps
from PyQt6 import uic
from PyQt6.QtCore import (
    QFile,
    QObject,
    QSize,
    Qt,
    QThread,
    QTimer,
    pyqtSignal,
    pyqtSlot,
)
from PyQt6.QtGui import QCloseEvent, QImage, QPixmap, QResizeEvent
from PyQt6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from album_processor.image_io import SUPPORTED_EXTENSIONS, iter_source_images
from album_processor.naming import next_version_path
from album_processor.settings import APPLICATION_DIR, SETTINGS_PATH, SettingsError
from album_processor.settings_editor import (
    DEFAULT_OPERATOR_SETTINGS,
    OperatorSettings,
    default_enhancement_modes,
    read_operator_settings,
    replace_invalid_text_with_defaults,
    save_operator_settings,
)


APP_TITLE = "CopyPhoto"
_WidgetT = TypeVar("_WidgetT", bound=QWidget)
SETTINGS_FORM_PATH = Path(
    getattr(sys, "_MEIPASS", APPLICATION_DIR)
) / "settings_form.ui"


class _SignalStream(TextIOBase):
    """Текстовый поток, отправляющий готовые строки через Qt-сигнал."""

    def __init__(self, output: Any) -> None:
        self._output = output
        self._buffer = ""

    def write(self, text: str) -> int:
        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self._output.emit(line.rstrip("\r"))
        return len(text)

    def flush(self) -> None:
        if self._buffer:
            self._output.emit(self._buffer)
            self._buffer = ""


class ProcessingWorker(QObject):
    """Запуск консольной обработки вне потока интерфейса."""

    output = pyqtSignal(str)
    finished = pyqtSignal(int)

    @pyqtSlot()
    def run(self) -> None:
        from contextlib import redirect_stderr, redirect_stdout

        from main import main as console_main

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


class SettingsWidget(QScrollArea):
    """Загруженная из settings_form.ui форма операторских параметров."""

    settings_changed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._updating = False
        self.setWidgetResizable(True)
        loaded = uic.loadUi(str(SETTINGS_FORM_PATH))
        if not isinstance(loaded, QWidget):
            raise RuntimeError(f"не удалось загрузить форму {SETTINGS_FORM_PATH}")
        self.setWidget(loaded)

        self.input_directory = self._find(loaded, QLineEdit, "inputDirectoryEdit")
        self.output_directory = self._find(loaded, QLineEdit, "outputDirectoryEdit")
        self.final_directory = self._find(loaded, QLineEdit, "finalDirectoryEdit")
        self.output_format = self._find(loaded, QComboBox, "outputFormatCombo")
        self.jpeg_quality_label = self._find(loaded, QLabel, "jpegQualityLabel")
        self.jpeg_quality = self._find(loaded, QSpinBox, "jpegQualitySpin")
        self.jpeg_quality_decrease = self._find(
            loaded, QPushButton, "jpegQualityDecreaseButton"
        )
        self.jpeg_quality_increase = self._find(
            loaded, QPushButton, "jpegQualityIncreaseButton"
        )
        self.jpeg_quality_decrease.clicked.connect(
            lambda: self.jpeg_quality.stepDown()
        )
        self.jpeg_quality_increase.clicked.connect(
            lambda: self.jpeg_quality.stepUp()
        )
        self.filename_prefix = self._find(loaded, QLineEdit, "filenamePrefixEdit")
        self.filename_digits = self._find(loaded, QSpinBox, "filenameDigitsSpin")
        self.filename_digits_decrease = self._find(
            loaded, QPushButton, "filenameDigitsDecreaseButton"
        )
        self.filename_digits_increase = self._find(
            loaded, QPushButton, "filenameDigitsIncreaseButton"
        )
        self.rotate_portrait = self._find(loaded, QCheckBox, "rotatePortraitCheck")
        self.enhancement_mode = self._find(
            loaded, QComboBox, "enhancementModeCombo"
        )
        self.enhancement_intensity = self._find(
            loaded, QSpinBox, "enhancementIntensitySpin"
        )
        self.enhancement_intensity_label = self._find(
            loaded, QLabel, "enhancementIntensityLabel"
        )
        self.enhancement_intensity_decrease = self._find(
            loaded, QPushButton, "enhancementIntensityDecreaseButton"
        )
        self.enhancement_intensity_increase = self._find(
            loaded, QPushButton, "enhancementIntensityIncreaseButton"
        )
        self.diagnostics_enabled = self._find(
            loaded, QCheckBox, "diagnosticsEnabledCheck"
        )
        self.diagnostics_directory = self._find(
            loaded, QLineEdit, "diagnosticsDirectoryEdit"
        )
        self.enhancement_mode.addItems(default_enhancement_modes())
        for decrease, increase, spin_box in (
            (
                self.filename_digits_decrease,
                self.filename_digits_increase,
                self.filename_digits,
            ),
            (
                self.enhancement_intensity_decrease,
                self.enhancement_intensity_increase,
                self.enhancement_intensity,
            ),
        ):
            decrease.clicked.connect(lambda _checked=False, spin=spin_box: spin.stepDown())
            increase.clicked.connect(lambda _checked=False, spin=spin_box: spin.stepUp())

        browse_fields = (
            ("inputBrowseButton", self.input_directory),
            ("outputBrowseButton", self.output_directory),
            ("finalBrowseButton", self.final_directory),
            ("diagnosticsBrowseButton", self.diagnostics_directory),
        )
        for button_name, field in browse_fields:
            button = self._find(loaded, QPushButton, button_name)
            button.clicked.connect(lambda _checked=False, edit=field: self._browse(edit))

        self.output_format.currentTextChanged.connect(self._update_dependencies)
        self.enhancement_mode.currentTextChanged.connect(
            self._update_dependencies
        )
        self.diagnostics_enabled.toggled.connect(self._update_dependencies)
        for signal in (
            self.input_directory.textChanged,
            self.output_directory.textChanged,
            self.final_directory.textChanged,
            self.output_format.currentTextChanged,
            self.filename_prefix.textChanged,
            self.filename_digits.valueChanged,
            self.jpeg_quality.valueChanged,
            self.rotate_portrait.toggled,
            self.enhancement_mode.currentTextChanged,
            self.enhancement_intensity.valueChanged,
            self.diagnostics_enabled.toggled,
            self.diagnostics_directory.textChanged,
        ):
            signal.connect(self._emit_settings_changed)

    @staticmethod
    def _find(
        parent: QWidget,
        widget_type: type[_WidgetT],
        name: str,
    ) -> _WidgetT:
        widget: _WidgetT | None = parent.findChild(widget_type, name)
        if widget is None:
            raise RuntimeError(f"в settings_form.ui не найден элемент {name}")
        return widget

    def _browse(self, field: QLineEdit) -> None:
        current = Path(field.text().strip()).expanduser()
        if not current.is_absolute():
            current = APPLICATION_DIR / current
        initial = current if current.is_dir() else APPLICATION_DIR
        dialog = self._directory_dialog(initial)
        if dialog.exec():
            selected = dialog.selectedFiles()
            if selected:
                field.setText(selected[0])

    def _directory_dialog(self, initial: Path) -> QFileDialog:
        """Создать выбор каталога с видимым содержимым и русскими кнопками."""
        dialog = QFileDialog(self, "Выберите каталог", str(initial))
        dialog.setFileMode(QFileDialog.FileMode.Directory)
        dialog.setViewMode(QFileDialog.ViewMode.Detail)
        dialog.setOption(QFileDialog.Option.ShowDirsOnly, False)
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        buttons = dialog.findChild(QDialogButtonBox)
        if buttons is not None:
            accept_button = buttons.button(QDialogButtonBox.StandardButton.Open)
            cancel_button = buttons.button(QDialogButtonBox.StandardButton.Cancel)
            if accept_button is not None:
                accept_button.setText("Выбрать")
            if cancel_button is not None:
                cancel_button.setText("Отмена")
        return dialog

    def _update_dependencies(self) -> None:
        jpeg_enabled = self.output_format.currentText() == "JPEG"
        self.jpeg_quality.setEnabled(jpeg_enabled)
        self.jpeg_quality_label.setEnabled(jpeg_enabled)
        self.jpeg_quality_decrease.setEnabled(jpeg_enabled)
        self.jpeg_quality_increase.setEnabled(jpeg_enabled)
        self.enhancement_intensity.setEnabled(
            self.enhancement_mode.currentText() == "Мягкая"
        )
        enhancement_enabled = self.enhancement_mode.currentText() == "Мягкая"
        self.enhancement_intensity_label.setEnabled(enhancement_enabled)
        self.enhancement_intensity_decrease.setEnabled(enhancement_enabled)
        self.enhancement_intensity_increase.setEnabled(enhancement_enabled)
        self.diagnostics_directory.setEnabled(self.diagnostics_enabled.isChecked())

    def _emit_settings_changed(self) -> None:
        if not self._updating:
            self.settings_changed.emit()

    def set_settings(self, settings: OperatorSettings) -> None:
        self._updating = True
        try:
            self.input_directory.setText(settings.input_directory)
            self.output_directory.setText(settings.output_directory)
            self.final_directory.setText(settings.final_directory)
            output_format = (
                "JPEG" if settings.output_format.casefold() in {"jpg", "jpeg"} else "PNG"
            )
            self.output_format.setCurrentText(output_format)
            self.filename_prefix.setText(settings.filename_prefix)
            self.filename_digits.setValue(settings.filename_digits)
            self.jpeg_quality.setValue(settings.jpeg_quality)
            self.rotate_portrait.setChecked(settings.rotate_portrait)
            self.enhancement_mode.setCurrentText(settings.enhancement_mode)
            self.enhancement_intensity.setValue(settings.enhancement_intensity)
            self.diagnostics_enabled.setChecked(settings.diagnostics_enabled)
            self.diagnostics_directory.setText(settings.diagnostics_directory)
            self._update_dependencies()
        finally:
            self._updating = False

    def settings(self) -> OperatorSettings:
        return OperatorSettings(
            input_directory=self.input_directory.text().strip(),
            output_directory=self.output_directory.text().strip(),
            final_directory=self.final_directory.text().strip(),
            output_format=self.output_format.currentText().casefold(),
            filename_prefix=self.filename_prefix.text().strip(),
            filename_digits=self.filename_digits.value(),
            jpeg_quality=self.jpeg_quality.value(),
            rotate_portrait=self.rotate_portrait.isChecked(),
            enhancement_mode=self.enhancement_mode.currentText(),
            enhancement_intensity=self.enhancement_intensity.value(),
            diagnostics_enabled=self.diagnostics_enabled.isChecked(),
            diagnostics_directory=self.diagnostics_directory.text().strip(),
        )


class ImagePreview(QLabel):
    """Масштабируемая область предварительного просмотра изображения."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._source_pixmap: QPixmap | None = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(360, 280)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setText("Выберите изображение")

    def show_pixmap(self, pixmap: QPixmap) -> None:
        self._source_pixmap = pixmap
        self._scale_pixmap()

    def show_message(self, message: str) -> None:
        self._source_pixmap = None
        self.clear()
        self.setText(message)

    def resizeEvent(self, event: QResizeEvent | None) -> None:
        super().resizeEvent(event)
        self._scale_pixmap()

    def _scale_pixmap(self) -> None:
        if self._source_pixmap is None:
            return
        available = self.size() - QSize(20, 20)
        self.setPixmap(
            self._source_pixmap.scaled(
                available,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )


class DirectoryWidget(QWidget):
    """Список поддерживаемых изображений каталога и их предпросмотр."""

    def __init__(
        self,
        empty_text: str,
        parent: QWidget | None = None,
        *,
        allow_cleanup: bool = True,
    ) -> None:
        super().__init__(parent)
        self._directory = Path()
        self._empty_text = empty_text
        self._cleanup_allowed = allow_cleanup
        self._allow_cleanup = allow_cleanup

        self.path_label = QLabel()
        self.path_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        refresh_button = QPushButton("Обновить список")
        refresh_button.setToolTip("Повторно прочитать содержимое каталога")
        refresh_button.clicked.connect(self.refresh)
        self.clear_button = QPushButton("Очистить…")
        self.clear_button.clicked.connect(self._confirm_cleanup)

        self.header = QHBoxLayout()
        self.header.addWidget(self.path_label, 1)
        self.header.addWidget(refresh_button)
        self.header.addWidget(self.clear_button)
        self.clear_button.setVisible(allow_cleanup)

        self.file_list = QListWidget()
        self.file_list.setMinimumWidth(260)
        self.file_list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.file_list.currentItemChanged.connect(self._show_selected)
        self.preview = ImagePreview()
        self.details = QLabel()
        self.details.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.details.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        preview_column = QWidget()
        preview_layout = QVBoxLayout(preview_column)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.addWidget(self.preview, 1)
        preview_layout.addWidget(self.details)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.file_list)
        splitter.addWidget(preview_column)
        splitter.setStretchFactor(1, 1)

        layout = QVBoxLayout(self)
        layout.addLayout(self.header)
        layout.addWidget(splitter, 1)

    def add_header_action(self, text: str, callback: Any) -> QPushButton:
        """Добавить действие над файлами перед кнопкой очистки."""
        button = QPushButton(text)
        button.clicked.connect(lambda: callback())
        self.header.insertWidget(self.header.count() - 1, button)
        return button

    def add_select_all_action(self) -> QPushButton:
        """Добавить кнопку выделения всех показанных изображений."""
        return self.add_header_action("Выделить все", self.file_list.selectAll)

    def selected_paths(self) -> list[Path]:
        """Вернуть выбранные в списке изображения."""
        return [
            Path(item.data(Qt.ItemDataRole.UserRole))
            for item in self.file_list.selectedItems()
        ]

    def set_directory(self, directory: Path) -> None:
        if directory == self._directory:
            return
        self._directory = directory
        self.refresh()

    def refresh(self) -> None:
        selected_path = None
        current = self.file_list.currentItem()
        if current is not None:
            selected_path = current.data(Qt.ItemDataRole.UserRole)

        self.path_label.setText(str(self._directory))
        self.path_label.setToolTip(str(self._directory))
        self.file_list.clear()
        try:
            paths = iter_source_images(self._directory)
        except OSError as error:
            self.preview.show_message("Не удалось прочитать каталог")
            self.details.setText(str(error))
            return
        for path in paths:
            item = QListWidgetItem(path.name)
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            item.setToolTip(str(path))
            self.file_list.addItem(item)
            if str(path) == selected_path:
                self.file_list.setCurrentItem(item)

        if self.file_list.count() == 0:
            self.preview.show_message(self._empty_text)
            self.details.setText("Поддерживаются JPG, PNG, HEIC и HEIF")
        elif self.file_list.currentItem() is None:
            self.file_list.setCurrentRow(0)
        self.clear_button.setEnabled(
            self._allow_cleanup
            and self._cleanup_allowed
            and self.file_list.count() > 0
        )

    def set_cleanup_enabled(self, enabled: bool) -> None:
        """Разрешить очистку, если обработка не выполняется и есть файлы."""
        self._cleanup_allowed = enabled
        self.clear_button.setEnabled(
            self._allow_cleanup and enabled and self.file_list.count() > 0
        )

    def _confirm_cleanup(self) -> None:
        """Запросить подтверждение и переместить изображения в Корзину."""
        try:
            paths = iter_source_images(self._directory)
        except OSError as error:
            self._show_cleanup_message(
                QMessageBox.Icon.Critical,
                "Не удалось прочитать каталог",
                str(error),
            )
            return
        if not paths:
            self._show_cleanup_message(
                QMessageBox.Icon.Information,
                "Каталог уже пуст",
                "Поддерживаемых изображений для удаления нет.",
            )
            return

        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setWindowTitle("Очистить каталог")
        dialog.setText(
            f"Переместить в Корзину изображений: {len(paths)}?"
        )
        dialog.setInformativeText(
            f"Каталог: {self._directory}\n\n"
            "Сам каталог, вложенные папки и остальные типы файлов "
            "будут сохранены."
        )
        clean_button = dialog.addButton(
            "Переместить в Корзину",
            QMessageBox.ButtonRole.DestructiveRole,
        )
        cancel_button = dialog.addButton(
            "Отмена",
            QMessageBox.ButtonRole.RejectRole,
        )
        dialog.setDefaultButton(cancel_button)
        dialog.exec()
        if dialog.clickedButton() is not clean_button:
            return

        moved, failures = self._trash_images(paths)
        self.refresh()
        if failures:
            failed_names = ", ".join(path.name for path in failures[:5])
            if len(failures) > 5:
                failed_names += f" и ещё {len(failures) - 5}"
            self._show_cleanup_message(
                QMessageBox.Icon.Warning,
                "Каталог очищен не полностью",
                f"Перемещено в Корзину: {moved}.\n"
                f"Не удалось переместить: {failed_names}",
            )
        else:
            self._show_cleanup_message(
                QMessageBox.Icon.Information,
                "Каталог очищен",
                f"Перемещено в Корзину изображений: {moved}.",
            )

    def _trash_images(self, paths: list[Path]) -> tuple[int, list[Path]]:
        """Переместить только непосредственные файлы текущего каталога."""
        directory = self._directory.resolve()
        moved = 0
        failures: list[Path] = []
        for path in paths:
            try:
                if path.parent.resolve() != directory or not self._move_to_trash(path):
                    failures.append(path)
                else:
                    moved += 1
            except OSError:
                failures.append(path)
        return moved, failures

    @staticmethod
    def _move_to_trash(path: Path) -> bool:
        success, _new_path = QFile.moveToTrash(str(path))
        return success

    def _show_cleanup_message(
        self,
        icon: QMessageBox.Icon,
        title: str,
        text: str,
    ) -> None:
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

    def _show_selected(
        self,
        current: QListWidgetItem | None,
        _previous: QListWidgetItem | None,
    ) -> None:
        if current is None:
            return
        path = Path(current.data(Qt.ItemDataRole.UserRole))
        try:
            with Image.open(path) as opened:
                image = ImageOps.exif_transpose(opened).convert("RGB")
                original_size = image.size
                image.thumbnail((1800, 1400), Image.Resampling.LANCZOS)
                data = image.tobytes("raw", "RGB")
                qt_image = QImage(
                    data,
                    image.width,
                    image.height,
                    image.width * 3,
                    QImage.Format.Format_RGB888,
                ).copy()
            self.preview.show_pixmap(QPixmap.fromImage(qt_image))
            size_megabytes = path.stat().st_size / (1024 * 1024)
            self.details.setText(
                f"{path.name}  •  {original_size[0]} × {original_size[1]}  •  "
                f"{size_megabytes:.2f} МБ"
            )
        except Exception as error:
            self.preview.show_message("Не удалось открыть изображение")
            self.details.setText(f"{path.name}: {error}")


class MainWindow(QMainWindow):
    """Главное окно управления CopyPhoto."""

    def __init__(self) -> None:
        super().__init__()
        self._thread: QThread | None = None
        self._worker: ProcessingWorker | None = None
        self._settings_dirty = False
        self._last_settings_error = ""
        self.setWindowTitle(APP_TITLE)
        self.resize(980, 840)
        self.setMinimumSize(800, 700)

        title = QLabel("CopyPhoto")
        title.setObjectName("applicationTitle")
        subtitle = QLabel(
            "Выделение бумажных фотографий на однотонной подложке"
        )
        subtitle.setObjectName("applicationSubtitle")
        heading = QVBoxLayout()
        heading.setSpacing(0)
        heading.addWidget(title)
        heading.addWidget(subtitle)

        self.restore_button = QPushButton("Восстановить по умолчанию")
        self.restore_button.clicked.connect(lambda: self.restore_defaults())
        self.run_button = QPushButton("Запустить обработку")
        self.run_button.setObjectName("primaryButton")
        self.run_button.clicked.connect(self.start_processing)

        actions = QHBoxLayout()
        actions.addLayout(heading, 1)
        actions.addWidget(self.restore_button)
        actions.addWidget(self.run_button)

        self.tabs = QTabWidget()
        self.settings_widget = SettingsWidget()
        self.settings_widget.settings_changed.connect(self._schedule_auto_save)
        self.tabs.addTab(self.settings_widget, "Настройки")

        self.directory_tabs = QTabWidget()
        self.input_files = DirectoryWidget("Во входном каталоге нет изображений")
        self.output_files = DirectoryWidget("В каталоге результатов нет изображений")
        self.final_files = DirectoryWidget(
            "В итоговом каталоге нет изображений",
            allow_cleanup=False,
        )
        self.diagnostic_files = DirectoryWidget(
            "В диагностическом каталоге нет изображений"
        )
        self.input_select_all_button = self.input_files.add_select_all_action()
        self.input_move_to_final_button = self.input_files.add_header_action(
            "В итоговые…",
            lambda: self._confirm_move_to_final("input"),
        )
        self.output_select_all_button = self.output_files.add_select_all_action()
        self.output_move_to_final_button = self.output_files.add_header_action(
            "В итоговые…",
            lambda: self._confirm_move_to_final("output"),
        )
        self.directory_tabs.addTab(self.input_files, "Входные")
        self.directory_tabs.addTab(self.output_files, "Готовые")
        self.directory_tabs.addTab(self.final_files, "Итоговые")
        self.directory_tabs.addTab(self.diagnostic_files, "Диагностика")
        self.tabs.addTab(self.directory_tabs, "Изображения")

        log_page = QWidget()
        log_layout = QVBoxLayout(log_page)
        log_actions = QHBoxLayout()
        clear_log_button = QPushButton("Очистить журнал")
        clear_log_button.clicked.connect(self._clear_log)
        save_log_button = QPushButton("Сохранить журнал…")
        save_log_button.clicked.connect(self._save_log)
        log_actions.addStretch(1)
        log_actions.addWidget(clear_log_button)
        log_actions.addWidget(save_log_button)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        log_layout.addLayout(log_actions)
        log_layout.addWidget(self.log, 1)
        self.tabs.addTab(log_page, "Журнал")

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(22, 18, 22, 22)
        layout.setSpacing(16)
        layout.addLayout(actions)
        layout.addWidget(self.tabs, 1)
        self.setCentralWidget(central)
        status_bar = self.statusBar()
        assert status_bar is not None
        self.status_bar = status_bar
        self.status_bar.showMessage(f"Настройки: {SETTINGS_PATH}")
        self.setStyleSheet(_STYLE_SHEET)

        self._auto_save_timer = QTimer(self)
        self._auto_save_timer.setSingleShot(True)
        self._auto_save_timer.setInterval(500)
        self._auto_save_timer.timeout.connect(self._auto_save)

        self._load_settings_from_disk()

    def _load_settings_from_disk(self) -> None:
        try:
            editor_settings = read_operator_settings(SETTINGS_PATH)
            application_settings = self._load_validated_settings()
        except SettingsError as error:
            self._show_error("Не удалось загрузить настройки", str(error))
            return

        self.settings_widget.set_settings(editor_settings)
        self.input_files.set_directory(
            application_settings.detector_config.input_dir
        )
        self.output_files.set_directory(
            application_settings.export_config.output_dir
        )
        self.final_files.set_directory(application_settings.final_directory)
        self.diagnostic_files.set_directory(
            application_settings.diagnostics_config.output_dir
        )
        self._settings_dirty = False

    @staticmethod
    def _load_validated_settings():
        from album_processor.settings import load_settings

        return load_settings(SETTINGS_PATH, APPLICATION_DIR)

    def save_settings(
        self,
        *,
        show_success: bool = True,
        show_error: bool = True,
    ) -> bool:
        try:
            save_operator_settings(
                SETTINGS_PATH,
                self.settings_widget.settings(),
                APPLICATION_DIR,
            )
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
        self._settings_dirty = False
        self._refresh_directory_paths()
        if show_success:
            self.status_bar.showMessage("Настройки сохранены автоматически", 3000)
        return True

    @pyqtSlot()
    def _schedule_auto_save(self) -> None:
        self._settings_dirty = True
        self.status_bar.showMessage("Сохранение настроек…")
        self._auto_save_timer.start()

    @pyqtSlot()
    def _auto_save(self) -> None:
        if self._settings_dirty:
            self.save_settings(show_success=True, show_error=False)

    def _refresh_directory_paths(self) -> None:
        try:
            settings = self._load_validated_settings()
        except SettingsError:
            return
        self.input_files.set_directory(settings.detector_config.input_dir)
        self.output_files.set_directory(settings.export_config.output_dir)
        self.final_files.set_directory(settings.final_directory)
        self.diagnostic_files.set_directory(
            settings.diagnostics_config.output_dir
        )

    def restore_defaults(self) -> None:
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
        self._auto_save_timer.stop()
        self.settings_widget.set_settings(DEFAULT_OPERATOR_SETTINGS)
        self._settings_dirty = True
        self.save_settings(show_success=True, show_error=True)

    def _confirm_move_to_final(self, source_kind: str) -> None:
        """Подтвердить перенос выбранных готовых фотографий в итоговые."""
        if source_kind == "input":
            source_widget = self.input_files
            source_title = "Входные"
            prefix_letter = "В"
        else:
            source_widget = self.output_files
            source_title = "Готовые"
            prefix_letter = ""
        sources = source_widget.selected_paths()
        if not sources:
            self._show_message(
                QMessageBox.Icon.Information,
                "Фотографии не выбраны",
                f"Выберите одну или несколько фотографий во вкладке «{source_title}».",
            )
            return
        try:
            settings = self._load_validated_settings()
        except SettingsError as error:
            self._show_error("Не удалось прочитать настройки", str(error))
            return

        source_directory = (
            settings.detector_config.input_dir.resolve()
            if source_kind == "input"
            else settings.export_config.output_dir.resolve()
        )
        final_directory = settings.final_directory.resolve()
        if source_directory == final_directory:
            self._show_error(
                "Каталоги совпадают",
                "Каталоги готовых и итоговых фотографий должны отличаться.",
            )
            return

        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Question)
        dialog.setWindowTitle("Переместить в итоговые")
        dialog.setText(f"Переместить выбранных фотографий: {len(sources)}?")
        dialog.setInformativeText(
            f"Из: {source_directory}\nВ: {final_directory}\n\n"
            + (
                "Свободные исходные имена будут сохранены. При совпадении "
                "к исходному имени будет добавлен номер версии."
                if source_kind == "output"
                else "Существующие файлы не будут перезаписаны."
            )
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
        if dialog.clickedButton() is not move_button:
            return

        moved, failures = self._move_files_to_final(
            sources,
            source_directory,
            final_directory,
            (
                self._transfer_prefix(prefix_letter, datetime.now())
                if prefix_letter
                else ""
            ),
            version_collisions=source_kind == "output",
        )
        source_widget.refresh()
        self.final_files.refresh()
        if failures:
            descriptions = "\n".join(failures[:5])
            if len(failures) > 5:
                descriptions += f"\n…и ещё {len(failures) - 5}"
            self._show_message(
                QMessageBox.Icon.Warning,
                "Перенос завершён не полностью",
                f"Перемещено: {moved}.\n\n{descriptions}",
            )
        else:
            self._show_message(
                QMessageBox.Icon.Information,
                "Фотографии перемещены",
                f"Перемещено в итоговый каталог: {moved}.",
            )

    @staticmethod
    def _transfer_prefix(source_letter: str, started_at: datetime) -> str:
        """Сформировать общий префикс источника и начала переноса."""
        return f"{source_letter}{started_at:%y-%m-%d-%H-%M}_"

    @staticmethod
    def _move_files_to_final(
        sources: list[Path],
        source_directory: Path,
        final_directory: Path,
        transfer_prefix: str,
        version_collisions: bool = False,
    ) -> tuple[int, list[str]]:
        """Без перезаписи переместить выбранные файлы между каталогами."""
        failures: list[str] = []
        moved = 0
        try:
            final_directory.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            return 0, [f"Не удалось создать итоговый каталог: {error}"]

        for source in sources:
            try:
                if (
                    source.parent.resolve() != source_directory
                    or source.suffix.casefold() not in SUPPORTED_EXTENSIONS
                    or not source.is_file()
                ):
                    failures.append(f"{source.name}: недопустимый исходный файл")
                    continue
                if (
                    version_collisions
                    and source.suffix.casefold() not in {".jpg", ".jpeg", ".png"}
                ):
                    failures.append(
                        f"{source.name}: готовая фотография должна быть JPEG или PNG"
                    )
                    continue
                if not version_collisions:
                    target = final_directory / f"{transfer_prefix}{source.name}"
                    if target.exists():
                        failures.append(f"{target.name}: имя уже занято")
                        continue
                else:
                    target = next_version_path(final_directory / source.name)
                shutil.move(str(source), str(target))
                moved += 1
            except OSError as error:
                failures.append(f"{source.name}: {error}")
        return moved, failures

    def start_processing(self) -> None:
        if self._thread is not None:
            return
        self._auto_save_timer.stop()
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
        self.run_button.setDisabled(processing)
        self.restore_button.setDisabled(processing)
        self.settings_widget.setDisabled(processing)
        self.input_files.set_cleanup_enabled(not processing)
        self.output_files.set_cleanup_enabled(not processing)
        self.diagnostic_files.set_cleanup_enabled(not processing)
        self.input_move_to_final_button.setDisabled(processing)
        self.output_move_to_final_button.setDisabled(processing)
        self.run_button.setText(
            "Обработка…" if processing else "Запустить обработку"
        )
        self.status_bar.showMessage(
            "Идёт обработка изображений…" if processing else "Готово"
        )

    @pyqtSlot(str)
    def _append_log_line(self, line: str) -> None:
        self.log.appendPlainText(line)
        scrollbar = self.log.verticalScrollBar()
        assert scrollbar is not None
        scrollbar.setValue(scrollbar.maximum())

    @pyqtSlot(int)
    def _processing_finished(self, exit_code: int) -> None:
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
        self._thread = None
        self._worker = None

    def _clear_log(self) -> None:
        if self._thread is None:
            self.log.clear()

    def _save_log(self) -> None:
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
        self._settings_dirty = True
        self.save_settings(show_success=False, show_error=False)
        return True

    def closeEvent(self, event: QCloseEvent | None) -> None:
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
        self._auto_save_timer.stop()
        if self._settings_dirty and not self.save_settings(
            show_success=False,
            show_error=False,
        ):
            if self._confirm_exit_with_defaults():
                event.accept()
            else:
                event.ignore()
            return
        event.accept()


_STYLE_SHEET = """
QMainWindow { background: #f4f6f8; }
QWidget { font-family: "Segoe UI"; font-size: 10pt; color: #20242a; }
QLabel#applicationTitle { font-size: 22pt; font-weight: 650; color: #17212b; }
QLabel#applicationSubtitle { color: #647181; padding-top: 2px; }
QGroupBox {
    background: white;
    border: 1px solid #d9dee5;
    border-radius: 8px;
    margin-top: 12px;
    padding: 14px 12px 10px 12px;
    font-weight: 600;
}
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; }
QPushButton {
    background: white;
    border: 1px solid #c8d0d9;
    border-radius: 6px;
    padding: 7px 13px;
}
QPushButton:hover { background: #f0f4f8; border-color: #9cabb9; }
QPushButton:disabled { color: #8c959f; background: #e9edf1; }
QPushButton#primaryButton {
    color: white;
    background: #1769aa;
    border-color: #1769aa;
    font-weight: 600;
}
QPushButton#primaryButton:hover { background: #12588f; }
QLineEdit, QComboBox, QListWidget, QPlainTextEdit {
    background: white;
    border: 1px solid #cfd6de;
    border-radius: 5px;
    padding: 5px;
    selection-background-color: #2f80c9;
}
QLabel:disabled { color: #8c959f; }
QSpinBox:disabled {
    color: #8c959f;
    background: #e3e7eb;
    border: 1px solid #d4d9df;
}
QTabWidget::pane { border: 1px solid #d3dae2; background: white; }
QTabBar::tab { padding: 9px 18px; background: #e7ebef; }
QTabBar::tab:selected { background: white; color: #1769aa; font-weight: 600; }
QListWidget::item { padding: 7px; }
QListWidget::item:selected { background: #dbeeff; color: #163c5c; }
QStatusBar { background: #e9edf1; }
"""


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
