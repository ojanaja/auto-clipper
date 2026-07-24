"""Konfigurasi kustomisasi visual (tab Kustomisasi) — model + persistence.

Disimpan terpisah dari AppConfig (config.py) supaya bisa diimpor/diekspor
sebagai file JSON preset mandiri, sesuai fitur Impor/Ekspor/Reset di tab
Kustomisasi. Tiap section (Subtitle/Overlay Sumber/Watermark/Overlay
Gambar/Color Grade) baru punya flag enabled di Fase 1a; field detail
(template, warna, posisi, slider) ditambah bertahap di Fase 1b-1e.
"""

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class SubtitleStyleConfig:
    enabled: bool = True


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
