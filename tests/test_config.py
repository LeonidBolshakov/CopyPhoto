"""Тесты двуязычных сообщений проверки конфигурации."""

from pathlib import Path
from typing import cast

import pytest

from album_processor.config import (
    CropperConfig,
    DetectorConfig,
    DiagnosticsConfig,
    EnhancerConfig,
    ExportConfig,
)


def assert_parameter_error(
    error: pytest.ExceptionInfo[ValueError],
    russian_name: str,
    english_name: str,
) -> None:
    """Проверить наличие понятного назначения и имени поля для поиска."""
    message = str(error.value)
    assert russian_name in message
    assert f"({english_name})" in message


def test_cropper_error_contains_both_parameter_names() -> None:
    with pytest.raises(ValueError) as error:
        CropperConfig(safety_margin_pixels=-1)

    assert_parameter_error(error, "Запас вокруг рамки", "safety_margin_pixels")


def test_enhancer_error_contains_both_parameter_names() -> None:
    with pytest.raises(ValueError) as error:
        EnhancerConfig(intensity=1.1)

    assert_parameter_error(error, "Интенсивность коррекции", "intensity")


def test_export_error_contains_both_parameter_names(tmp_path: Path) -> None:
    with pytest.raises(ValueError) as error:
        ExportConfig(output_dir=tmp_path, filename_digits=0)

    assert_parameter_error(error, "Количество цифр", "filename_digits")


def test_detector_error_contains_both_parameter_names(tmp_path: Path) -> None:
    with pytest.raises(ValueError) as error:
        DetectorConfig(input_dir=tmp_path, background_border_fraction=0.0)

    assert_parameter_error(
        error,
        "Доля края для оценки фона",
        "background_border_fraction",
    )


def test_detector_reports_aspect_ratio_below_one(tmp_path: Path) -> None:
    with pytest.raises(ValueError) as error:
        DetectorConfig(input_dir=tmp_path, min_aspect_ratio=0.9)

    assert_parameter_error(
        error,
        "Минимальное соотношение сторон",
        "min_aspect_ratio",
    )
    assert "получено 0.9" in str(error.value)


def test_detector_reports_reversed_aspect_ratio_limits(tmp_path: Path) -> None:
    with pytest.raises(ValueError) as error:
        DetectorConfig(
            input_dir=tmp_path,
            min_aspect_ratio=1.6,
            max_aspect_ratio=1.5,
        )

    message = str(error.value)
    assert "(min_aspect_ratio)" in message
    assert "(max_aspect_ratio)" in message
    assert "получено соответственно 1.6 и 1.5" in message


def test_diagnostics_error_contains_both_parameter_names(tmp_path: Path) -> None:
    with pytest.raises(ValueError) as error:
        DiagnosticsConfig(output_dir=tmp_path, enabled=cast(bool, 1))

    assert_parameter_error(error, "Режим отладки", "enabled")
