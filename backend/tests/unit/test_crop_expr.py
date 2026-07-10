from pipeline.crop_expr import build_crop_x_expr, build_crop_y_expr
from pipeline.reframe import CropBox


def test_build_crop_x_expr_contains_between_and_lerp():
    # Path timestamps absolut; clip_start=10s jadi relatif 0s dan 1s.
    path = [
        (10.0, CropBox(x=100, y=200, w=1080, h=1920)),
        (11.0, CropBox(x=300, y=200, w=1080, h=1920)),
    ]
    expr = build_crop_x_expr(path, clip_start=10.0, frame_w=1920, crop_w=1080)
    assert "between(" in expr
    assert "lerp(" in expr
    assert "clip(" in expr
    assert "between(t,0,1)" in expr


def test_build_crop_x_expr_single_point_is_constant():
    path = [(0.0, CropBox(x=500, y=200, w=1080, h=1920))]
    expr = build_crop_x_expr(path, clip_start=0.0, frame_w=1920, crop_w=1080)
    assert "between" not in expr
    assert "500" in expr


def test_build_crop_y_expr_uses_y_values():
    path = [
        (0.0, CropBox(x=100, y=200, w=1080, h=1920)),
        (1.0, CropBox(x=100, y=400, w=1080, h=1920)),
    ]
    expr = build_crop_y_expr(path, clip_start=0.0, frame_h=1080, crop_h=1920)
    assert "lerp(200,400" in expr


def test_expr_clamps_to_frame_bounds():
    path = [(0.0, CropBox(x=100, y=200, w=1080, h=1920))]
    xexpr = build_crop_x_expr(path, clip_start=0.0, frame_w=1920, crop_w=1080)
    assert "clip(" in xexpr
    assert "0,840" in xexpr  # frame_w - crop_w = 840
