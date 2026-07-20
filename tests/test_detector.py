from pathlib import Path

import cv2
import numpy as np

from album_processor.config import DetectorConfig
from album_processor.detector import (
    ContourRejectionReason,
    DetectionWarningCode,
    detect_photos,
)


def make_config(tmp_path: Path) -> DetectorConfig:
    return DetectorConfig(
        input_dir=tmp_path / "input",
        analysis_max_side=1600,
        background_distance_min=12.0,
        morph_kernel_fraction=0.006,
        min_photo_area_fraction=0.015,
        min_rectangularity=0.80,
    )


def draw_photo(
    image: np.ndarray, center: tuple[int, int], size: tuple[int, int], angle: float
) -> None:
    outer = cv2.boxPoints((center, size, angle)).astype(np.int32)
    cv2.fillConvexPoly(image, outer, (238, 238, 238))

    inner_size = (max(1, size[0] - 28), max(1, size[1] - 28))
    inner = cv2.boxPoints((center, inner_size, angle)).astype(np.int32)
    color = (45 + center[0] % 80, 70 + center[1] % 80, 155)
    cv2.fillConvexPoly(image, inner, color)


def test_detects_separated_slightly_rotated_photos(tmp_path: Path) -> None:
    image = np.full((1200, 1600, 3), (145, 125, 105), dtype=np.uint8)
    draw_photo(image, (370, 350), (430, 290), 5.0)
    draw_photo(image, (1120, 360), (360, 520), -4.0)
    draw_photo(image, (760, 880), (560, 360), 7.0)

    result = detect_photos(image, make_config(tmp_path))

    assert len(result.detections) == 3
    assert all(abs(item.angle) <= 8 for item in result.detections)


def test_blank_background_has_no_detections(tmp_path: Path) -> None:
    image = np.full((900, 1200, 3), (145, 125, 105), dtype=np.uint8)

    result = detect_photos(image, make_config(tmp_path))

    assert result.detections == ()
    assert any(
        warning.code is DetectionWarningCode.NO_PHOTOS
        for warning in result.warnings
    )


def test_background_estimation_ignores_contaminated_border_tiles(
    tmp_path: Path,
) -> None:
    background_bgr = (145, 125, 105)
    image = np.full((900, 1200, 3), background_bgr, dtype=np.uint8)
    draw_photo(image, (600, 450), (500, 340), 3.0)

    # Имитируем стол справа и посторонний предмет вдоль верхнего края.
    image[:, -90:] = (35, 45, 70)
    image[:70, :300] = (210, 65, 35)

    result = detect_photos(image, make_config(tmp_path))
    expected_lab = cv2.cvtColor(
        np.asarray([[background_bgr]], dtype=np.uint8), cv2.COLOR_BGR2LAB
    )[0, 0]

    assert len(result.detections) == 1
    assert np.linalg.norm(np.asarray(result.background_lab) - expected_lab) < 3
    assert result.background_tile_coverage >= 0.50
    assert result.background_warning is None


def test_warns_when_no_background_colour_dominates_border(tmp_path: Path) -> None:
    image = np.empty((800, 1000, 3), dtype=np.uint8)
    image[:400, :500] = (15, 15, 15)
    image[:400, 500:] = (245, 245, 245)
    image[400:, :500] = (20, 30, 210)
    image[400:, 500:] = (210, 40, 30)

    result = detect_photos(image, make_config(tmp_path))

    assert result.background_tile_coverage < 0.50
    assert result.background_warning is not None
    assert "периметра" in result.background_warning
    assert all(warning.recommendation for warning in result.warnings)


def test_reports_reasons_for_rejected_contours(tmp_path: Path) -> None:
    image = np.full((800, 1000, 3), (145, 125, 105), dtype=np.uint8)
    draw_photo(image, (250, 400), (100, 80), 0.0)
    draw_photo(image, (650, 400), (400, 100), 0.0)

    result = detect_photos(image, make_config(tmp_path))
    reasons = {rejection.reason for rejection in result.rejections}

    assert ContourRejectionReason.AREA_TOO_SMALL in reasons
    assert ContourRejectionReason.INVALID_ASPECT_RATIO in reasons
    assert all(rejection.details for rejection in result.rejections)
    assert all(
        np.all(
            (rejection.normalized_contour >= 0.0)
            & (rejection.normalized_contour <= 1.0)
        )
        for rejection in result.rejections
    )
