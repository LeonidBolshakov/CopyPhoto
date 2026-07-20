from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from album_processor.config import (
    DEFAULT_CROPPER_CONFIG,
    CropperConfig,
    DetectorConfig,
    ExportConfig,
)
from album_processor.cropper import crop_photo
from album_processor.detector import detect_photos
from album_processor.image_reader import iter_source_images, read_image, write_image
from album_processor.naming import find_next_output_index, output_path


@dataclass(frozen=True, slots=True)
class BatchSummary:
    total_files: int
    processed: int
    files_with_errors: int
    detected_photos: int
    saved_photos: int
    failed_photos: int
    errors: tuple[str, ...]


def _write_diagnostics(
    source: Path,
    annotated: np.ndarray,
    mask: np.ndarray,
    config: DetectorConfig,
) -> None:
    write_image(config.debug_dir / f"{source.stem}_detected.jpg", annotated)
    write_image(config.debug_dir / f"{source.stem}_mask.png", mask)


def _save_without_overwrite(
    image: np.ndarray,
    config: ExportConfig,
    start_index: int,
) -> tuple[Path, int]:
    index = start_index
    while True:
        target = output_path(config, index)
        try:
            write_image(
                target,
                image,
                jpeg_quality=config.jpeg_quality,
                overwrite=False,
            )
        except FileExistsError:
            index += 1
            continue
        return target, index + 1


def process_input_directory(
    config: DetectorConfig,
    export_config: ExportConfig,
    cropper_config: CropperConfig = DEFAULT_CROPPER_CONFIG,
) -> BatchSummary:
    config.input_dir.mkdir(parents=True, exist_ok=True)
    config.debug_dir.mkdir(parents=True, exist_ok=True)
    export_config.output_dir.mkdir(parents=True, exist_ok=True)

    processed = 0
    files_with_errors = 0
    detected_photos = 0
    saved_photos = 0
    failed_photos = 0
    errors: list[str] = []
    sources = iter_source_images(config.input_dir)
    next_index = find_next_output_index(export_config)

    if not sources:
        print("Во входной папке нет поддерживаемых изображений.")

    for source in sources:
        source_has_errors = False
        source_saved_photos = 0
        try:
            image = read_image(source)
            result = detect_photos(image, config)
            processed += 1
            detected_photos += len(result.detections)
        except Exception as error:  # Ошибка одного файла не должна останавливать пакет.
            errors.append(f"{source.name}: не удалось обработать исходный файл: {error}")
            files_with_errors += 1
            continue

        try:
            _write_diagnostics(source, result.annotated, result.mask, config)
        except Exception as error:
            errors.append(f"{source.name}: не удалось записать диагностику: {error}")
            source_has_errors = True

        for photo_number, detection in enumerate(result.detections, start=1):
            try:
                cropped = crop_photo(image, detection, cropper_config)
                target, next_index = _save_without_overwrite(
                    cropped,
                    export_config,
                    next_index,
                )
                saved_photos += 1
                source_saved_photos += 1
                print(f"  фото {photo_number}: сохранено {target.name}")
            except Exception as error:
                failed_photos += 1
                source_has_errors = True
                errors.append(
                    f"{source.name}, фото {photo_number}: не удалось сохранить: {error}"
                )

        if source_has_errors:
            files_with_errors += 1

        print(
            f"{source.name}: найдено {len(result.detections)}, "
            f"сохранено {source_saved_photos}/{len(result.detections)}, "
            f"порог фона {result.distance_threshold:.1f}, "
            f"покрытие фона {result.background_tile_coverage:.0%}"
        )
        if result.background_warning is not None:
            print(f"  ВНИМАНИЕ: {result.background_warning}")

    return BatchSummary(
        total_files=len(sources),
        processed=processed,
        files_with_errors=files_with_errors,
        detected_photos=detected_photos,
        saved_photos=saved_photos,
        failed_photos=failed_photos,
        errors=tuple(errors),
    )
