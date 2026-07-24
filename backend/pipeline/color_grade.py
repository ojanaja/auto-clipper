"""Color grade render: style konkret -> daftar filter ffmpeg -vf.

Dipisah dari customization.py (persistence/API) sama seperti pipeline/subtitle.py
memisah SubtitleStyle dari SubtitleStyleConfig -- modul ini cuma nerima nilai
jadi, tak tahu-menahu soal preset/preset gallery (dimiliki frontend) atau
persistence.
"""

import math
from dataclasses import dataclass


@dataclass
class ColorGradeStyle:
    contrast: float = 1.0
    brightness: float = 0.0
    saturation: float = 1.0
    gamma: float = 1.0
    temperature: int = 0
    vignette: float = 0.0


def _kelvin_from_temperature(temperature: int) -> int:
    """Petakan slider suhu (-100..100, 0=netral/6500K) ke Kelvin filter colortemperature.

    Positif (hangat) -> Kelvin lebih rendah (oranye, mis. cahaya lilin ~1900K).
    Negatif (dingin) -> Kelvin lebih tinggi (biru, mis. langit mendung ~10000K)."""
    return max(1000, min(40000, 6500 - temperature * 30))


def build_color_grade_filters(style: ColorGradeStyle) -> list[str]:
    """Bangun daftar filter ffmpeg dari style.

    Filter yang nilainya identity (default) di-skip supaya video tak disentuh
    sama sekali kalau semua slider netral -- konsisten dgn prinsip "kustomisasi
    nonaktif = tak ada filter tambahan" yang dipakai subtitle_style.
    """
    filters = []

    eq_parts = []
    if style.contrast != 1.0:
        eq_parts.append(f"contrast={style.contrast}")
    if style.brightness != 0.0:
        eq_parts.append(f"brightness={style.brightness}")
    if style.saturation != 1.0:
        eq_parts.append(f"saturation={style.saturation}")
    if style.gamma != 1.0:
        eq_parts.append(f"gamma={style.gamma}")
    if eq_parts:
        filters.append("eq=" + ":".join(eq_parts))

    if style.temperature != 0:
        kelvin = _kelvin_from_temperature(style.temperature)
        filters.append(f"colortemperature=temperature={kelvin}")

    if style.vignette > 0:
        # angle kecil = vignette kuat. Interpolasi PI/2 (nyaris tak kelihatan)
        # -> PI/8 (kuat) selaras dgn skala 0..1 slider vignette.
        angle = (math.pi / 2) - style.vignette * (math.pi / 2 - math.pi / 8)
        filters.append(f"vignette=angle={angle:.4f}")

    return filters
