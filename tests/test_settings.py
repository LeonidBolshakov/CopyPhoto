"""Тесты загрузки операторского INI, комментариев и проверки значений."""

from __future__ import annotations

from pathlib import Path

import pytest

import album_processor.settings as settings_module
from album_processor.config import EnhancementMode
from album_processor.settings import SettingsError, _application_dir, load_settings


VALID_SETTINGS = """
; Этот комментарий полностью игнорируется.
# Формат = jpeg

[Каталоги]
Входные изображения = input ; комментарий после значения
Готовые фотографии = result

[Сохранение]
; Формат = jpeg
Формат = png
Префикс имени = archive
Количество цифр = 5
Качество JPEG = 91

[Обработка]
Поворачивать портретные в альбомные = Нет
Режим коррекции = Мягкая
Интенсивность коррекции = 35 # допустим комментарий после значения

[Диагностика]
Режим отладки = Нет
Каталог = diagnostics
"""


def write_settings(path: Path, content: str = VALID_SETTINGS) -> None:
    path.write_text(content.strip(), encoding="utf-8")


def test_source_run_uses_project_directory() -> None:
    assert _application_dir() == Path(settings_module.__file__).resolve().parent.parent


def test_exe_run_uses_executable_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    executable = tmp_path / "distribution" / "CopyPhoto.exe"
    monkeypatch.setattr(settings_module.sys, "frozen", True, raising=False)
    monkeypatch.setattr(settings_module.sys, "executable", str(executable))

    assert _application_dir() == executable.parent.resolve()


def test_loads_operator_settings_and_ignores_comments(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    path = tmp_path / "settings.ini"
    write_settings(path)

    result = load_settings(path, project_dir)

    assert result.detector_config.input_dir == (project_dir / "input").resolve()
    assert result.export_config.output_dir == (project_dir / "result").resolve()
    assert result.export_config.output_format == "png"
    assert result.export_config.filename_prefix == "archive"
    assert result.export_config.filename_digits == 5
    assert result.export_config.jpeg_quality == 91
    assert not result.cropper_config.rotate_portrait_to_landscape
    assert result.enhancer_config.mode is EnhancementMode.SOFT
    assert result.enhancer_config.intensity == pytest.approx(0.35)
    assert not result.diagnostics_config.enabled
    assert result.diagnostics_config.output_dir == (
        project_dir / "diagnostics"
    ).resolve()


def test_accepts_absolute_directories(tmp_path: Path) -> None:
    absolute_input = (tmp_path / "absolute-input").resolve()
    path = tmp_path / "settings.ini"
    write_settings(
        path,
        VALID_SETTINGS.replace(
            "Входные изображения = input",
            f"Входные изображения = {absolute_input}",
        ),
    )

    result = load_settings(path, tmp_path / "other-project")

    assert result.detector_config.input_dir == absolute_input


def test_accepts_jpg_as_jpeg_format(tmp_path: Path) -> None:
    path = tmp_path / "settings.ini"
    write_settings(path, VALID_SETTINGS.replace("Формат = png", "Формат = jpg"))

    result = load_settings(path, tmp_path)

    assert result.export_config.output_format == "jpeg"
    assert result.export_config.file_extension == ".jpg"


def test_reports_missing_settings_file(tmp_path: Path) -> None:
    missing = tmp_path / "missing.ini"

    with pytest.raises(SettingsError, match="не найден файл настроек"):
        load_settings(missing, tmp_path)


@pytest.mark.parametrize(
    ("old_value", "new_value", "message"),
    (
        (
            "Интенсивность коррекции = 35 # допустим комментарий после значения",
            "Интенсивность коррекции = 150",
            "Интенсивность коррекции",
        ),
        (
            "Поворачивать портретные в альбомные = Нет",
            "Поворачивать портретные в альбомные = Возможно",
            "Да или Нет",
        ),
        (
            "Режим коррекции = Мягкая",
            "Режим коррекции = Сильная",
            "Режим коррекции",
        ),
        (
            "Формат = png",
            "Формат = bmp",
            "jpg, jpeg или png",
        ),
        (
            "Режим отладки = Нет",
            "Режим отладки = Иногда",
            "Да или Нет",
        ),
    ),
)
def test_reports_invalid_operator_values(
    tmp_path: Path,
    old_value: str,
    new_value: str,
    message: str,
) -> None:
    path = tmp_path / "settings.ini"
    write_settings(path, VALID_SETTINGS.replace(old_value, new_value))

    with pytest.raises(SettingsError, match=message):
        load_settings(path, tmp_path)


def test_reports_missing_parameter(tmp_path: Path) -> None:
    path = tmp_path / "settings.ini"
    write_settings(path, VALID_SETTINGS.replace("Количество цифр = 5", ""))

    with pytest.raises(SettingsError, match="Количество цифр"):
        load_settings(path, tmp_path)
