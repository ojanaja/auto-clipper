"""Pemilihan speaker aktif dari deteksi wajah berdasarkan gerakan mulut."""

import numpy as np

from pipeline.face_detect import Detection
from pipeline.reframe import BBox


def mouth_region(det: Detection, height_ratio: float = 0.25) -> BBox:
    """Kotak ROI sekitar mulut dari landmark mouth_left/right."""
    left = det.landmarks["mouth_left"]
    right = det.landmarks["mouth_right"]
    cx = (left[0] + right[0]) / 2
    cy = (left[1] + right[1]) / 2
    mouth_w = right[0] - left[0]
    margin = mouth_w * 0.5
    h = det.bbox.h * height_ratio
    w = mouth_w + 2 * margin
    return BBox(x=cx - w / 2, y=cy - h / 2, w=w, h=h)


def _extract_patch(frame: np.ndarray, bbox: BBox) -> np.ndarray:
    """Crop patch dari frame; clamp ke batas frame."""
    x1 = max(0, int(round(bbox.x)))
    y1 = max(0, int(round(bbox.y)))
    x2 = min(frame.shape[1], int(round(bbox.x + bbox.w)))
    y2 = min(frame.shape[0], int(round(bbox.y + bbox.h)))
    if x2 <= x1 or y2 <= y1:
        return np.zeros((1, 1, 3), dtype=np.uint8)
    return frame[y1:y2, x1:x2]


def mouth_motion_score(prev_patch: np.ndarray | None, cur_patch: np.ndarray) -> float:
    """Skor gerakan mulut 0..1 berdasarkan mean abs diff grayscale antar patch.

    Patch identik → 0; perbedaan maksimal → mendekati 1.
    """
    if prev_patch is None or cur_patch is None:
        return 0.0

    import cv2  # ponytail: ditunda; lihat catatan di face_detect.py

    def _gray(patch: np.ndarray) -> np.ndarray:
        if len(patch.shape) == 3 and patch.shape[2] >= 3:
            return cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY)
        if len(patch.shape) == 3:
            return patch[:, :, 0]
        return patch

    prev = _gray(prev_patch).astype(np.float32)
    cur = _gray(cur_patch).astype(np.float32)
    if prev.shape != cur.shape:
        cur = cv2.resize(cur, (prev.shape[1], prev.shape[0]))
    diff = np.mean(np.abs(cur - prev))
    return float(np.clip(diff / 255.0, 0.0, 1.0))


def compute_motion_scores(
    frames: dict[float, np.ndarray],
    scale: float,
    timeline: list[tuple[float, list[Detection]]],
) -> list[tuple[float, dict[int, float]]]:
    """Hitung skor gerakan mulut per wajah per timestamp.

    Args:
        frames: dict timestamp -> frame resized (sample coords).
        scale: sample_width / source_width.
        timeline: list (timestamp, list Detection di source coords).

    Returns:
        List (timestamp, dict face_index -> motion_score).
    """
    scores: list[tuple[float, dict[int, float]]] = []
    prev_patches: dict[int, np.ndarray] = {}
    for t, detections in timeline:
        frame = frames.get(t)
        frame_scores: dict[int, float] = {}
        for idx, det in enumerate(detections):
            region = mouth_region(det)
            sample_region = BBox(
                x=region.x * scale,
                y=region.y * scale,
                w=region.w * scale,
                h=region.h * scale,
            )
            patch = _extract_patch(frame, sample_region) if frame is not None else None
            score = mouth_motion_score(prev_patches.get(idx), patch)
            frame_scores[idx] = score
            if patch is not None:
                prev_patches[idx] = patch
        scores.append((t, frame_scores))
    return scores


def select_active_face(
    detections: list[Detection],
    motion_scores: dict[int, float],
    min_delta: float = 0.05,
) -> Detection | None:
    """Pilih wajah yang paling aktif bicara.

    - 0 wajah → None
    - 1 wajah → wajah itu
    - ≥2 wajah → pilih skor tertinggi bila selisih > min_delta; else fallback wajah terbesar.
    """
    if not detections:
        return None
    if len(detections) == 1:
        return detections[0]

    indexed = list(enumerate(detections))
    indexed.sort(key=lambda item: motion_scores.get(item[0], 0.0), reverse=True)
    top_idx, top_det = indexed[0]
    second_idx, _ = indexed[1]
    top_score = motion_scores.get(top_idx, 0.0)
    second_score = motion_scores.get(second_idx, 0.0)

    if top_score - second_score > min_delta:
        return top_det

    return max(detections, key=lambda d: d.bbox.w * d.bbox.h)


def apply_speaker_hysteresis(
    timeline: list[tuple[float, int | None]], min_dwell_s: float = 1.5
) -> list[tuple[float, int | None]]:
    """Stabilkan pilihan speaker: pindah ke wajah baru hanya bila bertahan min_dwell_s."""
    if not timeline:
        return []

    result = []
    current_id = timeline[0][1]
    candidate_id: int | None = None
    candidate_start = 0.0

    for t, selected_id in timeline:
        if selected_id == current_id:
            candidate_id = None
            result.append((t, current_id))
            continue

        if selected_id != candidate_id:
            candidate_id = selected_id
            candidate_start = t

        if candidate_id is not None and t - candidate_start >= min_dwell_s:
            current_id = candidate_id
            candidate_id = None

        result.append((t, current_id))

    return result


def build_active_timeline(
    timeline: list[tuple[float, list[Detection]]],
    motion_scores: list[tuple[float, dict[int, float]]],
    min_dwell_s: float = 1.5,
) -> list[tuple[float, Detection | None]]:
    """Gabung deteksi + motion score → timeline speaker aktif yang sudah di-hysteresis."""
    selected: list[tuple[float, int | None]] = []
    for (t, detections), (_, scores) in zip(timeline, motion_scores):
        det = select_active_face(detections, scores)
        selected.append((t, detections.index(det) if det is not None else None))

    stable = apply_speaker_hysteresis(selected, min_dwell_s=min_dwell_s)
    return [
        (t, detections[idx] if idx is not None else None)
        for (t, idx), (_, detections) in zip(stable, timeline)
    ]
