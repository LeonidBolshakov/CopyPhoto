from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


@dataclass(frozen=True, slots=True)
class CropperConfig:
    # Запас защищает край фотографии при интерполяции во время поворота.
    safety_margin_pixels: int = 32

    # Максимальная ширина остаточной полосы подложки после выравнивания.
    substrate_trim_pixels: int = 24
    substrate_color_distance: float = 32.0
    substrate_line_fraction: float = 0.75

    # Небольшой отступ внутрь убирает тени у углов бумажной фотографии.
    perspective_inset_pixels: float = 6.0

    # Для почти осевого прямоугольника обычный срез сохраняет исходные пиксели.
    # Порог задаёт допустимое смещение концов одного края в полном разрешении.
    perspective_bypass_max_edge_offset_pixels: float = 2.0

    # Альбомные отпечатки приводятся к горизонтальному положению.
    rotate_portrait_to_landscape: bool = True

    def __post_init__(self) -> None:
        if self.safety_margin_pixels < 0:
            raise ValueError("safety_margin_pixels не может быть отрицательным")
        if self.substrate_trim_pixels < 0:
            raise ValueError("substrate_trim_pixels не может быть отрицательным")
        if self.substrate_color_distance <= 0:
            raise ValueError("substrate_color_distance должен быть положительным")
        if not 0 < self.substrate_line_fraction <= 1:
            raise ValueError("substrate_line_fraction должен находиться в диапазоне (0, 1]")
        if self.perspective_inset_pixels < 0:
            raise ValueError("perspective_inset_pixels не может быть отрицательным")
        if self.perspective_bypass_max_edge_offset_pixels < 0:
            raise ValueError(
                "perspective_bypass_max_edge_offset_pixels не может быть отрицательным"
            )


DEFAULT_CROPPER_CONFIG = CropperConfig()


class EnhancementMode(Enum):
    NONE = "Без коррекции"
    SOFT = "Мягкая"


@dataclass(frozen=True, slots=True)
class EnhancerConfig:
    mode: EnhancementMode = EnhancementMode.NONE

    # Доля скорректированной яркости в итоговом изображении.
    intensity: float = 0.25

    # Параметры локального выравнивания яркости для мягкого режима.
    clahe_clip_limit: float = 2.0
    clahe_tile_grid_size: int = 8

    def __post_init__(self) -> None:
        if not isinstance(self.mode, EnhancementMode):
            raise ValueError("задан неизвестный режим коррекции")
        if not 0.0 <= self.intensity <= 1.0:
            raise ValueError(
                "интенсивность коррекции должна находиться в диапазоне [0, 1]"
            )
        if self.clahe_clip_limit <= 0:
            raise ValueError("ограничение локального контраста должно быть положительным")
        if self.clahe_tile_grid_size < 2:
            raise ValueError("размер сетки локальной коррекции должен быть не меньше 2")


DEFAULT_ENHANCER_CONFIG = EnhancerConfig()


@dataclass(frozen=True, slots=True)
class DiagnosticsConfig:
    output_dir: Path
    enabled: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ValueError("признак режима отладки должен иметь значение Да или Нет")


@dataclass(frozen=True, slots=True)
class ExportConfig:
    output_dir: Path
    filename_prefix: str = "photo"
    filename_digits: int = 4
    output_format: str = "jpeg"
    jpeg_quality: int = 95

    def __post_init__(self) -> None:
        if not self.filename_prefix or self.filename_prefix.strip() != self.filename_prefix:
            raise ValueError("префикс имени файла не может быть пустым или содержать пробелы по краям")
        forbidden = frozenset('<>:"/\\|?*')
        if any(character in forbidden for character in self.filename_prefix):
            raise ValueError("префикс имени файла содержит недопустимые символы")
        if self.filename_prefix.endswith((".", " ")):
            raise ValueError("префикс имени файла не может оканчиваться точкой или пробелом")
        if self.filename_digits < 1:
            raise ValueError("число разрядов в имени файла должно быть положительным")
        if self.output_format not in {"jpeg", "png"}:
            raise ValueError("формат результата должен быть 'jpeg' или 'png'")
        if not 1 <= self.jpeg_quality <= 100:
            raise ValueError("качество JPEG должно находиться в диапазоне [1, 100]")

    @property
    def file_extension(self) -> str:
        return ".jpg" if self.output_format == "jpeg" else ".png"


@dataclass(frozen=True, slots=True)
class DetectorConfig:
    input_dir: Path

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
