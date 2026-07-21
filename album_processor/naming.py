"""Формирование последовательных имён без перезаписи результатов."""

from __future__ import annotations

import re
from pathlib import Path

from album_processor.config import ExportConfig


def format_output_name(
    prefix: str,
    index: int,
    digits: int,
    extension: str = ".jpg",
) -> str:
    """Сформировать имя результата из префикса, номера и расширения."""
    if index < 1:
        raise ValueError("номер выходного файла должен быть положительным")
    if digits < 1:
        raise ValueError("число разрядов в имени файла должно быть положительным")
    if extension not in {".jpg", ".png"}:
        raise ValueError("расширение результата должно быть '.jpg' или '.png'")
    return f"{prefix}_{index:0{digits}d}{extension}"


def find_next_output_index(config: ExportConfig) -> int:
    """Найти следующий свободный номер среди файлов выбранного формата."""
    if not config.output_dir.exists():
        return 1
    pattern = re.compile(
        rf"^{re.escape(config.filename_prefix)}_(\d+){re.escape(config.file_extension)}$",
        re.IGNORECASE,
    )
    indices: list[int] = []
    for path in config.output_dir.iterdir():
        if not path.is_file():
            continue

        match = pattern.fullmatch(path.name)
        if match is None:
            continue

        indices.append(int(match.group(1)))

    return max(indices, default=0) + 1


def output_path(config: ExportConfig, index: int) -> Path:
    """Построить полный путь выходного файла для указанного номера."""
    return config.output_dir / format_output_name(
        config.filename_prefix,
        index,
        config.filename_digits,
        config.file_extension,
    )
