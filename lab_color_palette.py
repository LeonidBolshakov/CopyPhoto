r"""Вспомогательное построение палитры цветовых расстояний LAB.

Модуль предназначен только для изучения порогов цветового расстояния.
В работе основной программы CopyPhoto он не участвует и другими модулями
приложения не импортируется.

Запуск из каталога проекта::

    .\.venv\Scripts\python.exe -m lab_color_palette

Результат сохраняется в ``debug/lab_color_distances.png``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from PIL.ImageFont import FreeTypeFont, ImageFont as PillowImageFont


DEFAULT_OUTPUT_PATH: Final = Path("debug") / "lab_color_distances.png"
DEFAULT_REFERENCE_BGR: Final = (220, 220, 220)
DEFAULT_DISTANCES: Final = (14.0, 18.0, 32.0, 80.0)
_GRID_STEP: Final = 8


@dataclass(frozen=True, slots=True)
class LabColorSample:
    """Один отображаемый цвет и его расстояние до цвета подложки."""

    requested_distance: float | None
    actual_distance: float
    bgr: tuple[int, int, int]
    lab: tuple[int, int, int]


def _colors_to_lab(colors: np.ndarray) -> np.ndarray:
    """Преобразовать массив отображаемых цветов BGR в координаты OpenCV LAB."""
    image = colors.reshape((-1, 1, 3)).astype(np.uint8)
    return cv2.cvtColor(image, cv2.COLOR_BGR2LAB).reshape((-1, 3)).astype(np.float32)


def _color_to_lab(color: tuple[int, int, int]) -> np.ndarray:
    """Преобразовать один отображаемый цвет BGR в координаты OpenCV LAB."""
    return _colors_to_lab(np.asarray([color], dtype=np.uint8))[0]


def _coarse_colors() -> np.ndarray:
    """Создать равномерную сетку отображаемых цветов для начального поиска."""
    levels = np.append(np.arange(0, 256, _GRID_STEP), 255).astype(np.uint8)
    blue, green, red = np.meshgrid(levels, levels, levels, indexing="ij")
    return np.stack((blue, green, red), axis=-1).reshape((-1, 3))


def _local_colors(center: np.ndarray) -> np.ndarray:
    """Создать все целочисленные цвета рядом с результатом грубого поиска."""
    channels = tuple(
        np.arange(
            max(0, int(value) - _GRID_STEP),
            min(255, int(value) + _GRID_STEP) + 1,
            dtype=np.uint8,
        )
        for value in center
    )
    blue, green, red = np.meshgrid(*channels, indexing="ij")
    return np.stack((blue, green, red), axis=-1).reshape((-1, 3))


def _distances(lab_colors: np.ndarray, reference_lab: np.ndarray) -> np.ndarray:
    """Вычислить евклидовы расстояния от цветов до выбранной подложки."""
    return np.linalg.norm(lab_colors - reference_lab, axis=1)


def _int_triplet(values: np.ndarray) -> tuple[int, int, int]:
    """Преобразовать три значения массива NumPy в типизированный кортеж."""
    first, second, third = values
    return int(first), int(second), int(third)


def _select_for_distance(
    colors: np.ndarray,
    lab_colors: np.ndarray,
    reference_lab: np.ndarray,
    requested_distance: float,
) -> int:
    """Выбрать цвет с ближайшим расстоянием и выраженным отличием оттенка."""
    distances = _distances(lab_colors, reference_lab)
    errors = np.abs(distances - requested_distance)
    best_error = float(np.min(errors))
    nearest = np.flatnonzero(errors <= best_error + 1e-6)
    color_differences = lab_colors[nearest, 1:] - reference_lab[1:]
    chroma_distances = np.linalg.norm(color_differences, axis=1)
    return int(nearest[int(np.argmax(chroma_distances))])


def _sample_for_distance(
    coarse_colors: np.ndarray,
    coarse_lab: np.ndarray,
    reference_lab: np.ndarray,
    requested_distance: float,
) -> LabColorSample:
    """Найти отображаемый цвет для заданного расстояния LAB."""
    coarse_index = _select_for_distance(
        coarse_colors,
        coarse_lab,
        reference_lab,
        requested_distance,
    )
    local_colors = _local_colors(coarse_colors[coarse_index])
    local_lab = _colors_to_lab(local_colors)
    local_index = _select_for_distance(
        local_colors,
        local_lab,
        reference_lab,
        requested_distance,
    )
    actual_distance = float(
        np.linalg.norm(local_lab[local_index] - reference_lab)
    )
    return LabColorSample(
        requested_distance=requested_distance,
        actual_distance=actual_distance,
        bgr=_int_triplet(local_colors[local_index]),
        lab=_int_triplet(local_lab[local_index]),
    )


def _most_distant_sample(
    coarse_colors: np.ndarray,
    coarse_lab: np.ndarray,
    reference_lab: np.ndarray,
) -> LabColorSample:
    """Найти наиболее удалённый цвет сетки и уточнить результат рядом с ним."""
    coarse_index = int(np.argmax(_distances(coarse_lab, reference_lab)))
    local_colors = _local_colors(coarse_colors[coarse_index])
    local_lab = _colors_to_lab(local_colors)
    local_distances = _distances(local_lab, reference_lab)
    local_index = int(np.argmax(local_distances))
    return LabColorSample(
        requested_distance=None,
        actual_distance=float(local_distances[local_index]),
        bgr=_int_triplet(local_colors[local_index]),
        lab=_int_triplet(local_lab[local_index]),
    )


def generate_color_samples(
    reference_bgr: tuple[int, int, int] = DEFAULT_REFERENCE_BGR,
    distances: tuple[float, ...] = DEFAULT_DISTANCES,
) -> tuple[LabColorSample, ...]:
    """Сформировать отображаемые цвета для заданных расстояний LAB."""
    if any(not 0 <= channel <= 255 for channel in reference_bgr):
        raise ValueError(
            "Цвет подложки (reference_bgr): значения каналов должны находиться "
            "в диапазоне от 0 до 255"
        )
    if any(distance < 0 for distance in distances):
        raise ValueError(
            "Цветовые расстояния (distances): значения не могут быть отрицательными"
        )

    reference_lab = _color_to_lab(reference_bgr)
    coarse_colors = _coarse_colors()
    coarse_lab = _colors_to_lab(coarse_colors)
    requested_samples = tuple(
        _sample_for_distance(
            coarse_colors,
            coarse_lab,
            reference_lab,
            requested_distance,
        )
        for requested_distance in distances
    )
    return requested_samples + (
        _most_distant_sample(coarse_colors, coarse_lab, reference_lab),
    )


def _load_font(size: int) -> FreeTypeFont | PillowImageFont:
    """Загрузить шрифт с кириллицей из типичных каталогов Windows и Linux."""
    candidates = (
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    )
    for path in candidates:
        if path.is_file():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def _rgb(color_bgr: tuple[int, int, int]) -> tuple[int, int, int]:
    """Изменить порядок каналов BGR на RGB для Pillow."""
    blue, green, red = color_bgr
    return red, green, blue


def create_lab_palette(
    output_path: Path = DEFAULT_OUTPUT_PATH,
    reference_bgr: tuple[int, int, int] = DEFAULT_REFERENCE_BGR,
    distances: tuple[float, ...] = DEFAULT_DISTANCES,
) -> tuple[LabColorSample, ...]:
    """Создать PNG-палитру и вернуть сведения о показанных цветах."""
    samples = generate_color_samples(reference_bgr, distances)
    width = 1180
    header_height = 90
    row_height = 145
    image = Image.new("RGB", (width, header_height + row_height * len(samples)), "white")
    draw = ImageDraw.Draw(image)
    title_font = _load_font(25)
    text_font = _load_font(19)
    small_font = _load_font(16)

    reference_lab = tuple(int(value) for value in _color_to_lab(reference_bgr))
    draw.text(
        (24, 18),
        "Расстояния между отображаемыми цветами в OpenCV LAB",
        fill="black",
        font=title_font,
    )
    draw.text((24, 57), "Цвет подложки", fill="black", font=small_font)
    draw.text((285, 57), "Сравниваемый цвет", fill="black", font=small_font)

    for number, sample in enumerate(samples):
        top = header_height + number * row_height
        draw.rectangle((24, top, 260, top + 82), fill=_rgb(reference_bgr), outline="black")
        draw.rectangle((285, top, 521, top + 82), fill=_rgb(sample.bgr), outline="black")
        if sample.requested_distance is None:
            description = "Наиболее удалённый найденный отображаемый цвет"
        else:
            description = f"Заданное расстояние: {sample.requested_distance:g}"
        draw.text((550, top), description, fill="black", font=text_font)
        draw.text(
            (550, top + 31),
            f"Фактическое расстояние: {sample.actual_distance:.2f}",
            fill="black",
            font=text_font,
        )
        draw.text(
            (24, top + 94),
            f"Подложка BGR {reference_bgr}, LAB {reference_lab}",
            fill="black",
            font=small_font,
        )
        draw.text(
            (550, top + 66),
            f"Цвет BGR {sample.bgr}, LAB {sample.lab}",
            fill="black",
            font=small_font,
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, format="PNG")
    return samples


def main() -> int:
    """Создать стандартную учебную палитру и вывести путь к файлу."""
    samples = create_lab_palette()
    print(f"Создана вспомогательная палитра: {DEFAULT_OUTPUT_PATH.resolve()}")
    for sample in samples:
        requested = (
            "максимальное найденное"
            if sample.requested_distance is None
            else f"задано {sample.requested_distance:g}"
        )
        print(
            f"  {requested}; фактически {sample.actual_distance:.2f}; "
            f"BGR {sample.bgr}; LAB {sample.lab}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
