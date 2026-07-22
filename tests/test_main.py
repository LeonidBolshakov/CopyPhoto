"""Тесты русского консольного представления отчётов и ошибок настроек."""

from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

import copyphoto_cli as main_module
from album_processor.detector import (
    ContourRejectionReason,
    DetectionWarning,
    DetectionWarningCode,
)
from album_processor.config import DiagnosticsConfig
from album_processor.processor import (
    AlbumProcessor,
    BatchSummary,
    RejectionCount,
    SourceProcessingReport,
)
from album_processor.settings import ApplicationSettings, SettingsError
from copyphoto_cli import _print_source_report


def test_console_report_explains_rejections_and_warnings(
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = SourceProcessingReport(
        source=Path("альбом.png"),
        processed=True,
        detected_photos=1,
        saved_paths=(Path("photo_0001.png"),),
        failed_photos=0,
        rejection_counts=(
            RejectionCount(
                reason=ContourRejectionReason.LOW_RECTANGULARITY,
                count=2,
                example="прямоугольность 0.620, требуется не меньше 0.800",
            ),
        ),
        warnings=(
            DetectionWarning(
                code=DetectionWarningCode.LOW_BACKGROUND_COVERAGE,
                message="фон определён ненадёжно",
                recommendation="освободите края кадра",
            ),
        ),
        distance_threshold=24.5,
        background_tile_coverage=0.42,
        errors=(),
    )

    _print_source_report(report)
    output = capsys.readouterr().out

    assert "Отклонено контуров: 2" in output
    assert "контур недостаточно прямоугольный: 2" in output
    assert "прямоугольность 0.620" in output
    assert "ПРЕДУПРЕЖДЕНИЕ — неоднозначный фон" in output
    assert "освободите края кадра" in output


def test_console_reports_settings_error_without_starting_processing(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail_loading() -> None:
        raise SettingsError("синтетическая ошибка параметра")

    monkeypatch.setattr(main_module, "load_settings", fail_loading)

    exit_code = main_module.main()
    output = capsys.readouterr().out

    assert exit_code == 2
    assert "CopyPhoto: ошибка настроек" in output
    assert "синтетическая ошибка параметра" in output


@pytest.mark.parametrize("debug_enabled", [False, True])
def test_main_prints_source_details_only_in_debug_mode(
    debug_enabled: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = SourceProcessingReport(
        source=Path("альбом.png"),
        processed=True,
        detected_photos=1,
        saved_paths=(Path("photo_0001.png"),),
        failed_photos=0,
        rejection_counts=(),
        warnings=(),
        distance_threshold=24.5,
        background_tile_coverage=0.42,
        errors=(),
    )
    summary = BatchSummary(
        total_files=1,
        processed=1,
        files_with_errors=0,
        detected_photos=1,
        saved_photos=1,
        failed_photos=0,
        errors=(),
        files=(report,),
    )
    settings = cast(
        ApplicationSettings,
        SimpleNamespace(
            diagnostics_config=DiagnosticsConfig(
                output_dir=tmp_path / "debug",
                enabled=debug_enabled,
            )
        ),
    )
    processor = cast(
        AlbumProcessor,
        SimpleNamespace(process=lambda: summary),
    )

    monkeypatch.setattr(main_module, "load_settings", lambda: settings)
    monkeypatch.setattr(main_module, "_print_application_settings", lambda _: None)
    monkeypatch.setattr(main_module, "_create_processor", lambda _: processor)

    exit_code = main_module.main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert ("альбом.png: найдено 1, сохранено 1/1" in output) is debug_enabled
    assert ("Сохранено: photo_0001.png" in output) is debug_enabled
    assert "Итоговая статистика" in output
    assert "Сохранено фотографий: 1" in output
