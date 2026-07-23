"""Чтение и безопасное сохранение операторских значений settings.ini."""

from __future__ import annotations

import configparser
import os
import re
from dataclasses import dataclass
from pathlib import Path

from copyphoto.album_processor.config import EnhancementMode
from copyphoto.album_processor.settings import SettingsError, _read_parser, load_settings


@dataclass(frozen=True, slots=True)
class OperatorSettings:
    """Значения settings.ini в форме, удобной для редактирования оператором."""

    input_directory: str
    output_directory: str
    final_directory: str
    output_format: str
    filename_prefix: str
    filename_digits: int
    jpeg_quality: int
    rotate_portrait: bool
    enhancement_mode: str
    enhancement_intensity: int
    diagnostics_enabled: bool
    diagnostics_directory: str


DEFAULT_OPERATOR_SETTINGS = OperatorSettings(
    input_directory="input",
    output_directory="output",
    final_directory="final",
    output_format="png",
    filename_prefix="photo",
    filename_digits=4,
    jpeg_quality=95,
    rotate_portrait=True,
    enhancement_mode=EnhancementMode.SOFT.value,
    enhancement_intensity=25,
    diagnostics_enabled=True,
    diagnostics_directory="debug",
)


def _raw_value(
    parser: configparser.ConfigParser,
    section: str,
    option: str,
) -> str:
    """Прочитать обязательное значение без преобразования типа."""
    if not parser.has_section(section) or not parser.has_option(section, option):
        raise SettingsError(f"не найден параметр [{section}] «{option}»")
    return parser.get(section, option).strip()


def read_operator_settings(path: Path) -> OperatorSettings:
    """Загрузить редактируемые значения из settings.ini."""
    parser = _read_parser(path)

    def integer(section: str, option: str) -> int:
        """Прочитать целочисленное значение или сообщить об ошибке настройки."""
        value = _raw_value(parser, section, option)
        try:
            return int(value)
        except ValueError as error:
            raise SettingsError(
                f"в разделе [{section}] параметр «{option}» должен быть целым числом"
            ) from error

    def yes_no(section: str, option: str) -> bool:
        """Преобразовать операторское значение «Да» или «Нет» в bool."""
        value = _raw_value(parser, section, option).casefold()
        if value == "да":
            return True
        if value == "нет":
            return False
        raise SettingsError(
            f"в разделе [{section}] параметр «{option}» должен иметь значение Да или Нет"
        )

    return OperatorSettings(
        input_directory=_raw_value(
            parser, "Каталоги", "Входные изображения"
        ),
        output_directory=_raw_value(
            parser, "Каталоги", "Готовые фотографии"
        ),
        final_directory=_raw_value(
            parser, "Каталоги", "Итоговые фотографии"
        ),
        output_format=_raw_value(parser, "Сохранение", "Формат"),
        filename_prefix=_raw_value(parser, "Сохранение", "Префикс имени"),
        filename_digits=integer("Сохранение", "Количество цифр"),
        jpeg_quality=integer("Сохранение", "Качество JPEG"),
        rotate_portrait=yes_no(
            "Обработка", "Поворачивать портретные в альбомные"
        ),
        enhancement_mode=_raw_value(
            parser, "Обработка", "Режим коррекции"
        ),
        enhancement_intensity=integer(
            "Обработка", "Интенсивность коррекции"
        ),
        diagnostics_enabled=yes_no("Диагностика", "Режим отладки"),
        diagnostics_directory=_raw_value(parser, "Диагностика", "Каталог"),
    )


def _serialized_values(settings: OperatorSettings) -> dict[tuple[str, str], str]:
    """Преобразовать типизированные значения в текстовые значения INI."""
    return {
        ("Каталоги", "Входные изображения"): settings.input_directory.strip(),
        ("Каталоги", "Готовые фотографии"): settings.output_directory.strip(),
        ("Каталоги", "Итоговые фотографии"): settings.final_directory.strip(),
        ("Сохранение", "Формат"): settings.output_format.strip(),
        ("Сохранение", "Префикс имени"): settings.filename_prefix.strip(),
        ("Сохранение", "Количество цифр"): str(settings.filename_digits),
        ("Сохранение", "Качество JPEG"): str(settings.jpeg_quality),
        (
            "Обработка",
            "Поворачивать портретные в альбомные",
        ): "Да" if settings.rotate_portrait else "Нет",
        ("Обработка", "Режим коррекции"): settings.enhancement_mode.strip(),
        ("Обработка", "Интенсивность коррекции"): str(
            settings.enhancement_intensity
        ),
        ("Диагностика", "Режим отладки"): (
            "Да" if settings.diagnostics_enabled else "Нет"
        ),
        ("Диагностика", "Каталог"): settings.diagnostics_directory.strip(),
    }


_SECTION_PATTERN = re.compile(r"^\s*\[([^]]+)]\s*(?:[;#].*)?$")
_OPTION_PATTERN = re.compile(r"^(\s*)([^=:#]+?)(\s*)=(.*)$")
_SettingKey = tuple[str, str]


def _render_option_line(
    line: str,
    section: str,
    replacements: dict[_SettingKey, str],
) -> tuple[str, _SettingKey | None]:
    """Обновить одну известную строку параметра и вернуть её ключ."""
    content = line.rstrip("\r\n")
    option_match = _OPTION_PATTERN.match(content)
    if not option_match or content.lstrip().startswith((";", "#")):
        return line, None

    option = option_match.group(2).strip()
    key = (section, option)
    if key not in replacements:
        return line, None

    value = replacements[key]
    if not value or any(character in value for character in "\r\n"):
        raise SettingsError(f"параметр [{section}] «{option}» не может быть пустым")
    inline_comment = re.search(r"(\s+[;#].*)$", option_match.group(4))
    comment = inline_comment.group(1) if inline_comment else ""
    newline = line[len(content) :]
    rendered = f"{option_match.group(1)}{option} = {value}{comment}{newline}"
    return rendered, key


def render_operator_settings(source: str, settings: OperatorSettings) -> str:
    """Обновить параметры, сохранив разделы, порядок и комментарии INI."""
    replacements = _serialized_values(settings)
    missing = set(replacements)
    section = ""
    rendered: list[str] = []

    for line in source.splitlines(keepends=True):
        content = line.rstrip("\r\n")
        section_match = _SECTION_PATTERN.match(content)
        if section_match:
            section = section_match.group(1).strip()
            rendered.append(line)
            continue
        rendered_line, replaced_key = _render_option_line(
            line,
            section,
            replacements,
        )
        rendered.append(rendered_line)
        if replaced_key is not None:
            missing.discard(replaced_key)

    if missing:
        section, option = sorted(missing)[0]
        raise SettingsError(f"не найден параметр [{section}] «{option}»")
    return "".join(rendered)


def save_operator_settings(
    path: Path,
    settings: OperatorSettings,
    project_dir: Path,
) -> None:
    """Проверить и атомарно записать settings.ini без потери комментариев."""
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise SettingsError(f"не удалось прочитать файл настроек {path}: {error}") from error

    rendered = render_operator_settings(source, settings)
    temporary_path = path.with_name(f".{path.name}.tmp")
    try:
        temporary_path.write_text(rendered, encoding="utf-8")
        load_settings(temporary_path, project_dir)
        os.replace(temporary_path, path)
    except SettingsError:
        temporary_path.unlink(missing_ok=True)
        raise
    except (OSError, UnicodeError) as error:
        temporary_path.unlink(missing_ok=True)
        raise SettingsError(f"не удалось сохранить файл настроек {path}: {error}") from error


def default_enhancement_modes() -> tuple[str, ...]:
    """Вернуть режимы коррекции в порядке их показа в интерфейсе."""
    return tuple(mode.value for mode in EnhancementMode)


def replace_invalid_text_with_defaults(
    settings: OperatorSettings,
) -> OperatorSettings:
    """Заменить некорректные каталоги и префикс стандартными значениями."""
    values = _serialized_values(settings)

    def directory(section: str, option: str, default: str) -> str:
        """Вернуть допустимый текст каталога или стандартное значение."""
        value = values[(section, option)]
        return value if value and not any(character in value for character in "\r\n") else default

    prefix = values[("Сохранение", "Префикс имени")]
    if (
        not prefix
        or any(character in prefix for character in "\r\n")
        or any(character in '<>:"/\\|?*' for character in prefix)
    ):
        prefix = DEFAULT_OPERATOR_SETTINGS.filename_prefix

    return OperatorSettings(
        input_directory=directory(
            "Каталоги",
            "Входные изображения",
            DEFAULT_OPERATOR_SETTINGS.input_directory,
        ),
        output_directory=directory(
            "Каталоги",
            "Готовые фотографии",
            DEFAULT_OPERATOR_SETTINGS.output_directory,
        ),
        final_directory=directory(
            "Каталоги",
            "Итоговые фотографии",
            DEFAULT_OPERATOR_SETTINGS.final_directory,
        ),
        output_format=settings.output_format,
        filename_prefix=prefix,
        filename_digits=settings.filename_digits,
        jpeg_quality=settings.jpeg_quality,
        rotate_portrait=settings.rotate_portrait,
        enhancement_mode=settings.enhancement_mode,
        enhancement_intensity=settings.enhancement_intensity,
        diagnostics_enabled=settings.diagnostics_enabled,
        diagnostics_directory=directory(
            "Диагностика",
            "Каталог",
            DEFAULT_OPERATOR_SETTINGS.diagnostics_directory,
        ),
    )
