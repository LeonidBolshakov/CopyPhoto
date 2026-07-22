"""Неблокирующие проверки формы PyQt6 и автоматического сохранения."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QDialogButtonBox, QFileDialog

import gui as gui_module
from album_processor.settings_editor import read_operator_settings
from gui import DirectoryWidget, MainWindow, SettingsWidget


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


def test_final_directory_has_no_cleanup_and_move_does_not_overwrite(
    tmp_path: Path,
) -> None:
    source_directory = tmp_path / "output"
    final_directory = tmp_path / "final"
    source_directory.mkdir()
    final_directory.mkdir()
    movable = source_directory / "photo_0001.jpg"
    movable.write_text("new", encoding="utf-8")
    collision = source_directory / "photo_0002.png"
    collision.write_text("source", encoding="utf-8")
    existing_jpeg = final_directory / "photo_0001.jpg"
    existing_png = final_directory / "photo_0001.png"
    existing_jpeg.write_text("existing jpg", encoding="utf-8")
    existing_png.write_text("existing png", encoding="utf-8")
    final_widget = DirectoryWidget("Пусто", allow_cleanup=False)
    assert final_widget.clear_button.isHidden()
    moved, failures = MainWindow._move_files_to_final(
        [movable, collision],
        source_directory.resolve(),
        final_directory.resolve(),
        "",
        version_collisions=True,
    )

    assert moved == 2
    assert failures == []
    assert not movable.exists()
    assert not collision.exists()
    assert (final_directory / "photo_0001_2.jpg").read_text(encoding="utf-8") == "new"
    assert (final_directory / "photo_0002.png").read_text(encoding="utf-8") == "source"
    assert existing_jpeg.read_text(encoding="utf-8") == "existing jpg"
    assert existing_png.read_text(encoding="utf-8") == "existing png"


def test_transfer_prefix_uses_source_and_start_time() -> None:
    started_at = datetime(2026, 7, 22, 14, 35)

    assert MainWindow._transfer_prefix("В", started_at) == "В26-07-22-14-35_"


def test_ready_transfer_adds_version_to_each_colliding_name(
    tmp_path: Path,
) -> None:
    source_directory = tmp_path / "output"
    final_directory = tmp_path / "final"
    source_directory.mkdir()
    final_directory.mkdir()
    for index in range(1, 5):
        name = f"photo_{index:05d}.jpg"
        (source_directory / name).write_text(f"new {index}", encoding="utf-8")
        (final_directory / name).write_text(f"old {index}", encoding="utf-8")
    sources = sorted(source_directory.glob("*.jpg"))
    moved, failures = MainWindow._move_files_to_final(
        sources,
        source_directory.resolve(),
        final_directory.resolve(),
        "",
        version_collisions=True,
    )

    assert moved == 4
    assert failures == []
    assert not list(source_directory.glob("*.jpg"))
    for index in range(1, 5):
        assert (final_directory / f"photo_{index:05d}_2.jpg").is_file()


def test_ready_transfer_preserves_free_source_name(tmp_path: Path) -> None:
    source_directory = tmp_path / "output"
    final_directory = tmp_path / "final"
    source_directory.mkdir()
    final_directory.mkdir()
    source = source_directory / "photo_0007.jpg"
    source.write_text("source", encoding="utf-8")
    moved, failures = MainWindow._move_files_to_final(
        [source],
        source_directory.resolve(),
        final_directory.resolve(),
        "",
        version_collisions=True,
    )

    assert moved == 1
    assert failures == []
    assert (final_directory / "photo_0007.jpg").read_text(encoding="utf-8") == "source"
    assert not (final_directory / "photo_0001.jpg").exists()


def test_ready_transfer_continues_versions_of_colliding_name(tmp_path: Path) -> None:
    source_directory = tmp_path / "output"
    final_directory = tmp_path / "final"
    source_directory.mkdir()
    final_directory.mkdir()
    colliding = source_directory / "photo_0001.jpg"
    colliding.write_text("version 3", encoding="utf-8")
    (final_directory / "photo_0001.jpg").write_text("existing", encoding="utf-8")
    (final_directory / "photo_0001_2.jpg").write_text("version 2", encoding="utf-8")
    moved, failures = MainWindow._move_files_to_final(
        [colliding],
        source_directory.resolve(),
        final_directory.resolve(),
        "",
        version_collisions=True,
    )

    assert moved == 1
    assert failures == []
    assert (final_directory / "photo_0001_3.jpg").read_text(encoding="utf-8") == "version 3"


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
    widget = DirectoryWidget("Пусто")
    widget.set_directory(tmp_path)
    select_all_button = widget.add_select_all_action()
    select_all_button.click()
    assert len(widget.selected_paths()) == 2

    moved, failures = widget._trash_images(list(images))
    widget.refresh()

    assert moved == 2
    assert failures == []
    assert moved_paths == list(images)
    assert unrelated.exists()
    assert (nested / "inside.jpg").exists()
    assert not widget.clear_button.isEnabled()


def test_changed_settings_are_saved_automatically(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "settings.ini"
    path.write_text(SETTINGS_TEXT, encoding="utf-8")
    monkeypatch.setattr(gui_module, "APPLICATION_DIR", tmp_path)
    monkeypatch.setattr(gui_module, "SETTINGS_PATH", path)
    window = MainWindow()

    window.settings_widget.filename_prefix.setText("archive")
    window._auto_save_timer.stop()
    window._auto_save()

    assert read_operator_settings(path).filename_prefix == "archive"
    assert not window._settings_dirty
    window.close()


def test_close_flushes_pending_settings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "settings.ini"
    path.write_text(SETTINGS_TEXT, encoding="utf-8")
    monkeypatch.setattr(gui_module, "APPLICATION_DIR", tmp_path)
    monkeypatch.setattr(gui_module, "SETTINGS_PATH", path)
    window = MainWindow()

    window.settings_widget.filename_prefix.setText("on-close")
    window._auto_save_timer.stop()
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
    monkeypatch.setattr(gui_module, "APPLICATION_DIR", tmp_path)
    monkeypatch.setattr(gui_module, "SETTINGS_PATH", path)
    window = MainWindow()

    window._apply_defaults()

    restored = read_operator_settings(path)
    assert restored.filename_prefix == "photo"
    assert restored.input_directory == "input"
    assert restored.final_directory == "final"
    assert restored.diagnostics_directory == "debug"
    window.close()
