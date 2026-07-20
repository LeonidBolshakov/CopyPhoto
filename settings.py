"""Загрузка и проверка операторских параметров из файла settings.ini."""

from __future__ import annotations

import configparser
from dataclasses import dataclass
from pathlib import Path

from album_processor.config import (
    CropperConfig,
    DetectorConfig,
    DiagnosticsConfig,
    EnhancementMode,
    EnhancerConfig,
    ExportConfig,
)


PROJECT_DIR = Path(__file__).resolve().parent
SETTINGS_PATH = PROJECT_DIR / "settings.ini"


class SettingsError(ValueError):
    """Ошибка операторских настроек CopyPhoto."""


@dataclass(frozen=True, slots=True)
class ApplicationSettings:
    """Полный набор проверенных конфигураций для запуска CopyPhoto."""

    detector_config: DetectorConfig
    cropper_config: CropperConfig
    enhancer_config: EnhancerConfig
    export_config: ExportConfig
    diagnostics_config: DiagnosticsConfig


def _required_value(
    parser: configparser.ConfigParser,
    section: str,
    parameter: str,
) -> str:
    """Получить обязательное непустое значение параметра INI."""
    if not parser.has_section(section):
        raise SettingsError(f"отсутствует раздел [{section}]")
    if not parser.has_option(section, parameter):
        raise SettingsError(
            f"в разделе [{section}] отсутствует параметр «{parameter}»"
        )
    value = parser.get(section, parameter).strip()
    if not value:
        raise SettingsError(
            f"в разделе [{section}] параметр «{parameter}» не может быть пустым"
        )
    return value


def _integer_value(
    parser: configparser.ConfigParser,
    section: str,
    parameter: str,
) -> int:
    """Прочитать обязательный целочисленный параметр INI."""
    value = _required_value(parser, section, parameter)
    try:
        return int(value)
    except ValueError as error:
        raise SettingsError(
            f"в разделе [{section}] параметр «{parameter}» должен быть целым числом"
        ) from error


def _yes_no_value(
    parser: configparser.ConfigParser,
    section: str,
    parameter: str,
) -> bool:
    """Преобразовать русское значение «Да» или «Нет» в bool."""
    value = _required_value(parser, section, parameter).casefold()
    if value == "да":
        return True
    if value == "нет":
        return False
    raise SettingsError(
        f"в разделе [{section}] параметр «{parameter}» должен иметь значение Да или Нет"
    )


def _directory_value(
    parser: configparser.ConfigParser,
    section: str,
    parameter: str,
    project_dir: Path,
) -> Path:
    """Получить абсолютный путь, разрешая относительный от каталога проекта."""
    directory = Path(_required_value(parser, section, parameter)).expanduser()
    if not directory.is_absolute():
        directory = project_dir / directory
    return directory.resolve()


def _enhancement_mode(value: str) -> EnhancementMode:
    """Преобразовать операторское название режима коррекции во внутренний enum."""
    normalized = value.casefold()
    for mode in EnhancementMode:
        if normalized == mode.value.casefold():
            return mode
    allowed = " или ".join(mode.value for mode in EnhancementMode)
    raise SettingsError(
        "в разделе [Обработка] параметр «Режим коррекции» должен иметь "
        f"значение {allowed}"
    )


def _read_parser(path: Path) -> configparser.ConfigParser:
    """Прочитать INI в UTF-8 с поддержкой отдельных и встроенных комментариев."""
    if not path.is_file():
        raise SettingsError(f"не найден файл настроек: {path}")
    parser = configparser.ConfigParser(
        interpolation=None,
        comment_prefixes=("#", ";"),
        inline_comment_prefixes=("#", ";"),
        empty_lines_in_values=False,
    )
    try:
        with path.open("r", encoding="utf-8") as stream:
            parser.read_file(stream)
    except (OSError, UnicodeError, configparser.Error) as error:
        raise SettingsError(f"не удалось прочитать файл настроек {path}: {error}") from error
    return parser


def load_settings(
    path: Path = SETTINGS_PATH,
    project_dir: Path = PROJECT_DIR,
) -> ApplicationSettings:
    """Загрузить settings.ini и построить типизированные конфигурации приложения."""
    parser = _read_parser(path)

    input_dir = _directory_value(
        parser,
        "Каталоги",
        "Входные изображения",
        project_dir,
    )
    output_dir = _directory_value(
        parser,
        "Каталоги",
        "Готовые фотографии",
        project_dir,
    )
    output_format = _required_value(parser, "Сохранение", "Формат").casefold()
    if output_format not in {"jpeg", "png"}:
        raise SettingsError(
            "в разделе [Сохранение] параметр «Формат» должен иметь значение "
            "png или jpeg"
        )
    filename_prefix = _required_value(parser, "Сохранение", "Префикс имени")
    filename_digits = _integer_value(parser, "Сохранение", "Количество цифр")
    jpeg_quality = _integer_value(parser, "Сохранение", "Качество JPEG")

    rotate_portrait = _yes_no_value(
        parser,
        "Обработка",
        "Поворачивать портретные в альбомные",
    )
    mode_value = _required_value(parser, "Обработка", "Режим коррекции")
    intensity_percent = _integer_value(
        parser,
        "Обработка",
        "Интенсивность коррекции",
    )
    if not 0 <= intensity_percent <= 100:
        raise SettingsError(
            "в разделе [Обработка] параметр «Интенсивность коррекции» должен "
            "находиться в диапазоне от 0 до 100"
        )

    diagnostics_enabled = _yes_no_value(
        parser,
        "Диагностика",
        "Режим отладки",
    )
    diagnostics_dir = _directory_value(
        parser,
        "Диагностика",
        "Каталог",
        project_dir,
    )

    try:
        export_config = ExportConfig(
            output_dir=output_dir,
            filename_prefix=filename_prefix,
            filename_digits=filename_digits,
            output_format=output_format,
            jpeg_quality=jpeg_quality,
        )
    except ValueError as error:
        raise SettingsError(f"ошибка раздела [Сохранение]: {error}") from error

    return ApplicationSettings(
        detector_config=DetectorConfig(
            input_dir=input_dir,
        ),
        cropper_config=CropperConfig(
            rotate_portrait_to_landscape=rotate_portrait,
        ),
        enhancer_config=EnhancerConfig(
            mode=_enhancement_mode(mode_value),
            intensity=intensity_percent / 100.0,
        ),
        export_config=export_config,
        diagnostics_config=DiagnosticsConfig(
            output_dir=diagnostics_dir,
            enabled=diagnostics_enabled,
        ),
    )
