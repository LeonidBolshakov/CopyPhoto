from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pillow_heif
from PIL import Image, ImageOps


pillow_heif.register_heif_opener()

SUPPORTED_EXTENSIONS = frozenset({".heic", ".heif", ".jpg", ".jpeg", ".png"})


def iter_source_images(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )


def read_image(path: Path) -> np.ndarray:
    """Прочитать HEIC/JPEG/PNG, применить EXIF-ориентацию и вернуть пиксели BGR."""
    with Image.open(path) as opened:
        rgb = ImageOps.exif_transpose(opened).convert("RGB")
        pixels = np.asarray(rgb)
    return cv2.cvtColor(pixels, cv2.COLOR_RGB2BGR)


def write_image(
    path: Path,
    image: np.ndarray,
    jpeg_quality: int = 92,
    *,
    overwrite: bool = True,
) -> None:
    """Записать изображение через imencode с поддержкой кириллицы в пути Windows."""
    path.parent.mkdir(parents=True, exist_ok=True)
    extension = path.suffix.lower()
    parameters: list[int] = []
    if extension in {".jpg", ".jpeg"}:
        parameters = [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality]
    success, encoded = cv2.imencode(extension, image, parameters)
    if not success:
        raise OSError(f"OpenCV не смог закодировать файл {path.name}")
    mode = "wb" if overwrite else "xb"
    with path.open(mode) as stream:
        stream.write(encoded.tobytes())
