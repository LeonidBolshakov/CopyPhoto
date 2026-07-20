from album_processor.batch import process_input_directory
from settings import CONFIG, EXPORT_CONFIG


def main() -> int:
    print("CopyPhoto: пакетное выделение бумажных фотографий")
    print(f"Входная папка: {CONFIG.input_dir}")
    print(f"Результаты:     {EXPORT_CONFIG.output_dir}")
    print(f"Диагностика:   {CONFIG.debug_dir}")
    if EXPORT_CONFIG.output_format == "jpeg":
        format_description = f"JPEG, качество {EXPORT_CONFIG.jpeg_quality}"
    else:
        format_description = "PNG без потерь"
    print(
        f"Имена:          {EXPORT_CONFIG.filename_prefix}_*"
        f"{EXPORT_CONFIG.file_extension}, {format_description}"
    )

    summary = process_input_directory(CONFIG, EXPORT_CONFIG)

    print()
    print(f"Входных файлов: {summary.total_files}")
    print(f"Обработано файлов: {summary.processed}")
    print(f"Файлов с ошибками: {summary.files_with_errors}")
    print(f"Найдено фотографий: {summary.detected_photos}")
    print(f"Сохранено фотографий: {summary.saved_photos}")
    print(f"Ошибок фотографий: {summary.failed_photos}")
    print(f"Ошибок: {len(summary.errors)}")
    for error in summary.errors:
        print(f"  {error}")

    return 1 if summary.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
