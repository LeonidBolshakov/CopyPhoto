from __future__ import annotations

from album_processor.config import (
    DEFAULT_CROPPER_CONFIG,
    DEFAULT_ENHANCER_CONFIG,
    CropperConfig,
    DetectorConfig,
    DiagnosticsConfig,
    EnhancerConfig,
    ExportConfig,
)
from album_processor.processor import AlbumProcessor, BatchSummary


def process_input_directory(
    config: DetectorConfig,
    export_config: ExportConfig,
    cropper_config: CropperConfig = DEFAULT_CROPPER_CONFIG,
    enhancer_config: EnhancerConfig = DEFAULT_ENHANCER_CONFIG,
    diagnostics_config: DiagnosticsConfig | None = None,
) -> BatchSummary:
    """Совместимый функциональный интерфейс пакетной обработки."""
    return AlbumProcessor(
        config,
        export_config,
        cropper_config,
        enhancer_config,
        diagnostics_config,
    ).process()
