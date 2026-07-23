"""Форма редактирования операторских настроек в интерфейсе CopyPhoto."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path
from typing import TypeVar

from PyQt6 import uic
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialogButtonBox,
    QFileDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QWidget,
)

from copyphoto.album_processor.settings import APPLICATION_DIR
from copyphoto.album_processor.settings_editor import (
    OperatorSettings,
    default_enhancement_modes,
)


_WidgetT = TypeVar("_WidgetT", bound=QWidget)
SETTINGS_FORM_PATH = Path(str(files("copyphoto.gui").joinpath("settings_form.ui")))


class SettingsWidget(QScrollArea):
    """Загруженная из settings_form.ui форма операторских параметров."""

    settings_changed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Загрузить UI-форму, найти поля и подключить сигналы изменений."""
        super().__init__(parent)
        self._updating = False
        self.setWidgetResizable(True)
        loaded = self._load_form()
        self._bind_directory_fields(loaded)
        self._bind_export_fields(loaded)
        self._bind_processing_fields(loaded)
        self._bind_diagnostics_fields(loaded)
        self._connect_numeric_buttons()
        self._connect_browse_buttons(loaded)
        self._connect_dependency_signals()
        self._connect_change_signals()

    def _load_form(self) -> QWidget:
        """Загрузить settings_form.ui, установить форму и вернуть корневой виджет."""
        loaded = uic.loadUi(str(SETTINGS_FORM_PATH))
        if not isinstance(loaded, QWidget):
            raise RuntimeError(f"не удалось загрузить форму {SETTINGS_FORM_PATH}")
        self.setWidget(loaded)
        return loaded

    def _bind_directory_fields(self, loaded: QWidget) -> None:
        """Сохранить ссылки на поля рабочих каталогов."""
        self.input_directory = self._find(loaded, QLineEdit, "inputDirectoryEdit")
        self.output_directory = self._find(loaded, QLineEdit, "outputDirectoryEdit")
        self.final_directory = self._find(loaded, QLineEdit, "finalDirectoryEdit")

    def _bind_export_fields(self, loaded: QWidget) -> None:
        """Сохранить ссылки на элементы формата и именования результатов."""
        self.output_format = self._find(loaded, QComboBox, "outputFormatCombo")
        self.jpeg_quality_label = self._find(loaded, QLabel, "jpegQualityLabel")
        self.jpeg_quality = self._find(loaded, QSpinBox, "jpegQualitySpin")
        self.jpeg_quality_decrease = self._find(
            loaded, QPushButton, "jpegQualityDecreaseButton"
        )
        self.jpeg_quality_increase = self._find(
            loaded, QPushButton, "jpegQualityIncreaseButton"
        )
        self.filename_prefix = self._find(loaded, QLineEdit, "filenamePrefixEdit")
        self.filename_digits = self._find(loaded, QSpinBox, "filenameDigitsSpin")
        self.filename_digits_decrease = self._find(
            loaded, QPushButton, "filenameDigitsDecreaseButton"
        )
        self.filename_digits_increase = self._find(
            loaded, QPushButton, "filenameDigitsIncreaseButton"
        )

    def _bind_processing_fields(self, loaded: QWidget) -> None:
        """Сохранить ссылки на элементы ориентации и коррекции."""
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
        self.enhancement_mode.addItems(default_enhancement_modes())

    def _bind_diagnostics_fields(self, loaded: QWidget) -> None:
        """Сохранить ссылки на переключатель и каталог диагностики."""
        self.diagnostics_enabled = self._find(
            loaded, QCheckBox, "diagnosticsEnabledCheck"
        )
        self.diagnostics_directory = self._find(
            loaded, QLineEdit, "diagnosticsDirectoryEdit"
        )

    def _connect_numeric_buttons(self) -> None:
        """Подключить кнопки увеличения и уменьшения числовых параметров."""
        self.jpeg_quality_decrease.clicked.connect(
            lambda: self.jpeg_quality.stepDown()
        )
        self.jpeg_quality_increase.clicked.connect(
            lambda: self.jpeg_quality.stepUp()
        )
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
            decrease.clicked.connect(
                lambda _checked=False, spin=spin_box: spin.stepDown()
            )
            increase.clicked.connect(
                lambda _checked=False, spin=spin_box: spin.stepUp()
            )

    def _connect_browse_buttons(self, loaded: QWidget) -> None:
        """Связать кнопки обзора с соответствующими полями каталогов."""
        browse_fields = (
            ("inputBrowseButton", self.input_directory),
            ("outputBrowseButton", self.output_directory),
            ("finalBrowseButton", self.final_directory),
            ("diagnosticsBrowseButton", self.diagnostics_directory),
        )
        for button_name, field in browse_fields:
            button = self._find(loaded, QPushButton, button_name)
            button.clicked.connect(
                lambda _checked=False, edit=field: self._browse(edit)
            )

    def _connect_dependency_signals(self) -> None:
        """Подключить сигналы, изменяющие доступность зависимых полей."""
        self.output_format.currentTextChanged.connect(self._update_dependencies)
        self.enhancement_mode.currentTextChanged.connect(
            self._update_dependencies
        )
        self.diagnostics_enabled.toggled.connect(self._update_dependencies)

    def _connect_change_signals(self) -> None:
        """Подключить изменяемые значения формы к общему сигналу настроек."""
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
        """Найти обязательный элемент формы с проверкой его типа."""
        widget: _WidgetT | None = parent.findChild(widget_type, name)
        if widget is None:
            raise RuntimeError(f"в settings_form.ui не найден элемент {name}")
        return widget

    def _browse(self, field: QLineEdit) -> None:
        """Выбрать каталог и записать выбранный путь в указанное поле."""
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
        """Обновить доступность полей, зависящих от других настроек."""
        jpeg_enabled = self.output_format.currentText() == "JPEG"
        self.jpeg_quality.setEnabled(jpeg_enabled)
        self.jpeg_quality_label.setEnabled(jpeg_enabled)
        self.jpeg_quality_decrease.setEnabled(jpeg_enabled)
        self.jpeg_quality_increase.setEnabled(jpeg_enabled)
        enhancement_enabled = self.enhancement_mode.currentText() == "Мягкая"
        self.enhancement_intensity.setEnabled(enhancement_enabled)
        self.enhancement_intensity_label.setEnabled(enhancement_enabled)
        self.enhancement_intensity_decrease.setEnabled(enhancement_enabled)
        self.enhancement_intensity_increase.setEnabled(enhancement_enabled)
        self.diagnostics_directory.setEnabled(self.diagnostics_enabled.isChecked())

    def _emit_settings_changed(self) -> None:
        """Сообщить об изменении оператором, если форма не заполняется программно."""
        if not self._updating:
            self.settings_changed.emit()

    def set_settings(self, settings: OperatorSettings) -> None:
        """Заполнить элементы формы переданными операторскими настройками."""
        self._updating = True
        try:
            self.input_directory.setText(settings.input_directory)
            self.output_directory.setText(settings.output_directory)
            self.final_directory.setText(settings.final_directory)
            output_format = (
                "JPEG"
                if settings.output_format.casefold() in {"jpg", "jpeg"}
                else "PNG"
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
        """Собрать текущие значения элементов формы в OperatorSettings."""
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
