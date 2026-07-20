from __future__ import annotations

import cv2
import numpy as np

from album_processor.config import (
    DEFAULT_ENHANCER_CONFIG,
    EnhancementMode,
    EnhancerConfig,
)


def _validate_image(image: np.ndarray) -> None:
    if image.ndim != 3 or image.shape[2] != 3:
        raise ValueError("enhance_photo ожидает трёхканальное изображение BGR")
    if image.shape[0] == 0 or image.shape[1] == 0:
        raise ValueError("enhance_photo не может обработать пустое изображение")
    if image.dtype != np.uint8:
        raise ValueError("enhance_photo ожидает изображение с типом uint8")


def _soft_enhancement(image: np.ndarray, config: EnhancerConfig) -> np.ndarray:
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
    _validate_image(image)
    if config.mode is EnhancementMode.NONE:
        return np.ascontiguousarray(image.copy())
    if config.mode is EnhancementMode.SOFT:
        return _soft_enhancement(image, config)
    raise ValueError("задан неподдерживаемый режим коррекции")
