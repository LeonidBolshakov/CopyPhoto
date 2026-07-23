"""Первичная коррекция яркостного контраста вырезанных фотографий."""

from __future__ import annotations

import cv2
import numpy as np

from copyphoto.album_processor.config import (
    DEFAULT_ENHANCER_CONFIG,
    EnhancementMode,
    EnhancerConfig,
)
from copyphoto.album_processor.image_validation import validate_bgr_image


def _soft_enhancement(image: np.ndarray, config: EnhancerConfig) -> np.ndarray:
    """Мягко смешать исходную яркость с результатом локального CLAHE."""
    if config.intensity == 0:
        return np.ascontiguousarray(image.copy())

    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    luminance = lab[:, :, 0]
    clahe = cv2.createCLAHE(
        clipLimit=config.clahe_clip_limit,
        tileGridSize=(
            config.clahe_tile_grid_size,
            config.clahe_tile_grid_size,
        ),
    )
    corrected_luminance = clahe.apply(luminance)
    lab[:, :, 0] = cv2.addWeighted(
        luminance,
        1.0 - config.intensity,
        corrected_luminance,
        config.intensity,
        0.0,
    )
    return np.ascontiguousarray(cv2.cvtColor(lab, cv2.COLOR_LAB2BGR))


def enhance_photo(
    image: np.ndarray,
    config: EnhancerConfig = DEFAULT_ENHANCER_CONFIG,
) -> np.ndarray:
    """Выполняет выбранную первичную коррекцию фотографии."""
    validate_bgr_image(image, "enhance_photo")
    if config.mode is EnhancementMode.NONE:
        return np.ascontiguousarray(image.copy())
    if config.mode is EnhancementMode.SOFT:
        return _soft_enhancement(image, config)
    raise ValueError("задан неподдерживаемый режим коррекции")
