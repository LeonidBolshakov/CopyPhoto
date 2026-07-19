from pathlib import Path

import cv2
import numpy as np

from album_processor.config import DetectorConfig
from album_processor.detector import detect_photos


def make_config(tmp_path: Path) -> DetectorConfig:
    return DetectorConfig(
        input_dir=tmp_path / "input",
        debug_dir=tmp_path / "debug",
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
