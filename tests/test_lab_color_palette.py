"""Тесты вспомогательной палитры цветовых расстояний LAB."""

from pathlib import Path

from PIL import Image

from lab_color_palette import create_lab_palette, generate_color_samples


def test_generates_displayable_colors_near_requested_distances() -> None:
    requested = (14.0, 18.0, 32.0, 80.0)

    samples = generate_color_samples(distances=requested)

    assert len(samples) == len(requested) + 1
    for sample, distance in zip(samples, requested):
        assert sample.requested_distance == distance
        assert abs(sample.actual_distance - distance) <= 0.5
        assert all(0 <= channel <= 255 for channel in sample.bgr)
    assert samples[-1].requested_distance is None
    assert samples[-1].actual_distance > max(requested)


def test_creates_nonempty_rgb_png(tmp_path: Path) -> None:
    output_path = tmp_path / "palette.png"

    create_lab_palette(output_path)

    with Image.open(output_path) as image:
        assert image.format == "PNG"
        assert image.mode == "RGB"
        assert image.width > 0
        assert image.height > 0
