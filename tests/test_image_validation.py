"""Тесты общего технического контракта BGR-изображений."""

from typing import cast

import numpy as np
import pytest

from copyphoto.album_processor.image_validation import validate_bgr_image


def test_accepts_nonempty_three_channel_uint8_image() -> None:
    image = np.zeros((10, 20, 3), dtype=np.uint8)

    validate_bgr_image(image, "test_operation")


@pytest.mark.parametrize(
    ("image", "expected_text"),
    (
        (np.empty((10, 20), dtype=np.uint8), "(высота, ширина, 3)"),
        (np.empty((10, 20, 4), dtype=np.uint8), "(высота, ширина, 3)"),
        (np.empty((0, 20, 3), dtype=np.uint8), "ширину и высоту больше 0"),
        (np.empty((10, 0, 3), dtype=np.uint8), "ширину и высоту больше 0"),
        (np.empty((10, 20, 3), dtype=np.float32), "тип пикселей uint8"),
    ),
)
def test_reports_violated_image_requirement(
    image: np.ndarray,
    expected_text: str,
) -> None:
    with pytest.raises(ValueError) as error:
        validate_bgr_image(image, "test_operation")

    message = str(error.value)
    assert "test_operation" in message
    assert expected_text in message


def test_reports_value_that_is_not_numpy_array() -> None:
    value = cast(np.ndarray, [[0, 0, 0]])

    with pytest.raises(ValueError, match="массив NumPy"):
        validate_bgr_image(value, "test_operation")
