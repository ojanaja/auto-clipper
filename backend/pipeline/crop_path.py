"""Membangun jalur crop dinamis dari timeline wajah aktif."""

from pipeline.face_detect import Detection
from pipeline.reframe import CropBox, compute_crop_box, smooth_crop_boxes


def build_crop_path(
    frame_w: int,
    frame_h: int,
    active_timeline: list[tuple[float, Detection | None]],
    target_ratio: float,
) -> list[tuple[float, CropBox]]:
    """Bangun jalur crop per timestamp dari speaker aktif.

    Tiap entri: wajah aktif → crop box yang memuat wajah itu; None → center-crop.
    Hasil di-smooth untuk mengurangi jitter.
    """
    raw_boxes: list[CropBox] = []
    for _t, det in active_timeline:
        faces = [det.bbox] if det is not None else []
        box = compute_crop_box(frame_w, frame_h, faces, target_ratio=target_ratio)
        raw_boxes.append(box)

    smoothed = smooth_crop_boxes(raw_boxes, window=5)
    return [(active_timeline[i][0], smoothed[i]) for i in range(len(active_timeline))]


def simplify_path(
    path: list[tuple[float, CropBox]], min_delta_px: float = 6
) -> list[tuple[float, CropBox]]:
    """Buang titik jalur yang x/y-nya nyaris sama dengan titik sebelumnya.

    Mengurangi panjang expression ffmpeg tanpa mengubah gerakan signifikan.
    """
    if len(path) <= 2:
        return path

    kept = [path[0]]
    for t, box in path[1:]:
        last = kept[-1][1]
        if abs(box.x - last.x) >= min_delta_px or abs(box.y - last.y) >= min_delta_px:
            kept.append((t, box))

    # Pastikan titik akhir selalu ada.
    if kept[-1][0] != path[-1][0]:
        kept.append(path[-1])
    return kept
