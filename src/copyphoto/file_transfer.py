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
    except OSError as error:
        return TransferResult(
            moved=0,
            failures=[f"Не удалось создать итоговый каталог: {error}"],
        )

    for source in sources:
        try:
            if (
                source.parent.resolve() != source_directory
                or source.suffix.casefold() not in SUPPORTED_EXTENSIONS
                or not source.is_file()
            ):
                failures.append(f"{source.name}: недопустимый исходный файл")
                continue
            if (
                version_collisions
                and source.suffix.casefold() not in {".jpg", ".jpeg", ".png"}
            ):
                failures.append(
                    f"{source.name}: готовая фотография должна быть JPEG или PNG"
                )
                continue
            if version_collisions:
                target = next_version_path(final_directory / source.name)
            else:
                target = final_directory / f"{name_prefix}{source.name}"
                if target.exists():
                    failures.append(f"{target.name}: имя уже занято")
                    continue
            shutil.move(str(source), str(target))
            moved += 1
        except OSError as error:
            failures.append(f"{source.name}: {error}")
    return TransferResult(moved=moved, failures=failures)
