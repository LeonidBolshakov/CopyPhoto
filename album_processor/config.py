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

    # Робастный отбор однородных участков фона по периметру кадра.
    background_tiles_per_side: int = 12
    background_tile_mad_max: float = 8.0
    background_cluster_distance: float = 14.0
    background_inlier_fraction: float = 0.80
    background_refinement_iterations: int = 3
    background_min_cluster_fraction: float = 0.50

    # Цветовое отличие фотографии от подложки в пространстве LAB.
    background_distance_min: float = 18.0
    background_mad_multiplier: float = 5.0
    background_threshold_warning: float = 80.0

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
            raise ValueError("analysis_max_side должен быть не меньше 320")
        if self.background_tiles_per_side < 2:
            raise ValueError("background_tiles_per_side должен быть не меньше 2")
        if self.background_refinement_iterations < 1:
            raise ValueError("background_refinement_iterations должен быть положительным")
        for name in (
            "background_border_fraction",
            "background_inlier_fraction",
            "background_min_cluster_fraction",
            "morph_kernel_fraction",
            "min_photo_area_fraction",
            "max_photo_area_fraction",
            "min_photo_side_fraction",
            "min_rectangularity",
        ):
            value = getattr(self, name)
            if not 0 < value <= 1:
                raise ValueError(f"{name} должен находиться в диапазоне (0, 1]")
        for name in (
            "background_tile_mad_max",
            "background_cluster_distance",
            "background_distance_min",
            "background_mad_multiplier",
            "background_threshold_warning",
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} должен быть положительным")
        if self.min_photo_area_fraction >= self.max_photo_area_fraction:
            raise ValueError("минимальная площадь фотографии должна быть меньше максимальной")
        if self.min_aspect_ratio < 1 or self.min_aspect_ratio > self.max_aspect_ratio:
            raise ValueError("заданы неверные границы соотношения сторон")
        if not 0 <= self.max_deskew_angle <= 45:
            raise ValueError("max_deskew_angle должен находиться в диапазоне [0, 45]")
