import pytest

from pipeline.crop_path import build_crop_path, simplify_path
from pipeline.face_detect import Detection
from pipeline.reframe import BBox, CropBox


def _det(x, y, w, h):
    return Detection(bbox=BBox(x, y, w, h), landmarks={}, score=0.9)


def test_build_crop_path_follows_active_face():
    frame_w, frame_h = 1920, 1080
    active = [
        (0.0, _det(900, 400, 120, 120)),
        (1.0, None),  # fallback center
    ]
    path = build_crop_path(frame_w, frame_h, active, target_ratio=9 / 16)
    assert len(path) == 2
    # Wajah di tengah kanan -> crop box seharusnya memuat wajah.
    assert path[0][1].x <= 900 and 1020 <= path[0][1].x + path[0][1].w
    # Fallback center -> crop box di tengah horizontal.
    assert path[1][1].x + path[1][1].w / 2 == pytest.approx(960, abs=10)
    # Semua crop ratio 9:16.
    for _, box in path:
        assert box.w / box.h == pytest.approx(9 / 16, abs=0.02)


def test_build_crop_path_dimensions_constant():
    frame_w, frame_h = 1920, 1080
    active = [
        (0.0, _det(500, 400, 100, 100)),
        (0.5, _det(1000, 400, 100, 100)),
        (1.0, _det(1400, 400, 100, 100)),
    ]
    path = build_crop_path(frame_w, frame_h, active, target_ratio=9 / 16)
    widths = [box.w for _, box in path]
    heights = [box.h for _, box in path]
    assert len(set(widths)) == 1
    assert len(set(heights)) == 1


def test_simplify_path_drops_redundant_points():
    path = [
        (0.0, CropBox(x=100, y=100, w=200, h=300)),
        (0.5, CropBox(x=101, y=100, w=200, h=300)),
        (1.0, CropBox(x=102, y=100, w=200, h=300)),
        (1.5, CropBox(x=150, y=100, w=200, h=300)),
    ]
    simplified = simplify_path(path, min_delta_px=6)
    # Titik awal dan titik akhir (setelah gerakan signifikan) dipertahankan;
    # titik tengah redundan dibuang.
    assert len(simplified) == 2
    assert simplified[0][0] == 0.0
    assert simplified[-1][0] == 1.5


def test_simplify_path_keeps_all_when_moving():
    path = [
        (0.0, CropBox(x=0, y=0, w=100, h=100)),
        (0.5, CropBox(x=50, y=0, w=100, h=100)),
        (1.0, CropBox(x=100, y=0, w=100, h=100)),
    ]
    simplified = simplify_path(path, min_delta_px=6)
    assert len(simplified) == 3
