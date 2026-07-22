"""Консольный интерфейс CopyPhoto и форматирование отчётов обработки."""

from album_processor.config import EnhancementMode
from album_processor.processor import (
    AlbumProcessor,
    BatchSummary,
    SourceProcessingReport,
)
from album_processor.settings import (
    ApplicationSettings,
    SETTINGS_PATH,
    SettingsError,
    load_settings,
)


def _print_source_report(report: SourceProcessingReport) -> None:
    """Вывести результат обработки одного исходного изображения."""
    if not report.processed:
        print(f"{report.source.name}: обработать не удалось")
    else:
        print(
            f"{report.source.name}: найдено {report.detected_photos}, "
            f"сохранено {report.saved_photos}/{report.detected_photos}"
        )
        if (
            report.distance_threshold is not None
            and report.background_tile_coverage is not None
        ):
            print(
                f"  Фон: порог {report.distance_threshold:.1f}, "
                f"покрытие периметра {report.background_tile_coverage:.0%}"
            )
        for saved_path in report.saved_paths:
            print(f"  Сохранено: {saved_path.name}")

        rejected_total = sum(item.count for item in report.rejection_counts)
        if rejected_total:
            print(f"  Отклонено контуров: {rejected_total}")
            for item in report.rejection_counts:
                print(
                    f"    {item.reason.value}: {item.count} "
                    f"(пример: {item.example})"
                )

        for warning in report.warnings:
            print(f"  ПРЕДУПРЕЖДЕНИЕ — {warning.code.value}: {warning.text}")

    for error in report.errors:
        print(f"  ОШИБКА: {error}")


def _print_summary(summary: BatchSummary) -> None:
    """Вывести итоговую статистику пакетной обработки."""
    print()
    print("Итоговая статистика")
    print(f"Входных файлов: {summary.total_files}")
    print(f"Обработано файлов: {summary.processed}")
    print(f"Файлов с ошибками: {summary.files_with_errors}")
    print(f"Найдено фотографий: {summary.detected_photos}")
    print(f"Сохранено фотографий: {summary.saved_photos}")
    print(f"Ошибок фотографий: {summary.failed_photos}")
    print(f"Всего ошибок: {len(summary.errors)}")


def _print_application_settings(settings: ApplicationSettings) -> None:
    """Вывести каталоги, формат и активные параметры обработки."""
    detector_config = settings.detector_config
    cropper_config = settings.cropper_config
    enhancer_config = settings.enhancer_config
    export_config = settings.export_config
    diagnostics_config = settings.diagnostics_config

    print("CopyPhoto: пакетное выделение бумажных фотографий")
    print(f"Настройки:      {SETTINGS_PATH}")
    print(f"Входная папка:  {detector_config.input_dir}")
    print(f"Результаты:     {export_config.output_dir}")
    print(f"Итоговые:       {settings.final_directory}")
    if diagnostics_config.enabled:
        print(f"Диагностика:    включена, {diagnostics_config.output_dir}")
    else:
        print("Диагностика:    отключена")
    if export_config.output_format == "jpeg":
        format_description = f"JPEG, качество {export_config.jpeg_quality}"
    else:
        format_description = "PNG без потерь"
    print(
        f"Имена:          {export_config.filename_prefix}_*"
        f"{export_config.file_extension}, {format_description}"
    )
    orientation_description = (
        "портретные поворачиваются в альбомные"
        if cropper_config.rotate_portrait_to_landscape
        else "положение бумажной фотографии сохраняется"
    )
    print(f"Ориентация:     {orientation_description}")
    correction_description = enhancer_config.mode.value
    if enhancer_config.mode is EnhancementMode.SOFT:
        correction_description += f", интенсивность {enhancer_config.intensity:.0%}"
    print(f"Коррекция:      {correction_description}")
    print()


def _create_processor(settings: ApplicationSettings) -> AlbumProcessor:
    """Создать AlbumProcessor из проверенных конфигураций приложения."""
    return AlbumProcessor(
        settings.detector_config,
        settings.export_config,
        cropper_config=settings.cropper_config,
        enhancer_config=settings.enhancer_config,
        diagnostics_config=settings.diagnostics_config,
    )


def main() -> int:
    """Загрузить настройки, выполнить обработку и вернуть код завершения."""
    try:
        application_settings = load_settings()
    except SettingsError as error:
        print("CopyPhoto: ошибка настроек")
        print(f"Файл: {SETTINGS_PATH}")
        print(f"Причина: {error}")
        return 2

    _print_application_settings(application_settings)
    summary = _create_processor(application_settings).process()
    if not summary.files:
        print("Во входной папке нет поддерживаемых изображений.")
    if application_settings.diagnostics_config.enabled:
        for report in summary.files:
            _print_source_report(report)

    _print_summary(summary)
    return 1 if summary.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
