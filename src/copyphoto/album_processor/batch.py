"""Функциональный интерфейс пакетной обработки через AlbumProcessor."""

from __future__ import annotations

from copyphoto.album_processor.config import (
    DEFAULT_CROPPER_CONFIG,
    DEFAULT_ENHANCER_CONFIG,
    CropperConfig,
    DetectorConfig,
    DiagnosticsConfig,
    EnhancerConfig,
    ExportConfig,
)
from copyphoto.album_processor.processor import AlbumProcessor, BatchSummary


def process_input_directory(
    config: DetectorConfig,
    export_config: ExportConfig,
    cropper_config: CropperConfig = DEFAULT_CROPPER_CONFIG,
    enhancer_config: EnhancerConfig = DEFAULT_ENHANCER_CONFIG,
    diagnostics_config: DiagnosticsConfig | None = None,
) -> BatchSummary:
    """Запустить пакетную обработку через AlbumProcessor."""
    return AlbumProcessor(
        config,
        export_config,
        cropper_config,
        enhancer_config,
        diagnostics_config,
    ).process()
