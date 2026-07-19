from pathlib import Path

from album_processor.config import DetectorConfig


PROJECT_DIR = Path(__file__).resolve().parent

INPUT_DIR = PROJECT_DIR / "input"
DEBUG_DIR = PROJECT_DIR / "debug"

CONFIG = DetectorConfig(
    input_dir=INPUT_DIR,
    debug_dir=DEBUG_DIR,
)
