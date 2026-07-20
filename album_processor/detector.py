"""Обнаружение бумажных фотографий и формирование диагностики контуров."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import atan2, degrees

import cv2
import numpy as np

from album_processor.config import DetectorConfig


@dataclass(frozen=True, slots=True)
class PhotoDetection:
    """Нормализованная геометрия одной принятой фотографии."""

    normalized_box: np.ndarray
    angle: float
    area_fraction: float
    rectangularity: float
    aspect_ratio: float

    def box_for_size(self, width: int, height: int) -> np.ndarray:
        """Пересчитать нормализованную рамку для заданного разрешения."""
        scale = np.asarray((width, height), dtype=np.float32)
        return (self.normalized_box * scale).astype(np.float32)


class ContourRejectionReason(Enum):
    """Причины, по которым контур не считается фотографией."""

    AREA_TOO_SMALL = "площадь меньше допустимой"
    AREA_TOO_LARGE = "площадь больше допустимой"
    INVALID_RECTANGLE = "невозможно построить прямоугольную рамку"
    SIDE_TOO_SHORT = "короткая сторона меньше допустимой"
    LOW_RECTANGULARITY = "контур недостаточно прямоугольный"
    INVALID_ASPECT_RATIO = "неподходящее соотношение сторон"
    ANGLE_TOO_LARGE = "наклон превышает допустимый"


@dataclass(frozen=True, slots=True)
class ContourRejection:
    """Отклонённый контур с причиной и измеренными показателями."""

    reason: ContourRejectionReason
    normalized_contour: np.ndarray
    details: str

    def contour_for_size(self, width: int, height: int) -> np.ndarray:
        """Пересчитать нормализованный контур для заданного разрешения."""
        scale = np.asarray((width, height), dtype=np.float32)
        return (self.normalized_contour * scale).astype(np.float32)


class DetectionWarningCode(Enum):
    """Категории диагностических предупреждений детектора."""

    LOW_BACKGROUND_COVERAGE = "неоднозначный фон"
    HIGH_BACKGROUND_THRESHOLD = "неоднородный фон"
    NO_PHOTOS = "фотографии не найдены"


@dataclass(frozen=True, slots=True)
class DetectionWarning:
    """Предупреждение с объяснением и рекомендацией оператору."""

    code: DetectionWarningCode
    message: str
    recommendation: str

    @property
    def text(self) -> str:
        """Объединить сообщение и рекомендацию для консольного вывода."""
        return f"{self.message}. {self.recommendation}"


@dataclass(frozen=True, slots=True)
class DetectionResult:
    """Полный результат обнаружения вместе с диагностическими данными."""

    detections: tuple[PhotoDetection, ...]
    rejections: tuple[ContourRejection, ...]
    warnings: tuple[DetectionWarning, ...]
    preview: np.ndarray
    mask: np.ndarray
    annotated: np.ndarray
    background_lab: tuple[float, float, float]
    distance_threshold: float
    background_tile_coverage: float

    @property
    def background_warning(self) -> str | None:
        """Вернуть совместимый текст предупреждений об оценке фона."""
        background_warnings = tuple(
            warning.text
            for warning in self.warnings
            if warning.code
            in {
                DetectionWarningCode.LOW_BACKGROUND_COVERAGE,
                DetectionWarningCode.HIGH_BACKGROUND_THRESHOLD,
            }
        )
        return "; ".join(background_warnings) or None


@dataclass(frozen=True, slots=True)
class _BackgroundEstimate:
    """Внутренняя оценка цвета и надёжности однотонной подложки."""

    raw_mask: np.ndarray
    color_lab: np.ndarray
    distance_threshold: float
    tile_coverage: float
    warnings: tuple[DetectionWarning, ...]


def _resize_for_analysis(image: np.ndarray, max_side: int) -> np.ndarray:
    """Создать уменьшенную копию для быстрого анализа контуров."""
    height, width = image.shape[:2]
    scale = min(1.0, max_side / max(height, width))
    if scale == 1.0:
        return image.copy()
    size = (max(1, round(width * scale)), max(1, round(height * scale)))
    return cv2.resize(image, size, interpolation=cv2.INTER_AREA)


def _border_tiles(
    image: np.ndarray,
    fraction: float,
    tiles_per_side: int,
) -> tuple[np.ndarray, ...]:
    """Разбить периметр кадра на участки для оценки подложки."""
    height, width = image.shape[:2]
    border = min(min(height, width), max(1, round(min(height, width) * fraction)))
    horizontal_edges = np.linspace(0, width, tiles_per_side + 1, dtype=int)
    vertical_edges = np.linspace(0, height, tiles_per_side + 1, dtype=int)
    tiles: list[np.ndarray] = []

    for start, end in zip(horizontal_edges[:-1], horizontal_edges[1:]):
        if end > start:
            tiles.append(image[:border, start:end])
            tiles.append(image[-border:, start:end])
    for start, end in zip(vertical_edges[:-1], vertical_edges[1:]):
        if end > start:
            tiles.append(image[start:end, :border])
            tiles.append(image[start:end, -border:])

    return tuple(tiles)


def _tile_statistics(tile: np.ndarray) -> tuple[np.ndarray, float, np.ndarray]:
    """Вычислить медианный цвет, разброс и пиксели участка периметра."""
    pixels = tile.reshape(-1, 3)
    median = np.median(pixels, axis=0).astype(np.float32)
    distances = np.linalg.norm(pixels - median, axis=1)
    dispersion = float(np.median(distances))
    return median, dispersion, pixels


def _dominant_background_pixels(
    lab: np.ndarray,
    config: DetectorConfig,
) -> tuple[np.ndarray, float]:
    """Выбрать доминирующую цветовую группу однородных участков фона."""
    tiles = _border_tiles(
        lab,
        config.background_border_fraction,
        config.background_tiles_per_side,
    )
    statistics = tuple(_tile_statistics(tile) for tile in tiles)
    homogeneous = tuple(
        item for item in statistics if item[1] <= config.background_tile_mad_max
    )

    # Если все участки неоднородны, используем их для приблизительной оценки.
    candidates = homogeneous or statistics
    medians = np.stack([item[0] for item in candidates])
    dispersions = np.asarray([item[1] for item in candidates], dtype=np.float32)
    distances = np.linalg.norm(medians[:, None, :] - medians[None, :, :], axis=2)
    memberships = distances <= config.background_cluster_distance
    counts = memberships.sum(axis=1)

    # Выбираем крупнейшую цветовую группу, а при равенстве — более однородную.
    scores = tuple(
        (int(counts[index]), -float(np.median(dispersions[memberships[index]])))
        for index in range(len(candidates))
    )
    seed_index = max(range(len(candidates)), key=scores.__getitem__)
    selected = tuple(
        item for item, keep in zip(candidates, memberships[seed_index]) if keep
    )
    pixels = np.concatenate([item[2] for item in selected], axis=0)
    coverage = len(selected) / len(tiles)
    return pixels, coverage


def _refine_background(
    pixels: np.ndarray,
    config: DetectorConfig,
) -> np.ndarray:
    """Итеративно уточнить цвет фона, отбрасывая цветовые выбросы."""
    background = np.median(pixels, axis=0).astype(np.float32)
    for _ in range(config.background_refinement_iterations):
        distances = np.linalg.norm(pixels - background, axis=1)
        cutoff = float(np.quantile(distances, config.background_inlier_fraction))
        inliers = pixels[distances <= cutoff]
        background = np.median(inliers, axis=0).astype(np.float32)
    return background


def _background_mask(
    preview: np.ndarray, config: DetectorConfig
) -> _BackgroundEstimate:
    """Построить черновую маску переднего плана и оценить качество фона."""
    lab = cv2.cvtColor(preview, cv2.COLOR_BGR2LAB).astype(np.float32)
    background_pixels, coverage = _dominant_background_pixels(lab, config)
    background = _refine_background(background_pixels, config)

    # Уточнённый центр не учитывает выбросы, а порог сохраняет естественный
    # градиент освещения на всех выбранных участках фона.
    background_distance = np.linalg.norm(background_pixels - background, axis=1)
    median_distance = float(np.median(background_distance))
    mad = float(np.median(np.abs(background_distance - median_distance)))
    robust_sigma = 1.4826 * mad
    threshold = max(
        config.background_distance_min,
        median_distance + config.background_mad_multiplier * robust_sigma,
    )

    distance = np.linalg.norm(lab - background, axis=2)
    foreground = np.where(distance > threshold, 255, 0).astype(np.uint8)
    warnings: list[DetectionWarning] = []
    if coverage < config.background_min_cluster_fraction:
        warnings.append(
            DetectionWarning(
                code=DetectionWarningCode.LOW_BACKGROUND_COVERAGE,
                message=(
                    "доминирующий цвет фона найден только на "
                    f"{coverage:.0%} участков периметра"
                ),
                recommendation=(
                    "оставьте подложку видимой по всему краю кадра и уберите "
                    "посторонние предметы"
                ),
            )
        )
    if threshold > config.background_threshold_warning:
        warnings.append(
            DetectionWarning(
                code=DetectionWarningCode.HIGH_BACKGROUND_THRESHOLD,
                message=f"порог отделения фона необычно высок: {threshold:.1f}",
                recommendation=(
                    "сделайте освещение подложки равномернее и исключите блики и тени"
                ),
            )
        )

    return _BackgroundEstimate(
        raw_mask=foreground,
        color_lab=background,
        distance_threshold=threshold,
        tile_coverage=coverage,
        warnings=tuple(warnings),
    )


def _clean_mask(mask: np.ndarray, config: DetectorConfig) -> np.ndarray:
    """Закрыть разрывы и удалить мелкий шум морфологическими операциями."""
    height, width = mask.shape
    kernel_size = max(3, round(min(height, width) * config.morph_kernel_fraction))
    if kernel_size % 2 == 0:
        kernel_size += 1
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
    cleaned = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_OPEN, kernel, iterations=1)
    return cleaned


def _nearest_axis_angle(box: np.ndarray) -> float:
    """Вычислить отклонение длинного края от ближайшей оси кадра."""
    edges = np.roll(box, -1, axis=0) - box
    lengths = np.linalg.norm(edges, axis=1)
    longest = edges[int(np.argmax(lengths))]
    raw_angle = degrees(atan2(float(longest[1]), float(longest[0])))
    return (raw_angle + 45.0) % 90.0 - 45.0


def _rejection(
    contour: np.ndarray,
    width: int,
    height: int,
    reason: ContourRejectionReason,
    details: str,
) -> ContourRejection:
    """Создать диагностическое отклонение с нормализованным контуром."""
    scale = np.asarray((width, height), dtype=np.float32)
    normalized_contour = contour.astype(np.float32) / scale
    return ContourRejection(
        reason=reason,
        normalized_contour=normalized_contour,
        details=details,
    )


def _evaluate_contour(
    contour: np.ndarray,
    width: int,
    height: int,
    config: DetectorConfig,
) -> tuple[PhotoDetection | None, ContourRejection | None]:
    """Проверить геометрию контура и вернуть принятие либо первую причину отказа."""
    image_area = float(width * height)
    contour_area = float(cv2.contourArea(contour))
    area_fraction = contour_area / image_area
    if area_fraction < config.min_photo_area_fraction:
        return None, _rejection(
            contour,
            width,
            height,
            ContourRejectionReason.AREA_TOO_SMALL,
            (
                f"доля площади {area_fraction:.2%}, требуется не меньше "
                f"{config.min_photo_area_fraction:.2%}"
            ),
        )
    if area_fraction > config.max_photo_area_fraction:
        return None, _rejection(
            contour,
            width,
            height,
            ContourRejectionReason.AREA_TOO_LARGE,
            (
                f"доля площади {area_fraction:.2%}, допускается не больше "
                f"{config.max_photo_area_fraction:.2%}"
            ),
        )

    rectangle = cv2.minAreaRect(contour)
    rect_width, rect_height = rectangle[1]
    if rect_width <= 0 or rect_height <= 0:
        return None, _rejection(
            contour,
            width,
            height,
            ContourRejectionReason.INVALID_RECTANGLE,
            "ширина или высота построенной рамки равна нулю",
        )
    side_fraction = min(rect_width, rect_height) / min(width, height)
    if side_fraction < config.min_photo_side_fraction:
        return None, _rejection(
            contour,
            width,
            height,
            ContourRejectionReason.SIDE_TOO_SHORT,
            (
                f"доля короткой стороны {side_fraction:.2%}, требуется не меньше "
                f"{config.min_photo_side_fraction:.2%}"
            ),
        )

    rectangle_area = float(rect_width * rect_height)
    rectangularity = contour_area / rectangle_area
    if rectangularity < config.min_rectangularity:
        return None, _rejection(
            contour,
            width,
            height,
            ContourRejectionReason.LOW_RECTANGULARITY,
            (
                f"прямоугольность {rectangularity:.3f}, требуется не меньше "
                f"{config.min_rectangularity:.3f}"
            ),
        )

    aspect_ratio = max(rect_width, rect_height) / min(rect_width, rect_height)
    if not config.min_aspect_ratio <= aspect_ratio <= config.max_aspect_ratio:
        return None, _rejection(
            contour,
            width,
            height,
            ContourRejectionReason.INVALID_ASPECT_RATIO,
            (
                f"соотношение сторон {aspect_ratio:.2f}, допустимый диапазон "
                f"[{config.min_aspect_ratio:.2f}, {config.max_aspect_ratio:.2f}]"
            ),
        )

    box = cv2.boxPoints(rectangle).astype(np.float32)
    angle = _nearest_axis_angle(box)
    if abs(angle) > config.max_deskew_angle:
        return None, _rejection(
            contour,
            width,
            height,
            ContourRejectionReason.ANGLE_TOO_LARGE,
            (
                f"наклон {angle:+.1f}°, допускается не больше "
                f"{config.max_deskew_angle:.1f}° по модулю"
            ),
        )

    normalized_box = box / np.asarray((width, height), dtype=np.float32)
    return (
        PhotoDetection(
            normalized_box=normalized_box,
            angle=angle,
            area_fraction=area_fraction,
            rectangularity=rectangularity,
            aspect_ratio=aspect_ratio,
        ),
        None,
    )


def _annotate(
    preview: np.ndarray,
    detections: tuple[PhotoDetection, ...],
    rejections: tuple[ContourRejection, ...],
    warnings: tuple[DetectionWarning, ...],
) -> np.ndarray:
    """Нарисовать принятые и отклонённые контуры и состояние предупреждений."""
    annotated = preview.copy()
    height, width = annotated.shape[:2]
    for rejection in rejections:
        contour = np.rint(rejection.contour_for_size(width, height)).astype(np.int32)
        cv2.polylines(annotated, [contour], True, (0, 165, 255), 1, cv2.LINE_AA)
    for index, detection in enumerate(detections, start=1):
        box = np.rint(detection.box_for_size(width, height)).astype(np.int32)
        cv2.polylines(annotated, [box], True, (0, 220, 0), 3, cv2.LINE_AA)
        center = tuple(np.rint(box.mean(axis=0)).astype(int))
        label = f"{index}: {detection.angle:+.1f}"
        cv2.putText(
            annotated,
            label,
            center,
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (0, 0, 0),
            4,
            cv2.LINE_AA,
        )
        cv2.putText(
            annotated,
            label,
            center,
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (0, 255, 0),
            2,
            cv2.LINE_AA,
        )
    if warnings:
        cv2.rectangle(annotated, (2, 2), (width - 3, height - 3), (0, 0, 255), 8)
        cv2.putText(
            annotated,
            "!!!",
            (20, 42),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.85,
            (0, 0, 0),
            5,
            cv2.LINE_AA,
        )
        cv2.putText(
            annotated,
            "!!!",
            (20, 42),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.85,
            (0, 0, 255),
            2,
            cv2.LINE_AA,
        )
    return annotated


def detect_photos(image: np.ndarray, config: DetectorConfig) -> DetectionResult:
    """Найти фотографии на однотонной подложке в уменьшенной копии изображения."""
    if image.ndim != 3 or image.shape[2] != 3:
        raise ValueError("detect_photos ожидает трёхканальное изображение BGR")

    preview = _resize_for_analysis(image, config.analysis_max_side)
    background = _background_mask(preview, config)
    mask = _clean_mask(background.raw_mask, config)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    height, width = preview.shape[:2]
    evaluations = tuple(
        _evaluate_contour(contour, width, height, config) for contour in contours
    )
    detections = tuple(
        sorted(
            (candidate for candidate, _ in evaluations if candidate is not None),
            key=lambda item: item.area_fraction,
            reverse=True,
        )
    )
    rejections = tuple(
        rejection for _, rejection in evaluations if rejection is not None
    )
    warnings = list(background.warnings)
    if not detections:
        if rejections:
            reason_counts = {
                reason: sum(item.reason is reason for item in rejections)
                for reason in ContourRejectionReason
            }
            main_reason = max(reason_counts, key=reason_counts.__getitem__)
            recommendation = (
                f"основная причина отклонения: {main_reason.value}; "
                "проверьте диагностическую маску и параметры детектора"
            )
        else:
            recommendation = (
                "проверьте контраст фотографий с подложкой и равномерность освещения"
            )
        warnings.append(
            DetectionWarning(
                code=DetectionWarningCode.NO_PHOTOS,
                message="на изображении не найдено ни одной фотографии",
                recommendation=recommendation,
            )
        )
    result_warnings = tuple(warnings)
    annotated = _annotate(preview, detections, rejections, result_warnings)

    return DetectionResult(
        detections=detections,
        rejections=rejections,
        warnings=result_warnings,
        preview=preview,
        mask=mask,
        annotated=annotated,
        background_lab=(
            float(background.color_lab[0]),
            float(background.color_lab[1]),
            float(background.color_lab[2]),
        ),
        distance_threshold=background.distance_threshold,
        background_tile_coverage=background.tile_coverage,
    )
