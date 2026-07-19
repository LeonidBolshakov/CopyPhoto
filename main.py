from album_processor.batch import process_input_directory
from settings import CONFIG


def main() -> int:
    print("CopyPhoto: диагностический OpenCV-детектор")
    print(f"Входная папка: {CONFIG.input_dir}")
    print(f"Диагностика:   {CONFIG.debug_dir}")

    summary = process_input_directory(CONFIG)

    print()
    print(f"Обработано файлов: {summary.processed}")
    print(f"Найдено фотографий: {summary.detected_photos}")
    print(f"Ошибок: {len(summary.errors)}")
    for error in summary.errors:
        print(f"  {error}")

    return 1 if summary.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
