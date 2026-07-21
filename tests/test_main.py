"""Тесты русского консольного представления отчётов и ошибок настроек."""

from pathlib import Path

import pytest

import main as main_module
from album_processor.detector import (
    ContourRejectionReason,
    DetectionWarning,
    DetectionWarningCode,
)
from album_processor.processor import RejectionCount, SourceProcessingReport
from main import _print_source_report
from album_processor.settings import SettingsError


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
