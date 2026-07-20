from __future__ import annotations

import numpy as np
import pytest

from album_processor.config import EnhancementMode, EnhancerConfig
from album_processor.enhancer import enhance_photo


def make_low_contrast_image() -> np.ndarray:
    values = np.linspace(90, 130, 192, dtype=np.uint8)
    luminance = np.tile(values, (128, 1))
    return np.dstack(
        (
            luminance,
            np.clip(luminance + 4, 0, 255).astype(np.uint8),
            np.clip(luminance + 8, 0, 255).astype(np.uint8),
        )
    )


def test_no_correction_preserves_every_pixel() -> None:
    image = make_low_contrast_image()

    result = enhance_photo(
        image,
        EnhancerConfig(mode=EnhancementMode.NONE),
    )

    assert np.array_equal(result, image)
    assert result is not image
    assert not np.shares_memory(result, image)


def test_soft_correction_returns_technical_valid_image() -> None:
    image = make_low_contrast_image()

    result = enhance_photo(
        image,
        EnhancerConfig(mode=EnhancementMode.SOFT, intensity=0.25),
    )

    assert isinstance(result, np.ndarray)
    assert result.dtype == np.uint8
    assert result.shape == image.shape
    assert result.ndim == 3
    assert result.shape[2] == 3
    assert result.size > 0
    assert result.flags.c_contiguous
    assert not np.array_equal(result, image)


def test_zero_intensity_does_not_change_soft_mode_pixels() -> None:
    image = make_low_contrast_image()

    result = enhance_photo(
        image,
        EnhancerConfig(mode=EnhancementMode.SOFT, intensity=0.0),
    )

    assert np.array_equal(result, image)


def test_intensity_controls_strength_of_correction() -> None:
    image = make_low_contrast_image()
    weak = enhance_photo(
        image,
        EnhancerConfig(mode=EnhancementMode.SOFT, intensity=0.15),
    )
    strong = enhance_photo(
        image,
        EnhancerConfig(mode=EnhancementMode.SOFT, intensity=0.80),
    )

    weak_difference = np.mean(
        np.abs(weak.astype(np.int16) - image.astype(np.int16))
    )
    strong_difference = np.mean(
        np.abs(strong.astype(np.int16) - image.astype(np.int16))
    )

    assert weak_difference > 0
    assert strong_difference > weak_difference


def test_soft_correction_keeps_neutral_pixels_neutral() -> None:
    values = np.linspace(50, 210, 160, dtype=np.uint8)
    gray = np.tile(values, (120, 1))
    image = np.dstack((gray, gray, gray))

    result = enhance_photo(
        image,
        EnhancerConfig(mode=EnhancementMode.SOFT, intensity=0.25),
    )
    channel_spread = result.max(axis=2).astype(np.int16) - result.min(
        axis=2
    ).astype(np.int16)

    assert int(channel_spread.max()) <= 2


@pytest.mark.parametrize(
    "image",
    (
        np.empty((0, 10, 3), dtype=np.uint8),
        np.empty((10, 10), dtype=np.uint8),
        np.empty((10, 10, 4), dtype=np.uint8),
        np.empty((10, 10, 3), dtype=np.float32),
    ),
)
def test_rejects_technically_invalid_images(image: np.ndarray) -> None:
    with pytest.raises(ValueError):
        enhance_photo(image)


@pytest.mark.parametrize("intensity", (-0.01, 1.01))
def test_rejects_invalid_intensity(intensity: float) -> None:
    with pytest.raises(ValueError, match="интенсивность"):
        EnhancerConfig(intensity=intensity)
