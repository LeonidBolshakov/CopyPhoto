from __future__ import annotations

from dataclasses import dataclass
from math import atan2, degrees

import cv2
import numpy as np

from album_processor.config import DetectorConfig


@dataclass(frozen=True, slots=True)
class PhotoDetection:
    normalized_box: np.ndarray
    angle: float
    area_fraction: float
    rectangularity: float
    aspect_ratio: float

    def box_for_size(self, width: int, height: int) -> np.ndarray:
        scale = np.float32((width, height))
        return (self.normalized_box * scale).astype(np.float32)


@dataclass(frozen=True, slots=True)
class DetectionResult:
    detections: tuple[PhotoDetection, ...]
    preview: np.ndarray
    mask: np.ndarray
    annotated: np.ndarray
    background_lab: tuple[float, float, float]
    distance_threshold: float


def _resize_for_analysis(image: np.ndarray, max_side: int) -> np.ndarray:
    height, width = image.shape[:2]
    scale = min(1.0, max_side / max(height, width))
    if scale == 1.0:
        return image.copy()
    size = (max(1, round(width * scale)), max(1, round(height * scale)))
    return cv2.resize(image, size, interpolation=cv2.INTER_AREA)


def _border_pixels(image: np.ndarray, fraction: float) -> np.ndarray:
    height, width = image.shape[:2]
    border = max(3, round(min(height, width) * fraction))
    return np.concatenate(
        (
            image[:border].reshape(-1, 3),
            image[-border:].reshape(-1, 3),
            image[border:-border, :border].reshape(-1, 3),
            image[border:-border, -border:].reshape(-1, 3),
        ),
        axis=0,
    )


def _background_mask(
    preview: np.ndarray, config: DetectorConfig
) -> tuple[np.ndarray, np.ndarray, float]:
    lab = cv2.cvtColor(preview, cv2.COLOR_BGR2LAB).astype(np.float32)
    border = _border_pixels(lab, config.background_border_fraction)
    background = np.median(border, axis=0).astype(np.float32)

    border_distance = np.linalg.norm(border - background, axis=1)
    median_distance = float(np.median(border_distance))
    mad = float(np.median(np.abs(border_distance - median_distance)))
    robust_sigma = 1.4826 * mad
    threshold = max(
        config.background_distance_min,
        median_distance + config.background_mad_multiplier * robust_sigma,
    )

    distance = np.linalg.norm(lab - background, axis=2)
    foreground = np.where(distance > threshold, 255, 0).astype(np.uint8)
    return foreground, background, threshold


def _clean_mask(mask: np.ndarray, config: DetectorConfig) -> np.ndarray:
    height, width = mask.shape
    kernel_size = max(3, round(min(height, width) * config.morph_kernel_fraction))
    if kernel_size % 2 == 0:
        kernel_size += 1
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
    cleaned = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_OPEN, kernel, iterations=1)
    return cleaned


def _nearest_axis_angle(box: np.ndarray) -> float:
    edges = np.roll(box, -1, axis=0) - box
    lengths = np.linalg.norm(edges, axis=1)
    longest = edges[int(np.argmax(lengths))]
    raw_angle = degrees(atan2(float(longest[1]), float(longest[0])))
    return (raw_angle + 45.0) % 90.0 - 45.0


def _candidate_from_contour(
    contour: np.ndarray,
    width: int,
    height: int,
    config: DetectorConfig,
) -> PhotoDetection | None:
    image_area = float(width * height)
    contour_area = float(cv2.contourArea(contour))
    area_fraction = contour_area / image_area
    if not config.min_photo_area_fraction <= area_fraction <= config.max_photo_area_fraction:
        return None

    rectangle = cv2.minAreaRect(contour)
    rect_width, rect_height = rectangle[1]
    if rect_width <= 0 or rect_height <= 0:
        return None
    if min(rect_width, rect_height) / min(width, height) < config.min_photo_side_fraction:
        return None

    rectangle_area = float(rect_width * rect_height)
    rectangularity = contour_area / rectangle_area
    if rectangularity < config.min_rectangularity:
        return None

    aspect_ratio = max(rect_width, rect_height) / min(rect_width, rect_height)
    if not config.min_aspect_ratio <= aspect_ratio <= config.max_aspect_ratio:
        return None

    box = cv2.boxPoints(rectangle).astype(np.float32)
    angle = _nearest_axis_angle(box)
    if abs(angle) > config.max_deskew_angle:
        return None

    normalized_box = box / np.float32((width, height))
    return PhotoDetection(
        normalized_box=normalized_box,
        angle=angle,
        area_fraction=area_fraction,
        rectangularity=rectangularity,
        aspect_ratio=aspect_ratio,
    )


def _annotate(preview: np.ndarray, detections: tuple[PhotoDetection, ...]) -> np.ndarray:
    annotated = preview.copy()
    height, width = annotated.shape[:2]
    for index, detection in enumerate(detections, start=1):
        box = np.rint(detection.box_for_size(width, height)).astype(np.int32)
        cv2.polylines(annotated, [box], True, (0, 220, 0), 3, cv2.LINE_AA)
        center = tuple(np.rint(box.mean(axis=0)).astype(int))
        label = f"{index}: {detection.angle:+.1f} deg"
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
    return annotated


def detect_photos(image: np.ndarray, config: DetectorConfig) -> DetectionResult:
    if image.ndim != 3 or image.shape[2] != 3:
        raise ValueError("detect_photos expects a BGR image with three channels")

    preview = _resize_for_analysis(image, config.analysis_max_side)
    raw_mask, background, threshold = _background_mask(preview, config)
    mask = _clean_mask(raw_mask, config)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    height, width = preview.shape[:2]
    candidates = (
        candidate
        for contour in contours
        if (candidate := _candidate_from_contour(contour, width, height, config)) is not None
    )
    detections = tuple(sorted(candidates, key=lambda item: item.area_fraction, reverse=True))
    annotated = _annotate(preview, detections)

    return DetectionResult(
        detections=detections,
        preview=preview,
        mask=mask,
        annotated=annotated,
        background_lab=tuple(float(value) for value in background),
        distance_threshold=threshold,
    )
