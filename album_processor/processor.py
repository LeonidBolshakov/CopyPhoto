from __future__ import annotations

from collections import Counter
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
from album_processor.detector import (
    ContourRejection,
    ContourRejectionReason,
    DetectionResult,
    DetectionWarning,
    detect_photos,
)
from album_processor.image_reader import iter_source_images, read_image, write_image
from album_processor.naming import find_next_output_index, output_path


@dataclass(frozen=True, slots=True)
class RejectionCount:
    reason: ContourRejectionReason
    count: int
    example: str


@dataclass(frozen=True, slots=True)
class SourceProcessingReport:
    source: Path
    processed: bool
    detected_photos: int
    saved_paths: tuple[Path, ...]
    failed_photos: int
    rejection_counts: tuple[RejectionCount, ...]
    warnings: tuple[DetectionWarning, ...]
    distance_threshold: float | None
    background_tile_coverage: float | None
    errors: tuple[str, ...]

    @property
    def saved_photos(self) -> int:
        return len(self.saved_paths)


@dataclass(frozen=True, slots=True)
class BatchSummary:
    total_files: int
    processed: int
    files_with_errors: int
    detected_photos: int
    saved_photos: int
    failed_photos: int
    errors: tuple[str, ...]
    files: tuple[SourceProcessingReport, ...]


def _summarize_rejections(
    rejections: tuple[ContourRejection, ...],
) -> tuple[RejectionCount, ...]:
    counts = Counter(item.reason for item in rejections)
    return tuple(
        RejectionCount(
            reason=reason,
            count=counts[reason],
            example=next(
                item.details for item in rejections if item.reason is reason
            ),
        )
        for reason in ContourRejectionReason
        if counts[reason]
    )


class AlbumProcessor:
    """Управляет пакетной обработкой, не реализуя алгоритмы изображений."""

    def __init__(
        self,
        detector_config: DetectorConfig,
        export_config: ExportConfig,
        cropper_config: CropperConfig = DEFAULT_CROPPER_CONFIG,
    ) -> None:
        self.detector_config = detector_config
        self.export_config = export_config
        self.cropper_config = cropper_config

    def process(self) -> BatchSummary:
        self._prepare_directories()
        sources = tuple(iter_source_images(self.detector_config.input_dir))
        next_index = find_next_output_index(self.export_config)
        reports: list[SourceProcessingReport] = []

        for source in sources:
            report, next_index = self._process_source(source, next_index)
            reports.append(report)

        file_reports = tuple(reports)
        errors = tuple(
            error for report in file_reports for error in report.errors
        )
        return BatchSummary(
            total_files=len(sources),
            processed=sum(report.processed for report in file_reports),
            files_with_errors=sum(bool(report.errors) for report in file_reports),
            detected_photos=sum(
                report.detected_photos for report in file_reports
            ),
            saved_photos=sum(report.saved_photos for report in file_reports),
            failed_photos=sum(report.failed_photos for report in file_reports),
            errors=errors,
            files=file_reports,
        )

    def _prepare_directories(self) -> None:
        self.detector_config.input_dir.mkdir(parents=True, exist_ok=True)
        self.detector_config.debug_dir.mkdir(parents=True, exist_ok=True)
        self.export_config.output_dir.mkdir(parents=True, exist_ok=True)

    def _process_source(
        self,
        source: Path,
        next_index: int,
    ) -> tuple[SourceProcessingReport, int]:
        try:
            image = read_image(source)
            result = detect_photos(image, self.detector_config)
        except Exception as error:  # Ошибка одного файла не останавливает пакет.
            message = (
                f"{source.name}: не удалось обработать исходный файл: {error}"
            )
            return (
                SourceProcessingReport(
                    source=source,
                    processed=False,
                    detected_photos=0,
                    saved_paths=(),
                    failed_photos=0,
                    rejection_counts=(),
                    warnings=(),
                    distance_threshold=None,
                    background_tile_coverage=None,
                    errors=(message,),
                ),
                next_index,
            )

        errors: list[str] = []
        saved_paths: list[Path] = []
        failed_photos = 0

        try:
            self._write_diagnostics(source, result)
        except Exception as error:
            errors.append(
                f"{source.name}: не удалось записать диагностику: {error}"
            )

        for photo_number, detection in enumerate(result.detections, start=1):
            try:
                cropped = crop_photo(image, detection, self.cropper_config)
                target, next_index = self._save_without_overwrite(
                    cropped,
                    next_index,
                )
                saved_paths.append(target)
            except Exception as error:
                failed_photos += 1
                errors.append(
                    f"{source.name}, фото {photo_number}: не удалось сохранить: {error}"
                )

        return (
            SourceProcessingReport(
                source=source,
                processed=True,
                detected_photos=len(result.detections),
                saved_paths=tuple(saved_paths),
                failed_photos=failed_photos,
                rejection_counts=_summarize_rejections(result.rejections),
                warnings=result.warnings,
                distance_threshold=result.distance_threshold,
                background_tile_coverage=result.background_tile_coverage,
                errors=tuple(errors),
            ),
            next_index,
        )

    def _write_diagnostics(self, source: Path, result: DetectionResult) -> None:
        write_image(
            self.detector_config.debug_dir / f"{source.stem}_detected.jpg",
            result.annotated,
        )
        write_image(
            self.detector_config.debug_dir / f"{source.stem}_mask.png",
            result.mask,
        )

    def _save_without_overwrite(
        self,
        image: np.ndarray,
        start_index: int,
    ) -> tuple[Path, int]:
        index = start_index
        while True:
            target = output_path(self.export_config, index)
            try:
                write_image(
                    target,
                    image,
                    jpeg_quality=self.export_config.jpeg_quality,
                    overwrite=False,
                )
            except FileExistsError:
                index += 1
                continue
            return target, index + 1
