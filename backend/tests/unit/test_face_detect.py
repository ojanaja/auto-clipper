from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from pipeline.face_detect import (
    YUNET_MODEL_FILENAME,
    Detection,
    _scale_detection,
    default_model_dir,
    detect_faces_sampled,
    ensure_model,
    yunet_model_path,
)
from pipeline.reframe import BBox


def test_yunet_model_path_env(monkeypatch):
    monkeypatch.setenv("AUTOCLIP_YUNET_MODEL", "/custom/yunet.onnx")
    assert yunet_model_path() == Path("/custom/yunet.onnx")


def test_yunet_model_path_default():
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.delenv("AUTOCLIP_YUNET_MODEL", raising=False)
    path = yunet_model_path()
    assert path.name == YUNET_MODEL_FILENAME
    assert path.parent == default_model_dir()
    monkeypatch.undo()


def test_ensure_model_existing(tmp_path):
    model_path = tmp_path / YUNET_MODEL_FILENAME
    model_path.write_text("model")
    assert ensure_model(model_path) == model_path


def test_ensure_model_downloads(tmp_path):
    model_path = tmp_path / YUNET_MODEL_FILENAME
    fake_data = b"onnx bytes"

    with patch("urllib.request.urlretrieve") as urlretrieve:
        urlretrieve.side_effect = lambda url, dst: Path(dst).write_bytes(fake_data)
        result = ensure_model(model_path)

    assert result == model_path
    assert model_path.read_bytes() == fake_data
    urlretrieve.assert_called_once()


def test_detection_scale():
    det = Detection(
        bbox=BBox(x=100, y=200, w=50, h=60),
        landmarks={
            "right_eye": (110, 210),
            "left_eye": (130, 210),
            "nose": (120, 230),
            "mouth_right": (110, 250),
            "mouth_left": (130, 250),
        },
        score=0.95,
    )
    scaled = _scale_detection(det, scale_x=2.0, scale_y=0.5)
    assert scaled.bbox == BBox(x=200, y=100, w=100, h=30)
    assert scaled.landmarks["right_eye"] == (220, 105)
    assert scaled.score == pytest.approx(0.95)


class FakeDetector:
    """detections_per_time: dict time -> list of Detection (in sample coords)."""

    def __init__(self, detections_per_time):
        self._detections = detections_per_time
        self._current_time = 0.0

    def setInputSize(self, size):
        pass

    def detect(self, frame):
        dets = self._detections.get(self._current_time, [])
        if not dets:
            return (1, None)
        rows = []
        for d in dets:
            row = [
                d.bbox.x,
                d.bbox.y,
                d.bbox.w,
                d.bbox.h,
                d.landmarks.get("right_eye", (0, 0))[0],
                d.landmarks.get("right_eye", (0, 0))[1],
                d.landmarks.get("left_eye", (0, 0))[0],
                d.landmarks.get("left_eye", (0, 0))[1],
                d.landmarks.get("nose", (0, 0))[0],
                d.landmarks.get("nose", (0, 0))[1],
                d.landmarks.get("mouth_right", (0, 0))[0],
                d.landmarks.get("mouth_right", (0, 0))[1],
                d.landmarks.get("mouth_left", (0, 0))[0],
                d.landmarks.get("mouth_left", (0, 0))[1],
                d.score,
            ]
            rows.append(row)
        return (1, np.array(rows, dtype=np.float32))


def _make_fake_detector(detections_per_time):
    return FakeDetector(detections_per_time)


class FakeCapture:
    def __init__(self, frames_by_time):
        self._frames = frames_by_time
        self._time = 0.0

    def isOpened(self):
        return True

    def get(self, prop):
        if prop == 5:  # CAP_PROP_FPS
            return 30.0
        if prop == 7:  # CAP_PROP_FRAME_COUNT
            return max(int(t * 30) for t in self._frames) + 1
        return 0.0

    def set(self, prop, value):
        if prop == 0:  # CAP_PROP_POS_MSEC
            self._time = value / 1000.0
        return True

    def read(self):
        frame = self._frames.get(self._time)
        if frame is None:
            return (False, None)
        return (True, frame)

    def release(self):
        pass


def test_detect_faces_sampled_scales_and_filters_by_time(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTOCLIP_YUNET_MODEL", str(tmp_path / YUNET_MODEL_FILENAME))
    (tmp_path / YUNET_MODEL_FILENAME).write_text("model")

    # Sumber 1920x1080; deteksi berjalan di frame resized 640x360 (scale 1/3).
    # Bbox di sample coords; hasil akhir harus 3x ke sumber.
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)

    detections = {
        0.0: [
            Detection(
                bbox=BBox(x=100, y=50, w=60, h=70),
                landmarks={
                    "right_eye": (105, 55),
                    "left_eye": (125, 55),
                    "nose": (115, 70),
                    "mouth_right": (105, 85),
                    "mouth_left": (125, 85),
                },
                score=0.91,
            )
        ],
        0.5: [],
    }
    detector = _make_fake_detector(detections)

    frames = {0.0: frame, 0.5: frame}

    with patch("pipeline.face_detect.cv2.VideoCapture", return_value=FakeCapture(frames)):
        timeline = detect_faces_sampled(
            "video.mp4", start=0.0, end=1.0, fps=2, detector=detector
        )

    assert len(timeline) == 2
    t0, dets0 = timeline[0]
    assert t0 == pytest.approx(0.0)
    assert len(dets0) == 1
    # Bbox terskala balik 3x.
    assert dets0[0].bbox == BBox(x=300, y=150, w=180, h=210)
    # Timestamp 0.5 detik tidak punya wajah.
    t05, dets05 = timeline[1]
    assert t05 == pytest.approx(0.5)
    assert dets05 == []


def test_detect_faces_sampled_only_inside_range(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTOCLIP_YUNET_MODEL", str(tmp_path / YUNET_MODEL_FILENAME))
    (tmp_path / YUNET_MODEL_FILENAME).write_text("model")

    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    detections = {
        0.0: [Detection(bbox=BBox(10, 10, 10, 10), landmarks={}, score=0.9)],
        0.5: [Detection(bbox=BBox(20, 20, 10, 10), landmarks={}, score=0.9)],
    }
    detector = _make_fake_detector(detections)
    frames = {0.0: frame, 0.5: frame}

    with patch("pipeline.face_detect.cv2.VideoCapture", return_value=FakeCapture(frames)):
        timeline = detect_faces_sampled(
            "video.mp4", start=0.2, end=0.6, fps=2, detector=detector
        )

    times = [t for t, _ in timeline]
    assert 0.0 not in times
    assert 0.2 in times
