from dataclasses import dataclass, replace

_DEFAULT_TARGET_RATIO = 9 / 16


@dataclass
class BBox:
    """Bounding box wajah dalam koordinat piksel frame sumber."""

    x: float
    y: float
    w: float
    h: float


@dataclass
class CropBox:
    x: int
    y: int
    w: int
    h: int


def _even(n: float) -> int:
    """Bulatkan ke bawah ke bilangan genap (syarat encoder)."""
    return int(n) // 2 * 2


def compute_crop_box(
    frame_w: int, frame_h: int, faces: list[BBox], target_ratio: float = _DEFAULT_TARGET_RATIO
) -> CropBox:
    """Hitung crop box target ratio terbesar; tanpa wajah -> center crop.

    Multi wajah: crop dipusatkan pada titik tengah gabungan semua bounding box.
    Crop selalu di-clamp agar tidak keluar dari frame sumber.
    """
    if frame_w / frame_h >= target_ratio:
        crop_h = _even(frame_h)
        crop_w = _even(crop_h * target_ratio)
    else:
        crop_w = _even(frame_w)
        crop_h = _even(crop_w / target_ratio)

    if faces:
        left = min(f.x for f in faces)
        right = max(f.x + f.w for f in faces)
        top = min(f.y for f in faces)
        bottom = max(f.y + f.h for f in faces)
        center_x = (left + right) / 2
        center_y = (top + bottom) / 2
    else:
        center_x = frame_w / 2
        center_y = frame_h / 2

    x = int(center_x - crop_w / 2)
    y = int(center_y - crop_h / 2)
    x = max(0, min(x, frame_w - crop_w))
    y = max(0, min(y, frame_h - crop_h))
    return CropBox(x=x, y=y, w=crop_w, h=crop_h)


def smooth_crop_boxes(boxes: list[CropBox], window: int = 5) -> list[CropBox]:
    """Haluskan posisi crop antar frame dengan centered moving average.

    Dimensi (w, h) tidak berubah; hanya posisi x/y yang dihaluskan agar
    crop tidak jitter mengikuti deteksi wajah yang lompat-lompat.
    """
    if len(boxes) <= 1:
        return boxes

    half = window // 2
    smoothed = []
    for i, box in enumerate(boxes):
        neighbors = boxes[max(0, i - half) : i + half + 1]
        avg_x = sum(b.x for b in neighbors) / len(neighbors)
        avg_y = sum(b.y for b in neighbors) / len(neighbors)
        smoothed.append(replace(box, x=round(avg_x), y=round(avg_y)))
    return smoothed
