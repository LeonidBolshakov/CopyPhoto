from __future__ import annotations

from album_processor.config import (
    DEFAULT_CROPPER_CONFIG,
    CropperConfig,
    DetectorConfig,
    ExportConfig,
)
from album_processor.processor import AlbumProcessor, BatchSummary


def process_input_directory(
    config: DetectorConfig,
    export_config: ExportConfig,
    cropper_config: CropperConfig = DEFAULT_CROPPER_CONFIG,
) -> BatchSummary:
    """Совместимый функциональный интерфейс пакетной обработки."""
    return AlbumProcessor(config, export_config, cropper_config).process()
