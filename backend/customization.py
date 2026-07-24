"""Konfigurasi kustomisasi visual (tab Kustomisasi) — model + persistence.

Disimpan terpisah dari AppConfig (config.py) supaya bisa diimpor/diekspor
sebagai file JSON preset mandiri, sesuai fitur Impor/Ekspor/Reset di tab
Kustomisasi. Tiap section (Subtitle/Overlay Sumber/Watermark/Overlay
Gambar/Color Grade) baru punya flag enabled di Fase 1a; field detail
ditambah bertahap: Subtitle (template + style) di Fase 1b, Color Grade
(preset + slider) di Fase 1c, sisanya di 1d-1e.

Section "template" (nama preset dipilih user di UI) cuma label tampilan —
field style konkret (warna, outline, dsb) yang disimpan & dipakai render
adalah field yang benar-benar dikirim; daftar preset "template X = kombinasi
field apa" itu sendiri dimiliki frontend (single source of truth di sana),
backend cuma validasi nama template termasuk salah satu yang dikenal.
"""

import json
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path


class CustomizationError(Exception):
    """Input kustomisasi tidak valid."""


ALLOWED_SUBTITLE_TEMPLATES = {
    "karaoke_pop",
    "hormozi",
    "neon_glow",
    "tiktok_bold",
    "word_punch",
    "clean",
}
ALLOWED_TEXT_ALIGN = {"left", "center", "right"}
ALLOWED_COLOR_GRADE_PRESETS = {
    "none",
    "cinematic",
    "hangat",
    "dingin",
    "cerah",
    "film",
    "mono",
}
_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _validate_hex_color(name: str, value: str) -> None:
    if not _HEX_COLOR_RE.match(value):
        raise CustomizationError(f"{name} harus warna hex 6 digit (mis. #FFFFFF)")


@dataclass
class SubtitleStyleConfig:
    enabled: bool = True
    template: str = "karaoke_pop"
    font: str = "Arial"
    size: int = 80
    align: str = "center"
    opacity: int = 100
    text_color: str = "#FFFFFF"
    highlight_color: str = "#FFFF00"
    outline_color: str = "#000000"
    shadow_color: str = "#000000"
    outline_width: float = 4.0
    shadow_width: float = 2.0
    background_box: bool = False
    pos_x: int = 50
    pos_y: int = 70

    def validate(self) -> None:
        if self.template not in ALLOWED_SUBTITLE_TEMPLATES:
            raise CustomizationError(
                f"subtitle.template harus salah satu dari {sorted(ALLOWED_SUBTITLE_TEMPLATES)}"
            )
        if self.align not in ALLOWED_TEXT_ALIGN:
            raise CustomizationError(
                f"subtitle.align harus salah satu dari {sorted(ALLOWED_TEXT_ALIGN)}"
            )
        if not 24 <= self.size <= 160:
            raise CustomizationError("subtitle.size harus antara 24 dan 160")
        if not 0 <= self.opacity <= 100:
            raise CustomizationError("subtitle.opacity harus antara 0 dan 100")
        if not 0 <= self.outline_width <= 10:
            raise CustomizationError("subtitle.outline_width harus antara 0 dan 10")
        if not 0 <= self.shadow_width <= 10:
            raise CustomizationError("subtitle.shadow_width harus antara 0 dan 10")
        if not 0 <= self.pos_x <= 100:
            raise CustomizationError("subtitle.pos_x harus antara 0 dan 100")
        if not 0 <= self.pos_y <= 100:
            raise CustomizationError("subtitle.pos_y harus antara 0 dan 100")
        _validate_hex_color("subtitle.text_color", self.text_color)
        _validate_hex_color("subtitle.highlight_color", self.highlight_color)
        _validate_hex_color("subtitle.outline_color", self.outline_color)
        _validate_hex_color("subtitle.shadow_color", self.shadow_color)


@dataclass
class OverlaySumberConfig:
    enabled: bool = False


@dataclass
class WatermarkConfig:
    enabled: bool = False


@dataclass
class OverlayGambarConfig:
    enabled: bool = False


@dataclass
class ColorGradeConfig:
    enabled: bool = False
    preset: str = "none"
    contrast: float = 1.0
    brightness: float = 0.0
    saturation: float = 1.0
    gamma: float = 1.0
    temperature: int = 0  # slider -100..100, 0=netral; petakan ke Kelvin di pipeline/color_grade.py
    vignette: float = 0.0

    def validate(self) -> None:
        if self.preset not in ALLOWED_COLOR_GRADE_PRESETS:
            raise CustomizationError(
                f"color_grade.preset harus salah satu dari {sorted(ALLOWED_COLOR_GRADE_PRESETS)}"
            )
        if not 0.5 <= self.contrast <= 2.0:
            raise CustomizationError("color_grade.contrast harus antara 0.5 dan 2.0")
        if not -0.5 <= self.brightness <= 0.5:
            raise CustomizationError("color_grade.brightness harus antara -0.5 dan 0.5")
        if not 0.0 <= self.saturation <= 2.0:
            raise CustomizationError("color_grade.saturation harus antara 0.0 dan 2.0")
        if not 0.5 <= self.gamma <= 2.0:
            raise CustomizationError("color_grade.gamma harus antara 0.5 dan 2.0")
        if not -100 <= self.temperature <= 100:
            raise CustomizationError("color_grade.temperature harus antara -100 dan 100")
        if not 0.0 <= self.vignette <= 1.0:
            raise CustomizationError("color_grade.vignette harus antara 0.0 dan 1.0")


_SECTION_TYPES = {
    "subtitle": SubtitleStyleConfig,
    "overlay_sumber": OverlaySumberConfig,
    "watermark": WatermarkConfig,
    "overlay_gambar": OverlayGambarConfig,
    "color_grade": ColorGradeConfig,
}


@dataclass
class CustomizationConfig:
    enabled: bool = False
    subtitle: SubtitleStyleConfig = field(default_factory=SubtitleStyleConfig)
    overlay_sumber: OverlaySumberConfig = field(default_factory=OverlaySumberConfig)
    watermark: WatermarkConfig = field(default_factory=WatermarkConfig)
    overlay_gambar: OverlayGambarConfig = field(default_factory=OverlayGambarConfig)
    color_grade: ColorGradeConfig = field(default_factory=ColorGradeConfig)

    def validate(self) -> None:
        """Validasi section yang sudah punya field detail; raise CustomizationError bila invalid."""
        self.subtitle.validate()
        self.color_grade.validate()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "CustomizationConfig":
        """Bangun config dari dict; unknown key & section rusak/absen pakai default."""
        kwargs: dict = {"enabled": bool(data.get("enabled", False))}
        for name, section_cls in _SECTION_TYPES.items():
            section_data = data.get(name)
            if not isinstance(section_data, dict):
                section_data = {}
            known = {f.name for f in section_cls.__dataclass_fields__.values()}
            filtered = {k: v for k, v in section_data.items() if k in known}
            kwargs[name] = section_cls(**filtered)
        return cls(**kwargs)


def default_customization_path() -> Path:
    """Path default file preset kustomisasi aktif; bisa dioverride via AUTOCLIP_CONFIG_DIR."""
    base = os.environ.get("AUTOCLIP_CONFIG_DIR", Path.home() / ".autoclip")
    return Path(base) / "customization.json"


def load_customization(path: Path | None = None) -> CustomizationConfig:
    """Load preset dari JSON; fallback ke default bila file tak ada/korup."""
    path = path or default_customization_path()
    if not path.exists():
        return CustomizationConfig()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return CustomizationConfig()
    return CustomizationConfig.from_dict(data)


def save_customization(cfg: CustomizationConfig, path: Path | None = None) -> None:
    """Simpan preset ke JSON; buat parent directory bila belum ada."""
    path = path or default_customization_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg.to_dict(), f, indent=2, ensure_ascii=False)
