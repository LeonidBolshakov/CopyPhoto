"""Полноразмерное выделение и геометрическое выравнивание фотографий."""

from __future__ import annotations

from collections.abc import Iterable
from math import ceil, floor

import cv2
import numpy as np

from copyphoto.album_processor.config import DEFAULT_CROPPER_CONFIG, CropperConfig
from copyphoto.album_processor.detector import PhotoDetection
from copyphoto.album_processor.image_validation import validate_bgr_image


def _source_patch(
    image: np.ndarray,
    box: np.ndarray,
    margin: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Извлечь участок с запасом и перевести рамку в локальные координаты."""
    height, width = image.shape[:2]
    left = floor(float(np.min(box[:, 0]))) - margin
    top = floor(float(np.min(box[:, 1]))) - margin
    right = ceil(float(np.max(box[:, 0]))) + margin
    bottom = ceil(float(np.max(box[:, 1]))) + margin

    source_left = max(0, left)
    source_top = max(0, top)
    source_right = min(width, right)
    source_bottom = min(height, bottom)
    if source_left >= source_right or source_top >= source_bottom:
        raise ValueError("рамка фотографии не пересекается с исходным изображением")

    patch = image[source_top:source_bottom, source_left:source_right]
    patch = cv2.copyMakeBorder(
        patch,
        source_top - top,
        bottom - source_bottom,
        source_left - left,
        right - source_right,
        cv2.BORDER_REPLICATE,
    )
    local_box = box - np.asarray((left, top), dtype=np.float32)
    return patch, local_box


def _affine_crop(
    patch: np.ndarray,
    box: np.ndarray,
    angle: float,
    background_lab: np.ndarray,
    config: CropperConfig,
) -> np.ndarray:
    """Исправить небольшой наклон аффинным поворотом и вырезать рамку."""
    center = box.mean(axis=0)
    rotation = cv2.getRotationMatrix2D(
        (float(center[0]), float(center[1])),
        angle,
        1.0,
    )
    aligned = cv2.warpAffine(
        patch,
        rotation,
        (patch.shape[1], patch.shape[0]),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )
    aligned_box = cv2.transform(box[np.newaxis, :, :], rotation)[0]

    left = max(0, floor(float(np.min(aligned_box[:, 0]))))
    top = max(0, floor(float(np.min(aligned_box[:, 1]))))
    right = min(aligned.shape[1], ceil(float(np.max(aligned_box[:, 0]))))
    bottom = min(aligned.shape[0], ceil(float(np.max(aligned_box[:, 1]))))
    if left >= right or top >= bottom:
        raise ValueError("после выравнивания рамка фотографии стала пустой")

    candidate = aligned[top:bottom, left:right]
    return _trim_substrate(candidate, background_lab, config)


def _photo_foreground_mask(
    patch: np.ndarray,
    background_lab: np.ndarray,
    config: CropperConfig,
) -> np.ndarray:
    """Построить и очистить маску отличающихся от подложки пикселей."""
    lab = cv2.cvtColor(patch, cv2.COLOR_BGR2LAB).astype(np.float32)
    distances = np.linalg.norm(lab - background_lab, axis=2)
    mask: np.ndarray = np.where(
        distances > config.substrate_color_distance,
        255,
        0,
    ).astype(np.uint8)
    kernel_size = max(3, round(min(patch.shape[:2]) * 0.008))
    if kernel_size % 2 == 0:
        kernel_size += 1
    kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (kernel_size, kernel_size),
    )
    return cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)


def _select_photo_contour(
    contours: tuple[np.ndarray, ...],
    center: np.ndarray,
) -> np.ndarray | None:
    """Выбрать содержащий центр или крупнейший внешний контур."""
    if not contours:
        return None
    containing = tuple(
        contour
        for contour in contours
        if cv2.pointPolygonTest(
            contour,
            (float(center[0]), float(center[1])),
            False,
        )
        >= 0
    )
    return max(containing or contours, key=cv2.contourArea)


def _approximate_quadrilateral(contour: np.ndarray) -> np.ndarray | None:
    """Найти выпуклую четырёхугольную аппроксимацию контура."""
    perimeter = cv2.arcLength(contour, True)
    for epsilon_percent in range(5, 51, 5):
        approximation = cv2.approxPolyDP(
            contour,
            perimeter * epsilon_percent / 1000.0,
            True,
        )
        if len(approximation) == 4 and cv2.isContourConvex(approximation):
            return approximation.reshape(4, 2).astype(np.float32)
    return None


def _has_plausible_quad_area(box: np.ndarray, quad: np.ndarray) -> bool:
    """Проверить близость площади четырёхугольника к исходной рамке."""
    box_area = abs(float(cv2.contourArea(box)))
    quad_area = abs(float(cv2.contourArea(quad)))
    return box_area > 0 and 0.75 <= quad_area / box_area <= 1.20


def _photo_quad(
    patch: np.ndarray,
    box: np.ndarray,
    background_lab: np.ndarray,
    config: CropperConfig,
) -> np.ndarray | None:
    """Уточнить четыре угла бумажной фотографии по цвету подложки."""
    mask = _photo_foreground_mask(patch, background_lab, config)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contour = _select_photo_contour(tuple(contours), box.mean(axis=0))
    if contour is None:
        return None

    quad = _approximate_quadrilateral(contour)
    if quad is None or not _has_plausible_quad_area(box, quad):
        return None
    return quad


def _order_quad(quad: np.ndarray) -> np.ndarray:
    """Упорядочить углы как левый верхний, правый верхний и далее по часовой."""
    coordinate_sum = quad.sum(axis=1)
    coordinate_difference = quad[:, 0] - quad[:, 1]
    ordered = np.asarray(
        (
            quad[int(np.argmin(coordinate_sum))],
            quad[int(np.argmax(coordinate_difference))],
            quad[int(np.argmax(coordinate_sum))],
            quad[int(np.argmin(coordinate_difference))],
        ),
        dtype=np.float32,
    )
    if len(np.unique(ordered, axis=0)) != 4:
        raise ValueError("не удалось упорядочить углы фотографии")
    return ordered


def _inset_quad(quad: np.ndarray, inset: float) -> np.ndarray:
    """Сместить углы внутрь для удаления узкой тени или полосы подложки."""
    if inset == 0:
        return quad
    center = quad.mean(axis=0)
    directions = center - quad
    lengths = np.linalg.norm(directions, axis=1, keepdims=True)
    if np.any(lengths <= inset):
        raise ValueError("отступ перспективы превышает размер фотографии")
    return (quad + directions / lengths * inset).astype(np.float32)


def _perspective_crop(
    patch: np.ndarray,
    quad: np.ndarray,
    background_lab: np.ndarray,
    config: CropperConfig,
) -> np.ndarray:
    """Выровнять перспективу четырёхугольной бумажной фотографии."""
    ordered_quad = _order_quad(quad)
    inset_quad = _inset_quad(ordered_quad, config.perspective_inset_pixels)
    top_left, top_right, bottom_right, bottom_left = inset_quad
    width = ceil(
        max(
            float(np.linalg.norm(top_right - top_left)),
            float(np.linalg.norm(bottom_right - bottom_left)),
        )
    ) + 1
    height = ceil(
        max(
            float(np.linalg.norm(bottom_left - top_left)),
            float(np.linalg.norm(bottom_right - top_right)),
        )
    ) + 1
    if width < 2 or height < 2:
        raise ValueError("размер фотографии после выравнивания слишком мал")

    destination = np.asarray(
        ((0, 0), (width - 1, 0), (width - 1, height - 1), (0, height - 1)),
        dtype=np.float32,
    )
    transform = cv2.getPerspectiveTransform(
        np.asarray((top_left, top_right, bottom_right, bottom_left)),
        destination,
    )
    aligned = cv2.warpPerspective(
        patch,
        transform,
        (width, height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )
    return _trim_substrate(aligned, background_lab, config)


def _is_axis_aligned_quad(quad: np.ndarray, max_edge_offset: float) -> bool:
    """Проверить возможность прямого среза без интерполяции пикселей."""
    top_left, top_right, bottom_right, bottom_left = quad
    edge_offsets = (
        abs(float(top_right[1] - top_left[1])),
        abs(float(bottom_right[1] - bottom_left[1])),
        abs(float(bottom_left[0] - top_left[0])),
        abs(float(bottom_right[0] - top_right[0])),
    )
    return max(edge_offsets) <= max_edge_offset


def _axis_aligned_crop(
    patch: np.ndarray,
    ordered_quad: np.ndarray,
    background_lab: np.ndarray,
    config: CropperConfig,
) -> np.ndarray:
    """Вырезать почти осевую фотографию обычным срезом NumPy."""
    inset_quad = _inset_quad(ordered_quad, config.perspective_inset_pixels)
    top_left, top_right, bottom_right, bottom_left = inset_quad
    left = max(0, ceil(max(float(top_left[0]), float(bottom_left[0]))))
    top = max(0, ceil(max(float(top_left[1]), float(top_right[1]))))
    right = min(
        patch.shape[1],
        floor(min(float(top_right[0]), float(bottom_right[0]))) + 1,
    )
    bottom = min(
        patch.shape[0],
        floor(min(float(bottom_left[1]), float(bottom_right[1]))) + 1,
    )
    if left >= right or top >= bottom:
        raise ValueError("обычное кадрирование привело к пустому изображению")

    candidate = patch[top:bottom, left:right]
    return _trim_substrate(candidate, background_lab, config)


def _normalize_orientation(image: np.ndarray, config: CropperConfig) -> np.ndarray:
    """При необходимости повернуть портретный результат в альбомное положение."""
    if config.rotate_portrait_to_landscape and image.shape[0] > image.shape[1]:
        return np.ascontiguousarray(cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE))
    return image


def _estimate_background_lab(patch: np.ndarray, box: np.ndarray) -> np.ndarray:
    """Оценить медианный цвет подложки за пределами рамки в LAB."""
    inside = np.zeros(patch.shape[:2], dtype=np.uint8)
    polygon = np.rint(box).astype(np.int32)
    cv2.fillConvexPoly(inside, polygon, 255)
    pixels = patch[inside == 0]
    if pixels.size == 0:
        pixels = np.concatenate(
            (patch[0], patch[-1], patch[:, 0], patch[:, -1]),
            axis=0,
        )
    lab = cv2.cvtColor(pixels.reshape(-1, 1, 3), cv2.COLOR_BGR2LAB)
    return np.median(lab.reshape(-1, 3), axis=0).astype(np.float32)


def _background_depth(
    scores: np.ndarray,
    limit: int,
    required_fraction: float,
    *,
    reverse: bool = False,
) -> int:
    """Посчитать число последовательных строк или столбцов подложки от края."""
    values = scores[::-1] if reverse else scores
    depth = 0
    for score in values[:limit]:
        if float(score) < required_fraction:
            break
        depth += 1
    return depth


def _trim_substrate(
    image: np.ndarray,
    background_lab: np.ndarray,
    config: CropperConfig,
) -> np.ndarray:
    """Удалить остаточные полосы подложки вдоль краёв выровненного кадра."""
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB).astype(np.float32)
    distances = np.linalg.norm(lab - background_lab, axis=2)
    background_like = distances <= config.substrate_color_distance
    row_scores = background_like.mean(axis=1)
    column_scores = background_like.mean(axis=0)
    vertical_limit = min(config.substrate_trim_pixels, max(0, image.shape[0] // 3))
    horizontal_limit = min(config.substrate_trim_pixels, max(0, image.shape[1] // 3))

    top = _background_depth(
        row_scores,
        vertical_limit,
        config.substrate_line_fraction,
    )
    bottom = _background_depth(
        row_scores,
        vertical_limit,
        config.substrate_line_fraction,
        reverse=True,
    )
    left = _background_depth(
        column_scores,
        horizontal_limit,
        config.substrate_line_fraction,
    )
    right = _background_depth(
        column_scores,
        horizontal_limit,
        config.substrate_line_fraction,
        reverse=True,
    )
    if left + right >= image.shape[1] or top + bottom >= image.shape[0]:
        raise ValueError("удаление полосы подложки привело к пустому изображению")
    return np.ascontiguousarray(image[top : image.shape[0] - bottom, left : image.shape[1] - right])


def crop_photo(
    image: np.ndarray,
    detection: PhotoDetection,
    config: CropperConfig = DEFAULT_CROPPER_CONFIG,
) -> np.ndarray:
    """Вырезает фотографию в полном разрешении и выравнивает её края."""
    validate_bgr_image(image, "crop_photo")
    height, width = image.shape[:2]
    box = detection.box_for_size(width, height)
    if box.shape != (4, 2) or not np.all(np.isfinite(box)):
        raise ValueError("рамка фотографии должна содержать четыре конечные вершины")

    patch, local_box = _source_patch(image, box, config.safety_margin_pixels)
    background_lab = _estimate_background_lab(patch, local_box)
    quad = _photo_quad(patch, local_box, background_lab, config)
    if quad is not None:
        ordered_quad = _order_quad(quad)
        if _is_axis_aligned_quad(
            ordered_quad,
            config.perspective_bypass_max_edge_offset_pixels,
        ):
            return _normalize_orientation(
                _axis_aligned_crop(
                    patch,
                    ordered_quad,
                    background_lab,
                    config,
                ),
                config,
            )
        return _normalize_orientation(
            _perspective_crop(
                patch,
                ordered_quad,
                background_lab,
                config,
            ),
            config,
        )
    return _normalize_orientation(
        _affine_crop(
            patch,
            local_box,
            detection.angle,
            background_lab,
            config,
        ),
        config,
    )


def crop_photos(
    image: np.ndarray,
    detections: Iterable[PhotoDetection],
    config: CropperConfig = DEFAULT_CROPPER_CONFIG,
) -> tuple[np.ndarray, ...]:
    """Вырезает все найденные фотографии, сохраняя порядок обнаружений."""
    return tuple(crop_photo(image, detection, config) for detection in detections)
