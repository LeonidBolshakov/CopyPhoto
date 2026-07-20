from album_processor.config import EnhancementMode
from album_processor.processor import (
    AlbumProcessor,
    BatchSummary,
    SourceProcessingReport,
)
from settings import CONFIG, ENHANCER_CONFIG, EXPORT_CONFIG


def _print_source_report(report: SourceProcessingReport) -> None:
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
    print()
    print("Итоговая статистика")
    print(f"Входных файлов: {summary.total_files}")
    print(f"Обработано файлов: {summary.processed}")
    print(f"Файлов с ошибками: {summary.files_with_errors}")
    print(f"Найдено фотографий: {summary.detected_photos}")
    print(f"Сохранено фотографий: {summary.saved_photos}")
    print(f"Ошибок фотографий: {summary.failed_photos}")
    print(f"Всего ошибок: {len(summary.errors)}")


def main() -> int:
    print("CopyPhoto: пакетное выделение бумажных фотографий")
    print(f"Входная папка: {CONFIG.input_dir}")
    print(f"Результаты:     {EXPORT_CONFIG.output_dir}")
    print(f"Диагностика:    {CONFIG.debug_dir}")
    if EXPORT_CONFIG.output_format == "jpeg":
        format_description = f"JPEG, качество {EXPORT_CONFIG.jpeg_quality}"
    else:
        format_description = "PNG без потерь"
    print(
        f"Имена:          {EXPORT_CONFIG.filename_prefix}_*"
        f"{EXPORT_CONFIG.file_extension}, {format_description}"
    )
    correction_description = ENHANCER_CONFIG.mode.value
    if ENHANCER_CONFIG.mode is EnhancementMode.SOFT:
        correction_description += f", интенсивность {ENHANCER_CONFIG.intensity:.0%}"
    print(f"Коррекция:      {correction_description}")
    print()

    summary = AlbumProcessor(
        CONFIG,
        EXPORT_CONFIG,
        enhancer_config=ENHANCER_CONFIG,
    ).process()
    if not summary.files:
        print("Во входной папке нет поддерживаемых изображений.")
    for report in summary.files:
        _print_source_report(report)

    _print_summary(summary)
    return 1 if summary.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
