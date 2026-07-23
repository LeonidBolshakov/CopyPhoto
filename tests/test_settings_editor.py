"""Тесты безопасного редактирования settings.ini для графического интерфейса."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from copyphoto.album_processor.settings import SettingsError, load_settings
from copyphoto.album_processor.settings_editor import (
    DEFAULT_OPERATOR_SETTINGS,
    OperatorSettings,
    read_operator_settings,
    render_operator_settings,
    replace_invalid_text_with_defaults,
    save_operator_settings,
)


SETTINGS_TEXT = """; Комментарий должен сохраниться.
[Каталоги]
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


def _values() -> OperatorSettings:
    return OperatorSettings(
        input_directory="incoming",
        output_directory="ready",
        final_directory="selected",
        output_format="jpg",
        filename_prefix="scan",
        filename_digits=6,
        jpeg_quality=88,
        rotate_portrait=False,
        enhancement_mode="Без коррекции",
        enhancement_intensity=10,
        diagnostics_enabled=False,
        diagnostics_directory="diagnostics",
    )


def test_render_replaces_values_and_preserves_comments() -> None:
    source = SETTINGS_TEXT.replace(
        "Формат = png", "Формат = png ; встроенный комментарий"
    )
    rendered = render_operator_settings(source, _values())

    assert rendered.startswith("; Комментарий должен сохраниться.")
    assert "Входные изображения = incoming" in rendered
    assert "Итоговые фотографии = selected" in rendered
    assert "Формат = jpg ; встроенный комментарий" in rendered
    assert "Поворачивать портретные в альбомные = Нет" in rendered
    assert "Режим отладки = Нет" in rendered


def test_save_validates_then_atomically_updates_settings(tmp_path: Path) -> None:
    path = tmp_path / "settings.ini"
    path.write_text(SETTINGS_TEXT, encoding="utf-8")

    save_operator_settings(path, _values(), tmp_path)

    saved = read_operator_settings(path)
    validated = load_settings(path, tmp_path)
    assert saved == _values()
    assert validated.detector_config.input_dir == (tmp_path / "incoming").resolve()
    assert validated.final_directory == (tmp_path / "selected").resolve()
    assert validated.export_config.output_format == "jpeg"
    assert not (tmp_path / ".settings.ini.tmp").exists()


def test_invalid_values_do_not_change_settings_file(tmp_path: Path) -> None:
    path = tmp_path / "settings.ini"
    path.write_text(SETTINGS_TEXT, encoding="utf-8")
    invalid = replace(_values(), filename_prefix="bad/name")

    with pytest.raises(SettingsError, match="Префикс имени"):
        save_operator_settings(path, invalid, tmp_path)

    assert path.read_text(encoding="utf-8") == SETTINGS_TEXT
    assert not (tmp_path / ".settings.ini.tmp").exists()


def test_render_rejects_missing_required_option() -> None:
    source = SETTINGS_TEXT.replace("Каталог = debug\n", "")

    with pytest.raises(SettingsError, match="Каталог"):
        render_operator_settings(source, _values())


def test_render_rejects_multiline_text_value() -> None:
    invalid = replace(_values(), input_directory="input\nother")

    with pytest.raises(SettingsError, match="Входные изображения"):
        render_operator_settings(SETTINGS_TEXT, invalid)


def test_invalid_text_fields_can_be_replaced_with_defaults_before_exit() -> None:
    invalid = replace(
        _values(),
        output_directory="",
        filename_prefix="bad/name",
    )

    fallback = replace_invalid_text_with_defaults(invalid)

    assert fallback.output_directory == DEFAULT_OPERATOR_SETTINGS.output_directory
    assert fallback.filename_prefix == DEFAULT_OPERATOR_SETTINGS.filename_prefix
    assert fallback.input_directory == invalid.input_directory
    assert fallback.final_directory == invalid.final_directory
    assert fallback.jpeg_quality == invalid.jpeg_quality
