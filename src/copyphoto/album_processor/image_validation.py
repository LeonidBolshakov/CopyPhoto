"""Общая проверка технического формата изображений CopyPhoto."""

from __future__ import annotations

import numpy as np


def validate_bgr_image(image: np.ndarray, operation: str) -> None:
    """Проверить тип массива, форму, размер и тип пикселей BGR-изображения."""
    if not isinstance(image, np.ndarray):
        raise ValueError(
            f"Функция «{operation}» ожидает массив NumPy; "
            f"получен тип {type(image).__name__}"
        )
    if image.ndim != 3 or image.shape[2] != 3:
        raise ValueError(
            f"Функция «{operation}» ожидает форму "
            f"(высота, ширина, 3); получена форма {image.shape}"
        )
    if image.shape[0] <= 0 or image.shape[1] <= 0:
        raise ValueError(
            f"Функция «{operation}» ожидает ширину и высоту больше 0; "
            f"получена форма {image.shape}"
        )
    if image.dtype != np.uint8:
        raise ValueError(
            f"Функция «{operation}» ожидает тип пикселей uint8; "
            f"получен тип {image.dtype}"
        )
