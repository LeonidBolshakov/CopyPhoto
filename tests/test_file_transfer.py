"""Проверки безопасного переноса фотографий в итоговый каталог."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from copyphoto.file_transfer import move_files_to_final, transfer_prefix


def test_ready_transfer_does_not_overwrite_existing_files(
    tmp_path: Path,
) -> None:
    source_directory = tmp_path / "output"
    final_directory = tmp_path / "final"
    source_directory.mkdir()
    final_directory.mkdir()
    movable = source_directory / "photo_0001.jpg"
    movable.write_text("new", encoding="utf-8")
    source_png = source_directory / "photo_0002.png"
    source_png.write_text("source", encoding="utf-8")
    existing_jpeg = final_directory / "photo_0001.jpg"
    existing_png = final_directory / "photo_0001.png"
    existing_jpeg.write_text("existing jpg", encoding="utf-8")
    existing_png.write_text("existing png", encoding="utf-8")

    result = move_files_to_final(
        [movable, source_png],
        source_directory.resolve(),
        final_directory.resolve(),
        "",
        version_collisions=True,
    )

    assert result.moved == 2
    assert result.failures == []
    assert not movable.exists()
    assert not source_png.exists()
    assert (final_directory / "photo_0001_2.jpg").read_text(
        encoding="utf-8"
    ) == "new"
    assert (final_directory / "photo_0002.png").read_text(
        encoding="utf-8"
    ) == "source"
    assert existing_jpeg.read_text(encoding="utf-8") == "existing jpg"
    assert existing_png.read_text(encoding="utf-8") == "existing png"


def test_transfer_prefix_uses_source_and_start_time() -> None:
    started_at = datetime(2026, 7, 22, 14, 35)

    assert transfer_prefix("В", started_at) == "В26-07-22-14-35_"


def test_ready_transfer_adds_version_to_each_colliding_name(
    tmp_path: Path,
) -> None:
    source_directory = tmp_path / "output"
    final_directory = tmp_path / "final"
    source_directory.mkdir()
    final_directory.mkdir()
    for index in range(1, 5):
        name = f"photo_{index:05d}.jpg"
        (source_directory / name).write_text(f"new {index}", encoding="utf-8")
        (final_directory / name).write_text(f"old {index}", encoding="utf-8")
    sources = sorted(source_directory.glob("*.jpg"))

    result = move_files_to_final(
        sources,
        source_directory.resolve(),
        final_directory.resolve(),
        "",
        version_collisions=True,
    )

    assert result.moved == 4
    assert result.failures == []
    assert not list(source_directory.glob("*.jpg"))
    for index in range(1, 5):
        assert (final_directory / f"photo_{index:05d}_2.jpg").is_file()


def test_ready_transfer_preserves_free_source_name(tmp_path: Path) -> None:
    source_directory = tmp_path / "output"
    final_directory = tmp_path / "final"
    source_directory.mkdir()
    final_directory.mkdir()
    source = source_directory / "photo_0007.jpg"
    source.write_text("source", encoding="utf-8")

    result = move_files_to_final(
        [source],
        source_directory.resolve(),
        final_directory.resolve(),
        "",
        version_collisions=True,
    )

    assert result.moved == 1
    assert result.failures == []
    assert (final_directory / "photo_0007.jpg").read_text(
        encoding="utf-8"
    ) == "source"
    assert not (final_directory / "photo_0001.jpg").exists()


def test_ready_transfer_continues_versions_of_colliding_name(
    tmp_path: Path,
) -> None:
    source_directory = tmp_path / "output"
    final_directory = tmp_path / "final"
    source_directory.mkdir()
    final_directory.mkdir()
    colliding = source_directory / "photo_0001.jpg"
    colliding.write_text("version 3", encoding="utf-8")
    (final_directory / "photo_0001.jpg").write_text("existing", encoding="utf-8")
    (final_directory / "photo_0001_2.jpg").write_text(
        "version 2", encoding="utf-8"
    )

    result = move_files_to_final(
        [colliding],
        source_directory.resolve(),
        final_directory.resolve(),
        "",
        version_collisions=True,
    )

    assert result.moved == 1
    assert result.failures == []
    assert (final_directory / "photo_0001_3.jpg").read_text(
        encoding="utf-8"
    ) == "version 3"
