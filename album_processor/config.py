from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class DetectorConfig:
    input_dir: Path
    debug_dir: Path

    # Уменьшенная копия используется только для быстрого поиска контуров.
    analysis_max_side: int = 1600

    # Полоса по краям кадра, используемая для оценки цвета подложки.
    background_border_fraction: float = 0.04

    # Цветовое отличие фотографии от подложки в пространстве LAB.
    background_distance_min: float = 18.0
    background_mad_multiplier: float = 4.0

    # Размер морфологического ядра относительно короткой стороны кадра.
    morph_kernel_fraction: float = 0.008

    # Геометрическая фильтрация найденных областей.
    min_photo_area_fraction: float = 0.02
    max_photo_area_fraction: float = 0.85
    min_photo_side_fraction: float = 0.08
    min_rectangularity: float = 0.55
    min_aspect_ratio: float = 1.0
    max_aspect_ratio: float = 2.25
    max_deskew_angle: float = 15.0

    def __post_init__(self) -> None:
        if self.analysis_max_side < 320:
            raise ValueError("analysis_max_side must be at least 320")
        for name in (
            "background_border_fraction",
            "morph_kernel_fraction",
            "min_photo_area_fraction",
            "max_photo_area_fraction",
            "min_photo_side_fraction",
            "min_rectangularity",
        ):
            value = getattr(self, name)
            if not 0 < value <= 1:
                raise ValueError(f"{name} must be in the range (0, 1]")
        if self.min_photo_area_fraction >= self.max_photo_area_fraction:
            raise ValueError("minimum photo area must be below maximum photo area")
        if self.min_aspect_ratio < 1 or self.min_aspect_ratio > self.max_aspect_ratio:
            raise ValueError("invalid aspect-ratio limits")
        if not 0 <= self.max_deskew_angle <= 45:
            raise ValueError("max_deskew_angle must be in the range [0, 45]")
