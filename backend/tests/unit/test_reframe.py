import pytest

from pipeline.reframe import BBox, CropBox, compute_crop_box, smooth_crop_boxes

FRAME_W, FRAME_H = 1920, 1080
# Crop 9:16 tertinggi di frame 1080p: h=1080, w=607 (dibulatkan genap ke 606).
EXPECTED_W = 606
EXPECTED_H = 1080


def _assert_inside_frame(crop: CropBox):
    assert crop.x >= 0
    assert crop.y >= 0
    assert crop.x + crop.w <= FRAME_W
    assert crop.y + crop.h <= FRAME_H


def _assert_ratio(crop: CropBox, ratio: float):
    assert crop.w / crop.h == pytest.approx(ratio, abs=0.01)


def _assert_916(crop: CropBox):
    _assert_ratio(crop, 9 / 16)


# --- compute_crop_box ---


def test_face_in_center_gives_centered_crop():
    face = BBox(x=910, y=490, w=100, h=100)  # tengah frame
    crop = compute_crop_box(FRAME_W, FRAME_H, [face])

    assert crop.w == EXPECTED_W
    assert crop.h == EXPECTED_H
    _assert_916(crop)
    _assert_inside_frame(crop)
    # Wajah harus di dalam crop.
    assert crop.x <= face.x and face.x + face.w <= crop.x + crop.w
    # Crop kurang-lebih centered di wajah.
    assert abs((crop.x + crop.w / 2) - (face.x + face.w / 2)) < 5


def test_face_at_left_edge_clamps_crop_inside_frame():
    face = BBox(x=0, y=490, w=100, h=100)
    crop = compute_crop_box(FRAME_W, FRAME_H, [face])

    assert crop.x == 0  # clamp kiri
    _assert_inside_frame(crop)
    assert crop.x <= face.x and face.x + face.w <= crop.x + crop.w


def test_face_at_right_edge_clamps_crop_inside_frame():
    face = BBox(x=1820, y=490, w=100, h=100)
    crop = compute_crop_box(FRAME_W, FRAME_H, [face])

    assert crop.x + crop.w == FRAME_W  # clamp kanan
    _assert_inside_frame(crop)
    assert crop.x <= face.x and face.x + face.w <= crop.x + crop.w


def test_two_faces_crop_centers_between_them():
    faces = [BBox(x=700, y=400, w=100, h=100), BBox(x=1100, y=400, w=100, h=100)]
    crop = compute_crop_box(FRAME_W, FRAME_H, faces)

    _assert_inside_frame(crop)
    # Pusat crop kira-kira di tengah kedua wajah (pusat gabungan = 950).
    assert abs((crop.x + crop.w / 2) - 950) < 5


def test_no_face_falls_back_to_center_crop():
    crop = compute_crop_box(FRAME_W, FRAME_H, [])

    assert crop.w == EXPECTED_W
    assert crop.h == EXPECTED_H
    _assert_inside_frame(crop)
    # Centered horizontal.
    assert abs((crop.x + crop.w / 2) - FRAME_W / 2) < 5


def test_portrait_source_crop_fits_width():
    # Sumber sudah portrait (720x1280): crop pakai lebar penuh.
    crop = compute_crop_box(720, 1280, [])
    assert crop.w == 720
    assert crop.h == 1280
    assert crop.x == 0 and crop.y == 0


def test_narrower_than_916_source_letterboxes_height():
    # Sumber lebih sempit dari 9:16 (mis. 500x1280): lebar penuh, tinggi menyesuaikan.
    crop = compute_crop_box(500, 1280, [])
    assert crop.w == 500
    assert crop.h == 888  # even(500 * 16/9)
    _assert_916_ratio = crop.w / crop.h
    assert _assert_916_ratio == pytest.approx(9 / 16, abs=0.01)
    assert crop.y >= 0 and crop.y + crop.h <= 1280


def test_crop_dimensions_are_even():
    # Encoder butuh dimensi genap.
    crop = compute_crop_box(1919, 1079, [])
    assert crop.w % 2 == 0
    assert crop.h % 2 == 0


def test_custom_target_ratio_1_1():
    crop = compute_crop_box(1920, 1080, [], target_ratio=1 / 1)
    _assert_ratio(crop, 1.0)
    _assert_inside_frame(crop)
    assert crop.w == crop.h == 1080
    assert abs((crop.x + crop.w / 2) - FRAME_W / 2) < 5


def test_custom_target_ratio_16_9():
    crop = compute_crop_box(1920, 1080, [], target_ratio=16 / 9)
    _assert_ratio(crop, 16 / 9)
    _assert_inside_frame(crop)
    assert crop.w == 1920
    assert crop.h == 1080


def test_custom_target_ratio_clamps_inside_frame():
    face = BBox(x=0, y=490, w=100, h=100)
    crop = compute_crop_box(1920, 1080, [face], target_ratio=4 / 5)
    _assert_ratio(crop, 4 / 5)
    assert crop.x == 0
    _assert_inside_frame(crop)
    assert crop.x <= face.x and face.x + face.w <= crop.x + crop.w


# --- smooth_crop_boxes ---


def _boxes_from_xs(xs):
    return [CropBox(x=x, y=0, w=EXPECTED_W, h=EXPECTED_H) for x in xs]


def test_smoothing_reduces_jitter():
    # Posisi x lompat-lompat drastis antar frame.
    jumpy_xs = [100, 700, 100, 700, 100, 700, 100, 700]
    smoothed = smooth_crop_boxes(_boxes_from_xs(jumpy_xs), window=5)

    assert len(smoothed) == len(jumpy_xs)
    deltas = [abs(smoothed[i + 1].x - smoothed[i].x) for i in range(len(smoothed) - 1)]
    # Tanpa smoothing delta 600; setelah smoothing harus jauh di bawah.
    assert max(deltas) < 300


def test_smoothing_preserves_stable_positions():
    stable_xs = [400] * 10
    smoothed = smooth_crop_boxes(_boxes_from_xs(stable_xs), window=5)
    assert all(b.x == pytest.approx(400) for b in smoothed)


def test_smoothing_empty_list():
    assert smooth_crop_boxes([], window=5) == []


def test_smoothing_single_box():
    boxes = _boxes_from_xs([250])
    assert smooth_crop_boxes(boxes, window=5) == boxes
