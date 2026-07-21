"""Deteksi wajah sampled dengan YuNet (OpenCV FaceDetectorYN).

Tidak decode seluruh video: hanya frame pada interval 1/fps detik yang dibaca.
Koordinat hasil deteksi di-frame kecil (lebar 640) diskala balik ke resolusi sumber.
"""

import os
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from pipeline.reframe import BBox

# ponytail: import cv2 (opencv) ditunda ke dalam fungsi yang memakainya.
# cv2 punya DLL rapuh di Windows/PyInstaller; kalau di-import di top-level,
# kegagalan load-nya menjatuhkan seluruh backend saat startup (app -> orchestrator
# -> face_detect) padahal face-tracking default OFF dan jalur transkrip tak butuh cv2.

YUNET_MODEL_URL = (
    "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/"
    "face_detection_yunet_2023mar.onnx"
)
YUNET_MODEL_FILENAME = "face_detection_yunet_2023mar.onnx"

_SAMPLE_WIDTH = 640


class FaceDetectError(Exception):
    pass


@dataclass
class Detection:
    bbox: BBox
    landmarks: dict[str, tuple[float, float]]
    score: float


def _bundled_model_dir() -> Path | None:
    """Direktori model saat di-bundle: di samping executable sidecar."""
    if getattr(sys, "frozen", False):
        # Sidecar executable berada di resources/backend/; model dikirim di
        # resources/backend/models/ agar terlihat oleh build manifest.
        exe_dir = Path(sys.executable).parent
        return exe_dir / "models"
    return None


def default_model_dir() -> Path:
    bundled = _bundled_model_dir()
    if bundled is not None:
        return bundled
    return Path.home() / ".autoclip" / "models"


def yunet_model_path() -> Path:
    """Path ke model YuNet; override via env AUTOCLIP_YUNET_MODEL."""
    env = os.environ.get("AUTOCLIP_YUNET_MODEL")
    if env:
        return Path(env)
    return default_model_dir() / YUNET_MODEL_FILENAME


def ensure_model(model_path: Path | None = None) -> Path:
    """Pastikan model YuNet tersedia di disk; download bila belum ada."""
    path = Path(model_path or yunet_model_path())
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        urllib.request.urlretrieve(YUNET_MODEL_URL, str(path))
    except Exception as e:
        raise FaceDetectError(f"Gagal download model YuNet: {e}") from e
    return path


def _scale_detection(det: Detection, scale_x: float, scale_y: float) -> Detection:
    """Skala koordinat deteksi dari frame sample ke resolusi sumber."""
    bbox = det.bbox
    scaled_bbox = BBox(
        x=bbox.x * scale_x,
        y=bbox.y * scale_y,
        w=bbox.w * scale_x,
        h=bbox.h * scale_y,
    )
    scaled_landmarks = {
        name: (x * scale_x, y * scale_y) for name, (x, y) in det.landmarks.items()
    }
    return Detection(bbox=scaled_bbox, landmarks=scaled_landmarks, score=det.score)


def _parse_faces(array: np.ndarray | None) -> list[Detection]:
    """Parse output FaceDetectorYN (N x 15) jadi list Detection."""
    if array is None or len(array) == 0:
        return []
    detections = []
    for row in array:
        x, y, w, h = row[:4].tolist()
        landmarks = {
            "right_eye": (float(row[4]), float(row[5])),
            "left_eye": (float(row[6]), float(row[7])),
            "nose": (float(row[8]), float(row[9])),
            "mouth_right": (float(row[10]), float(row[11])),
            "mouth_left": (float(row[12]), float(row[13])),
        }
        score = float(row[14])
        detections.append(Detection(bbox=BBox(x, y, w, h), landmarks=landmarks, score=score))
    return detections


def sample_frames(
    video_path: str | Path,
    start: float,
    end: float,
    fps: int = 2,
    sample_width: int = _SAMPLE_WIDTH,
) -> tuple[dict[float, np.ndarray], float]:
    """Ambil frame sample yang di-resize untuk scoring gerak mulut.

    Returns:
        (dict timestamp -> resized frame, scale factor sample/source_width).
    """
    if start >= end:
        return {}, 1.0

    import cv2

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise FaceDetectError(f"Tidak bisa membuka video {video_path}")

    frames: dict[float, np.ndarray] = {}
    step = 1.0 / fps
    t = start
    scale = 1.0
    while t < end:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        if not ok or frame is None:
            t += step
            continue
        h, w = frame.shape[:2]
        scale = sample_width / w
        sample_height = int(round(h * scale))
        resized = cv2.resize(frame, (sample_width, sample_height))
        frames[t] = resized.astype(np.uint8)
        t += step

    cap.release()
    return frames, scale


def detect_faces_sampled(
    video_path: str | Path,
    start: float,
    end: float,
    fps: int = 2,
    detector=None,
    model_path: Path | None = None,
    sample_width: int = _SAMPLE_WIDTH,
) -> list[tuple[float, list[Detection]]]:
    """Deteksi wajah pada frame sample dalam rentang [start, end].

    Args:
        video_path: path ke video sumber.
        start, end: rentang waktu dalam detik (inklusif start, eksklusif end).
        fps: berapa frame per detik yang di-sample.
        detector: instance FaceDetectorYN (injectable untuk test).
        model_path: path model YuNet; default via yunet_model_path().
        sample_width: lebar frame sebelum deteksi (resize untuk kecepatan).

    Returns:
        List pasangan (timestamp, list Detection) untuk tiap sample point.
    """
    if start >= end:
        return []

    import cv2

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise FaceDetectError(f"Tidak bisa membuka video {video_path}")

    own_detector = detector is None
    if own_detector:
        model_file = ensure_model(model_path)
        detector = cv2.FaceDetectorYN.create(
            str(model_file),
            "",
            input_size=(sample_width, sample_width),
            score_threshold=0.9,
            nms_threshold=0.3,
            top_k=5000,
        )

    timeline: list[tuple[float, list[Detection]]] = []
    step = 1.0 / fps
    t = start
    while t < end:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        if not ok or frame is None:
            timeline.append((t, []))
            t += step
            continue

        h, w = frame.shape[:2]
        scale = sample_width / w
        sample_height = int(round(h * scale))
        resized = cv2.resize(frame, (sample_width, sample_height))
        resized = resized.astype(np.float32)

        detector.setInputSize((sample_width, sample_height))
        try:
            detector._current_time = t
        except AttributeError:
            pass  # Seam hanya untuk fake detector di unit test.
        _, faces = detector.detect(resized)
        detections = _parse_faces(faces)
        scaled = [_scale_detection(d, 1 / scale, 1 / scale) for d in detections]
        timeline.append((t, scaled))
        t += step

    cap.release()
    if own_detector:
        # FaceDetectorYN tidak punya release() public; biarkan GC.
        pass
    return timeline
