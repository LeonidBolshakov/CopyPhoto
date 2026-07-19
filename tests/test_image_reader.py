from pathlib import Path

import numpy as np

from album_processor.image_reader import iter_source_images, read_image, write_image


def test_unicode_round_trip_and_source_filtering(tmp_path: Path) -> None:
    source = tmp_path / "Альбом 1.jpg"
    expected = np.zeros((40, 60, 3), dtype=np.uint8)
    expected[:, :, 1] = 180
    write_image(source, expected, jpeg_quality=100)
    (tmp_path / "notes.txt").write_text("ignored", encoding="utf-8")

    sources = iter_source_images(tmp_path)
    actual = read_image(source)

    assert sources == [source]
    assert actual.shape == expected.shape
    assert float(actual[:, :, 1].mean()) > 170
