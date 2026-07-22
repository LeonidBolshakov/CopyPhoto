"""Форма редактирования операторских настроек CopyPhoto."""

from __future__ import annotations

import sys
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

from album_processor.settings import APPLICATION_DIR
from album_processor.settings_editor import (
    OperatorSettings,
    default_enhancement_modes,
)


_WidgetT = TypeVar("_WidgetT", bound=QWidget)
SETTINGS_FORM_PATH = Path(
    getattr(sys, "_MEIPASS", APPLICATION_DIR)
) / "settings_form.ui"


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
            decrease.clicked.connect(
                lambda _checked=False, spin=spin_box: spin.stepDown()
            )
            increase.clicked.connect(
                lambda _checked=False, spin=spin_box: spin.stepUp()
            )

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
        enhancement_enabled = self.enhancement_mode.currentText() == "Мягкая"
        self.enhancement_intensity.setEnabled(enhancement_enabled)
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
