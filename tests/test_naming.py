"""Тесты формирования имён и продолжения нумерации результатов."""

from pathlib import Path

import pytest

from album_processor.config import ExportConfig
from album_processor.naming import (
    find_next_output_index,
    format_output_name,
    next_version_path,
    output_path,
)


def test_formats_output_name_with_prefix_and_leading_zeroes() -> None:
    assert format_output_name("album", 7, 4) == "album_0007.jpg"
    assert format_output_name("album", 12345, 4) == "album_12345.jpg"
    assert format_output_name("album", 7, 4, ".png") == "album_0007.png"


def test_finds_next_index_without_reusing_existing_names(tmp_path: Path) -> None:
    config = ExportConfig(
        output_dir=tmp_path,
        filename_prefix="scan",
        filename_digits=3,
    )
    (tmp_path / "scan_002.jpg").touch()
    (tmp_path / "SCAN_009.JPG").touch()
    (tmp_path / "other_100.jpg").touch()
    (tmp_path / "scan_bad.jpg").touch()

    next_index = find_next_output_index(config)

    assert next_index == 10
    assert output_path(config, next_index) == tmp_path / "scan_010.jpg"


def test_rejects_invalid_export_settings(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Качество JPEG"):
        ExportConfig(output_dir=tmp_path, jpeg_quality=101)
    with pytest.raises(ValueError, match="запрещённый символ"):
        ExportConfig(output_dir=tmp_path, filename_prefix="album*")
    with pytest.raises(ValueError, match="Формат"):
        ExportConfig(output_dir=tmp_path, output_format="gif")


def test_removes_spaces_around_filename_prefix(tmp_path: Path) -> None:
    config = ExportConfig(
        output_dir=tmp_path,
        filename_prefix="  family album  ",
    )

    assert config.filename_prefix == "family album"
    assert output_path(config, 1) == tmp_path / "family album_0001.jpg"


def test_allows_dot_at_end_of_filename_prefix(tmp_path: Path) -> None:
    config = ExportConfig(output_dir=tmp_path, filename_prefix="photo.")

    assert output_path(config, 1) == tmp_path / "photo._0001.jpg"


def test_treats_jpg_output_format_as_jpeg(tmp_path: Path) -> None:
    config = ExportConfig(output_dir=tmp_path, output_format="jpg")

    assert config.output_format == "jpeg"
    assert config.file_extension == ".jpg"


def test_rejects_filename_prefix_containing_only_spaces(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="после удаления пробелов"):
        ExportConfig(output_dir=tmp_path, filename_prefix="   ")


def test_png_numbering_is_independent_from_jpeg(tmp_path: Path) -> None:
    config = ExportConfig(
        output_dir=tmp_path,
        filename_prefix="scan",
        output_format="png",
    )
    (tmp_path / "scan_009.jpg").touch()
    (tmp_path / "scan_003.png").touch()

    assert find_next_output_index(config) == 4
    assert output_path(config, 4) == tmp_path / "scan_0004.png"


def test_version_path_preserves_free_name(tmp_path: Path) -> None:
    original = tmp_path / "photo_0001.jpg"

    assert next_version_path(original) == original


def test_version_path_continues_versions_of_same_name(tmp_path: Path) -> None:
    (tmp_path / "photo_0001.jpg").touch()
    (tmp_path / "photo_0001_2.jpg").touch()
    (tmp_path / "photo_0001_4.jpg").touch()
    (tmp_path / "photo_0002_9.jpg").touch()

    assert next_version_path(tmp_path / "photo_0001.jpg") == (
        tmp_path / "photo_0001_5.jpg"
    )
