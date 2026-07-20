from pathlib import Path

from album_processor.config import DetectorConfig, ExportConfig


PROJECT_DIR = Path(__file__).resolve().parent

INPUT_DIR = PROJECT_DIR / "input"
DEBUG_DIR = PROJECT_DIR / "debug"
OUTPUT_DIR = PROJECT_DIR / "output"

CONFIG = DetectorConfig(
    input_dir=INPUT_DIR,
    debug_dir=DEBUG_DIR,
)

EXPORT_CONFIG = ExportConfig(
    output_dir=OUTPUT_DIR,
    output_format="png",  # Допустимые значения: "jpeg" и "png".
)
