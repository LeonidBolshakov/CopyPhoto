from pathlib import Path

import numpy as np
import pytest

from album_processor.image_reader import iter_source_images, read_image, write_image


def test_unicode_round_trip_and_source_filtering(tmp_path: Path) -> None:
    source = tmp_path / "Альбом 1.jpg"
    expected = np.zeros((40, 60, 3), dtype=np.uint8)
    expected[:, :, 1] = 180
    write_image(source, expected, jpeg_quality=100)
    (tmp_path / "notes.txt").write_text("пропустить", encoding="utf-8")

    sources = iter_source_images(tmp_path)
    actual = read_image(source)

    assert sources == [source]
    assert actual.shape == expected.shape
    assert float(actual[:, :, 1].mean()) > 170


def test_write_image_refuses_to_overwrite_existing_file(tmp_path: Path) -> None:
    target = tmp_path / "photo.jpg"
    original = np.full((20, 30, 3), 80, dtype=np.uint8)
    replacement = np.full((20, 30, 3), 220, dtype=np.uint8)
    write_image(target, original)
    original_bytes = target.read_bytes()

    with pytest.raises(FileExistsError):
        write_image(target, replacement, overwrite=False)

    assert target.read_bytes() == original_bytes


def test_png_round_trip_preserves_pixels_exactly(tmp_path: Path) -> None:
    target = tmp_path / "photo.png"
    expected = np.arange(24 * 32 * 3, dtype=np.uint16).reshape(24, 32, 3)
    expected = (expected % 256).astype(np.uint8)

    write_image(target, expected)
    actual = read_image(target)

    assert np.array_equal(actual, expected)
