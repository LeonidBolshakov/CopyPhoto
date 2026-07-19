from __future__ import annotations

from dataclasses import dataclass

from album_processor.config import DetectorConfig
from album_processor.detector import detect_photos
from album_processor.image_reader import iter_source_images, read_image, write_image


@dataclass(frozen=True, slots=True)
class BatchSummary:
    processed: int
    detected_photos: int
    errors: tuple[str, ...]


def process_input_directory(config: DetectorConfig) -> BatchSummary:
    config.input_dir.mkdir(parents=True, exist_ok=True)
    config.debug_dir.mkdir(parents=True, exist_ok=True)

    processed = 0
    detected_photos = 0
    errors: list[str] = []
    sources = iter_source_images(config.input_dir)

    if not sources:
        print("Во входной папке нет поддерживаемых изображений.")

    for source in sources:
        try:
            image = read_image(source)
            result = detect_photos(image, config)
            write_image(config.debug_dir / f"{source.stem}_detected.jpg", result.annotated)
            write_image(config.debug_dir / f"{source.stem}_mask.png", result.mask)
            processed += 1
            detected_photos += len(result.detections)
            print(
                f"{source.name}: найдено {len(result.detections)}, "
                f"порог фона {result.distance_threshold:.1f}"
            )
        except Exception as error:  # Batch processing must continue after a bad source file.
            errors.append(f"{source.name}: {error}")

    return BatchSummary(
        processed=processed,
        detected_photos=detected_photos,
        errors=tuple(errors),
    )
