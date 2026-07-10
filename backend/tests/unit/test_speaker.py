import numpy as np
import pytest

from pipeline.reframe import BBox
from pipeline.speaker import (
    Detection,
    apply_speaker_hysteresis,
    build_active_timeline,
    compute_motion_scores,
    mouth_motion_score,
    mouth_region,
    select_active_face,
)


def _det(x, y, w, h, score=0.9):
    return Detection(
        bbox=BBox(x, y, w, h),
        landmarks={
            "mouth_left": (x + w * 0.3, y + h * 0.7),
            "mouth_right": (x + w * 0.7, y + h * 0.7),
        },
        score=score,
    )


def test_mouth_region_from_landmarks():
    det = _det(100, 100, 100, 100)
    region = mouth_region(det)
    # Midpoint mouth ~ (150, 170); width 40 + margin; height ~25 (0.25 * bbox.h)
    assert region.x < 150 < region.x + region.w
    assert region.y < 170 < region.y + region.h
    assert region.h == pytest.approx(25, abs=2)


def test_mouth_motion_score_identical_patches_zero():
    patch = np.full((20, 20, 3), 128, dtype=np.uint8)
    assert mouth_motion_score(patch, patch) == pytest.approx(0.0, abs=0.01)


def test_mouth_motion_score_different_patches_high():
    a = np.full((20, 20, 3), 0, dtype=np.uint8)
    b = np.full((20, 20, 3), 255, dtype=np.uint8)
    score = mouth_motion_score(a, b)
    assert 0.5 < score <= 1.0


def test_select_active_face_empty():
    assert select_active_face([], {}) is None


def test_select_active_face_single():
    d = _det(0, 0, 50, 50)
    assert select_active_face([d], {0: 0.0}) == d


def test_select_active_face_clear_winner():
    a = _det(0, 0, 50, 50)
    b = _det(100, 0, 50, 50)
    winner = select_active_face([a, b], {0: 0.1, 1: 0.8})
    assert winner == b


def test_select_active_face_ambiguous_falls_back_to_largest():
    small = _det(0, 0, 40, 40)
    big = _det(100, 0, 100, 100)
    # Skor mirip -> pilih wajah terbesar.
    chosen = select_active_face([small, big], {0: 0.31, 1: 0.30})
    assert chosen == big


def test_apply_speaker_hysteresis_prevents_quick_switching():
    # Timeline: A selected, then B selected sebentar, lalu A lagi.
    timeline = [
        (0.0, 0),
        (0.5, 0),
        (1.0, 1),  # B muncul 0.5 detik -> belum cukup dwell
        (1.5, 0),  # kembali A
        (2.0, 0),
    ]
    result = apply_speaker_hysteresis(timeline, min_dwell_s=1.0)
    ids = [idx for _, idx in result]
    assert ids == [0, 0, 0, 0, 0]


def test_apply_speaker_hysteresis_switches_after_dwell():
    timeline = [
        (0.0, 0),
        (0.5, 1),
        (1.0, 1),
        (1.5, 1),
        (2.0, 1),
    ]
    result = apply_speaker_hysteresis(timeline, min_dwell_s=1.0)
    ids = [idx for _, idx in result]
    # Setelah B bertahan >=1 detik, switch ke B.
    assert ids == [0, 0, 0, 1, 1]


def test_apply_speaker_hysteresis_preserves_none():
    timeline = [(0.0, None), (0.5, 0), (1.0, 0)]
    result = apply_speaker_hysteresis(timeline, min_dwell_s=0.4)
    ids = [idx for _, idx in result]
    # Setelah wajah 0 bertahan cukup lama, switch dari None.
    assert ids == [None, None, 0]


def test_compute_motion_scores_identifies_moving_mouth():
    a = np.full((100, 100, 3), 100, dtype=np.uint8)
    b = np.full((100, 100, 3), 100, dtype=np.uint8)
    b[60:70, 40:60] = 200  # gerakan di area mulut

    det = _det(10, 10, 80, 80)
    frames = {0.0: a, 0.5: b}
    timeline = [(0.0, [det]), (0.5, [det])]
    scores = compute_motion_scores(frames, scale=1.0, timeline=timeline)
    assert len(scores) == 2
    # Frame pertama tidak punya prev -> skor 0.
    assert scores[0][1][0] == pytest.approx(0.0, abs=0.01)
    # Frame kedua punya gerakan -> skor > 0.
    assert scores[1][1][0] > 0.05


def test_build_active_timeline_picks_clear_speaker():
    # a lebih kecil -> fallback saat ambigu memilih b.
    a = _det(0, 0, 30, 30)
    b = _det(100, 0, 50, 50)
    timeline = [
        (0.0, [a, b]),
        (0.5, [a, b]),
    ]
    # Wajah 1 (b) jauh lebih aktif.
    motion_scores = [
        (0.0, {0: 0.0, 1: 0.0}),
        (0.5, {0: 0.05, 1: 0.5}),
    ]
    active = build_active_timeline(timeline, motion_scores, min_dwell_s=0.0)
    assert active[0][1] == b
    assert active[1][1] == b
