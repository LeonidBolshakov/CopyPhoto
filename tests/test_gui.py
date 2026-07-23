"""Неблокирующие проверки формы PyQt6 и автоматического сохранения."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QDialogButtonBox, QFileDialog

import copyphoto.gui.main_window as main_window_module
from copyphoto.album_processor.settings_editor import read_operator_settings
from copyphoto.gui.directory_widget import DirectoryWidget
from copyphoto.gui.main_window import MainWindow
from copyphoto.gui.settings_widget import SettingsWidget


SETTINGS_TEXT = """[Каталоги]
Входные изображения = input
Готовые фотографии = output
Итоговые фотографии = final

[Сохранение]
Формат = png
Префикс имени = photo
Количество цифр = 4
Качество JPEG = 95

[Обработка]
Поворачивать портретные в альбомные = Да
Режим коррекции = Мягкая
Интенсивность коррекции = 25

[Диагностика]
Режим отладки = Да
Каталог = debug
"""

_APPLICATION = QApplication.instance()
if not isinstance(_APPLICATION, QApplication):
    _APPLICATION = QApplication([])


def test_directory_dialog_shows_files_while_selecting_directory(
    tmp_path: Path,
) -> None:
    widget = SettingsWidget()

    dialog = widget._directory_dialog(tmp_path)

    assert dialog.fileMode() is QFileDialog.FileMode.Directory
    assert not dialog.testOption(QFileDialog.Option.ShowDirsOnly)
    assert dialog.testOption(QFileDialog.Option.DontUseNativeDialog)
    buttons = dialog.findChild(QDialogButtonBox)
    assert buttons is not None
    open_button = buttons.button(QDialogButtonBox.StandardButton.Open)
    cancel_button = buttons.button(QDialogButtonBox.StandardButton.Cancel)
    assert open_button is not None
    assert cancel_button is not None
    assert open_button.text() == "Выбрать"
    assert cancel_button.text() == "Отмена"


def test_spin_boxes_increment_and_jpeg_quality_depends_on_format() -> None:
    widget = SettingsWidget()
    assert [widget.output_format.itemText(index) for index in range(2)] == [
        "PNG",
        "JPEG",
    ]
    assert widget.output_format.count() == 2
    widget.output_format.setCurrentText("JPEG")
    widget.enhancement_mode.setCurrentText("Мягкая")
    widget.filename_digits.setValue(4)
    widget.enhancement_intensity.setValue(25)
    widget.jpeg_quality.setValue(90)

    widget.filename_digits_increase.click()
    widget.enhancement_intensity_increase.click()
    widget.jpeg_quality_increase.click()

    assert widget.filename_digits.value() == 5
    assert widget.enhancement_intensity.value() == 26
    assert widget.jpeg_quality.value() == 91
    assert widget.jpeg_quality.isEnabled()
    widget.output_format.setCurrentText("PNG")
    assert not widget.jpeg_quality.isEnabled()
    assert not widget.jpeg_quality_label.isEnabled()
    assert not widget.jpeg_quality_decrease.isEnabled()
    assert not widget.jpeg_quality_increase.isEnabled()


def test_final_directory_has_no_cleanup() -> None:
    final_widget = DirectoryWidget(empty_text="Пусто", allow_cleanup=False)

    assert final_widget.clear_button.isHidden()


def test_directory_cleanup_moves_only_supported_top_level_images(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    images = (tmp_path / "source.jpg", tmp_path / "mask.png")
    for path in images:
        path.write_text("test", encoding="utf-8")
    unrelated = tmp_path / "notes.txt"
    unrelated.write_text("keep", encoding="utf-8")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "inside.jpg").write_text("keep", encoding="utf-8")
    moved_paths: list[Path] = []

    def move_to_trash(path: Path) -> bool:
        moved_paths.append(path)
        path.unlink()
        return True

    monkeypatch.setattr(
        DirectoryWidget,
        "_move_to_trash",
        staticmethod(move_to_trash),
    )
    widget = DirectoryWidget(empty_text="Пусто")
    widget.set_directory(tmp_path)
    widget.configure("Пусто", move_to_final=lambda: None)
    widget.select_all_button.click()
    assert len(widget.selected_paths()) == 2

    moved, failures = widget._trash_images(list(images))
    widget.refresh()

    assert moved == 2
    assert failures == []
    assert moved_paths == list(images)
    assert unrelated.exists()
    assert (nested / "inside.jpg").exists()
    assert not widget.clear_button.isEnabled()


def test_text_settings_are_saved_after_editing_finishes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "settings.ini"
    path.write_text(SETTINGS_TEXT, encoding="utf-8")
    monkeypatch.setattr(main_window_module, "APPLICATION_DIR", tmp_path)
    monkeypatch.setattr(main_window_module, "SETTINGS_PATH", path)
    window = MainWindow()

    window.settings_widget.filename_prefix.setText("archive")
    assert read_operator_settings(path).filename_prefix == "photo"
    window.settings_widget.filename_prefix.editingFinished.emit()

    assert read_operator_settings(path).filename_prefix == "archive"
    window.close()


def test_non_text_settings_are_saved_immediately(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "settings.ini"
    path.write_text(SETTINGS_TEXT, encoding="utf-8")
    monkeypatch.setattr(main_window_module, "APPLICATION_DIR", tmp_path)
    monkeypatch.setattr(main_window_module, "SETTINGS_PATH", path)
    window = MainWindow()

    window.settings_widget.filename_digits.setValue(6)
    assert read_operator_settings(path).filename_digits == 6

    window.settings_widget.output_format.setCurrentText("JPEG")
    assert read_operator_settings(path).output_format == "jpeg"

    window.settings_widget.rotate_portrait.setChecked(False)
    assert not read_operator_settings(path).rotate_portrait
    window.close()


def test_close_flushes_pending_settings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "settings.ini"
    path.write_text(SETTINGS_TEXT, encoding="utf-8")
    monkeypatch.setattr(main_window_module, "APPLICATION_DIR", tmp_path)
    monkeypatch.setattr(main_window_module, "SETTINGS_PATH", path)
    window = MainWindow()

    window.settings_widget.filename_prefix.setText("on-close")
    window.close()

    assert read_operator_settings(path).filename_prefix == "on-close"


def test_restore_button_saves_standard_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "settings.ini"
    path.write_text(
        SETTINGS_TEXT.replace("Префикс имени = photo", "Префикс имени = archive"),
        encoding="utf-8",
    )
    monkeypatch.setattr(main_window_module, "APPLICATION_DIR", tmp_path)
    monkeypatch.setattr(main_window_module, "SETTINGS_PATH", path)
    window = MainWindow()

    window._apply_defaults()

    restored = read_operator_settings(path)
    assert restored.filename_prefix == "photo"
    assert restored.input_directory == "input"
    assert restored.final_directory == "final"
    assert restored.diagnostics_directory == "debug"
    window.close()
