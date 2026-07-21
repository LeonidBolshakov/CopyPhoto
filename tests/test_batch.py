"""Интеграционные тесты AlbumProcessor и совместимого пакетного интерфейса."""

from pathlib import Path

import cv2
import numpy as np
import pytest

import album_processor.processor as processor_module
from album_processor.batch import process_input_directory
from album_processor.config import (
    DetectorConfig,
    DiagnosticsConfig,
    EnhancementMode,
    EnhancerConfig,
    ExportConfig,
)
from album_processor.image_io import read_image, write_image
from album_processor.processor import AlbumProcessor


def make_detector_config(tmp_path: Path) -> DetectorConfig:
    return DetectorConfig(
        input_dir=tmp_path / "input",
        analysis_max_side=1600,
        background_distance_min=12.0,
        morph_kernel_fraction=0.006,
        min_photo_area_fraction=0.015,
        min_rectangularity=0.80,
    )


def make_export_config(
    tmp_path: Path,
    output_format: str = "jpeg",
) -> ExportConfig:
    return ExportConfig(
        output_dir=tmp_path / "output",
        filename_prefix="album",
        filename_digits=3,
        output_format=output_format,
        jpeg_quality=88,
    )


def make_source(path: Path) -> None:
    image = np.full((800, 1000, 3), (145, 125, 105), dtype=np.uint8)
    outer = cv2.boxPoints(((500, 400), (500, 340), 4.0)).astype(np.int32)
    inner = cv2.boxPoints(((500, 400), (470, 310), 4.0)).astype(np.int32)
    cv2.fillConvexPoly(image, outer, (238, 238, 238))
    cv2.fillConvexPoly(image, inner, (45, 95, 175))
    write_image(path, image)


def test_batch_creates_separate_jpeg_and_continues_numbering(tmp_path: Path) -> None:
    detector_config = make_detector_config(tmp_path)
    export_config = make_export_config(tmp_path)
    make_source(detector_config.input_dir / "Альбом.png")

    first = process_input_directory(detector_config, export_config)
    first_path = export_config.output_dir / "album_001.jpg"
    first_bytes = first_path.read_bytes()
    second = process_input_directory(detector_config, export_config)
    second_path = export_config.output_dir / "album_002.jpg"

    assert first.total_files == 1
    assert first.processed == 1
    assert first.files_with_errors == 0
    assert first.detected_photos == 1
    assert first.saved_photos == 1
    assert first.failed_photos == 0
    assert first.errors == ()
    assert first_path.exists()
    assert read_image(first_path).shape[1] > read_image(first_path).shape[0]
    assert second.saved_photos == 1
    assert second_path.exists()
    assert first_path.read_bytes() == first_bytes


def test_batch_continues_after_broken_source_file(tmp_path: Path) -> None:
    detector_config = make_detector_config(tmp_path)
    export_config = make_export_config(tmp_path)
    make_source(detector_config.input_dir / "good.png")
    (detector_config.input_dir / "broken.jpg").write_bytes(
        "это не JPEG".encode("utf-8")
    )

    summary = process_input_directory(detector_config, export_config)

    assert summary.total_files == 2
    assert summary.processed == 1
    assert summary.files_with_errors == 1
    assert summary.detected_photos == 1
    assert summary.saved_photos == 1
    assert summary.failed_photos == 0
    assert len(summary.errors) == 1
    assert "broken.jpg" in summary.errors[0]
    assert (export_config.output_dir / "album_001.jpg").exists()


def test_batch_reports_crop_error_without_stopping(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    detector_config = make_detector_config(tmp_path)
    export_config = make_export_config(tmp_path)
    make_source(detector_config.input_dir / "good.png")

    def fail_crop(*args: object, **kwargs: object) -> np.ndarray:
        raise ValueError("синтетическая ошибка кадрирования")

    monkeypatch.setattr(processor_module, "crop_photo", fail_crop)

    summary = process_input_directory(detector_config, export_config)

    assert summary.processed == 1
    assert summary.files_with_errors == 1
    assert summary.detected_photos == 1
    assert summary.saved_photos == 0
    assert summary.failed_photos == 1
    assert len(summary.errors) == 1
    assert "фото 1" in summary.errors[0]


def test_batch_can_export_lossless_png(tmp_path: Path) -> None:
    detector_config = make_detector_config(tmp_path)
    export_config = make_export_config(tmp_path, output_format="png")
    make_source(detector_config.input_dir / "good.png")

    summary = process_input_directory(detector_config, export_config)
    target = export_config.output_dir / "album_001.png"

    assert summary.saved_photos == 1
    assert target.exists()
    assert not (export_config.output_dir / "album_001.jpg").exists()
    assert read_image(target).shape[1] > read_image(target).shape[0]


def test_album_processor_returns_structured_report_without_console_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    detector_config = make_detector_config(tmp_path)
    export_config = make_export_config(tmp_path)
    make_source(detector_config.input_dir / "good.png")

    summary = AlbumProcessor(detector_config, export_config).process()

    assert capsys.readouterr().out == ""
    assert len(summary.files) == 1
    report = summary.files[0]
    assert report.source.name == "good.png"
    assert report.processed
    assert report.detected_photos == 1
    assert report.saved_photos == 1
    assert report.saved_paths[0].name == "album_001.jpg"
    assert report.distance_threshold is not None
    assert report.background_tile_coverage is not None


def test_album_processor_applies_configured_enhancement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    detector_config = make_detector_config(tmp_path)
    export_config = make_export_config(tmp_path, output_format="png")
    enhancer_config = EnhancerConfig(
        mode=EnhancementMode.SOFT,
        intensity=0.40,
    )
    make_source(detector_config.input_dir / "good.png")
    received_configs: list[EnhancerConfig] = []

    def record_enhancement(
        image: np.ndarray,
        config: EnhancerConfig,
    ) -> np.ndarray:
        received_configs.append(config)
        return image.copy()

    monkeypatch.setattr(processor_module, "enhance_photo", record_enhancement)

    summary = AlbumProcessor(
        detector_config,
        export_config,
        enhancer_config=enhancer_config,
    ).process()

    assert summary.saved_photos == 1
    assert received_configs == [enhancer_config]


def test_enabled_debug_mode_writes_diagnostic_files(tmp_path: Path) -> None:
    detector_config = make_detector_config(tmp_path)
    export_config = make_export_config(tmp_path, output_format="png")
    diagnostics_config = DiagnosticsConfig(
        output_dir=tmp_path / "diagnostics",
        enabled=True,
    )
    make_source(detector_config.input_dir / "album.png")

    summary = AlbumProcessor(
        detector_config,
        export_config,
        diagnostics_config=diagnostics_config,
    ).process()

    assert summary.saved_photos == 1
    assert (diagnostics_config.output_dir / "album_detected.jpg").exists()
    assert (diagnostics_config.output_dir / "album_mask.png").exists()


def test_disabled_debug_mode_does_not_create_diagnostic_directory(
    tmp_path: Path,
) -> None:
    detector_config = make_detector_config(tmp_path)
    export_config = make_export_config(tmp_path, output_format="png")
    diagnostics_config = DiagnosticsConfig(
        output_dir=tmp_path / "diagnostics",
        enabled=False,
    )
    make_source(detector_config.input_dir / "album.png")

    summary = AlbumProcessor(
        detector_config,
        export_config,
        diagnostics_config=diagnostics_config,
    ).process()

    assert summary.saved_photos == 1
    assert not diagnostics_config.output_dir.exists()
