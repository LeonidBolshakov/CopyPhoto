from __future__ import annotations

import cv2
import numpy as np
from pytest import MonkeyPatch

from album_processor.config import DEFAULT_CROPPER_CONFIG, CropperConfig
from album_processor.cropper import crop_photo, crop_photos
from album_processor.detector import PhotoDetection


BACKGROUND = (24, 31, 38)
PHOTO_SIZE = (160, 100)
PHOTO_CENTER = (210, 160)


def make_detection(
    box: np.ndarray,
    image: np.ndarray,
    angle: float,
) -> PhotoDetection:
    height, width = image.shape[:2]
    normalized_box = box.astype(np.float32) / np.asarray(
        (width, height), dtype=np.float32
    )
    return PhotoDetection(
        normalized_box=normalized_box,
        angle=angle,
        area_fraction=0.25,
        rectangularity=1.0,
        aspect_ratio=1.6,
    )


def make_scene(
    angle: float,
    *,
    canvas_size: tuple[int, int] = (420, 320),
    center: tuple[int, int] = PHOTO_CENTER,
    photo_size: tuple[int, int] = PHOTO_SIZE,
    edge_strips: bool = False,
) -> tuple[np.ndarray, PhotoDetection]:
    width, height = canvas_size
    image: np.ndarray = np.full(
        (height, width, 3), BACKGROUND, dtype=np.uint8
    )
    photo_width, photo_height = photo_size
    left = center[0] - photo_width // 2
    top = center[1] - photo_height // 2
    right = left + photo_width
    bottom = top + photo_height

    visible_left = max(0, left)
    visible_top = max(0, top)
    visible_right = min(width, right)
    visible_bottom = min(height, bottom)
    image[visible_top:visible_bottom, visible_left:visible_right] = (90, 110, 130)

    if edge_strips and left >= 0 and top >= 0 and right <= width and bottom <= height:
        strip = 14
        image[top:bottom, left : left + strip] = (255, 0, 0)
        image[top:bottom, right - strip : right] = (0, 255, 0)
        image[top : top + strip, left:right] = (0, 0, 255)
        image[bottom - strip : bottom, left:right] = (0, 255, 255)

    if angle:
        rotation = cv2.getRotationMatrix2D(center, -angle, 1.0)
        image = cv2.warpAffine(
            image,
            rotation,
            (width, height),
            flags=cv2.INTER_NEAREST,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=BACKGROUND,
        )

    box = cv2.boxPoints((center, photo_size, angle)).astype(np.float32)
    return image, make_detection(box, image, angle)


def make_perspective_scene(quad: np.ndarray) -> tuple[np.ndarray, PhotoDetection]:
    width, height = 420, 320
    photo = np.full((100, 160, 3), (90, 110, 130), dtype=np.uint8)
    strip = 14
    photo[:, :strip] = (255, 0, 0)
    photo[:, -strip:] = (0, 255, 0)
    photo[:strip] = (0, 0, 255)
    photo[-strip:] = (0, 255, 255)
    source = np.asarray(((0, 0), (159, 0), (159, 99), (0, 99)), np.float32)
    transform = cv2.getPerspectiveTransform(source, quad.astype(np.float32))
    warped = cv2.warpPerspective(
        photo,
        transform,
        (width, height),
        flags=cv2.INTER_NEAREST,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=BACKGROUND,
    )
    image = np.full((height, width, 3), BACKGROUND, dtype=np.uint8)
    mask = cv2.warpPerspective(
        np.full((100, 160), 255, dtype=np.uint8),
        transform,
        (width, height),
        flags=cv2.INTER_NEAREST,
    )
    image[mask > 0] = warped[mask > 0]
    detection_box = cv2.boxPoints(cv2.minAreaRect(quad.astype(np.float32)))
    return image, make_detection(detection_box, image, 0.0)


def assert_is_photo(crop: np.ndarray) -> None:
    assert crop.size > 0
    assert crop.shape[0] > 0
    assert crop.shape[1] > 0
    center_pixel = crop[crop.shape[0] // 2, crop.shape[1] // 2]
    assert np.linalg.norm(center_pixel.astype(np.float32) - (90, 110, 130)) < 8


def test_crops_axis_aligned_rectangle() -> None:
    image, detection = make_scene(0.0)

    crop = crop_photo(image, detection)

    inset = int(np.ceil(DEFAULT_CROPPER_CONFIG.perspective_inset_pixels))
    assert PHOTO_SIZE[1] - 2 * inset <= crop.shape[0] <= PHOTO_SIZE[1]
    assert PHOTO_SIZE[0] - 2 * inset <= crop.shape[1] <= PHOTO_SIZE[0]
    assert_is_photo(crop)


def test_axis_aligned_crop_does_not_interpolate_pixels(
    monkeypatch: MonkeyPatch,
) -> None:
    image, detection = make_scene(0.0, edge_strips=True)

    def fail_warp(*args: object, **kwargs: object) -> np.ndarray:
        raise AssertionError("для выровненной фотографии интерполяция не требуется")

    monkeypatch.setattr(cv2, "warpPerspective", fail_warp)

    crop = crop_photo(image, detection)

    source_pixels = image.reshape(-1, 3)
    crop_pixels = crop.reshape(-1, 3)
    assert all(np.any(np.all(source_pixels == pixel, axis=1)) for pixel in crop_pixels)


def test_small_edge_offset_uses_direct_crop(monkeypatch: MonkeyPatch) -> None:
    quad = np.asarray(
        ((130, 110), (289, 111), (289, 210), (130, 209)),
        dtype=np.float32,
    )
    image, detection = make_perspective_scene(quad)

    def fail_warp(*args: object, **kwargs: object) -> np.ndarray:
        raise AssertionError("малое отклонение должно допускать обычное кадрирование")

    monkeypatch.setattr(cv2, "warpPerspective", fail_warp)
    config = CropperConfig(perspective_bypass_max_edge_offset_pixels=2.0)

    crop = crop_photo(image, detection, config)

    assert_is_photo(crop)


def test_crops_rectangle_with_positive_angle() -> None:
    image, detection = make_scene(7.0)

    crop = crop_photo(image, detection)

    inset = int(np.ceil(DEFAULT_CROPPER_CONFIG.perspective_inset_pixels))
    assert PHOTO_SIZE[1] - 2 * inset <= crop.shape[0] <= PHOTO_SIZE[1] + 2
    assert PHOTO_SIZE[0] - 2 * inset <= crop.shape[1] <= PHOTO_SIZE[0] + 2
    assert_is_photo(crop)


def test_crops_rectangle_with_negative_angle() -> None:
    image, detection = make_scene(-8.0)

    crop = crop_photo(image, detection)

    inset = int(np.ceil(DEFAULT_CROPPER_CONFIG.perspective_inset_pixels))
    assert PHOTO_SIZE[1] - 2 * inset <= crop.shape[0] <= PHOTO_SIZE[1] + 2
    assert PHOTO_SIZE[0] - 2 * inset <= crop.shape[1] <= PHOTO_SIZE[0] + 2
    assert_is_photo(crop)


def test_uses_full_resolution_box_after_preview_detection() -> None:
    image, full_detection = make_scene(
        5.0,
        canvas_size=(2400, 1800),
        center=(1200, 900),
        photo_size=(960, 640),
    )
    preview_width, preview_height = 600, 450
    full_box = full_detection.box_for_size(image.shape[1], image.shape[0])
    preview_box = full_box * np.asarray((0.25, 0.25), dtype=np.float32)
    preview_detection = make_detection(
        preview_box,
        np.empty((preview_height, preview_width, 3), dtype=np.uint8),
        full_detection.angle,
    )

    crop = crop_photo(image, preview_detection)

    inset = int(np.ceil(DEFAULT_CROPPER_CONFIG.perspective_inset_pixels))
    assert crop.shape[0] >= 640 - 2 * inset
    assert crop.shape[1] >= 960 - 2 * inset
    assert_is_photo(crop)


def test_preserves_coloured_control_strips_at_photo_edges() -> None:
    image, detection = make_scene(6.0, edge_strips=True)

    crop = crop_photo(image, detection)
    middle_y = crop.shape[0] // 2
    middle_x = crop.shape[1] // 2

    assert crop[middle_y, 3, 0] > 220
    assert crop[middle_y, -4, 1] > 220
    assert crop[3, middle_x, 2] > 220
    assert crop[-4, middle_x, 1] > 220
    assert crop[-4, middle_x, 2] > 220


def test_straightens_perspective_trapezoid() -> None:
    quad = np.asarray(
        ((110, 85), (305, 96), (286, 232), (125, 218)),
        dtype=np.float32,
    )
    image, detection = make_perspective_scene(quad)

    crop = crop_photo(image, detection)
    middle_y = crop.shape[0] // 2
    middle_x = crop.shape[1] // 2

    assert 182 <= crop.shape[1] <= 200
    assert 122 <= crop.shape[0] <= 145
    assert crop[middle_y, 3, 0] > 220
    assert crop[middle_y, -4, 1] > 220
    assert crop[3, middle_x, 2] > 220
    assert crop[-4, middle_x, 1] > 220
    assert crop[-4, middle_x, 2] > 220


def test_removes_asymmetric_substrate_strip() -> None:
    image = np.full((320, 420, 3), BACKGROUND, dtype=np.uint8)
    image[110:210, 130:290] = (90, 110, 130)
    detection_box = np.asarray(
        ((130, 110), (290, 110), (290, 226), (130, 226)),
        dtype=np.float32,
    )
    detection = make_detection(detection_box, image, 0.0)

    crop = crop_photo(image, detection)

    inset = int(np.ceil(DEFAULT_CROPPER_CONFIG.perspective_inset_pixels))
    assert 100 - 2 * inset <= crop.shape[0] <= 100
    assert 160 - 2 * inset <= crop.shape[1] <= 160
    assert np.all(crop[-1] == (90, 110, 130))


def test_handles_box_near_source_image_edge() -> None:
    image, detection = make_scene(
        -4.0,
        canvas_size=(300, 260),
        center=(34, 130),
        photo_size=(90, 130),
    )

    crop = crop_photo(image, detection)

    assert crop.size > 0
    short_side, long_side = sorted(crop.shape[:2])
    assert short_side >= 78
    assert long_side >= 116


def test_rotates_portrait_photo_to_landscape_without_reflection() -> None:
    image, detection = make_scene(
        0.0,
        photo_size=(100, 160),
        edge_strips=True,
    )

    crop = crop_photo(image, detection)
    middle_x = crop.shape[1] // 2

    assert crop.shape[1] > crop.shape[0]
    assert crop[3, middle_x, 0] > 220


def test_crop_photos_never_returns_empty_crops() -> None:
    first_image, first_detection = make_scene(4.0)
    _, second_detection = make_scene(-5.0, center=(210, 160))

    crops = crop_photos(first_image, (first_detection, second_detection))

    assert len(crops) == 2
    assert all(crop.size > 0 for crop in crops)


def test_result_is_three_channel_numpy_array() -> None:
    image, detection = make_scene(3.0)

    crop = crop_photo(image, detection)

    assert isinstance(crop, np.ndarray)
    assert crop.ndim == 3
    assert crop.shape[2] == 3
    assert crop.flags.c_contiguous
