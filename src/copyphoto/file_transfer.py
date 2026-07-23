"""Безопасный перенос выбранных фотографий в итоговый каталог."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from copyphoto.album_processor.image_io import SUPPORTED_EXTENSIONS
from copyphoto.album_processor.naming import next_version_path


@dataclass(slots=True)
class TransferResult:
    """Количество перемещённых файлов и описания отказов."""

    moved: int
    failures: list[str]


def transfer_prefix(source_letter: str, started_at: datetime) -> str:
    """Сформировать общий префикс источника и начала переноса."""
    return f"{source_letter}{started_at:%y-%m-%d-%H-%M}_"


def _source_validation_error(
    source: Path,
    source_directory: Path,
    *,
    version_collisions: bool,
) -> str | None:
    """Вернуть описание недопустимого источника или None."""
    if (
        source.parent.resolve() != source_directory
        or source.suffix.casefold() not in SUPPORTED_EXTENSIONS
        or not source.is_file()
    ):
        return f"{source.name}: недопустимый исходный файл"
    if (
        version_collisions
        and source.suffix.casefold() not in {".jpg", ".jpeg", ".png"}
    ):
        return f"{source.name}: готовая фотография должна быть JPEG или PNG"
    return None


def _transfer_target(
    source: Path,
    final_directory: Path,
    name_prefix: str,
    *,
    version_collisions: bool,
) -> tuple[Path, str | None]:
    """Выбрать свободный целевой путь или вернуть сообщение о совпадении."""
    if version_collisions:
        return next_version_path(final_directory / source.name), None
    target = final_directory / f"{name_prefix}{source.name}"
    error = f"{target.name}: имя уже занято" if target.exists() else None
    return target, error


def _move_source(
    source: Path,
    source_directory: Path,
    final_directory: Path,
    name_prefix: str,
    *,
    version_collisions: bool,
) -> str | None:
    """Переместить один допустимый файл или вернуть описание отказа."""
    try:
        error = _source_validation_error(
            source,
            source_directory,
            version_collisions=version_collisions,
        )
        if error is not None:
            return error
        target, error = _transfer_target(
            source,
            final_directory,
            name_prefix,
            version_collisions=version_collisions,
        )
        if error is not None:
            return error
        shutil.move(str(source), str(target))
    except OSError as exception:
        return f"{source.name}: {exception}"
    return None


def move_files_to_final(
    sources: list[Path],
    source_directory: Path,
    final_directory: Path,
    name_prefix: str,
    *,
    version_collisions: bool = False,
) -> TransferResult:
    """Без перезаписи переместить выбранные файлы между каталогами."""
    failures: list[str] = []
    moved = 0
    try:
        final_directory.mkdir(parents=True, exist_ok=True)
    except OSError as exception:
        return TransferResult(
            moved=0,
            failures=[f"Не удалось создать итоговый каталог: {exception}"],
        )

    for source in sources:
        failure = _move_source(
            source,
            source_directory,
            final_directory,
            name_prefix,
            version_collisions=version_collisions,
        )
        if failure is None:
            moved += 1
        else:
            failures.append(failure)
    return TransferResult(moved=moved, failures=failures)
